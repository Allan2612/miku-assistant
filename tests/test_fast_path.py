"""H-023, H-024: the local fast path must only handle unambiguous commands (volume, media, notes, timers).

Tools are replaced by recorders, so nothing on the PC changes.
Run: core\\.venv\\Scripts\\python.exe -m tests.test_fast_path  (or with pytest)
"""

import core.tools.apps as apps
import core.tools.media as media
import core.tools.web as web
from core.llm import MikuBrain

calls = []


def _rec(name, ok=True):
    def f(*args, **kwargs):
        calls.append((name, args))
        return {"ok": ok, "result": f"{name} failed"}
    return f


def _setup():
    calls.clear()
    apps.close_app = _rec("close_app")
    apps.open_app = _rec("open_app")
    media.change_volume = _rec("change_volume")
    media.mute = _rec("mute")
    media.media_control = _rec("media_control")
    web.web_search = _rec("web_search")
    web.youtube_search = _rec("youtube_search")


def fast(text):
    return MikuBrain._try_fast_path_tool(None, text)


def test_closing_goes_to_gemini():
    # Closing needs to know what is open (apps, tabs): Gemini gets that in the PC state, regexes do not
    _setup()
    for phrase in ("apaga la música", "cierra la ventana", "cierra e", "quitar el silencio", "cierra spotify"):
        assert fast(phrase) is None, phrase
    assert not calls, calls


def test_no_hijacking():
    _setup()
    assert fast("recuérdame tomar agua a la hora de comer") is None
    assert fast("busca el archivo informe") is None
    fast("abre mi playlist favorita")
    assert not any(c[0] == "media_control" for c in calls), calls
    _setup()
    fast("pon la música")
    assert calls == [("media_control", ("play",))], calls


def test_reports_tool_failure():
    _setup()
    media.change_volume = _rec("change_volume", ok=False)
    emotion, text, _ = fast("sube el volumen")
    assert emotion == "sad" and "failed" in text, (emotion, text)


if __name__ == "__main__":
    test_closing_goes_to_gemini()
    test_no_hijacking()
    test_reports_tool_failure()
    print("ok")
