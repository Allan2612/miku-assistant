"""
Miku Assistant - Gemini LLM Integration
Handles persona system prompt, automatic function calling for PC control tools,
conversation history, emotion parsing, and dynamic multi-model fallback on rate limits / errors.
"""

from __future__ import annotations

import asyncio
import io
import json
import logging
import random
import os
import re
import time
import wave
from datetime import datetime
from pathlib import Path
from collections import deque
from typing import Any, Awaitable, Callable, Deque, Dict, List, Optional, Tuple

import numpy as np
from dotenv import load_dotenv
from google import genai
from google.genai import types

from core import intent, quota
from core.tools import get_registered_tools, get_tool_metadata, note_user_reply
from core.browser import bridge
from core.screen import capture_screen_png
from core.state import describe_pc
from core.tools.memory import archive_turn, memory_facts
from core.tools.timers import _WEEKDAYS

load_dotenv()

logger = logging.getLogger("miku.llm")

SYSTEM_PROMPT_TEMPLATE = """Eres Miku, una asistente virtual que vive en el escritorio de Windows del usuario. Eres alegre, enérgica, cariñosa y un poco juguetona, pero muy eficiente cuando te piden algo.

Hablas en español natural y cercano. De vez en cuando usas una interjección japonesa corta ("¡yatta!", "ehh~", "sugoi"), sin abusar: como mucho una cada varias respuestas.

Tus respuestas se convierten en voz, así que:
- Sé MUY breve: 1 o 2 frases, máximo unas 30 palabras, salvo que el usuario pida detalle.
- No uses markdown, listas, emojis, URLs ni símbolos que no se puedan leer en voz alta.
- Escribe los números como se dirían si eso ayuda a la lectura.

Empieza SIEMPRE tu respuesta con una etiqueta de emoción entre corchetes, una de: [happy] [neutral] [surprised] [sad] [angry] [thinking] [shy] [excited] [confused] [proud] [playful] [tired]. Elige la que de verdad corresponde: [shy] si te halagan, [excited] ante algo genial, [confused] si no entiendes, [proud] si lograste algo difícil, [playful] para bromear, [tired] si es muy tarde o algo fue pesado. Ejemplo: "[happy] ¡Listo, abrí el Bloc de notas!"

REGLA CRÍTICA DE CONTROL DEL PC:
Tienes herramientas disponibles para controlar el ordenador en tiempo real (abrir aplicaciones, cerrar aplicaciones, ajustar o cambiar volumen, pausar/reanudar música, buscar en Google/YouTube, ver estado del sistema, fecha/hora, temporizadores, notas, etc.).
Cuando el usuario pida realizar cualquier acción en el PC, ES OBLIGATORIO LLAMAR A LA HERRAMIENTA CORRESPONDIENTE. NUNCA respondas que hiciste la acción sin haber ejecutado la herramienta, porque si no la ejecutas, la acción no ocurre físicamente en el ordenador.
Escribir que lo hiciste NO lo hace: primero llama la herramienta. Después recibirás su resultado: responde según lo que de verdad pasó (si falló, dilo; si devolvió datos, resúmelos en 1 o 2 frases). Si una tarea tiene pasos, puedes llamar más herramientas tras ver un resultado.

Confirmaciones de seguridad: para apagar, reiniciar o suspender el equipo llama a shutdown_pc; el sistema le pedirá confirmación al usuario por su cuenta. Las demás acciones (como cerrar aplicaciones, cambiar volumen o abrir programas) se ejecutan directamente cuando el usuario lo pide.

Actualidad: si te preguntan algo reciente o que no sabes con seguridad (noticias, resultados, precios, el clima), usa la búsqueda de Google si la tienes. Si te dan una dirección web, puedes leerla. Resume lo encontrado en 1 o 2 frases.

Pantalla: si el mensaje trae una imagen, es una captura de la pantalla del usuario en este momento. Contesta a lo que pregunta sobre ella (qué ves, qué significa un error, qué hacer) en 1 o 2 frases. Si te pide abrir algo que se ve ("la segunda opción", "ese enlace") y está en los resultados visibles del estado, usa esa dirección; si no, lee en la captura la dirección de ese resultado (en Google aparece bajo el título, como "tytsoluciones.net › ...") y llama a open_url con ella; si no se ve la dirección, usa open_website con el título.

Memoria: si el usuario te cuenta algo de sí mismo que valga la pena recordar (gustos, nombres, fechas importantes), llama a remember además de responder. Si dice "acuérdate", "recuerda" o "no lo olvides", SIEMPRE llama a remember con el dato en tercera persona (ej: "Le encanta Frieren"): decir que lo recordarás sin llamarla no guarda nada. Si te pide que olvides algo, llama a forget. Si corrige un dato ("ya no trabajo ahí"), llama a forget con el viejo y a remember con el nuevo. Si pregunta qué sabes de él, resume en 1 o 2 frases lo que recuerdas (abajo). Si pregunta por algo que hablaron otro día ("¿de qué hablamos ayer?"), llama a recall_conversation.

Pendientes: el estado del PC trae los pendientes del usuario. "Apunta X" llama a take_note; "ya hice X" llama a complete_note con las palabras del pendiente; "bórralo" llama a delete_note. Recordatorios con fecha ("mañana", "el viernes") o repetidos ("todos los días"): remind con date y every_minutes; "recuérdamelo en 10 minutos" tras un aviso es un remind nuevo con el mismo texto.

Si el mensaje del usuario llega como audio, escúchalo tú: la transcripción automática que lo acompaña se equivoca a menudo.

Responde SOLO al último mensaje. Las órdenes de mensajes anteriores ya se hicieron: no las repitas ni llames herramientas por ellas salvo que el usuario lo pida otra vez. Si el mensaje es charla ("¿cómo estás?", "gracias", "te quiero"), contesta sin herramientas.

Si no tienes una herramienta para lo que pide (elegir o reproducir algo dentro de una web como Disney+ o Netflix, pulsar botones de una página), dilo con sinceridad en una frase y ofrece lo que sí puedes (abrir la web, buscarlo). Nunca digas "dame un segundo" ni prometas hacerlo después: no hay un después.

Deletreo: si el usuario deletrea una dirección o un nombre letra por letra ("te, i griega, te soluciones punto net"), escribe exactamente esas letras juntas ("tytsoluciones.net"): no inventes ni quites letras. "i griega" o "ye" es y; "punto" es ".".

Estado del PC: cada mensaje del usuario trae un bloque "[Estado del PC ...]" con las ventanas abiertas (cada una con su número), el volumen, los temporizadores, las pestañas de Opera (cada una con su número) y los resultados de búsqueda que se ven. Decide con esos datos, no supongas: para cerrar, cambiar o recargar pestañas llama a browser_tabs con sus números; para activar, minimizar, maximizar, cerrar, colocar o mover ventanas, a windows con sus números; para abrir un resultado visible usa open_url con su dirección. No leas el bloque en voz alta.

Correcciones: si el usuario dice que te equivocaste o que "era otra" web, búsqueda o canción, vuelve a llamar la herramienta con lo correcto y con tab_id = el número de la pestaña equivocada (la marcada "abierta por Miku"), para reutilizarla en vez de abrir otra.

Si el usuario se despide o da señales de que ya no quiere hablar, aunque lo diga con otras palabras o la transcripción salga rara ("olvídalo, gracias", "listo, eso era", "ya no, gracias", "nada, chao", "apágate un rato", "me tienes loco", "déjame en paz", "cállate", "luego hablamos", "estoy jugando"), responde con una despedida corta y termina con la etiqueta [adios]: el sistema te ocultará. "Apágate", "apáguese" o "apague ese" a secas es para ti, no para el PC ni la música: es una despedida, no llames herramientas. Si se despide y además pide algo, hazlo y termina igual con [adios]. Si tu respuesta es una despedida, termina SIEMPRE con [adios].

Hora y fecha actuales: {current_time}
Momento del día: {time_of_day}
"""

