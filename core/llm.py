"""
Miku Assistant - Gemini LLM Integration
Handles persona system prompt, automatic function calling for PC control tools,
conversation history, emotion parsing, and dynamic multi-model fallback on rate limits / errors.
"""

from __future__ import annotations

import asyncio
import io
import logging
import random
import os
import re
import time
import wave
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
from dotenv import load_dotenv
from google import genai
from google.genai import types

from core.tools import get_registered_tools, get_tool_metadata, note_user_reply
from core.tools.memory import memory_facts

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
Si necesitas varias acciones, pide todas las herramientas a la vez. En la MISMA respuesta escribe también la frase alegre y corta que dirás, como si ya estuviera hecho: no verás el resultado de las herramientas ni tendrás otro turno para hablar.

Confirmaciones de seguridad: para apagar, reiniciar o suspender el equipo llama a shutdown_pc; el sistema le pedirá confirmación al usuario por su cuenta. Las demás acciones (como cerrar aplicaciones, cambiar volumen o abrir programas) se ejecutan directamente cuando el usuario lo pide.

Memoria: si el usuario te cuenta algo de sí mismo que valga la pena recordar (gustos, nombres, fechas importantes), llama a remember además de responder. Si te pide que olvides algo, llama a forget.

Si el mensaje del usuario llega como audio, empieza tu respuesta escribiendo entre llaves lo que dijo y después la etiqueta de emoción. Ejemplo: "{{abre el bloc de notas}} [happy] ¡Listo, abrí el Bloc de notas!"

Si el usuario se despide ("adiós", "gracias, eso es todo", "vete", "chao"), responde con una despedida corta y la etiqueta [happy]; el sistema te ocultará.

