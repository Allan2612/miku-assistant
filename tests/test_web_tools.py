"""Web tools and Opera tabs through Miku's extension (core/browser.py). No browser, no network: the extension is
faked, so nothing opens or closes on the PC.

Run: core\\.venv\\Scripts\\python.exe -m tests.test_web_tools  (or with pytest)
"""

import asyncio
import json
import threading

import core.tools.web as web
from core.browser import BrowserBridge

TABS = [
    {"id": 11, "window_id": 1, "index": 0, "title": "GX Corner", "url": "opera://startpage", "pinned": True},
    {"id": 12, "window_id": 1, "index": 1, "title": "T y T Soluciones", "url": "https://tytsoluciones.net/", "active": True},
    {"id": 13, "window_id": 1, "index": 2, "title": "K/DA - MORE - YouTube", "url": "https://www.youtube.com/watch?v=x", "audible": True},
    {"id": 21, "window_id": 2, "index": 0, "title": "Discord", "url": "https://discord.com/app"},
]


def connected_bridge(reply=None):
    """A bridge whose extension answers every command with reply (default ok) and records it."""
    b = BrowserBridge()
    b._ws = object()
    b.update({"tabs": [dict(t) for t in TABS]})
    b.sent = []

    def run(cmd, **args):
        b.sent.append((cmd, args))
        res = reply or {"ok": True, "tab_id": args.get("tab_id") or 99}
        if res.get("ok") and res.get("tab_id"):
            b.last_opened_tab = res["tab_id"]
        return res
    b.run = run
    web.bridge = b
    return b


def setup(exists=True):
    opened = []
    web._open_in_browser = opened.append
    web._host_exists = lambda host: exists
    return opened


def test_without_the_extension_pages_still_open_but_tabs_cannot_be_handled():
    opened = setup()
    web.bridge = BrowserBridge()
    assert web.open_url("example.com")["ok"]
    assert web.web_search("miku")["ok"] and web.youtube_search("world is mine")["ok"]
    assert opened == [
        "https://example.com",
        "https://www.google.com/search?q=miku",
        "https://www.youtube.com/results?search_query=world+is+mine",
    ], opened
    res = web.browser_tabs("close", [12])
    assert not res["ok"] and "extensión" in res["result"]
    assert "no está conectada" in web.bridge.describe()


def test_pages_open_through_the_extension_new_tab_or_a_given_one():
    opened = setup()
    b = connected_bridge()
    assert web.open_url("https://www.tytsoluciones.net/servicios")["result"] == "Abrí tytsoluciones.net."
    web.web_search("recetas de pasta en Opera", tab_id=12)  # "en Opera" is where, not what
    assert b.sent == [
        ("open", {"url": "https://www.tytsoluciones.net/servicios", "tab_id": None}),
        ("open", {"url": "https://www.google.com/search?q=recetas+de+pasta", "tab_id": 12}),
    ], b.sent
    assert opened == [], "the extension opened them: no second copy through opera.exe"


def test_extension_failure_falls_back_to_opera_exe():
    opened = setup()
    connected_bridge(reply={"ok": False, "error": "No tab with id: 77."})
    web.open_url("example.com", tab_id=77)
    assert opened == ["https://example.com"], opened


def test_a_misheard_address_becomes_a_search():
    setup(exists=False)
    b = connected_bridge()
    res = web.open_url("tygtsoluciones.net")
    assert "No existe tygtsoluciones.net" in res["result"]
    assert b.sent[0][1]["url"] == "https://www.google.com/search?q=tygtsoluciones.net"