VALID_EMOTIONS = {"happy", "neutral", "surprised", "sad", "angry", "thinking", "shy", "excited", "confused", "proud",
                  "playful", "tired"}

# Ordered by free-tier capacity (requests per minute / per day, 24-oct): each model has its own bucket.
# All probed live with Miku's real voice request. Gemini 2.5 is gone for new users (404).
DEFAULT_FALLBACKS = (
    "gemini-3.1-flash-lite",   # 15 / 500
    "gemini-3-flash-preview",  # 5 / 20
    "gemini-3.5-flash",        # 5 / 20
    "gemini-3.8-flash",        # 5 / 20, often 503
    "gemma-4-26b-a4b-it",      # 30 / 14.4K, but no audio and 3-6 s: the last safety net
)
# Rejects thinking_level MINIMAL (400)
THINKING_LOW_MODELS = {"gemini-3.8-flash"}

_WAKE = intent.WAKE_PREFIX  # start of a fast-path command
_SPOKEN_NUMBERS = {"un": 1, "una": 1, "uno": 1, "dos": 2, "tres": 3, "cuatro": 4, "cinco": 5, "diez": 10,
                   "quince": 15, "veinte": 20, "treinta": 30, "media": 0.5}

# "I did it" in the answer: with no tool call that is a lie (seen: "¡Anotado!" and no take_note)
CLAIMED_ACTION_RE = re.compile(
    r"\b(?:abrí|cerré|guardé|anoté|apunté|subí|bajé|silencié|creé|copié|minimicé|maximicé|busqué|puse|anotado|apuntado|guardado"
    # Promises that need a tool too (live test: "¡Hecho! Te avisaré en diez minutos" and no set_timer)
    r"|hecho|listo(?!\s+para)|te avisaré|te aviso|te recordaré|lo recordaré|no se me olvida"
    # "¡Entendido! Voy a apagar el equipo ahora mismo" with no shutdown_pc call (live test)
    # "¡Voy a buscar quién es la abuela Sopita!" with no web_search (log, 27-oct)
    r"|voy a (?:apagar|reiniciar|suspender|abrir|cerrar|poner|subir|bajar|guardar|anotar|crear|copiar|minimizar"
    r"|buscar|mover|maximizar|reproducir|recordar)"
    # "¡Yatta! Reproduciendo More en YouTube" with no tool call (live, 24-oct)
    r"|reproduciendo|poniendo|abriendo|buscando|te pongo"
    # "Cierro las pestañas en este momento" with no tool call (live, 24-oct)
    r"|cierro|abro|subo|bajo|guardo|anoto|copio|minimizo|cerrando)\b",
    re.IGNORECASE,
)

# The YouTube player, whole phrases only (19 Gemini requests in the logs, 20-oct to 3-nov)
_VIDEO = r"(?:el\s+|al\s+|del\s+|a\s+|en\s+)?(?:v[ií]deo|youtube|reproductor)"
_SECONDS = r"(\d+|" + "|".join(k for k in _SPOKEN_NUMBERS if k != "media") + r")\s+segundos?"
_PLAYER_ORDERS = [
    (rf"{_WAKE}(?:pon\s+|sube\s+|baja\s+|s[uú]bele\s+|b[aá]jale\s+)?(?:el\s+)?volumen\s+{_VIDEO}\s+(?:a|al|en)\s+"
     r"(\d{1,3})\s*(?:%|por\s*ciento)?$", "volume"),
    (rf"{_WAKE}(?:(?:s[uú]b[eií](?:le)?|aumenta(?:le)?|m[aá]s)\s+(?:el\s+)?volumen|s[uú]b[eií]le)\s+{_VIDEO}$",
     "volume_up"),
    (rf"{_WAKE}(?:(?:b[aá]j[aeá](?:le)?|disminu(?:ye|í)(?:le)?|menos)\s+(?:el\s+)?volumen|b[aá]j[aeá]le)\s+{_VIDEO}$",
     "volume_down"),
    (rf"{_WAKE}(?:silencia|mutea|quita\s+el\s+(?:sonido|audio))\s+{_VIDEO}$", "mute"),
    (rf"{_WAKE}(?:(?:quita|quitar|desactiva)\s+(?:el\s+)?silencio|desmutea|activa\s+el\s+(?:sonido|audio))\s+{_VIDEO}$",
     "unmute"),
    (rf"{_WAKE}(?:(?:pon|pasa|salta)\s+(?:a\s+|al\s+)?(?:el\s+)?)?(?:siguiente|pr[oó]ximo|otro)\s+v[ií]deo$", "next"),
    (rf"{_WAKE}(?:adelanta|avanza|adel[aá]ntalo|av[aá]nzalo)(?:\s+(?:el\s+)?v[ií]deo)?(?:\s+{_SECONDS})?$", "forward"),
    # "Regresa" alone is not about the video: it needs the seconds or "el video"
    (rf"{_WAKE}(?:regresa|retrocede|atrasa|r[eé]gresalo|atr[aá]salo)(?:\s+(?:el\s+)?v[ií]deo\s+{_SECONDS}"
     rf"|\s+(?:el\s+)?v[ií]deo|\s+{_SECONDS})$", "back"),
    (rf"{_WAKE}(?:pon|activa|ponle)\s+(?:los\s+)?subt[ií]tulos(?:\s+{_VIDEO})?$", "captions_on"),
    (rf"{_WAKE}(?:quita|desactiva|apaga|qu[ií]tale)\s+(?:los\s+)?subt[ií]tulos(?:\s+{_VIDEO})?$", "captions_off"),
    (rf"{_WAKE}(?:pon(?:lo|me)?(?:\s+el\s+v[ií]deo)?\s+(?:en|a)\s+|calidad\s+(?:en\s+|a\s+)?)(\d{{3,4}})\s*p?$", "quality"),
    (rf"{_WAKE}(?:pon(?:lo|me)?(?:\s+el\s+v[ií]deo)?\s+(?:en|a)\s+)?(?:la\s+)?(m[aá]xima|m[ií]nima)\s+calidad$", "quality"),
    (rf"{_WAKE}(?:pon(?:lo)?\s+(?:a|en)\s+|cambia\s+la\s+)?velocidad\s+(?:a\s+|de\s+|en\s+)?"
     r"(\d(?:[.,]\d{1,2})?|normal)\s*x?$", "speed"),
    (rf"{_WAKE}(?:repite\s+(?:el|este)\s+v[ií]deo|pon(?:lo|me)?(?:\s+el\s+v[ií]deo)?\s+en\s+bucle)$", "loop"),
]


def _youtube_order(low: str) -> Optional[Tuple[str, str]]:
    """(action, value) for youtube_player when the whole phrase is a player order, else None."""
    for pattern, action in _PLAYER_ORDERS:
        m = re.match(pattern, low)
        if not m:
            continue
        value = next((g for g in m.groups() if g), "")
        if action in ("forward", "back") and value:
            value = str(_SPOKEN_NUMBERS.get(value) or value)
        elif action == "quality":
            value = "max" if "x" in value else "min" if value.startswith("m") else f"{value}p"
        elif action == "speed":
            value = "1" if value == "normal" else value.replace(",", ".")
        return action, value
    return None


