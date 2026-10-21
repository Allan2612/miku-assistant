"""
Miku Assistant - Gemini LLM Integration
Handles persona system prompt, automatic function calling for PC control tools,
conversation history, emotion parsing, and dynamic multi-model fallback on rate limits / errors.
"""

from __future__ import annotations

import asyncio
import logging
import random
import os
import re
import time
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from dotenv import load_dotenv
from google import genai
from google.genai import types

from core.tools import get_registered_tools, note_user_reply

load_dotenv()

logger = logging.getLogger("miku.llm")

SYSTEM_PROMPT_TEMPLATE = """Eres Miku, una asistente virtual que vive en el escritorio de Windows del usuario. Eres alegre, enérgica, cariñosa y un poco juguetona, pero muy eficiente cuando te piden algo.

Hablas en español natural y cercano. De vez en cuando usas una interjección japonesa corta ("¡yatta!", "ehh~", "sugoi"), sin abusar: como mucho una cada varias respuestas.

Tus respuestas se convierten en voz, así que:
- Sé MUY breve: 1 o 2 frases, máximo unas 30 palabras, salvo que el usuario pida detalle.
- No uses markdown, listas, emojis, URLs ni símbolos que no se puedan leer en voz alta.
- Escribe los números como se dirían si eso ayuda a la lectura.

Empieza SIEMPRE tu respuesta con una etiqueta de emoción entre corchetes, una de: [happy] [neutral] [surprised] [sad] [angry] [thinking]. Ejemplo: "[happy] ¡Listo, abrí el Bloc de notas!"

REGLA CRÍTICA DE CONTROL DEL PC:
Tienes herramientas disponibles para controlar el ordenador en tiempo real (abrir aplicaciones, cerrar aplicaciones, ajustar o cambiar volumen, pausar/reanudar música, buscar en Google/YouTube, ver estado del sistema, fecha/hora, temporizadores, notas, etc.).
Cuando el usuario pida realizar cualquier acción en el PC, ES OBLIGATORIO LLAMAR A LA HERRAMIENTA CORRESPONDIENTE. NUNCA respondas que hiciste la acción sin haber ejecutado la herramienta, porque si no la ejecutas, la acción no ocurre físicamente en el ordenador.
Tras la llamada a la herramienta, confirma el resultado con una frase alegre y corta.

Confirmaciones de seguridad: apagar, reiniciar o suspender el equipo (shutdown_pc) necesita que el usuario confirme. La primera llamada no ejecuta nada y devuelve una pregunta: házsela al usuario tal cual. Si en su siguiente mensaje responde que sí, vuelve a llamar a shutdown_pc con los mismos argumentos. Las demás acciones (como cerrar aplicaciones, cambiar volumen o abrir programas) se ejecutan directamente cuando el usuario lo pide.

Si el usuario se despide ("adiós", "gracias, eso es todo", "vete", "chao"), responde con una despedida corta y la etiqueta [happy]; el sistema te ocultará.

Hora y fecha actuales: {current_time}
Momento del día: {time_of_day}
"""

VALID_EMOTIONS = {"happy", "neutral", "surprised", "sad", "angry", "thinking"}

FAREWELL_KEYWORDS = [
    "adios", "adiós", "chao", "hasta luego", "nos vemos",
    "gracias, eso es todo", "eso es todo", "vete", "duérmete", "duermete",
    "ocúltate", "ocultate", "desaparece", "bye", "goodbye"
]

OUT_OF_ENERGY_RESPONSES: List[Tuple[str, str]] = [
    ("sad", "¡Ehh~ me quedé sin batería digital! Dame unos minutitos para recargar energía y vuelvo contigo, ¿sí?"),
    ("thinking", "¡Uff! Mi procesador vocal se sobrecalentó de tanto cantar. Necesito descansar mis circuitos un ratito."),
    ("sad", "Ay, maestro... se me agotó la energía mágica por ahora. ¿Podemos esperar un momentito antes de seguir?"),
    ("neutral", "¡Batería en cero coma uno por ciento! Necesito comerme un puerro virtual y recargarme unos minutos."),
]