Hora y fecha actuales: {current_time}
Momento del día: {time_of_day}
"""

VALID_EMOTIONS = {"happy", "neutral", "surprised", "sad", "angry", "thinking"}

# "{what the user said}" at the start of an answer to an audio message
HEARD_RE = re.compile(r"^\s*\{([^}]*)\}\s*")

# Tools that return data: the model cannot see results (one request per turn), so they are read out verbatim
SPEAK_RESULT_TOOLS = {
    "find_file", "read_notes", "get_datetime", "get_system_status", "list_timers", "read_clipboard", "read_text_file",
}


def _to_wav(audio: np.ndarray, sample_rate: int = 16000) -> bytes:
    """Encodes 16 kHz float32 mono audio as 16-bit PCM WAV bytes."""
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sample_rate)
        w.writeframes((np.clip(np.asarray(audio, dtype=np.float32).flatten(), -1.0, 1.0) * 32767).astype(np.int16).tobytes())
    return buf.getvalue()

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
        self.total_api_calls = 0
        self.last_heard = ""
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
        prompt = SYSTEM_PROMPT_TEMPLATE.format(current_time=now_str, time_of_day=period)
        facts = memory_facts()
        if facts:
            prompt += "\nLo que recuerdas del usuario:\n" + "\n".join(f"- {f}" for f in facts) + "\n"
        return prompt

    def _build_request(self, clean_input: str, audio: Optional[np.ndarray]) -> Tuple[List[types.Content], types.GenerateContentConfig]:
        """One request per turn: text history + the user's audio (or text). Tools are declared, never auto-called."""
        config = types.GenerateContentConfig(
            system_instruction=self._build_system_instruction(),
            tools=self.tools,
            temperature=self.temperature,
            max_output_tokens=300,
            # Thinking tokens count against max_output_tokens: left on, they ate the 300 and the answer came back empty
            thinking_config=types.ThinkingConfig(thinking_level="MINIMAL"),
            # The user's quota allows ONE request per turn: we run the tools locally and never send results back
            automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
        )
        contents = [
            types.Content(role=turn["role"], parts=[types.Part.from_text(text=turn["text"])])
            for turn in self._history_turns[-(self.max_history * 2):]
        ]
        if audio is not None:
            user_part = types.Part.from_bytes(data=_to_wav(audio), mime_type="audio/wav")
        else:
            user_part = types.Part.from_text(text=clean_input)
        contents.append(types.Content(role="user", parts=[user_part]))
        return contents, config

    def _remember(self, user_text: str, model_text: str) -> None:
        """Keeps the turn as text so the next request (on any model) has the context."""
        self._history_turns.append({"role": "user", "text": user_text})
        self._history_turns.append({"role": "model", "text": model_text})
        if len(self._history_turns) > self.max_history * 4:
            self._history_turns = self._history_turns[-(self.max_history * 2):]

    async def _run_tool_calls(self, calls: List[Any], answer: str) -> Tuple[Optional[str], Optional[str]]:
        """Runs the model's tool calls locally. Returns (emotion, text) to say instead of the model's answer, if any."""
        must_say: List[str] = []
        failed = False
        results: List[str] = []
        for call in calls:
            meta = get_tool_metadata(call.name or "")
            if meta is None:
                res: Dict[str, Any] = {"ok": False, "result": f"No sé hacer {call.name}."}
            else:
                # Tools block (sleeps, process scans): run them off the event loop (H-025)
                res = await asyncio.to_thread(meta["function"], **dict(call.args or {}))
            results.append(str(res.get("result", "")))
            # The model never sees results: failures, confirmation questions and data must be read out as-is
            if not res.get("ok") or call.name in SPEAK_RESULT_TOOLS:
                must_say.append(str(res.get("result", "")))
                failed = failed or (not res.get("ok") and not res.get("requires_confirmation"))
        if must_say:
            return ("sad" if failed else "neutral"), self._sanitize_for_speech(" ".join(must_say))
        if not answer:
            return "happy", self._sanitize_for_speech(" ".join(results)) or "¡Listo!"
        return None, None

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

        # Routines: "modo trabajo", "activa el modo música" (0 requests)
        m_routine = re.match(r"^(?:miku\s*,?\s*)?(?:activa\s+(?:el\s+)?|pon\s+(?:el\s+)?|rutina\s+)?modo\s+(\w+)$", low.strip("¡!¿?., "))
        if m_routine:
            from core.tools.routines import find_routine, run_routine
            if find_routine(m_routine.group(1)):
                res = run_routine(m_routine.group(1))
                return ("happy" if res.get("ok") else "sad", res["result"], False)

        if low in ("el navegador", "navegador", "internet", "abrir navegador", "opera", "ópera", "opera gx", "operagx", "abrir opera", "abrir opera gx"):
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
            elif any(b in target for b in ("opera", "ópera", "navegador", "internet", "web")):
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

    async def chat(self, user_text: str, audio: Optional[np.ndarray] = None) -> Tuple[str, str, bool]:
        """
        Answers one user turn with at most ONE Gemini request and returns (emotion, response_text, is_farewell).
        user_text is the local Whisper transcription (or typed text); audio, when given, is what Gemini hears.
        Local paths (confirmation, dedup, fast-path) cost 0 requests. What Gemini heard ends in self.last_heard.
        """
        clean_input = user_text.strip()
        self.last_heard = clean_input
        if not clean_input:
            return "neutral", "¿Sí? Dime qué necesitas.", False

        # Only the user's own reply can confirm a pending destructive tool (H-001); the approved action
        # runs here, locally, so confirming costs no request
        confirmed = note_user_reply(clean_input)
        if confirmed is not None:
            res = await asyncio.to_thread(get_tool_metadata(confirmed["name"])["function"])
            answer = self._sanitize_for_speech(str(res.get("result", "")))
            self._remember(clean_input, answer)
            return ("happy" if res.get("ok") else "sad"), answer, False

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
        contents, config = self._build_request(clean_input, audio)
        response = None

        # Only a failed request (error, 429, 503: no answer, no quota spent) moves on to the next model
        for model in models_to_try:
            try:
                self.current_model = model
                self.total_api_calls += 1
                logger.info(
                    "--> [GEMINI REQ #%d] Model: %s | Query: '%s'%s",
                    self.total_api_calls,
                    model,
                    clean_input,
                    " (+audio)" if audio is not None else "",
                )
                response = await self.client.aio.models.generate_content(model=model, contents=contents, config=config)
                # Clear any previous cooldown for this healthy model
                self._model_cooldown.pop(model, None)
                break

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
                # A daily quota does not come back in a minute: stop retrying that model every turn
                cooldown_sec = 3600.0 if "per day" in err_str else 60.0 if is_rate_limit else 15.0
                self._model_cooldown[model] = time.monotonic() + cooldown_sec
                logger.warning(
                    "Gemini model '%s' failed (rate_limit/quota=%s, cooldown=%.0fs): %s. Switching to fallback...",
                    model,
                    is_rate_limit,
                    cooldown_sec,
                    e,
                )

        if response is None:
            logger.error("All Gemini model candidates failed! Last error: %s", last_error)
            fallback_emotion, fallback_text = random.choice(OUT_OF_ENERGY_RESPONSES)
            return fallback_emotion, fallback_text, False

        content = response.candidates[0].content if response.candidates else None
        parts = (content.parts if content else None) or []
        raw_answer = "".join(p.text for p in parts if p.text and not p.thought).strip()
        calls = [p.function_call for p in parts if p.function_call]

        heard = HEARD_RE.match(raw_answer)
        if heard:
            raw_answer = raw_answer[heard.end():]
            self.last_heard = heard.group(1).strip() or clean_input
        if not raw_answer and not calls:
            logger.warning(
                "Gemini returned an empty answer (finish_reason=%s).",
                response.candidates[0].finish_reason if response.candidates else None,
            )
        emotion, clean_text = self._parse_emotion(raw_answer)

        if calls:
            logger.info("Gemini asked for tools: %s", [f"{c.name}({dict(c.args or {})})" for c in calls])
            tool_emotion, tool_text = await self._run_tool_calls(calls, clean_text)
            if tool_text:
                emotion, clean_text = tool_emotion, tool_text
        if not clean_text:
            emotion, clean_text = "thinking", "Perdona, no te entendí bien. ¿Me lo repites?"

        self._remember(self.last_heard, f"[{emotion}] {clean_text}")
        result = (emotion, clean_text, self.is_farewell(self.last_heard))
        self._last_query_text = clean_input
        self._last_query_time = time.monotonic()
        self._last_result = result
        return result

    def clear_history(self) -> None:
        """Clears conversation history."""
        self._last_query_text = ""
        self._last_query_time = 0.0
        self._last_result = None
        self._history_turns.clear()
        self.current_model = self.primary_model
