"""Tables of real phrases for every text rule: fast path, lie detector, screenshot trigger, answer parsing, app names.

Tools are replaced by recorders, so nothing on the PC changes.
Run: core\\.venv\\Scripts\\python.exe -m tests.test_language  (or with pytest)
"""

import os

os.environ.setdefault("GEMINI_API_KEY", "test")

import core.tools.apps as apps
import core.tools.downloads as downloads
import core.tools.media as media
import core.tools.memory as memory
import core.tools.notes as notes
import core.tools.obs as obs
import core.tools.routines as routines
import core.tools.system as system
import core.tools.timers as timers
import core.tools.weather as weather
import core.tools.web as web
from core.intent import asks_about_screen, points_at_screen
from core.llm import CLAIMED_ACTION_RE, MikuBrain
from core.tools.apps import _spoken_app_list

calls = []
OBS_OPEN = [True]


def _rec(name):
    def f(*args, **kwargs):
        calls.append((name, args or tuple(kwargs.values())))
        return {"ok": True, "result": ""}
    return f


def fast(text):
    calls.clear()
    for mod, name in [(apps, "open_app"), (apps, "close_app"), (apps, "show_desktop"), (media, "change_volume"),
                      (media, "mute"), (media, "media_control"), (media, "set_volume"), (web, "web_search"), (web, "youtube_search"), (web, "youtube_play"), (web, "browser_tabs"), (web, "open_website"),
                      (web, "open_url"), (web, "youtube_player"), (system, "lock_pc"), (notes, "take_note"), (notes, "open_notes"), (timers, "set_timer"), (timers, "list_timers"), (memory, "remember"), (system, "shutdown_pc"),
                      (notes, "my_day"), (system, "quota_status"), (obs, "obs"), (weather, "weather"),
                      (downloads, "watch_downloads")]:
        setattr(mod, name, _rec(name))
    obs.obs_open = lambda: OBS_OPEN[0]
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
    ("Baja el volumen.", ("change_volume", (-15,))),
    ("sube el volumen", ("change_volume", (15,))),
    ("silencio", ("mute", (True,))),
    ("pausa", ("media_control", ("pause",))),
    ("¡Modo trabajo!", ("routine_step", ())),
    ("activa el modo trabajo", ("routine_step", ())),
    ("muestra el escritorio", ("show_desktop", ())),
    ("minimiza todas las ventanas", ("show_desktop", ())),
    ("Pausa la música.", ("media_control", ("pause",))),  # the three from the log
    ("Ponle pausa la canción.", ("media_control", ("pause",))),
    ("¡Pom pausa!", ("media_control", ("pause",))),
    ("dale play a la canción", ("media_control", ("play",))),
    ("pon la música", ("media_control", ("play",))),
    ("silencia el pc", ("mute", (True,))),
    # Real Whisper transcriptions from the user's log
    ("¡Bajá el volumen!", ("change_volume", (-15,))),
    ("Subele el volumen a 100%.", ("set_volume", (100,))),  # log 05:13: used to add 15
    ("pon el volumen al 30", ("set_volume", (30,))),
    ("volumen al 50 por ciento", ("set_volume", (50,))),
    ("súbelo al máximo", ("set_volume", (100,))),
    ("sube el volumen a tope", ("set_volume", (100,))),
    ("baja el volumen al mínimo", ("set_volume", (0,))),
    ("¡Listo, volumen al máximo!", ("set_volume", (100,))),  # what Gemini claimed: repaired locally
    ("bájale el volumen", ("change_volume", (-15,))),
    ("Subile al volumen", None),  # "al volumen" is not the pattern: Gemini decides
    # The video's own volume (youtube_player), not Windows' (27-oct); local since 3-nov
    ("sube el volumen del video", ("youtube_player", ("volume_up", ""))),
    ("súbele el volumen a YouTube", ("youtube_player", ("volume_up", ""))),
    ("bájale el volumen al reproductor", ("youtube_player", ("volume_down", ""))),
    ("silencia el video", ("youtube_player", ("mute", ""))),
    ("Quita el silencio del video.", ("youtube_player", ("unmute", ""))),
    ("Pon el volumen del video al 50.", ("youtube_player", ("volume", "50"))),
    ("Siguiente video.", ("youtube_player", ("next", ""))),
    ("Adelanta 30 segundos.", ("youtube_player", ("forward", "30"))),
    ("Regresa diez segundos.", ("youtube_player", ("back", "10"))),
    ("Adelanta el video.", ("youtube_player", ("forward", ""))),
    ("Regresa.", None),  # not about the video
    ("Pon subtítulos.", ("youtube_player", ("captions_on", ""))),
    ("Quita los subtítulos.", ("youtube_player", ("captions_off", ""))),
    ("Ponlo en 1080.", ("youtube_player", ("quality", "1080p"))),
    ("Máxima calidad.", ("youtube_player", ("quality", "max"))),
    ("Ponlo en mínima calidad.", ("youtube_player", ("quality", "min"))),
    ("Velocidad 1,5.", ("youtube_player", ("speed", "1.5"))),
    ("Velocidad normal.", ("youtube_player", ("speed", "1"))),
    ("Ponlo en bucle.", ("youtube_player", ("loop", ""))),
    ("Repite.", None),  # "say it again", not the video
    # Songs, sound, lock, reminders (3-nov)
    ("Siguiente canción.", ("media_control", ("next",))),
    ("Pasa a la siguiente.", ("media_control", ("next",))),
    ("Salta esta canción.", ("media_control", ("next",))),
    ("Pon la anterior.", ("media_control", ("previous",))),
    ("Canción anterior.", ("media_control", ("previous",))),
    ("Activa el sonido.", ("mute", (False,))),
    ("Bloquea el PC.", ("lock_pc", ())),
    ("¿Qué recordatorios tengo?", ("list_timers", ())),
    ("¿Cuáles son mis recordatorios?", ("list_timers", ())),
    ("¿Qué canción es la siguiente en la lista?", None),
    # My day, quota, OBS, weather, downloads (3-nov)
    ("¿Qué tengo hoy?", ("my_day", ())),
    ("¿Qué tengo que hacer hoy?", ("my_day", ())),
    ("¿Cómo está mi día?", ("my_day", ())),
    ("¿Cuánta cuota me queda?", ("quota_status", ())),
    ("¿Cuántas peticiones llevas hoy?", ("quota_status", ())),
    ("Cuanta capacidad tengo hoy.", ("quota_status", ())),  # log 3-nov: went to Gemini
    ("Guarda eso.", ("obs", ("clip", ""))),
    ("¡Clip!", ("obs", ("clip", ""))),
    ("Miku, clipé eso.", ("obs", ("clip", ""))),
    ("Empieza a grabar.", ("obs", ("record_start", ""))),
    ("Deja de grabar.", ("obs", ("record_stop", ""))),
    ("Para la grabación.", ("obs", ("record_stop", ""))),
    ("Cambia a la escena de pantalla de espera.", ("obs", ("scene", "pantalla de espera"))),
    ("¿Cómo está el clima?", ("weather", ("hoy",))),
    ("¿Va a llover mañana?", ("weather", ("mañana",))),
    ("¿Qué temperatura hace?", ("weather", ("hoy",))),
    ("¿Va a llover en Tokio?", None),  # another city: Gemini
    ("Avísame cuando termine la descarga.", ("watch_downloads", ())),
    ("Avísame cuando terminen las descargas.", ("watch_downloads", ())),
    ("súbele el volumen", ("change_volume", (15,))),
    ("Recuérdame en 10 minutos que saque la ropa de lavadora.", ("set_timer", (10.0, "Recordatorio: saque la ropa de lavadora"))),
    ("avísame en media hora", ("set_timer", (30.0, "Temporizador"))),
    ("pon un temporizador de cinco minutos para el té", ("set_timer", (5.0, "el té"))),  # a timer, not a reminder
    ("Recuérdame en un minuto tomar agua.", ("set_timer", (1.0, "Recordatorio: tomar agua"))),  # log 26-oct: no "que"
    ("Hey Miku, recuérdame en una hora que llame a mamá", ("set_timer", (60.0, "Recordatorio: llame a mamá"))),
    ("Recuerda que mi gato se llama Mochi.", ("remember", ("mi gato se llama Mochi",))),
    ("acuérdate de que mi cumple es el 3 de mayo", ("remember", ("mi cumple es el 3 de mayo",))),
    ("Pestaña nueva", None),  # no verb: Gemini
    # Apps, web pages, searches, YouTube and tabs go to Gemini: it sees the PC state (open apps, tabs with ids,
    # visible results) and picks the right tool and target; regexes guessed wrong too often (logs, 24-oct)
    ('¡Abre mi ópera!', None),
    ('abre el navegador', None),
    ('ópera', None),
    ('abre youtube', None),
    ('busca recetas de pasta', None),
    ('busca en youtube world is mine', None),
    ('Busca en Google recetas de arroz con leche.', None),
    ('Hey Miku, busca el clima de mañana', None),
    ('Hey Miku, abre mi ópera.', None),
    ('Ábreme Opera.', None),
    ('¡Abreme el blog de notas!', None),
    ('Ponme more en YouTube.', None),
    ('Pon la canción more, reprodúcela por mí.', None),
    ('reproduce el video de los tigres del norte', None),
    ('Reprodúceme world is mine en youtube', None),
    ('Oye Miku, cierra spotify', None),
    ('Cierra esta pestaña.', None),
    ('cierra la pestaña de youtube', None),
    ('abre una nueva pestaña con wikipedia.org', None),
    ('ve a la pestaña de discord', None),
    ('Recarga la página.', None),
    ('vuelve atrás', None),
    ('cierra la ventana de opera', None),
    ('Cierra todas las pestañas.', None),
    ('cierra todas las pestañas de opera excepto la de youtube', None),
    ('Cierra todas las pestañas menos la de YouTube', None),
    ('cierra las demás pestañas', None),
    ('Busca ttsoluciones.net en Opera', None),
    ('abre tytsoluciones.net', None),
    ('No, era tytsoluciones.net', None),
    ('Abre la página del Banco de Costa Rica', None),
    ('entra a la página web de steam', None),
    ('Busca recetas de pasta en Opera', None),
    ('abre la página web del banco', None),
    # Must go to Gemini (ambiguous, or not a simple command)
    ("cierra la ventana", None),  # which window? (H-023)
    ("me encanta Frieren, acuérdate de eso", None),  # the fact is before: Gemini writes it
    ("abre spotify y sube el volumen", None),  # two orders: the volume rule alone dropped the first
    ("pon el volumen al 30, luego abre discord", None),
    ("Abre mi ópera y pon YouTube con la canción More.", None),
    ("recuérdame mañana a las 8 que tengo cita", None),  # a clock time: remind(at=...), Gemini's job
    ("Abre los sigres de notas en el recopo, y a ver, me lluta", None),  # once opened the notes
    ("Reproduce la canción que estoy escuchando ahora.", None),
    ("Reprodúceme una canción en YouTube.", None),  # vague: Gemini picks one
    ("modo avión", None),
    ("quita el silencio", ("mute", (False,))),
    ("¿quién va a ganar el mundial?", None),
    ("cuéntame un chiste", None),
    ("busca el archivo informe", None),
    ("busca en mis documentos el contrato", None),
    ("apaga el pc", ("shutdown_pc", ("shutdown",))),  # only asks for confirmation
    ("¡Reinicia la computadora!", ("shutdown_pc", ("restart",))),
    ("apaga la música", None),
]


