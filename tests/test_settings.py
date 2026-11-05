"""The panel's settings: config.yaml edited value by value (its comments stay), secrets never read back in full,
bad values refused, and a tool turned off in the panel refuses to run.

Works on copies: the real config.yaml and .env are never touched.
Run: core\\.venv\\Scripts\\python.exe -m tests.test_settings  (or with pytest)
"""

import shutil
import tempfile
from pathlib import Path

import core.settings as settings
import core.tools as tools


def test_settings_keep_comments_and_check_values():
    tmp = Path(tempfile.mkdtemp())
    settings.CONFIG = tmp / "config.yaml"
    settings.ENV = tmp / ".env"
    shutil.copy(Path(__file__).resolve().parents[1] / "config.yaml", settings.CONFIG)
    settings.ENV.write_text("GEMINI_API_KEY=AIzaSyABCDEFGH1234\n", encoding="utf-8")
    before = settings.CONFIG.read_text(encoding="utf-8")

    got = settings.get()
    assert got["gemini"]["has_key"] and got["gemini"]["hint"] == "1234" and "AIza" not in str(got), "no full secret"

    assert settings.set_({"model": "gemini-3.1-flash-lite", "threshold": 0.4, "rvc_enabled": False,
                          "weather_city": "Pérez Zeledón, Costa Rica", "vocabulary": ["Miku", "K/DA"],
                          "disabled_tools": ["lock_pc"], "obs_password": "secreto"}) == {"ok": True}
    got = settings.get()
    assert (got["gemini"]["model"], got["threshold"], got["rvc_enabled"], got["weather_city"], got["vocabulary"],
            got["disabled_tools"]) == ("gemini-3.1-flash-lite", 0.4, False, "Pérez Zeledón, Costa Rica", ["Miku", "K/DA"],
                                       ["lock_pc"])
    after = settings.CONFIG.read_text(encoding="utf-8")
    assert [l for l in before.splitlines() if "#" in l and l.split("#", 1)[1] not in after] == [], "comments stay"
    assert settings.CONFIG.with_suffix(".yaml.bak").read_text(encoding="utf-8") == before, "the old file is kept"
    assert "OBS_PASSWORD=secreto" in settings.ENV.read_text(encoding="utf-8")

    # The hotkey (top-level key) and the microphone (a section the file did not have before 3-nov)
    assert settings.set_({"hotkey": "Ctrl+Shift+K", "input_device": "Micrófono (Logitech G733 Gaming"}) == {"ok": True}
    got = settings.get()
    assert (got["hotkey"], got["input_device"]) == ("Ctrl+Shift+K", "Micrófono (Logitech G733 Gaming"), got
    # Miku's screen and the text box in her window (keys the window section did not have before 3-nov)
    assert settings.get()["window_over_fullscreen"] is True, "on unless turned off"
    assert settings.set_({"window_over_fullscreen": False}) == {"ok": True}
    assert settings.get()["window_over_fullscreen"] is False
    assert settings.set_({"monitor": 2, "window_chat": True}) == {"ok": True}
    got = settings.get()
    assert (got["monitor"], got["window_chat"]) == (2, True), got
    after = settings.CONFIG.read_text(encoding="utf-8")

    # Bad values never reach the file
    for bad in ({"threshold": 5}, {"model": "gpt"}, {"weather_city": ""}, {"vocabulary": ["a\nb"]},
                {"hotkey": "M"}, {"hotkey": "Ctrl+Alt+Esc"}, {"monitor": -1}, {"monitor": True}, {"window_chat": "sí"}):
        assert not settings.set_(bad)["ok"], bad
    assert settings.CONFIG.read_text(encoding="utf-8") == after


def test_disabled_tool_refuses():
    tools.DISABLED.add("lock_pc")
    try:
        res = tools.get_tool_metadata("lock_pc")["function"]()
        assert not res["ok"] and "desactivada" in res["result"], res
        assert all(f.__name__ != "lock_pc" for f in tools.get_registered_tools()), "Gemini does not see it"
    finally:
        tools.DISABLED.discard("lock_pc")


if __name__ == "__main__":
    test_settings_keep_comments_and_check_values()
    test_disabled_tool_refuses()
    print("ok")