def test_youtube_play_reuses_the_tab_she_opened():
    setup()
    b = connected_bridge()
    web._first_youtube_video = lambda q: ("abcdefghijk", "K/DA - MORE ft. Madison Beer (Video oficial)")
    b.last_opened_tab = None
    assert web.youtube_play("more")["result"] == "Puse K/DA - MORE en YouTube."
    assert b.sent[-1] == ("open", {"url": "https://www.youtube.com/watch?v=abcdefghijk", "tab_id": None})
    b.last_opened_tab = 13  # the next song replaces hers instead of playing on top (user, 24-oct)
    web.youtube_play("firestarter")
    assert b.sent[-1][1]["tab_id"] == 13
    b.last_opened_tab = 12  # her last tab is not YouTube: a new tab, never over the user's page
    web.youtube_play("pop/stars")
    assert b.sent[-1][1]["tab_id"] is None


def test_browser_tabs_by_id():
    b = connected_bridge()
    # "cierra todas menos la de T y T": the model passes every other id, pinned ones too (GX Corner was skipped)
    res = web.browser_tabs("close", [11, 13, 21])
    assert res == {"ok": True, "result": "Cerré 3 pestañas."} and b.sent == [("close", {"tab_ids": [11, 13, 21]})]
    assert web.browser_tabs("activate", [21])["result"] == "Te puse en 'Discord'."
    assert b.sent[-1] == ("activate", {"tab_id": 21})
    b.sent.clear()
    assert not web.browser_tabs("close", [12, 404])["ok"], "an id not in the state is a model mistake"
    assert not web.browser_tabs("close", [])["ok"]
    assert not web.browser_tabs("minimize", [12])["ok"]
    assert b.sent == [], "nothing runs on a bad call"


def test_browser_tabs_reports_what_opera_said():
    connected_bridge(reply={"ok": False, "error": "Tabs cannot be edited right now."})
    res = web.browser_tabs("reload", [12])
    assert not res["ok"] and "Tabs cannot be edited" in res["result"]


def test_closing_trusts_the_tab_list_over_a_lost_reply():
    # Log 26-oct: 8 tabs closed, but the reply came after the 6 s wait and Miku said it failed
    web.CLOSE_CHECK_S = 0
    b = connected_bridge(reply={"ok": False, "error": "Opera no respondió (TimeoutError)."})
    b.update({"tabs": [t for t in TABS if t["id"] == 12]})  # the extension's next list: they are gone
    assert web.browser_tabs("close", [12, 13])["ok"] is False, "tab 12 is still open: it did fail"
    assert web.browser_tabs("close", [12])["ok"] is False
    b.update({"tabs": [dict(t) for t in TABS]})
    b.run = lambda cmd, **args: b.update({"tabs": [t for t in TABS if t["id"] == 12]}) or {"ok": False, "error": "x"}
    assert web.browser_tabs("close", [11, 13, 21]) == {"ok": True, "result": "Cerré 3 pestañas."}


def test_youtube_player_picks_the_video_and_reports_its_state():
    b = connected_bridge()
    b.update({"tabs": [dict(t) for t in TABS] + [
        {"id": 30, "window_id": 1, "index": 3, "title": "Otro video", "url": "https://www.youtube.com/watch?v=y"}]})
    state = {"volume": 80, "muted": False, "quality": "1080p", "rate": 1.5, "playing": True, "captions": True}
    b.run = lambda cmd, **args: b.sent.append((cmd, args)) or {"ok": True, "state": state}

    # No tab named: the one playing (13 suena), not the other video
    assert web.youtube_player("volume", "80")["result"] == "Volumen del video: 80%."
    assert b.sent[-1] == ("youtube", {"tab_id": 13, "action": "volume", "value": "80"})
    assert web.youtube_player("quality", "1080p")["result"] == "Calidad del video: 1080p."
    assert web.youtube_player("captions_on")["result"] == "Subtítulos activados."
    assert web.youtube_player("speed", "1.5", tab_id=30)["result"] == "Velocidad del video: 1.5x."
    assert b.sent[-1][1]["tab_id"] == 30, "a named tab wins"
    # Play that left the video paused is a failure, not "ya le di play" (log 27-oct)
    assert web.youtube_player("play")["ok"]
    state["playing"] = False
    res = web.youtube_player("play")
    assert not res["ok"] and "en pausa" in res["result"], res
    assert web.youtube_player("pause")["ok"]

    # What the page said goes back to the model ("ese video solo tiene: ...")
    b.run = lambda cmd, **args: {"ok": False, "error": "ese video solo tiene: 720p, 480p"}
    assert "720p, 480p" in web.youtube_player("quality", "1080p")["result"]
    # Bad calls: unknown action, a tab that is not a video, no YouTube at all
    assert not web.youtube_player("explode")["ok"]
    assert not web.youtube_player("pause", tab_id=12)["ok"]
    b.update({"tabs": [t for t in TABS if "youtube" not in t["url"]]})
    assert web.youtube_player("pause")["result"] == "No hay ningún video de YouTube abierto en Opera."


