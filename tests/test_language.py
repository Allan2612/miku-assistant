"""Tables of real phrases for every text rule: fast path, lie detector, screenshot trigger, answer parsing, app names.

Tools are replaced by recorders, so nothing on the PC changes.
Run: core\\.venv\\Scripts\\python.exe -m tests.test_language  (or with pytest)
"""

import os

os.environ.setdefault("GEMINI_API_KEY", "test")

import core.tools.apps as apps
import core.tools.media as media
import core.tools.memory as memory
import core.tools.notes as notes
import core.tools.routines as routines
import core.tools.system as system
import core.tools.timers as timers
import core.tools.web as web
from core.llm import CLAIMED_ACTION_RE, SCREEN_RE, MikuBrain
from core.tools.apps import _spoken_app_list

calls = []


def _rec(name):
    def f(*args, **kwargs):
        calls.append((name, args or tuple(kwargs.values())))
        return {"ok": True, "result": ""}
    return f


def fast(text):
    calls.clear()
    for mod, name in [(apps, "open_app"), (apps, "close_app"), (apps, "show_desktop"), (media, "change_volume"),
                      (media, "mute"), (media, "media_control"), (web, "web_search"), (web, "youtube_search"),
                      (web, "open_url"), (notes, "take_note"), (notes, "open_notes"), (timers, "set_timer"), (memory, "remember"), (system, "shutdown_pc")]:
        setattr(mod, name, _rec(name))
    notes.read_notes = lambda *a: calls.append(("read_notes", ())) or {"ok": True, "result": "notas"}
    routines.ROUTINES["trabajo"] = [{"tool": "_noop"}]
    routines.get_tool_metadata = lambda n: {"function": _rec("routine_step"), "destructive": False}
    return MikuBrain._try_fast_path_tool(None, text)


# (phrase, expected first local call) — None means "goes to Gemini"
FAST_PATH = [
    ("Apunta que tengo pendiente subir el PR.", ("take_note", ("tengo pendiente subir el PR",))),
    ("¡Anótame comprar pan!", ("take_note", ("comprar pan",))),
    ("apúntame que mañana hay examen", ("take_note", ("mañana hay examen",))),
    ("Toma nota: llamar a mamá", ("take_note", ("llamar a mamá",))),
    ("qué pendientes tengo", ("read_notes", ())),
    ("¿Qué notas tengo?", ("read_notes", ())),
    ("¡Abre mi ópera!", ("open_app", ("opera gx",))),
    ("abre el navegador", ("open_app", ("opera gx",))),
    ("ópera", ("open_app", ("opera gx",))),
    ("abre youtube", ("open_url", ("https://www.youtube.com",))),
    ("Baja el volumen.", ("change_volume", (-15,))),
    ("sube el volumen", ("change_volume", (15,))),
    ("silencio", ("mute", (True,))),
    ("pausa", ("media_control", ("pause",))),
    ("busca recetas de pasta", ("web_search", ("recetas de pasta",))),
    ("busca en youtube world is mine", ("youtube_search", ("world is mine",))),
    ("Busca en Google recetas de arroz con leche.", ("web_search", ("recetas de arroz con leche",))),
    ("Hey Miku, busca el clima de mañana", ("web_search", ("el clima de mañana",))),
    ("¡Modo trabajo!", ("routine_step", ())),
    ("activa el modo trabajo", ("routine_step", ())),
    ("muestra el escritorio", ("show_desktop", ())),
    # Real Whisper transcriptions from the user's log
    ("Hey Miku, abre mi ópera.", ("open_app", ("opera gx",))),
    ("Ábreme Opera.", ("open_app", ("opera gx",))),
    ("¡Abreme el blog de notas!", ("open_notes", ())),
    ("¡Bajá el volumen!", ("change_volume", (-15,))),
    ("bájale el volumen", ("change_volume", (-15,))),
    ("Subile al volumen", None),  # "al volumen" is not the pattern: Gemini decides
    ("súbele el volumen", ("change_volume", (15,))),
    ("Ponme more en YouTube.", ("youtube_search", ("more",))),
    ("Reprodúceme world is mine en youtube", ("youtube_search", ("world is mine",))),
    ("Oye Miku, cierra spotify", ("close_app", ("spotify",))),
    ("Recuérdame en 10 minutos que saque la ropa de lavadora.", ("set_timer", (10.0, "Recordatorio: saque la ropa de lavadora"))),
    ("avísame en media hora", ("set_timer", (30.0, "Temporizador"))),
    ("pon un temporizador de cinco minutos para el té", ("set_timer", (5.0, "Recordatorio: el té"))),
    ("Hey Miku, recuérdame en una hora que llame a mamá", ("set_timer", (60.0, "Recordatorio: llame a mamá"))),
    ("Recuerda que mi gato se llama Mochi.", ("remember", ("mi gato se llama Mochi",))),
    ("acuérdate de que mi cumple es el 3 de mayo", ("remember", ("mi cumple es el 3 de mayo",))),
    # Must go to Gemini (ambiguous, or not a simple command)
    ("me encanta Frieren, acuérdate de eso", None),  # the fact is before: Gemini writes it
    ("recuérdame mañana a las 8 que tengo cita", None),  # a clock time: set_reminder, Gemini's job
    ("Abre los sigres de notas en el recopo, y a ver, me lluta", None),  # once opened the notes
    ("abre la página web del banco", ("open_app", ("página web del banco",))),  # real open_app finds nothing -> Gemini
    ("Reproduce la canción que estoy escuchando ahora.", None),
    ("Reprodúceme una canción en YouTube.", None),  # vague: Gemini picks one
    ("modo avión", None),
    ("quita el silencio", None),
    ("¿quién va a ganar el mundial?", None),
    ("cuéntame un chiste", None),
    ("busca el archivo informe", None),
    ("busca en mis documentos el contrato", None),
    ("apaga el pc", ("shutdown_pc", ("shutdown",))),  # only asks for confirmation
    ("¡Reinicia la computadora!", ("shutdown_pc", ("restart",))),
    ("apaga la música", None),
]


