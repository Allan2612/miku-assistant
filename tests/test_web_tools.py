"""open_url / web_search / youtube_search open the browser (8dbb6f8 had deleted their helper: NameError on every call).

Run: core\\.venv\\Scripts\\python.exe -m tests.test_web_tools  (or with pytest)
"""

import core.tools.web as web


def test_web_tools_open_browser():
    opened = []
    # Mock below the helper so the real _open_in_browser runs
    web._find_opera_gx = lambda: None
    web.os.startfile = opened.append
    web._host_exists = lambda host: True  # no network in tests
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

def test_browser_action_only_types_into_a_focused_opera():
    import types as _t
    import core.tools.apps as apps
    keys = []
    fg = [42]
    titles = {42: "Inicio - Opera"}
    web.ctypes = _t.SimpleNamespace(windll=_t.SimpleNamespace(user32=_t.SimpleNamespace(GetForegroundWindow=lambda: fg[0])))
    web._is_opera = lambda hwnd: hwnd == 42
    web._opera_windows = lambda: [42]
    web._window_title = lambda hwnd: titles[hwnd]
    apps._find_window = lambda name, exe=None: 42 if exe == "opera" and name.lower() in titles[42].lower() else None
    apps._bring_to_front = lambda hwnd: fg[0] == hwnd
    apps._press = lambda *vks: keys.append(vks)
    apps._type_into_foreground = lambda text: keys.append(text)

    assert web.browser_action("close_tab")["ok"] and keys == [(0x11, ord("W"))]
    keys.clear()
    web.browser_action("new_tab", "wikipedia.org")
    assert keys == [(0x11, ord("T")), (0x11, ord("L")), "https://wikipedia.org", (0x2E,), (0x0D,)], keys
    keys.clear()
    web.browser_action("new_tab", "recetas de pasta")
    assert keys[2] == "https://www.google.com/search?q=recetas+de+pasta", keys

    # Ctrl+Tab until the title matches; a full lap without it: not found, and nothing is closed
    order = iter(["Inicio - Opera", "Discord - Opera", "YouTube - Opera"])
    def next_title(*vks):
        keys.append(vks)
        titles[42] = next(order, "Inicio - Opera")
    apps._press = next_title
    titles[42] = "Mail - Opera"
    keys.clear()
    res = web.browser_action("close_tab", "youtube")
    assert res["ok"] and keys[-1] == (0x11, ord("W")) and keys.count((0x11, 0x22)) == 3, keys
    keys.clear()
    titles[42] = "Inicio - Opera"
    order = iter(["Discord - Opera", "Inicio - Opera"])
    assert not web.browser_action("close_tab", "twitch")["ok"] and (0x11, ord("W")) not in keys

    # Another app has the focus and Opera cannot be brought up: no key at all
    apps._press = lambda *vks: keys.append(vks)
    keys.clear()
    fg[0] = 7
    assert not web.browser_action("close_window")["ok"] and keys == []
    assert not web.browser_action("fly")["ok"]


def test_open_url_checks_the_address_and_can_replace_the_last_page():
    import types as _t
    opened, navigated = [], []
    web._open_in_browser = opened.append
    web.threading = _t.SimpleNamespace(Thread=lambda **kw: _t.SimpleNamespace(start=lambda: None))
    # Spoken without "https://www." (the voice dropped the whole URL before)
    web._host_exists = lambda host: True
    assert web.open_url("https://www.tytsoluciones.net")["result"] == "He abierto tytsoluciones.net."
    # A misspelled dictation does not exist: Google with that name, which usually suggests the right one
    web._host_exists = lambda host: False
    res = web.open_url("tygtsoluciones.net")
    assert "No encontré tygtsoluciones.net" in res["result"] and opened[-1].endswith("q=tygtsoluciones.net"), opened
    # DNS did not answer in time: open it anyway
    web._host_exists = lambda host: None
    web.open_url("tytsoluciones.net")
    assert opened[-1] == "https://tytsoluciones.net"
    # "No, era X": the same tab, if she opened a page there a moment ago
    web._host_exists = lambda host: True
    web.ctypes = _t.SimpleNamespace(windll=_t.SimpleNamespace(user32=_t.SimpleNamespace(IsWindow=lambda h: True)))
    web._navigate_in = lambda hwnd, url: navigated.append((hwnd, url)) or True
    web._last_page.update(time=web.time.monotonic(), hwnd=55)
    opened.clear()
    web.open_url("tytsoluciones.net", replace=True)
    assert navigated == [(55, "https://tytsoluciones.net")] and opened == [], (navigated, opened)
    web.open_url("wikipedia.org")  # no replace: a new tab
    assert opened == ["https://wikipedia.org"]
    # "busca X en Opera": "en Opera" is where, not what
    assert web.web_search("recetas de pasta en Opera")["result"] == "He buscado 'recetas de pasta' en Google."