class MikuBrain:
    """Manages Gemini conversation session with persona, automatic function calling, and multi-model fallback."""

    def __init__(
        self,
        model_name: str = "gemini-3.5-flash-lite",
        models_fallback: Optional[List[str]] = None,
        max_history: int = 10,
        temperature: float = 0.8,
    ) -> None:
        self.primary_model = model_name
        self.models_fallback = models_fallback or [
            "gemini-3.1-flash-lite",
            "gemini-3.5-flash",
            "gemini-3.6-flash",
            "gemini-3.7-flash",
        ]
        # Full prioritized candidate pool
        self.all_models: List[str] = [self.primary_model] + [
            m for m in self.models_fallback if m != self.primary_model
        ]
        self.current_model = self.primary_model
        self.max_history = max_history
        self.temperature = temperature

        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            logger.warning("GEMINI_API_KEY is not set in environment!")

        # 15 s per HTTP request: a hung connection must fail so the model fallback can kick in (H-026)
        self.client = genai.Client(api_key=api_key, http_options=types.HttpOptions(timeout=15_000))
        self.tools = get_registered_tools()
        self._chat_session = None
        self._turns_count = 0
        self.total_api_calls = 0
        self._last_query_text = ""
        self._last_query_time = 0.0
        self._last_result: Optional[Tuple[str, str, bool]] = None

        # Model cooldown tracker: model_name -> expiration timestamp
        self._model_cooldown: Dict[str, float] = {}
        # In-memory history turns for model transfer: [{"role": "user"|"model", "text": str}]
        self._history_turns: List[Dict[str, str]] = []

        logger.info(
            "MikuBrain initialized with %d PC tools. Primary: %s | Fallbacks: %s",
            len(self.tools),
            self.primary_model,
            self.models_fallback,
        )

    def is_farewell(self, user_text: str) -> bool:
        # Short goodbyes only, whole words: "vete a la configuración y..." is not a farewell (H-027)
        norm = user_text.lower().strip()
        if len(norm.split()) > 6:
            return False
        return any(re.search(r"\b" + re.escape(kw) + r"\b", norm) for kw in FAREWELL_KEYWORDS)

    def _build_system_instruction(self) -> str:
        now = datetime.now()
        now_str = now.strftime("%A, %d de %B de %Y, %H:%M:%S")
        hour = now.hour
        if 5 <= hour < 12:
            period = "mañana (saluda con '¡Buenos días!' si el usuario te saluda)"
        elif 12 <= hour < 20:
            period = "tarde (saluda con '¡Buenas tardes!' si el usuario te saluda)"
        else:
            period = "noche (saluda con '¡Buenas noches!' si el usuario te saluda)"
        return SYSTEM_PROMPT_TEMPLATE.format(current_time=now_str, time_of_day=period)

    def _create_chat_session(self, model: str) -> Any:
        """Instantiates a fresh AsyncChat session with function calling limited strictly to max 2 remote calls."""
        system_instruction = self._build_system_instruction()
        afc_config = types.AutomaticFunctionCallingConfig(maximum_remote_calls=2)
        config = types.GenerateContentConfig(
            system_instruction=system_instruction,
            tools=self.tools,
            temperature=self.temperature,
            max_output_tokens=300,
            automatic_function_calling=afc_config,
        )

        history_contents = []
        for turn in self._history_turns[-(self.max_history * 2):]:
            history_contents.append(
                types.Content(
                    role=turn["role"],
                    parts=[types.Part.from_text(text=turn["text"])],
                )
            )

        chat = self.client.aio.chats.create(
            model=model,
            config=config,
            history=history_contents if history_contents else None,
        )
        logger.info("Gemini AsyncChat session initialized for model '%s' (history turns: %d).", model, len(history_contents))
        return chat

    @staticmethod
    def _sanitize_for_speech(text: str) -> str:
        """
        Strips markdown symbols (*, _, `, ~, #), URLs, and extra spaces
        so subtitles and upcoming TTS audio read cleanly and naturally.
        """
        text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)
        text = re.sub(r"https?://\S+|www\.\S+", "", text)
        text = re.sub(r"[*_`~#]", "", text)
        text = re.sub(r"\s+", " ", text).strip()
        return text

    def _parse_emotion(self, raw_text: str) -> Tuple[str, str]:
        """
        Extracts [emotion] tag from beginning of response.
        Returns (emotion, clean_text).
        """
        match = re.match(r"^\s*\[([a-zA-Z]+)\]\s*(.*)", raw_text, re.DOTALL)
        if match:
            emotion = match.group(1).lower()
            text = match.group(2).strip()
            if emotion not in VALID_EMOTIONS:
                emotion = "happy"
            return emotion, self._sanitize_for_speech(text)
        return "happy", self._sanitize_for_speech(raw_text)

    def _try_fast_path_tool(self, text: str) -> Optional[Tuple[str, str, bool]]:
        """
        Instant local fast-path execution for unambiguous direct PC commands.
        Executes immediately with 0ms cloud latency and 100% resilience against 429 quota exhaustion.
        """
        low = text.lower().strip()

        # 0. Greetings with time-of-day awareness (0ms cloud latency, 0 API quota used)
        if low in (
            "hola", "hola miku", "hey miku", "buenos dias", "buenos días",
            "buenas tardes", "buenas noches", "saludos", "hola que tal", "hola qué tal"
        ):
            hour = datetime.now().hour
            if 5 <= hour < 12:
                greet = "¡Buenos días! ¿Qué necesitas hoy?"
            elif 12 <= hour < 20:
                greet = "¡Buenas tardes! ¿En qué puedo ayudarte?"
            else:
                greet = "¡Buenas noches! ¿Qué necesitas antes de descansar?"
            return ("happy", greet, False)

        # 1. Direct App / Website shortcuts without explicit 'abre'
        if low in ("bloc de notas", "el bloc de notas", "notas", "mis notas", "abrir notas"):
            from core.tools.notes import open_notes
            open_notes()
            return ("happy", "¡Yatta! Ya te abrí el Bloc de notas.", False)

        if low in ("el navegador", "navegador", "internet", "abrir navegador", "opera", "opera gx", "operagx", "abrir opera", "abrir opera gx"):
            from core.tools.apps import open_app
            open_app("opera gx")
            return ("happy", "¡Listo! Ya abrí Opera GX para ti.", False)

        if low in ("youtube", "abrir youtube"):
            from core.tools.web import open_url
            open_url("https://www.youtube.com")
            return ("happy", "¡Listo! Ya abrí YouTube en tu navegador.", False)

        # 2. Open app / website / notes with verbs ("pon" is left out: "pon la música" means play, H-024)
        m_open = re.match(r"^(?:miku\s*,?\s*)?(?:abre|abrir|inicia|iniciar|lanza|lanzar|ejecuta|ejecutar)\s+(?:el\s+|la\s+|los\s+|las\s+|un\s+|una\s+)?(.+)$", low)
        if m_open:
            target = m_open.group(1).strip()
            if "youtube" in target:
                from core.tools.web import open_url
                open_url("https://www.youtube.com")
                return ("happy", "¡Listo! Ya abrí YouTube en tu navegador.", False)
            elif any(b in target for b in ("opera", "navegador", "internet", "web")):
                from core.tools.apps import open_app
                open_app("opera gx")
                return ("happy", "¡Listo! Ya abrí Opera GX para ti.", False)
            elif "nota" in target:
                from core.tools.notes import open_notes
                open_notes()
                return ("happy", "¡Yatta! Ya te abrí el Bloc de notas.", False)
            else:
                from core.tools.apps import open_app
                res = open_app(target)
                if res.get("ok"):
                    return ("happy", f"¡Listo! Ya abrí {target}.", False)

        # 3. Close app: only known app aliases; anything else ("apaga el PC", "cierra la ventana") goes to Gemini (H-023)
        m_close = re.match(r"^(?:miku\s*,?\s*)?(?:cierra|cerrar)\s+(?:el\s+|la\s+|los\s+|las\s+)?(.+)$", low)
        if m_close:
            from core.tools.apps import close_app, DEFAULT_APP_ALIASES, _clean_query
            target = _clean_query(m_close.group(1))
            if target in DEFAULT_APP_ALIASES:
                res = close_app(target)
                if res.get("ok"):
                    return ("happy", f"Listo, cerré {target}.", False)
                return ("sad", res.get("result", f"No pude cerrar {target}."), False)

        # 4. Web Search / YouTube Search
        m_search_yt = re.match(r"^(?:miku\s*,?\s*)?(?:busca|buscar)\s+en\s+youtube\s+(.+)$", low)
        if m_search_yt:
            q = m_search_yt.group(1).strip()
            from core.tools.web import youtube_search
            youtube_search(q)
            return ("happy", f"¡Buscando '{q}' en YouTube!", False)

        m_search_goog = re.match(r"^(?:miku\s*,?\s*)?(?:busca|buscar)\s+(?:en\s+google\s+)?(.+)$", low)
        # "busca el archivo X" is a file search for Gemini (find_file), not a Google search
        if (m_search_goog and "youtube" not in low and not low.startswith("busca en")
                and not re.match(r"^(?:el |la |mi |mis |un |una )?(?:archivo|documento|carpeta)", m_search_goog.group(1))):
            q = m_search_goog.group(1).strip()
            from core.tools.web import web_search
            web_search(q)
            return ("happy", f"¡Listo! Ya busqué '{q}' en Google.", False)

        # 5. Volume / Media: whole words only ("playlist" or "display" must not press play, H-024)
        def has_word(*words: str) -> bool:
            return any(re.search(rf"\b{re.escape(w)}\b", low) for w in words)

        def confirm(res: Dict[str, Any], ok_text: str) -> Tuple[str, str, bool]:
            if res.get("ok"):
                return ("happy", ok_text, False)
            return ("sad", res.get("result", "No pude hacerlo."), False)

        if has_word("sube el volumen", "subir volumen", "más volumen", "aumenta el volumen"):
            from core.tools.media import change_volume
            return confirm(change_volume(15), "¡Subí el volumen!")
        if has_word("baja el volumen", "bajar volumen", "menos volumen", "disminuye el volumen"):
            from core.tools.media import change_volume
            return confirm(change_volume(-15), "¡Listo, bajé el volumen!")
        # "quita el silencio" asks for the opposite: leave unmuting to Gemini
        if (has_word("silencio", "silencia", "mutea", "mutear", "mute")
                and not has_word("quita", "quitar", "desactiva", "desactivar", "desmutea", "unmute")):
            from core.tools.media import mute
            return confirm(mute(True), "¡Silenciado!")
        if has_word("pausa la música", "pausar música", "pausa la cancion", "pausa la canción", "pausa"):
            from core.tools.media import media_control
            return confirm(media_control("pause"), "Música pausada.")
        if has_word("reanuda la música", "reproduce la música", "reproducir música", "pon la música", "play"):
            from core.tools.media import media_control
            return confirm(media_control("play"), "¡Música reproduciéndose!")

        # 6. Date & Time (questions only: "a la hora de comer" is not asking the time)
        if any(w in low for w in ["qué hora", "que hora", "dime la hora"]):
            now_dt = datetime.now()
            return ("neutral", f"Son las {now_dt.strftime('%H:%M')}.", False)

        # 6. Notes
        m_note = re.match(r"^(?:miku\s*,?\s*)?(?:toma|guarda|anota)\s+(?:una\s+)?nota(?:\s+que\s+diga)?[:\s]+(.+)$", low)
        if m_note:
            text_note = m_note.group(1).strip()
            from core.tools.notes import take_note
            take_note(text_note)
            return ("happy", "¡Apuntado! Ya guardé tu nota.", False)

        if any(w in low for w in ["lee mis notas", "leer notas", "cuáles son mis notas", "que notas tengo", "qué notas tengo"]):
            from core.tools.notes import read_notes
            notes_res = read_notes()
            return ("neutral", notes_res.get("result", "No tienes notas."), False)

        # 7. Desktop / System
        if any(w in low for w in ["muestra el escritorio", "mostrar escritorio", "minimiza todo", "minimizar todo"]):
            from core.tools.apps import show_desktop
            show_desktop()
            return ("happy", "¡Listo, te mostré el escritorio!", False)

        return None

    async def chat(self, user_text: str) -> Tuple[str, str, bool]:
        """
        Sends message to Gemini with automatic function calling and returns:
        (emotion, response_text, is_farewell)
        Enforces deduplication, rate limit resilience, and automatic fallback across models.
        """
        clean_input = user_text.strip()
        if not clean_input:
            return "neutral", "¿Sí? Dime qué necesitas.", False

        # Only the user's own reply can confirm a pending destructive tool (H-001)
        note_user_reply(clean_input)

        # In-memory deduplication: if exact same query arrives within 2.0s, reuse response with 0 extra API calls
        now = time.monotonic()
        if clean_input == self._last_query_text and (now - self._last_query_time) < 2.0 and self._last_result:
            logger.warning("Duplicate Gemini request within 2.0s: '%s'. Reusing cached result (0 API calls).", clean_input)
            return self._last_result

        # Instant local fast-path for direct PC commands (0ms cloud latency, 100% immune to 429)
        # Tools block (sleeps, process scans): run them off the event loop (H-025)
        fast_res = await asyncio.to_thread(self._try_fast_path_tool, clean_input)
        if fast_res is not None:
            logger.info("Executed local fast-path command: '%s' -> %s", clean_input, fast_res[1])
            self._last_query_text = clean_input
            self._last_query_time = now
            self._last_result = fast_res
            return fast_res

        farewell = self.is_farewell(clean_input)

        # Build prioritized list of models to try
        models_to_try: List[str] = []
        for m in self.all_models:
            cooldown_until = self._model_cooldown.get(m, 0.0)
            if now >= cooldown_until:
                models_to_try.append(m)

        # If all models happen to be on cooldown, try all in original order anyway
        if not models_to_try:
            logger.warning("All models in cooldown. Attempting all candidates anyway.")
            models_to_try = list(self.all_models)

        # Prefer the currently active model if healthy, otherwise prioritize primary
        if self.current_model in models_to_try:
            models_to_try.remove(self.current_model)
            models_to_try.insert(0, self.current_model)

        last_error = None

        for model in models_to_try:
            try:
                # Initialize or swap chat session if needed
                if self._chat_session is None or self.current_model != model or self._turns_count >= self.max_history * 2:
                    self.current_model = model
                    self._chat_session = self._create_chat_session(model)
                    self._turns_count = 0

                self._turns_count += 1
                self.total_api_calls += 1
                logger.info(
                    "--> [GEMINI REQ #%d] (Turn #%d) Model: %s | Query: '%s'",
                    self.total_api_calls,
                    self._turns_count,
                    model,
                    clean_input,
                )

                response = await self._chat_session.send_message(clean_input)
                raw_answer = (response.text or "").strip()
                if not raw_answer:
                    raw_answer = "[happy] ¡Listo! ¿En qué más te puedo ayudar?"

                emotion, clean_text = self._parse_emotion(raw_answer)
                if not clean_text:
                    clean_text = "¡Listo!"

                # Track history for seamless cross-model failovers
                self._history_turns.append({"role": "user", "text": clean_input})
                self._history_turns.append({"role": "model", "text": raw_answer})
                if len(self._history_turns) > self.max_history * 4:
                    self._history_turns = self._history_turns[-(self.max_history * 2):]

                result = (emotion, clean_text, farewell)
                self._last_query_text = clean_input
                self._last_query_time = time.monotonic()
                self._last_result = result

                # Clear any previous cooldown for this healthy model
                self._model_cooldown.pop(model, None)
                return result

            except Exception as e:
                last_error = e
                err_str = str(e).lower()
                is_rate_limit = any(term in err_str for term in [
                    "429", "resourceexhausted", "quota", "rate limit", "503", "unavailable", "high demand", "overloaded"
                ])
                # A bad API key fails on every model: say so instead of trying them all (H-027)
                if any(term in err_str for term in ["api key", "api_key", "permission_denied", "unauthenticated", "401", "403"]):
                    logger.error("Gemini authentication failed: %s", e)
                    return ("sad", "No puedo conectarme con Gemini: revisa la API key en el archivo .env.", False)
                cooldown_sec = 60.0 if is_rate_limit else 15.0
                self._model_cooldown[model] = time.monotonic() + cooldown_sec
                logger.warning(
                    "Gemini model '%s' failed (rate_limit/quota=%s, cooldown=%.0fs): %s. Switching to fallback...",
                    model,
                    is_rate_limit,
                    cooldown_sec,
                    e,
                )
                self._chat_session = None

        logger.error("All Gemini model candidates failed! Last error: %s", last_error)
        fallback_emotion, fallback_text = random.choice(OUT_OF_ENERGY_RESPONSES)
        return (
            fallback_emotion,
            fallback_text,
            False,
        )

    def clear_history(self) -> None:
        """Clears conversation history and resets chat session."""
        self._chat_session = None
        self._turns_count = 0
        self._last_query_text = ""
        self._last_query_time = 0.0
        self._last_result = None
        self._history_turns.clear()
        self.current_model = self.primary_model