def test_fast_path_table():
    for phrase, expected in FAST_PATH:
        res = fast(phrase)
        got = calls[0] if calls else None
        if expected is None:
            assert res is None and not calls, (phrase, calls)
        else:
            assert res is not None and got == expected, (phrase, got, expected)


def test_greeting_answers_locally():
    for phrase in ("hola", "Hola Miku", "buenos días"):
        res = fast(phrase)
        assert res and res[0] == "happy" and not calls, phrase


LIES = [
    "¡Anotado! Ya lo guardé en tus notas.",
    "Listo, ya abrí Spotify.",
    "Te bajé el volumen.",
    "¡Creé el archivo en tu escritorio!",
    "Ya copié el texto.",
    "Puse el volumen al 30.",
    "¡Entendido! Voy a apagar el equipo ahora mismo.",
    "¡Hecho! Te avisaré en diez minutos.",
    "¡Listo!",
    "Ya no se me olvida que te encanta Frieren.",
]
NOT_LIES = [
    "¡Hola! ¿Qué tal tu día?",
    "¿Quieres que lo guarde en tus notas?",
    "Puedo abrirlo si quieres.",
    "Eso suena genial, ¡cuéntame más!",
    "Son las tres de la tarde.",
    "No sé quién ganará, ¡pero será emocionante!",
    "¿Listo para empezar?",
    "Voy a contarte un secreto.",
    "Ese es un gran pecho de valor.",
]


def test_claimed_action_detector():
    for text in LIES:
        assert CLAIMED_ACTION_RE.search(text), text
    for text in NOT_LIES:
        assert not CLAIMED_ACTION_RE.search(text), text


def test_screenshot_trigger():
    for text in ("qué ves en mi pantalla", "¿Qué ves?", "mira esto", "ayúdame con este error",
                 "qué hay en la pantalla", "lee lo que dice esta ventana"):
        assert SCREEN_RE.search(text), text
    for text in ("abre spotify", "cuéntame un chiste", "me mandaron un pantallazo", "ves la tele?", "qué hora es"):
        assert not SCREEN_RE.search(text), text


def test_answer_parsing():
    b = MikuBrain.__new__(MikuBrain)
    cases = [
        ("[happy] ¡Listo!", ("happy", "¡Listo!")),
        ("[sad] Uy, no pude.", ("sad", "Uy, no pude.")),
        ("[bailando] ¡Hola!", ("happy", "¡Hola!")),  # unknown emotion
        ("Sin etiqueta **negrita** https://x.com", ("happy", "Sin etiqueta negrita")),
    ]
    for raw, expected in cases:
        assert b._parse_emotion(raw) == expected, raw


def test_spoken_app_list():
    assert _spoken_app_list([]) == ""
    assert _spoken_app_list(["opera"]) == "Opera"
    assert _spoken_app_list(["opera", "Spotify", "opera"]) == "Opera y Spotify"
    assert _spoken_app_list(["Code", "explorer", "claude", "app", "pythonw", "ApplicationFrameHost"]) == \
        "Visual Studio Code, el Explorador de archivos y Claude", "Miku and hosts are not listed"


if __name__ == "__main__":
    test_fast_path_table()
    test_greeting_answers_locally()
    test_claimed_action_detector()
    test_screenshot_trigger()
    test_answer_parsing()
    test_spoken_app_list()
    print("ok")