def test_close_other_tabs_keeps_one():
    import types as _t
    import core.tools.apps as apps
    tabs = ["GX Corner - Opera", "YouTube - Opera", "Mail - Opera", "Docs - Opera", "News - Opera"]
    pinned = {"GX Corner - Opera"}  # Opera GX pins it: Ctrl+W does nothing there (78 phantom closes, live)
    state = {"i": 0}
    keys = []
    web.ctypes = _t.SimpleNamespace(windll=_t.SimpleNamespace(user32=_t.SimpleNamespace(GetForegroundWindow=lambda: 42)))
    web._is_opera = lambda hwnd: True
    web._window_title = lambda hwnd: tabs[state["i"]]
    apps._find_window = lambda name, exe=None: 42 if exe == "opera" and name.lower() in tabs[state["i"]].lower() else None
    apps._bring_to_front = lambda hwnd: True
    web._opera_windows = lambda: [42]

    def press(*vks):
        keys.append(vks)
        if vks == (0x11, 0x22):
            state["i"] = (state["i"] + 1) % len(tabs)
        elif vks == (0x11, ord("W")) and tabs[state["i"]] not in pinned:  # the right tab takes over, or the left at the end
            tabs.pop(state["i"])
            state["i"] = min(state["i"], len(tabs) - 1)
    apps._press = press
    state["i"] = 3  # the user is on "Docs"; "todas menos la de YouTube"
    res = web.browser_action("close_other_tabs", "youtube")
    assert tabs == ["GX Corner - Opera", "YouTube - Opera"] and res["ok"] and "Cerré 3 pestañas" in res["result"], (tabs, res)


def test_close_window_tab_by_tab_and_never_beyond_it():
    # Ctrl+Shift+W made Opera ask "Confirmar el cierre" (live): close the tabs one by one instead
    import types as _t
    import core.tools.apps as apps
    state = {"tabs": 3, "fg": 42}
    alive = lambda h: h == 42 and state["tabs"] > 0
    web.ctypes = _t.SimpleNamespace(windll=_t.SimpleNamespace(user32=_t.SimpleNamespace(
        GetForegroundWindow=lambda: state["fg"], IsWindow=alive, IsWindowVisible=alive,
        PostMessageW=lambda h, msg, w, l: state.update(tabs=0, fg=99))))
    web._window_title = lambda h: f"tab {state['tabs']}"
    web._is_opera = lambda hwnd: True
    web._opera_windows = lambda: [42]
    apps._find_window = lambda name, exe=None: 42
    apps._bring_to_front = lambda hwnd: True
    closes = []

    def press(*vks):
        closes.append(vks)
        state["tabs"] -= 1
        if state["tabs"] == 0:
            state["fg"] = 99  # the window is gone: another one comes to the front
    apps._press = press
    assert web.browser_action("close_window")["ok"] and closes == [(0x11, ord("W"))] * 3, closes
    assert len(closes) == 3, "no Ctrl+W reaches the window that came to the front afterwards"

    state.update(tabs=5, fg=42)  # the focus goes elsewhere midway: stop, do not keep pressing
    closes.clear()
    def press_then_lose_focus(*vks):
        press(*vks)
        state["fg"] = 7
    apps._press = press_then_lose_focus
    assert not web.browser_action("close_all_tabs")["ok"] and len(closes) == 1

    # Only a pinned tab left (Ctrl+W ignored): WM_CLOSE the window instead of pressing forever
    state.update(tabs=2, fg=42)
    closes.clear()
    def press_pinned(*vks):
        closes.append(vks)
        if state["tabs"] > 1:
            state["tabs"] -= 1
    apps._press = press_pinned
    assert web.browser_action("close_window")["ok"] and len(closes) == 2 and state["tabs"] == 0, (closes, state)


def test_close_other_tabs_also_closes_other_windows():
    import types as _t
    import core.tools.apps as apps
    shut = []
    web.ctypes = _t.SimpleNamespace(windll=_t.SimpleNamespace(user32=_t.SimpleNamespace(GetForegroundWindow=lambda: 42)))
    web._is_opera = lambda hwnd: True
    web._opera_windows = lambda: [42, 77, 88]
    web._find_tab = lambda name, first: 42
    web._close_other_tabs = lambda hwnd: 2
    web._close_window_tabs = lambda hwnd: shut.append(hwnd) or True
    apps._find_window = lambda name, exe=None: 42
    apps._bring_to_front = lambda hwnd: True
    res = web.browser_action("close_other_tabs", "paranoia")
    assert shut == [77, 88] and "2 ventanas más" in res["result"], (shut, res)


def test_open_website_says_where_it_went():
    opened = []
    web._open_page = lambda url, replace: opened.append((url, replace))
    web._first_web_result = lambda name: "https://www.bancobcr.com/"
    assert web.open_website("banco de costa rica")["result"] == "Abrí bancobcr.com."
    web._first_web_result = lambda name: None
    assert "búsqueda en Google" in web.open_website("algo raro", replace=True)["result"] and opened[-1][1] is True


def test_tab_search_is_loose_but_not_blind():
    # Log 06:15: "t-soluciones", "tytsoluciones" and "T y T" all missed the tab; a clear match only
    from core.tools.web import _closeness, _norm_title, MIN_TAB_CLOSENESS
    def best(q, titles):
        return max((_closeness(_norm_title(q), _norm_title(t)), t) for t in titles)
    titles = ["TyT Soluciones | Inicio - Opera", "T&T Tecnología - Buscar con Google - Opera", "Disney+ | Iniciar sesión - Opera"]
    for q, expected in (("t-soluciones", 0), ("tytsoluciones", 0), ("T y T tecnología", 1), ("disney plus", 2)):
        score, title = best(q, titles)
        assert title == titles[expected] and score >= MIN_TAB_CLOSENESS, (q, title, score)
    assert best("twitch", titles)[0] < MIN_TAB_CLOSENESS


if __name__ == "__main__":
    test_web_tools_open_browser()
    test_youtube_play_reuses_her_tab_and_never_types_elsewhere()
    test_browser_action_only_types_into_a_focused_opera()
    test_open_url_checks_the_address_and_can_replace_the_last_page()
    test_close_other_tabs_keeps_one()
    test_close_window_tab_by_tab_and_never_beyond_it()
    test_close_other_tabs_also_closes_other_windows()
    test_open_website_says_where_it_went()
    test_tab_search_is_loose_but_not_blind()
    print("ok")
