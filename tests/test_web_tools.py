"""open_url / web_search / youtube_search open the browser (8dbb6f8 had deleted their helper: NameError on every call).

Run: core\\.venv\\Scripts\\python.exe -m tests.test_web_tools  (or with pytest)
"""

import core.tools.web as web


def test_web_tools_open_browser():
    opened = []
    # Mock below the helper so the real _open_in_browser runs
    web._find_opera_gx = lambda: None
    web.os.startfile = opened.append
    assert web.open_url("example.com")["ok"]
    assert web.web_search("miku")["ok"]
    assert web.youtube_search("world is mine")["ok"]
    assert opened == [
        "https://example.com",
        "https://www.google.com/search?q=miku",
        "https://www.youtube.com/results?search_query=world+is+mine",
    ], opened




def test_youtube_play_reuses_her_tab_and_never_types_elsewhere():
    # A second song used to open a second tab while the first kept playing (user, 24-oct)
    import types as _t
    import core.tools.apps as apps
    keys, opened = [], []
    fg = [42]
    web._first_youtube_video = lambda q: ("abcdefghijk", "K/DA - MORE (Video oficial)")
    web._open_in_browser = opened.append
    web.ctypes = _t.SimpleNamespace(windll=_t.SimpleNamespace(user32=_t.SimpleNamespace(GetForegroundWindow=lambda: fg[0])))
    apps._find_window = lambda name, exe=None: 42 if (name, exe) == ("youtube", "opera") else None
    apps._bring_to_front = lambda hwnd: fg[0] == hwnd
    apps._press = lambda *vks: keys.append(vks)
    apps._type_into_foreground = lambda text: keys.append(text)
    url = "https://www.youtube.com/watch?v=abcdefghijk"

    web._last_youtube_open = float("-inf")  # she never opened one: a new tab, no keys
    assert web.youtube_play("more")["result"] == "¡Poniendo K/DA - MORE en YouTube!"
    assert opened == [url] and keys == []

    opened.clear()  # she did: same tab, Ctrl+L, URL, Delete (autocomplete), Enter
    web.youtube_play("firestarter")
    assert opened == [] and keys == [(0x11, ord("L")), url, (0x2E,), (0x0D,)], keys

    keys.clear()  # another app keeps the focus: no typing at all, new tab instead
    fg[0] = 7
    web.youtube_play("pop/stars")
    assert keys == [] and opened == [url]

if __name__ == "__main__":
    test_web_tools_open_browser()
    test_youtube_play_reuses_her_tab_and_never_types_elsewhere()
    print("ok")
