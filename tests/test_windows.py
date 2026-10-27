"""Windows by number, like Opera's tabs. Fake window list and fake user32: no real window is touched.

Run: core\\.venv\\Scripts\\python.exe -m tests.test_windows  (or with pytest)
"""

import core.tools.windows as win

REAL_APPLY = win._apply  # saved before setup() fakes it


def w(id, exe, title, monitor=1, **marks):
    return {"id": id, "exe": exe, "title": title, "monitor": monitor, "monitors": 2,
            "active": marks.get("active", False), "minimized": marks.get("minimized", False),
            "maximized": marks.get("maximized", False)}


WINDOWS = [
    w(10, "LeagueClient", "League of Legends (TM) Client", 2, active=True),
    w(11, "Code", "README.md - miku-assistant - Visual Studio Code", 1, maximized=True),
    w(12, "Discord", "Discord", 2, maximized=True),
    w(13, "explorer", "Descargas", 2, minimized=True),
    w(14, "app", "Miku Assistant", 1),  # Miku herself: never listed nor touched
]


class FakeUser32:
    def __init__(self):
        self.calls = []

    def ShowWindow(self, hwnd, cmd):
        self.calls.append(("show", hwnd, cmd))

    def PostMessageW(self, hwnd, msg, wp, lp):
        self.calls.append(("post", hwnd, msg))


def setup():
    applied = []
    win.visible_windows = lambda: [dict(x) for x in WINDOWS]
    win._apply = lambda action, window, monitor: applied.append((action, window["id"], monitor))
    return applied


def test_state_lists_windows_by_number():
    setup()
    text = win.describe_windows()
    assert "[10] LeagueClient — League of Legends (TM) Client — activa, monitor 2" in text
    assert "[11] Visual Studio Code — README.md - miku-assistant - Visual Studio Code — maximizada, monitor 1" in text
    assert "[12] Discord — maximizada, monitor 2" in text, "a title that is just the app name is not repeated"
    assert "[13] el Explorador de archivos — Descargas — minimizada" in text
    assert "Miku" not in text and "[14]" not in text


def test_actions_by_number():
    applied = setup()
    # "minimiza todo menos el juego": the model passes every other number
    assert win.windows("minimize", [11, 12, 13]) == {"ok": True, "result": "Minimicé 3 ventanas."}
    assert applied == [("minimize", 11, 0), ("minimize", 12, 0), ("minimize", 13, 0)]
    applied.clear()
    assert win.windows("move", [12], monitor=1)["result"] == "Moví Discord al monitor 1."
    assert win.windows("focus", [11, 12])["result"] == "Te puse delante Visual Studio Code.", "focus is one window"
    assert applied == [("move", 12, 1), ("focus", 11, 0)]
    applied.clear()
    # Bad calls do nothing: unknown numbers, Miku's own window, a missing monitor, an unknown action
    assert not win.windows("close", [12, 999])["ok"]
    assert not win.windows("close", [14])["ok"]
    assert not win.windows("close", [])["ok"]
    assert not win.windows("move", [12], monitor=3)["ok"]
    assert not win.windows("explode", [12])["ok"]
    assert applied == []


def test_minimize_never_takes_the_focus_and_close_is_the_x_button():
    fake = FakeUser32()
    win._user32 = lambda: fake
    REAL_APPLY("minimize", w(12, "Discord", "Discord"), 0)
    REAL_APPLY("close", w(13, "explorer", "Descargas"), 0)
    # SW_MINIMIZE (6) would activate the next window: maybe taking the focus from a game
    assert fake.calls == [("show", 12, win.SW_SHOWMINNOACTIVE), ("post", 13, win.WM_CLOSE)], fake.calls
    assert win.SW_SHOWMINNOACTIVE == 7


if __name__ == "__main__":
    test_state_lists_windows_by_number()
    test_actions_by_number()
    test_minimize_never_takes_the_focus_and_close_is_the_x_button()
    print("ok")