def test_obs_phrases_need_obs_open():
    OBS_OPEN[0] = False
    try:
        assert fast("Guarda eso.") is None and not calls, "without OBS, 'guarda eso' is Gemini's"
    finally:
        OBS_OPEN[0] = True


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
    "¡Yatta! Reproduciendo More en YouTube para ti.",
    "Cierro las pestañas en este momento.",
    "¡Hecho! Te avisaré en diez minutos.",
    "¡Listo!",
    "Ya no se me olvida que te encanta Frieren.",
    "¡Voy a buscar quién es la abuela Sopita!",  # log 27-oct: no web_search followed
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
        assert asks_about_screen(text), text
    for text in ("abre spotify", "cuéntame un chiste", "me mandaron un pantallazo", "ves la tele?", "qué hora es"):
        assert not asks_about_screen(text), text


def test_position_references():
    # Log 06:13: "ármeme la segunda opción" repeated the search: she could not see the results
    for text in ("Muy bien, ábreme la segunda opción.", "abre el primer resultado", "dale a ese enlace", "la tercera opción"):
        assert points_at_screen(text), text
    for text in ("primero abre spotify", "esta es mi opinión", "segundo plano"):
        assert not points_at_screen(text), text


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
    test_obs_phrases_need_obs_open()
    test_greeting_answers_locally()
    test_claimed_action_detector()
    test_screenshot_trigger()
    test_position_references()
    test_answer_parsing()
    test_spoken_app_list()
    print("ok")