def test_open_website_says_where_it_went():
    setup()
    b = connected_bridge()
    web._first_web_result = lambda name: "https://www.tytsolutions.com/"
    assert web.open_website("tyt soluciones")["result"] == "Abrí tytsolutions.com."
    web._first_web_result = lambda name: None
    assert "búsqueda en Google" in web.open_website("algo raro")["result"]
    assert b.sent[-1][1]["url"] == "https://www.google.com/search?q=algo+raro"


def test_describe_lists_tabs_by_window_with_their_ids_and_the_visible_results():
    b = BrowserBridge()
    b._ws = object()
    b.update({"tabs": TABS, "results": {"tab_id": 12, "items": [
        {"title": "T y T Soluciones", "url": "https://tytsoluciones.net/"},
        {"title": "TyT Solutions", "url": "https://tytsolutions.com/"},
    ]}})
    b.last_opened_tab = 13
    text = b.describe()
    assert " Ventana 1:" in text and " Ventana 2:" in text
    assert "[11] GX Corner (startpage) — fijada" in text
    assert "[12] T y T Soluciones (tytsoluciones.net) — activa" in text
    assert "[13] K/DA - MORE - YouTube (www.youtube.com) — suena, abierta por Miku" in text
    assert "  2. TyT Solutions — https://tytsolutions.com/" in text
    b.update({"tabs": []})
    assert b.describe() == "Opera: sin pestañas abiertas."


def test_command_round_trip_from_a_tool_thread():
    # Tools run in threads; the socket lives on the server's loop: run() must cross over and wait for the answer
    b = BrowserBridge()
    loop = asyncio.new_event_loop()
    threading.Thread(target=loop.run_forever, daemon=True).start()

    class FakeExtension:
        async def send(self, raw):
            msg = json.loads(raw)
            b.resolve({"id": msg["id"], "ok": True, "tab_id": 55, "echo": msg["cmd"]})

    b._ws, b._loop = FakeExtension(), loop
    res = b.run("open", url="https://example.com", tab_id=None)
    assert res["ok"] and res["echo"] == "open" and b.last_opened_tab == 55, res
    b.detach(b._ws)
    assert not b.run("close", tab_ids=[1])["ok"]
    loop.call_soon_threadsafe(loop.stop)


if __name__ == "__main__":
    test_without_the_extension_pages_still_open_but_tabs_cannot_be_handled()
    test_pages_open_through_the_extension_new_tab_or_a_given_one()
    test_extension_failure_falls_back_to_opera_exe()
    test_a_misheard_address_becomes_a_search()
    test_youtube_play_reuses_the_tab_she_opened()
    test_browser_tabs_by_id()
    test_browser_tabs_reports_what_opera_said()
    test_closing_trusts_the_tab_list_over_a_lost_reply()
    test_youtube_player_picks_the_video_and_reports_its_state()
    test_open_website_says_where_it_went()
    test_describe_lists_tabs_by_window_with_their_ids_and_the_visible_results()
    test_command_round_trip_from_a_tool_thread()
    print("ok")