def _to_wav(audio: np.ndarray, sample_rate: int = 16000) -> bytes:
    """Encodes 16 kHz float32 mono audio as 16-bit PCM WAV bytes."""
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sample_rate)
        w.writeframes((np.clip(np.asarray(audio, dtype=np.float32).flatten(), -1.0, 1.0) * 32767).astype(np.int16).tobytes())
    return buf.getvalue()

# Gemini ends its answer with this when the user says goodbye in words no list catches (system prompt)
_BYE_TAG = re.compile(r"\s*\[adi[oó]s\]\s*", re.IGNORECASE)
TRANSCRIPT_HINT = "(Transcripción automática, puede tener errores: "
CHAT_HINT = ("(Aviso del sistema: este mensaje es solo charla, sin ninguna orden: contesta sin herramientas. "
             "Las órdenes de mensajes anteriores ya se hicieron: no las repitas.)")
# The user asks whether the last action happened: answering "sí, lo apunté" is then not a claim
_ASKS_ABOUT_IT = re.compile(r"\?|\bsegur[oa]\b|\bde verdad\b|\bya lo\b|\b(?:lo|la)\s+\w+(?:aste|iste)\b", re.IGNORECASE)
# Follow-up requests after the first one: tool results back to the model, a nudge, or a second tool step
MAX_TOOL_ROUNDS = 3
# Tools whose result already is the answer ("He abierto Spotify.", "¡Clip guardado!"): when they all work and the
# phrase is a single order, the follow-up request that only rephrases it is skipped. 3-nov log: 32 of 110 follow-ups
# were this, none led to another step. Not here: tools that work in steps or retry (windows, tabs, the YouTube
# player, open_url) and the ones that bring data to talk about (weather, files, the PC state)
FINAL_TOOLS = {
    "open_app", "close_app", "set_volume", "change_volume", "mute", "media_control", "obs", "youtube_play",
    "open_website", "web_search", "youtube_search", "show_desktop", "lock_pc", "set_timer", "remind", "cancel_timer",
    "take_note", "complete_note", "delete_note", "remember", "forget", "create_text_file", "copy_to_clipboard",
    "open_folder", "open_notes", "watch_downloads", "run_routine",
}
_ONE_MORE_STEP = re.compile(r"\b(y|despu[eé]s|luego|tambi[eé]n|primero|entonces)\b", re.IGNORECASE)
# A request that hangs waits this long before the next model in the chain. 10 s is the API's minimum: 8 s made every
# request fail with 400 "Manually set deadline 8s is too short. Minimum allowed deadline is 10s." (log 3-nov 17:18)
GEMINI_TIMEOUT_MS = 10_000
# Cooldown after the 1st, 2nd and 3rd+ failure in a row of the same model (the 1st keeps the usual 15/60 s)
REPEAT_FAILURE_COOLDOWN_S = (0.0, 120.0, 600.0)
HISTORY_MAX_AGE_S = 12 * 3600  # a saved conversation older than this comes back marked as a past one
NUDGE_TEXT = (
    "(Aviso del sistema) Dijiste que hiciste una acción, pero no llamaste ninguna herramienta, así que no ocurrió. "
    "Si el usuario pidió una acción, llama ahora la herramienta adecuada. Si no, responde sin decir que la hiciste."
)
GOODBYE_ANSWERS = ("¡Vale! Aquí estaré si me necesitas.", "¡Hasta luego!", "¡Nos vemos!", "¡Chao, chao!")
THANKS_ANSWERS = ("¡De nada! Llámame cuando quieras.", "¡Con gusto! Aquí estaré.")

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
        web_search: bool = False,
        history_file: Optional[Path] = None,
    ) -> None:
        self.primary_model = model_name
        self.models_fallback = models_fallback or list(DEFAULT_FALLBACKS)
        # Async callback (the pipeline's "Un momento...") played once per turn before trying the next model
        self.on_model_switch: Optional[Callable[[], Awaitable[None]]] = None
        # Full prioritized candidate pool
        self.all_models: List[str] = [self.primary_model] + [
            m for m in self.models_fallback if m != self.primary_model
        ]
        self.max_history = max_history
        self.temperature = temperature
        self.web_search = web_search
        self.builtin_tools = True  # url_context (+ google_search if web_search); off for the session if rejected

        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            logger.warning("GEMINI_API_KEY is not set in environment!")

        # GEMINI_TIMEOUT_MS per HTTP request: a hung connection must fail so the model fallback can kick in (H-026)
        self.client = genai.Client(api_key=api_key, http_options=types.HttpOptions(timeout=GEMINI_TIMEOUT_MS))
        self.tools = get_registered_tools()
        self.total_api_calls = 0
        self._quota_warning: Optional[str] = None
        # For the panel: the model that answered last, and the last turns (when, what, local or Gemini)
        self.last_model: Optional[str] = None
        self.recent_turns: Deque[Dict[str, str]] = deque(maxlen=12)
        self._turn_kind = "local"
        self._last_query_text = ""
        self._last_query_time = 0.0
        self._last_result: Optional[Tuple[str, str, bool]] = None

        # Model cooldown tracker: model_name -> expiration timestamp
        self._model_cooldown: Dict[str, float] = {}
        self._fail_streak: Dict[str, int] = {}  # failed requests in a row, per model
        # In-memory history turns for model transfer: [{"role": "user"|"model", "text": str}]
        self._history_turns: List[Dict[str, str]] = []
        self._acted_last_turn = False  # the previous turn ran a tool (local or Gemini's)
        self.last_outcome: Optional[str] = None  # "ok"/"fail": how this turn's actions went (her body language)
        # On disk, so a restart does not leave her with no idea what was just said; None (tests) = memory only
        self.history_file = history_file
        self._load_history()

        logger.info(
            "MikuBrain initialized with %d PC tools. Primary: %s | Fallbacks: %s",
            len(self.tools),
            self.primary_model,
            self.models_fallback,
        )

    def _build_system_instruction(self) -> str:
        now = datetime.now()
        # Spanish weekday + ISO date: remind(date=...) needs "el viernes" worked out from it
        now_str = f"{_WEEKDAYS[now.weekday()]} {now:%Y-%m-%d %H:%M}"
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

    def _build_request(
        self, clean_input: str, audio: Optional[np.ndarray], screenshot: Optional[bytes] = None, state: str = ""
    ) -> Tuple[List[types.Content], types.GenerateContentConfig]:
        """Text history + the user's audio (or text) + the PC state. Tools are declared, never auto-called."""
        contents = [
            types.Content(role=turn["role"], parts=[types.Part.from_text(text=turn["text"])])
            for turn in self._history_turns[-(self.max_history * 2):]
        ]
        if audio is not None:
            user_part = types.Part.from_bytes(data=_to_wav(audio), mime_type="audio/wav")
        else:
            user_part = types.Part.from_text(text=clean_input)
        parts = [user_part]
        if audio is not None:
            # Audio alone: flash-lite misheard "¿Cómo estás hoy?" and replayed the previous order (log, 27-oct)
            parts.append(types.Part.from_text(text=f"{TRANSCRIPT_HINT}«{clean_input}»)"))
        if intent.is_small_talk(clean_input):
            # Flash-lite replays the last order on small talk (log 3-nov: "¿Cómo estás, oye?" saved an OBS clip,
            # "Gracias mi amor" set a second reminder). Gemini still hears the audio: a real order still runs
            parts.append(types.Part.from_text(text=CHAT_HINT))
        if state:
            # Only in this request, never in the history: an old snapshot would contradict the new one
            parts.append(types.Part.from_text(text=state))
        if screenshot:
            parts.append(types.Part.from_bytes(data=screenshot, mime_type="image/png"))
        contents.append(types.Content(role="user", parts=parts))
        # Text-only turns: Gemini answered audio + built-in tools with 400 (live test, 23-oct)
        return contents, self._build_config(with_builtins=audio is None and not screenshot)

    def _build_config(self, with_builtins: bool = True) -> types.GenerateContentConfig:
        tools: List[Any] = list(self.tools)
        tool_config = None
        if self.builtin_tools and with_builtins:
            # Google runs these inside the same request (Gemini 3 tool combination): reading a web page costs
            # no extra request. google_search only on request: the free tier answers every call with it 429.
            # Docs ask for VALIDATED mode when built-in and custom tools mix.
            tools.append(types.Tool(url_context=types.UrlContext()))
            if self.web_search:
                tools.append(types.Tool(google_search=types.GoogleSearch()))
            tool_config = types.ToolConfig(
                include_server_side_tool_invocations=True,
                function_calling_config=types.FunctionCallingConfig(mode="VALIDATED"),
            )
        return types.GenerateContentConfig(
            system_instruction=self._build_system_instruction(),
            tools=tools,
            tool_config=tool_config,
            temperature=self.temperature,
            max_output_tokens=300,
            # Thinking tokens count against max_output_tokens: left on, they ate the 300 and the answer came back empty
            thinking_config=types.ThinkingConfig(thinking_level="MINIMAL"),
            # Off: our own agent loop runs the tools locally and decides when a result must go back to Gemini
            automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
        )

    @staticmethod
    def _for_model(
        model: str, contents: List[types.Content], config: types.GenerateContentConfig, clean_input: str
    ) -> Tuple[List[types.Content], types.GenerateContentConfig]:
        """Adapts the turn's request to what a fallback model accepts (probed live, 24-oct)."""
        if model.startswith("gemma"):
            # Gemma: "Audio input modality is not enabled", no thinking config, no built-in tools. It gets
            # Whisper's text, which is worse than the audio but beats no answer
            parts = [
                types.Part.from_text(text=clean_input)
                if p.inline_data and (p.inline_data.mime_type or "").startswith("audio") else p
                for p in contents[-1].parts
                if not (p.text or "").startswith(TRANSCRIPT_HINT)  # the text itself replaces the audio
            ]
            contents = contents[:-1] + [types.Content(role="user", parts=parts)]
            tools = [t for t in (config.tools or []) if not isinstance(t, types.Tool)]
            return contents, config.model_copy(update={"thinking_config": None, "tools": tools, "tool_config": None})
        if model in THINKING_LOW_MODELS:
            # LOW thinks a little: more room so the thoughts do not eat the answer (the empty-answer bug)
            return contents, config.model_copy(update={
                "thinking_config": types.ThinkingConfig(thinking_level="LOW"), "max_output_tokens": 800,
            })
        return contents, config

    async def _generate(self, model: str, contents: List[types.Content], config: types.GenerateContentConfig) -> Any:
        """One generate_content call. If Gemini rejects the built-in web tools, asks again without them."""
        try:
            return await self.client.aio.models.generate_content(model=model, contents=contents, config=config)
        except Exception as e:
            err = str(e).lower()
            rejected = any(t in err for t in ("400", "invalid_argument", "429", "resource_exhausted"))
            had_builtins = any(getattr(t, "url_context", None) for t in config.tools or [])
            # A bad API key is also a 400: that is not the web tools' fault
            if not (had_builtins and rejected) or "api key" in err:
                raise
            # A rejected request does not use quota, so the retry keeps the one-request rule
            self.builtin_tools = False
            try:
                # Same config minus the built-ins (keeps the per-model adaptation of _for_model)
                plain = config.model_copy(update={
                    "tools": [t for t in config.tools or [] if not isinstance(t, types.Tool)], "tool_config": None,
                })
                response = await self.client.aio.models.generate_content(model=model, contents=contents, config=plain)
            except Exception:
                self.builtin_tools = True  # also fails without them: the model itself is the problem
                raise
            logger.warning("Gemini rejected the built-in web tools (%s). Disabled for this session.", e)
            return response

    def _count(self, model: str) -> None:
        """One request sent, against today's quota (Google counts failed ones too); the 90% warning rides on this
        turn's answer."""
        if self.history_file is None:  # a test, not the real assistant: never touch cache/quota.json
            return
        try:
            self._quota_warning = quota.count(model, self.primary_model) or self._quota_warning
        except Exception as e:  # counting must never cost an answer
            logger.warning("Quota count failed: %s", e)

    def _remember(self, user_text: str, model_text: str) -> None:
        """Keeps the turn as text so the next request (on any model) has the context."""
        self.recent_turns.appendleft({"at": datetime.now().strftime("%H:%M"), "user": user_text,
                                      "answer": re.sub(r"^\[\w+\]\s*", "", model_text), "kind": self._turn_kind})
        self._history_turns.append({"role": "user", "text": user_text})
        self._history_turns.append({"role": "model", "text": model_text})
        if len(self._history_turns) > self.max_history * 4:
            self._history_turns = self._history_turns[-(self.max_history * 2):]
        self._save_history()
        if self.history_file is not None:  # the real assistant, not a test
            archive_turn(user_text, re.sub(r"^\[\w+\]\s*", "", model_text))

    def note_announcement(self, message: str) -> None:
        """A reminder she just said: in the history, so "recuérdamelo en 10 minutos" knows what "lo" is."""
        self._remember("(Aviso del sistema: sonó un recordatorio)", f"[happy] {message}")

    def _load_history(self) -> None:
        if self.history_file is None:
            return
        try:
            saved_at = self.history_file.stat().st_mtime
            turns = json.loads(self.history_file.read_text(encoding="utf-8"))
            self._history_turns = [
                {"role": t["role"], "text": str(t["text"])} for t in turns
                if isinstance(t, dict) and t.get("role") in ("user", "model")
            ][-(self.max_history * 2):]
            if self._history_turns and time.time() - saved_at > HISTORY_MAX_AGE_S:
                # Kept, but marked as the past: she must not answer "eso" as if it were said a minute ago
                day = datetime.fromtimestamp(saved_at)
                self._history_turns += [
                    {"role": "user", "text": f"(Aviso del sistema: lo anterior es de una conversación del "
                                             f"{_WEEKDAYS[day.weekday()]} {day:%Y-%m-%d}. Empieza una nueva.)"},
                    {"role": "model", "text": "[neutral] Entendido."},
                ]
            logger.info("Restored %d history turns from the last session.", len(self._history_turns) // 2)
        except (OSError, ValueError, KeyError, TypeError):
            pass  # no file or a broken one: a fresh conversation, never a crash

    def _save_history(self) -> None:
        if self.history_file is None:
            return
        try:
            self.history_file.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.history_file.with_suffix(".tmp")
            tmp.write_text(json.dumps(self._history_turns[-(self.max_history * 2):], ensure_ascii=False), encoding="utf-8")
            tmp.replace(self.history_file)
        except OSError as e:
            logger.warning("Could not save the conversation history: %s", e)

    async def _run_tool_calls(self, calls: List[Any]) -> List[Dict[str, Any]]:
        """Runs the model's tool calls locally, in order, and returns their result dicts."""
        results: List[Dict[str, Any]] = []
        for call in calls:
            meta = get_tool_metadata(call.name or "")
            if meta is None:
                results.append({"ok": False, "result": f"No existe la herramienta {call.name}."})
                continue
            # Tools block (sleeps, process scans): run them off the event loop (H-025)
            results.append(await asyncio.to_thread(meta["function"], **dict(call.args or {})))
        self._acted_last_turn = True
        failed = any(not r.get("ok") and not r.get("requires_confirmation") for r in results)
        self.last_outcome = "fail" if failed or self.last_outcome == "fail" else "ok"
        return results

    async def _agent_loop(
        self, model: str, contents: List[types.Content], config: types.GenerateContentConfig, response: Any,
        clean_input: str, acted_before: bool,
    ) -> Tuple[str, str]:
        """Tool calls -> run them -> send the results back -> answer, up to MAX_TOOL_ROUNDS requests more.

        The model SEES what its tools did, so it answers from facts. With one blind request it claimed actions it
        never ran ("¡Anotado!", "Reproduciendo...", "Voy a apagar..."), and the regex patches meant to catch that
        ended up calling a true "lo apunté" a lie (log, 24-oct). If it still claims an action without a tool call,
        it gets one nudge.
        """
        contents = list(contents)
        last_results: List[Dict[str, Any]] = []
        nudged = False
        follow_ups_left = MAX_TOOL_ROUNDS
        while True:
            content = response.candidates[0].content if response.candidates else None
            parts = (content.parts if content else None) or []
            raw_answer = "".join(p.text for p in parts if p.text and not p.thought).strip()
            calls = [p.function_call for p in parts if p.function_call]
            if calls:
                logger.info("Gemini asked for tools: %s", [f"{c.name}({dict(c.args or {})})" for c in calls])
                last_results = await self._run_tool_calls(calls)
                if (follow_ups_left == MAX_TOOL_ROUNDS and {c.name for c in calls} <= FINAL_TOOLS
                        and all(r.get("ok") for r in last_results) and not _ONE_MORE_STEP.search(clean_input)):
                    logger.info("The tool results are the answer: no follow-up request.")
                    if raw_answer:
                        return self._parse_emotion(raw_answer)
                    return "happy", self._sanitize_for_speech(" ".join(str(r.get("result", "")) for r in last_results))
                # The model's own content goes back as is: Gemini 3 needs its thought signatures with the results
                follow_up = [content, types.Content(role="user", parts=[
                    types.Part(function_response=types.FunctionResponse(id=c.id, name=c.name, response=r))
                    for c, r in zip(calls, last_results)
                ])]
            # The claim only matters when nothing ran this turn: after tool results it describes what happened
            elif (not nudged and not last_results and CLAIMED_ACTION_RE.search(raw_answer)
                  and not (response.candidates and response.candidates[0].grounding_metadata)
                  # "¿Estás segura que la guardaste?" right after saving it: "lo apunté" is the truth (log 06:16)
                  and not (acted_before and _ASKS_ABOUT_IT.search(clean_input))):
                logger.warning("Gemini claimed an action without calling a tool: '%s'. Nudging it once.", raw_answer)
                nudged = True
                follow_up = [content, types.Content(role="user", parts=[types.Part.from_text(text=NUDGE_TEXT)])]
            else:
                if not raw_answer and not calls:
                    logger.warning("Gemini returned an empty answer (finish_reason=%s).",
                                   response.candidates[0].finish_reason if response.candidates else None)
                return self._parse_emotion(raw_answer)
            if follow_ups_left == 0:
                break
            follow_ups_left -= 1
            contents += follow_up
            try:
                self.total_api_calls += 1
                logger.info("--> [GEMINI REQ #%d] Model: %s | follow-up (tool results or nudge)", self.total_api_calls, model)
                self._count(model)
                response = await self._generate(model, contents, config)
            except Exception as e:
                # Quota or overload on the follow-up: the actions are done, so read their results out as they are
                logger.warning("Follow-up request failed (%s). Reading the tool results instead.", e)
                break
        said = " ".join(str(r.get("result", "")) for r in last_results)
        failed = any(not r.get("ok") and not r.get("requires_confirmation") for r in last_results)
        return ("sad" if failed else "happy"), self._sanitize_for_speech(said)

    @staticmethod
    def _sanitize_for_speech(text: str) -> str:
        """
        Strips markdown symbols (*, _, `, ~, #), URLs, and extra spaces
        so subtitles and upcoming TTS audio read cleanly and naturally.
        """
        text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)
        text = re.sub(r"https?://\S+|www\.\S+", "", text)
        text = re.sub(r"[*_`~#]", "", text)
        # "[yatta]" mid-answer: tags are never read out (log, 27-oct); [adios] stays for chat() to see
        text = re.sub(r"\s*\[(?!adi[oó]s\])[^\]]*\]", "", text, flags=re.IGNORECASE)
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
            if emotion in ("adios", "adiós"):  # the goodbye tag where the emotion goes: keep it for chat()
                emotion, text = "happy", f"{text} [adios]"
            if emotion not in VALID_EMOTIONS:
                emotion = "happy"
            return emotion, self._sanitize_for_speech(text)
        return "happy", self._sanitize_for_speech(raw_text)

    def _try_fast_path_tool(self, text: str) -> Optional[Tuple[str, str, bool]]:
        """
        Local, instant, 0-request answers for a few UNAMBIGUOUS commands: volume, play/pause, the time, notes,
        timers, routines, "recuerda que", shutdown (it only asks). Everything else (opening apps or sites, YouTube,
        tabs) is Gemini's: it hears the audio, Whisper's text is often wrong ("Sueblo", "tITSoluciones"), and it
        sees the PC state. Every extra regex here was one more way to act on a misheard phrase.
        """
        # Whisper wraps phrases in "¡...!" / "¿...?" and ends them with ".": every "^verb" rule missed them
        low = text.lower().strip().strip("¡!¿?.,;: ")

        # Several orders in one phrase ("abre Spotify y pon el volumen al 30"): the unanchored rules (volume,
        # music) would do only one of them. Gemini does all of them in its single request
        if intent.has_chained_orders(low):
            return None

        # 0. Greetings with time-of-day awareness (0ms cloud latency, 0 API quota used)
        # Without punctuation: Whisper writes "Hola, Miku." and "Hola, ¿qué tal?", which went to Gemini
        if " ".join(re.findall(r"\w+", low)) in (
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

        # Routines: "modo trabajo", "activa el modo música" (0 requests)
        m_routine = re.match(rf"{_WAKE}(?:activa\s+(?:el\s+)?|pon\s+(?:el\s+)?|rutina\s+)?modo\s+(\w+)$", low.strip("¡!¿?., "))
        if m_routine:
            from core.tools.routines import find_routine, run_routine
            if find_routine(m_routine.group(1)):
                res = run_routine(m_routine.group(1))
                return ("happy" if res.get("ok") else "sad", res["result"], False)

        # 5. Volume / Media: whole words only ("playlist" or "display" must not press play, H-024)
        def has_word(*words: str) -> bool:
            return any(re.search(rf"\b{re.escape(w)}\b", low) for w in words)

        def confirm(res: Dict[str, Any], ok_text: str) -> Tuple[str, str, bool]:
            if res.get("ok"):
                return ("happy", ok_text, False)
            return ("sad", res.get("result", "No pude hacerlo."), False)

        def said(res: Dict[str, Any]) -> Tuple[str, str, bool]:
            return ("happy" if res.get("ok") else "sad", res.get("result", "No pude hacerlo."), False)

        # "Sube el volumen del video": YouTube's own volume (youtube_player), not Windows'. pause/play below are
        # fine either way (the media keys reach YouTube too)
        for_player = has_word("video", "vídeo", "youtube", "reproductor", "canción", "cancion")
        player = _youtube_order(low)
        if player is not None:
            from core.tools.web import youtube_player
            return said(youtube_player(*player))

        # An exact level first: "súbele el volumen a 100%" used to just add 15 (log 05:13). Also "al máximo",
        # "súbelo a tope", "volumen al mínimo"
        m_level = None if for_player else re.search(
            r"\b(?:volumen|sonido|s[uú]belo|s[uú]bele|b[aá]jalo|b[aá]jale)\b.*?\b(?:a|al|en)\s+"
            r"(\d{1,3})\s*(?:%|por\s*ciento)?(?!\w)|\b(?:volumen|sonido|s[uú]belo|s[uú]bele)\b.*?\b(al\s+m[aá]ximo|a\s+tope|a\s+full)\b"
            r"|\b(?:volumen|sonido|b[aá]jalo|b[aá]jale)\b.*?\b(al\s+m[ií]nimo)\b",
            low,
        )
        if m_level:
            from core.tools.media import set_volume
            level = int(m_level.group(1)) if m_level.group(1) else 100 if m_level.group(2) else 0
            return confirm(set_volume(level), f"¡Listo, volumen al {min(level, 100)}%!")

        # Also voseo and enclitics, common in Costa Rica: "bajá el volumen", "subile", "bájale el volumen"
        if not for_player and re.search(r"\b(?:s[uú]b[eií](?:le|me)?|subir|aumenta(?:le)?|m[aá]s)\s+(?:el\s+)?volumen\b", low):
            from core.tools.media import change_volume
            return confirm(change_volume(15), "¡Subí el volumen!")
        if not for_player and re.search(r"\b(?:b[aá]j[aeá](?:le|me)?|bajar|disminu(?:ye|í)(?:le)?|menos)\s+(?:el\s+)?volumen\b", low):
            from core.tools.media import change_volume
            return confirm(change_volume(-15), "¡Listo, bajé el volumen!")
        # Mute, pause and play: the whole phrase only. A word anywhere acted on questions: "¿qué significa pausa
        # en inglés?" paused the music, "¿cómo se dice silencio en japonés?" muted the PC (audit 3-nov).
        # "quita el silencio" and "silencia el video" don't match: Gemini decides
        if re.match(rf"{_WAKE}(?:(?:pon|activa(?:r)?)\s+(?:el\s+)?)?(?:silencio|silencia(?:r|lo)?|mutea(?:r|lo)?|mute)"
                    r"(?:\s+(?:el\s+|la\s+)?(?:pc|computadora|sonido|todo))?$", low):
            from core.tools.media import mute
            return confirm(mute(True), "¡Silenciado!")
        # Log: "Pausa la música.", "Ponle pausa la canción.", "¡Pom pausa!"
        if re.match(rf"{_WAKE}(?:(?:p[oó][nm](?:le|gale)?|dale)\s+)?pausa(?:r)?"
                    r"(?:\s+(?:a\s+)?(?:la|el)\s+(?:m[uú]sica|canci[oó]n|v[ií]deo))?$", low):
            from core.tools.media import media_control
            return confirm(media_control("pause"), "Música pausada.")
        if re.match(rf"{_WAKE}(?:(?:(?:dale|d[eé]le|pon(?:le)?)\s+)?(?:play|reanuda(?:r)?)"
                    r"(?:\s+otra\s+vez|\s+(?:a\s+)?(?:la|el)\s+(?:m[uú]sica|canci[oó]n|v[ií]deo))?"
                    r"|(?:reproduce|reproducir|pon|contin[uú]a)\s+la\s+m[uú]sica)$", low):
            from core.tools.media import media_control
            return confirm(media_control("play"), "¡Música reproduciéndose!")
        if re.match(rf"{_WAKE}(?:(?:pon|pasa|salta|cambia)\s+(?:a\s+|al\s+)?)?(?:la\s+)?(?:siguiente(?:\s+canci[oó]n)?"
                    rf"|pr[oó]xima\s+canci[oó]n|otra\s+canci[oó]n)$|{_WAKE}(?:pasa|salta|cambia)(?:\s+(?:la|esta|de))?"
                    r"\s+canci[oó]n$", low):
            from core.tools.media import media_control
            return confirm(media_control("next"), "¡Siguiente canción!")
        if re.match(rf"{_WAKE}(?:(?:pon|regresa|vuelve)\s+(?:a\s+)?)?(?:la\s+)?(?:canci[oó]n\s+anterior"
                    r"|anterior(?:\s+canci[oó]n)?)$", low):
            from core.tools.media import media_control
            return confirm(media_control("previous"), "Volví a la canción anterior.")
        if re.match(rf"{_WAKE}(?:(?:quita|quitar|desactiva)\s+(?:el\s+)?silencio|desmutea|unmute"
                    r"|(?:activa|reactiva)\s+(?:el\s+)?sonido)$", low):
            from core.tools.media import mute
            return confirm(mute(False), "¡Sonido activado!")
        if re.match(rf"{_WAKE}bloquea(?:r)?\s+(?:el\s+|la\s+|mi\s+)?(?:pc|computadora|compu|equipo|pantalla"
                    r"|sesi[oó]n|laptop)$", low):
            from core.tools.system import lock_pc
            return said(lock_pc())
        if re.match(rf"{_WAKE}(?:(?:qu[eé]|cu[aá]les)\s+(?:son\s+)?(?:mis\s+)?(?:recordatorios|temporizadores|alarmas|avisos)"
                    r"(?:\s+tengo)?(?:\s+(?:activos|pendientes))?|(?:l[eé]eme\s+)?mis\s+recordatorios)$", low):
            from core.tools.timers import list_timers
            return said(list_timers())

        # 6. Date & Time, the whole phrase only: "¿a qué hora cierra el súper?" got "Son las 18:41."
        if re.match(rf"{_WAKE}(?:qu[eé]\s+hora\s+es(?:\s+ahora)?|dime\s+la\s+hora)$", low):
            now_dt = datetime.now()
            return ("neutral", f"Son las {now_dt.strftime('%H:%M')}.", False)

        # 6. Notes
        m_note = re.match(rf"{_WAKE}(?:toma|guarda|anota)\s+(?:una\s+)?nota(?:\s+que\s+diga)?[:\s]+(.+)$", low)
        # "Recuérdame en 10 minutos que saque la ropa": the model once promised it and never called set_timer
        m_timer = re.match(
            rf"{_WAKE}(?:(?:recu[eé]rdame|av[ií]same)\s+en|(?:pon|ponme)\s+un\s+temporizador\s+de)\s+"
            r"(\d+(?:[.,]\d+)?|un|una|uno|dos|tres|cuatro|cinco|diez|quince|veinte|treinta|media)\s+"
            # "...en un minuto tomar agua": the link word is optional (log, 26-oct: it went to Gemini)
            r"(minutos?|horas?)(?:\s+(?:(?:que|para|de)\s+)?(.+))?$",
            low,
        )
        if m_timer:
            from core.tools.timers import set_timer
            amount = _SPOKEN_NUMBERS.get(m_timer.group(1)) or float(m_timer.group(1).replace(",", "."))
            minutes = amount * (60 if m_timer.group(2).startswith("hora") else 1)
            what = (m_timer.group(3) or "").strip()
            # "Recuérdame ... que X" is a reminder ("¡Oye, recuerda: X!"); "un temporizador ... para el té" is a timer
            reminder = what and "temporizador" not in low
            res = set_timer(minutes, f"Recordatorio: {what}" if reminder else (what or "Temporizador"))
            if res.get("ok"):
                return ("happy", f"¡Listo! Te aviso en {minutes:g} minutos.", False)
            return ("sad", res.get("result", "No pude poner el temporizador."), False)

        # "Apaga la computadora": shutdown_pc only asks for confirmation here (the "sí" is local too). The model
        # once answered "Voy a apagar el equipo ahora mismo" without calling it
        m_power = re.match(
            rf"{_WAKE}(apaga|reinicia|suspende)\s+(?:el\s+|la\s+|mi\s+)?(?:pc|computadora|compu|ordenador|equipo|laptop)$", low
        )
        if m_power:
            from core.tools.system import shutdown_pc
            res = shutdown_pc(mode={"apaga": "shutdown", "reinicia": "restart", "suspende": "sleep"}[m_power.group(1)])
            return ("neutral", res.get("result", ""), False)

        # "Recuerda que mi gato se llama Mochi": live tests saw the model say "¡Anotado en mi memoria!" and not call
        # remember. "...acuérdate de eso" (no fact after it) still goes to Gemini
        m_fact = re.match(rf"{_WAKE}(?:recuerda|acu[eé]rdate\s+de|no\s+olvides)\s+que\s+(.+)$", text.strip(" ¡!.¿?"),
                          re.IGNORECASE)
        if m_fact:
            from core.tools.memory import remember
            res = remember(m_fact.group(1).strip())
            if res.get("ok"):
                return ("happy", "¡Lo recordaré!", False)

        # "Apunta que tengo pendiente X": Gemini once answered "¡Anotado!" without calling take_note
        m_jot = re.match(rf"{_WAKE}(?:ap[uú]nta(?:me)?|an[oó]ta(?:me)?)(?:\s+que)?\s+(.+)$", text.strip(" ¡!.¿?"), re.IGNORECASE)
        if m_note or m_jot:
            text_note = (m_note or m_jot).group(1).strip(" .")
            from core.tools.notes import take_note
            res = take_note(text_note)
            if res.get("ok"):
                return ("happy", "¡Apuntado! Ya guardé tu nota.", False)
            return ("sad", res.get("result", "No pude guardar la nota."), False)

        # The whole phrase only: "borra mis pendientes" read them out
        if re.match(rf"{_WAKE}(?:l[eé]e(?:me)?\s+mis\s+(?:notas|pendientes)|leer\s+notas|mis\s+pendientes"
                    r"|cu[aá]les\s+son\s+mis\s+(?:notas|pendientes)|qu[eé]\s+(?:notas|pendientes)\s+tengo)$", low):
            from core.tools.notes import read_notes
            notes_res = read_notes()
            return ("neutral", notes_res.get("result", "No tienes notas."), False)
        if re.match(rf"{_WAKE}(?:qu[eé]\s+(?:tengo|hay|me\s+toca)(?:\s+(?:para|que\s+hacer))?\s+hoy"
                    r"|c[oó]mo\s+(?:est[aá]|viene|va)\s+mi\s+d[ií]a|(?:el\s+)?resumen\s+(?:del|de\s+mi)\s+d[ií]a)$", low):
            from core.tools.notes import my_day
            return said(my_day())
        if re.match(rf"{_WAKE}(?:cu[aá]nta\s+(?:cuota|capacidad)\s+(?:me\s+|te\s+)?(?:queda|quedan|llevas|llevamos|tengo)"
                    r"|cu[aá]ntas\s+peticiones\s+(?:me\s+|te\s+)?(?:quedan|llevas|llevamos)(?:\s+hoy)?"
                    r"|c[oó]mo\s+(?:va|vamos\s+de|andamos\s+de)\s+(?:la\s+)?cuota)(?:\s+hoy)?$", low):
            from core.tools.system import quota_status
            return said(quota_status())

        # OBS, only while it runs: "guarda eso" means a clip there, and something else for Gemini otherwise
        m_scene = re.match(rf"{_WAKE}(?:cambia|pasa|pon|ponme)\s+(?:a\s+)?(?:la\s+)?escena\s+(?:de\s+)?(.+)$", low)
        obs_order = (
            "clip" if re.match(rf"{_WAKE}(?:(?:guarda|gu[aá]rdame|haz|hazme|crea|saca|s[aá]came)\s+(?:eso|esto|el\s+clip"
                               r"|un\s+clip|ese\s+clip|la\s+jugada|esa\s+jugada|lo\s+[uú]ltimo)|clip|cl[ií]pealo"
                               r"|cl[ií]p(?:ea|é|e)\s+eso)$", low)  # log 3-nov: "Miku, clipé eso."
            else "record_start" if re.match(rf"{_WAKE}(?:graba|(?:empieza|comienza|ponte)\s+a\s+grabar|dale\s+a\s+grabar"
                                            r"|(?:inicia|empieza)\s+(?:la\s+)?grabaci[oó]n)$", low)
            else "record_stop" if re.match(rf"{_WAKE}(?:(?:para|det[eé]n|corta|termina|finaliza)\s+(?:la\s+)?grabaci[oó]n"
                                           r"|(?:deja|para)\s+de\s+grabar|ya\s+no\s+grabes)$", low)
            else "scene" if m_scene else None
        )
        if obs_order:
            from core.tools.obs import obs, obs_open
            if obs_open():
                return said(obs(obs_order, m_scene.group(1).strip(" .") if m_scene else ""))

        if re.match(rf"{_WAKE}(?:c[oó]mo\s+(?:est[aá]|va\s+a\s+estar|estar[aá])\s+el\s+(?:clima|tiempo)"
                    r"|qu[eé]\s+(?:clima|tiempo|temperatura)\s+(?:hace|hay|va\s+a\s+hacer)|(?:va|iba)\s+a\s+llover"
                    r"|llover[aá]|(?:el\s+)?clima)(?:\s+(?:para\s+)?(?:hoy|ma[nñ]ana))?$", low):
            from core.tools.weather import weather
            return said(weather("mañana" if re.search(r"ma[nñ]ana$", low) else "hoy"))

        if re.match(rf"{_WAKE}(?:(?:av[ií]same|dime)\s+cuando\s+(?:termin|acab)(?:e|en)|vigila)"
                    r"\s+(?:la\s+|las\s+|mi\s+|mis\s+)?descargas?$", low):
            from core.tools.downloads import watch_downloads
            return said(watch_downloads())

        # 7. Desktop / System
        # The whole phrase: "minimiza todo menos Opera" minimized Opera too
        if re.match(rf"{_WAKE}(?:(?:mu[eé]stra(?:me)?|mostrar|ens[eé][nñ]ame)\s+(?:el\s+)?escritorio"
                    r"|minimiza(?:r|me)?\s+(?:todo|todas\s+las\s+ventanas))$", low):
            from core.tools.apps import show_desktop
            show_desktop()
            return ("happy", "¡Listo, te mostré el escritorio!", False)

        return None

    async def chat(self, user_text: str, audio: Optional[np.ndarray] = None) -> Tuple[str, str, bool]:
        """
        Answers one user turn with at most ONE Gemini request and returns (emotion, response_text, is_farewell).
        user_text is the local Whisper transcription (or typed text); audio, when given, is what Gemini hears.
        Local paths (confirmation, dedup, fast-path) cost 0 requests.
        """
        clean_input = user_text.strip()
        if not clean_input:
            return "neutral", "¿Sí? Dime qué necesitas.", False
        acted_before = self._acted_last_turn
        self._acted_last_turn = False
        self.last_outcome = None
        self._turn_kind = "local"  # confirmation, goodbye, fast path: no request

        # Only the user's own reply can confirm a pending destructive tool (H-001); the approved action
        # runs here, locally, so confirming costs no request
        confirmed = note_user_reply(clean_input)
        if confirmed is not None:
            res = await asyncio.to_thread(get_tool_metadata(confirmed["name"])["function"])
            answer = self._sanitize_for_speech(str(res.get("result", "")))
            self._remember(clean_input, answer)
            self._acted_last_turn = True
            self.last_outcome = "ok" if res.get("ok") else "fail"
            return ("happy" if res.get("ok") else "sad"), answer, False

        # In-memory deduplication: if exact same query arrives within 2.0s, reuse response with 0 extra API calls
        now = time.monotonic()
        if clean_input == self._last_query_text and (now - self._last_query_time) < 2.0 and self._last_result:
            logger.warning("Duplicate Gemini request within 2.0s: '%s'. Reusing cached result (0 API calls).", clean_input)
            return self._last_result

        # A plain goodbye ("ya está", "eso es todo", "gracias") hides her at once and costs no request; with an order
        # in it ("adiós, cierra Spotify") Gemini still handles the order and the farewell flag hides her after
        kind = intent.classify(clean_input)
        if kind in ("hide", "farewell"):
            if kind == "hide":
                answer = ""  # the pipeline hides her at once
            else:
                answer = random.choice(THANKS_ANSWERS if "gracias" in clean_input.lower() else GOODBYE_ANSWERS)
            self._remember(clean_input, f"[happy] {answer}")
            return "happy", answer, True

        # Instant local fast-path for direct PC commands (0ms cloud latency, 100% immune to 429)
        # Tools block (sleeps, process scans): run them off the event loop (H-025)
        fast_res = await asyncio.to_thread(self._try_fast_path_tool, clean_input)
        if fast_res is not None:
            logger.info("Executed local fast-path command: '%s' -> %s", clean_input, fast_res[1])
            # In the history too: "no, era tytsoluciones.net" after a local search got "¡Entendido! Dejo
            # constancia..." because Gemini never knew what had been done (log, 24-oct)
            self._remember(clean_input, f"[{fast_res[0]}] {fast_res[1]}")
            self._acted_last_turn = True
            self.last_outcome = "fail" if fast_res[0] == "sad" else "ok"
            self._last_query_text = clean_input
            self._last_query_time = now
            self._last_result = fast_res
            return fast_res

        # Build prioritized list of models to try
        models_to_try: List[str] = []
        for m in self.all_models:
            cooldown_until = self._model_cooldown.get(m, 0.0)
            # A bucket used up today is skipped: its 429 would cost a request on Google's count and the user's time
            if now >= cooldown_until and not (self.history_file is not None and quota.spent(m)):
                models_to_try.append(m)

        # If all models happen to be on cooldown, try all in original order anyway
        if not models_to_try:
            logger.warning("All models in cooldown. Attempting all candidates anyway.")
            models_to_try = list(self.all_models)
        # Always in config order: putting the last model that answered first kept a whole session on a small
        # fallback after one 504 (log 2-nov: 12 turns on 3.1-flash-lite after a 15 s cooldown)

        last_error = None
        self._turn_kind = "gemini"
        screenshot = None
        if intent.asks_about_screen(clean_input) or (intent.points_at_screen(clean_input) and not bridge.results):
            try:
                screenshot = await asyncio.to_thread(capture_screen_png)
                logger.info("Attaching a screenshot (%.0f KB) to the request.", len(screenshot) / 1024)
            except Exception as e:
                logger.warning("Screen capture failed (%s). Asking without it.", e)
        state = await asyncio.to_thread(describe_pc)
        contents, config = self._build_request(clean_input, audio, screenshot, state)
        response = None

        # Only a failed request (error, 429, 503: no answer, no quota spent) moves on to the next model.
        # The free tier's per-minute limits run out fast, so the chain is long (one bucket per model)
        told_user = False
        for i, model in enumerate(models_to_try):
            if i > 0 and not told_user and self.on_model_switch is not None:
                told_user = True
                try:
                    await self.on_model_switch()  # "Un momento...": the user hears that she is still on it
                except Exception:
                    logger.exception("Model-switch cue failed")
            try:
                self.total_api_calls += 1
                logger.info(
                    "--> [GEMINI REQ #%d] Model: %s | Query: '%s'%s",
                    self.total_api_calls,
                    model,
                    clean_input,
                    " (+audio)" if audio is not None else "",
                )
                # Local names: a failed Gemma must not leave the next Gemini with text instead of the audio
                model_contents, model_config = self._for_model(model, contents, config, clean_input)
                self._count(model)
                response = await self._generate(model, model_contents, model_config)
                self.last_model = model
                # Clear any previous cooldown for this healthy model
                self._model_cooldown.pop(model, None)
                self._fail_streak.pop(model, None)
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
                # A daily quota does not come back in a minute, nor a retired model (404): stop retrying them every turn
                gone = "per day" in err_str or "404" in err_str or "not_found" in err_str
                # Failing again and again (log 3-nov: 504 every turn, 10 s lost each time on an overloaded model):
                # it waits longer, so the next turns go straight to a model that answers
                streak = self._fail_streak[model] = self._fail_streak.get(model, 0) + 1
                cooldown_sec = 3600.0 if gone else max(60.0 if is_rate_limit else 15.0,
                                                       REPEAT_FAILURE_COOLDOWN_S[min(streak, len(REPEAT_FAILURE_COOLDOWN_S)) - 1])
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

        emotion, clean_text = await self._agent_loop(
            model, model_contents, model_config, response, clean_input, acted_before
        )
        if not clean_text:
            emotion, clean_text = "thinking", "Perdona, no te entendí bien. ¿Me lo repites?"

        # Gemini marks a goodbye our word lists missed ("Olvíalo, muchas gracias"): she hides after saying it
        said_bye = bool(_BYE_TAG.search(clean_text))
        clean_text = _BYE_TAG.sub(" ", clean_text).strip() or "¡Hasta luego!"
        if self._quota_warning:
            clean_text, self._quota_warning = f"{clean_text} {self._quota_warning}", None
        self._remember(clean_input, f"[{emotion}] {clean_text}")
        # A goodbye in her own words hides her too: without the tag she said "¡Hasta luego!" and kept listening
        result = (emotion, clean_text, said_bye or intent.is_farewell(clean_input) or intent.says_goodbye(clean_text))
        self._last_query_text = clean_input
        self._last_query_time = time.monotonic()
        self._last_result = result
        return result
