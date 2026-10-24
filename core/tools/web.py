"""
Miku Assistant - Web and Search Tools (tools/web.py)
"""

import ctypes
import difflib
import json
import logging
import os
import re
import socket
import subprocess
import threading
import time
import unicodedata
import urllib.parse
import urllib.request
import webbrowser
from typing import Any, Dict, List, Optional, Tuple

from core.tools import tool
from core.tools._win import find_opera_gx as _find_opera_gx

logger = logging.getLogger("miku.tools.web")


def _open_in_browser(target_url: str) -> None:
    opera_exe = _find_opera_gx()
    if opera_exe:
        try:
            logger.info("Opening URL in Opera GX: %s", target_url)
            subprocess.Popen([opera_exe, target_url])
            return
        except Exception as e:
            logger.warning("Failed to launch Opera GX with URL %s: %s", target_url, e)

    try:
        os.startfile(target_url)
    except Exception:
        webbrowser.open(target_url)


DNS_CHECK_S = 2.0


def _host_exists(host: str) -> Optional[bool]:
    """True/False from DNS, None if it did not answer in DNS_CHECK_S (on this network some lookups hang ~10 s,
    which tripped the tool timeout): unknown means open it anyway."""
    box: Dict[str, Any] = {}

    def lookup() -> None:
        try:
            socket.getaddrinfo(host, 443)
            box["ok"] = True
        except (socket.gaierror, UnicodeError):
            box["ok"] = False
        except OSError:
            pass

    t = threading.Thread(target=lookup, daemon=True, name="miku-dns")
    t.start()
    t.join(DNS_CHECK_S)
    return box.get("ok")


@tool(
    name="open_url",
    description=(
        "Abre una web (solo http/https) en Opera GX. replace: true si el usuario corrige la web que acabas de abrir "
        "('no, era otra', 'te equivocaste'): se carga en la misma pestaña en vez de abrir otra."
    ),
)
def open_url(url: str = "", uri: str = "", replace: bool = False) -> Dict[str, Any]:
    """Abre una URL en el navegador."""
    target_url = url or uri
    if not target_url:
        return {"ok": False, "result": "Debes especificar una URL para abrir."}
    clean_url = target_url.strip()
    if not clean_url.startswith(("http://", "https://")):
        clean_url = f"https://{clean_url}"

    parsed = urllib.parse.urlparse(clean_url)
    if parsed.scheme not in ("http", "https") or not parsed.netloc or not parsed.hostname:
        return {"ok": False, "result": f"La URL '{target_url}' no es válida."}
    # Said aloud: "tytsoluciones.net", not "https colon slash slash www..." (the voice dropped it altogether)
    bare = parsed.hostname.removeprefix("www.")

    # A dictated or spelled address often comes out wrong ("tygtsoluciones.net"). If it does not exist, Google
    # with that name usually finds the right one ("quizás quisiste decir")
    if _host_exists(parsed.hostname) is False:
        _open_page("https://www.google.com/search?q=" + urllib.parse.quote_plus(bare), replace)
        return {"ok": True, "result": f"No encontré {bare}; te lo busqué en Google por si se escribe distinto."}

    _open_page(clean_url, replace)
    return {"ok": True, "result": f"He abierto {bare}."}


@tool(
    name="web_search",
    description=(
        "Abre en el navegador una búsqueda de Google. Solo si el usuario pide buscar algo; si te hace una pregunta, "
        "respóndela tú. replace: true si corrige la búsqueda o web que acabas de abrir (misma pestaña)."
    ),
)
def web_search(query: str = "", search_query: str = "", replace: bool = False) -> Dict[str, Any]:
    """Busca en Google y abre los resultados."""
    # "busca X en Opera": where to search is not part of what to search
    target_q = re.sub(r"\s+en\s+(?:opera|ópera|el\s+navegador|internet|google)$", "", (query or search_query).strip(),
                      flags=re.IGNORECASE)
    if not target_q:
        return {"ok": False, "result": "Debes especificar qué deseas buscar en Google."}
    _open_page("https://www.google.com/search?q=" + urllib.parse.quote_plus(target_q), replace)
    return {"ok": True, "result": f"He buscado '{target_q}' en Google."}


@tool(
    name="youtube_search",
    description="Abre la página de resultados de una búsqueda en YouTube (no reproduce nada). Para poner o reproducir algo, usa youtube_play."
)
def youtube_search(query: str = "", search_query: str = "") -> Dict[str, Any]:
    """Busca en YouTube y abre los resultados."""
    target_q = query or search_query
    if not target_q:
        return {"ok": False, "result": "Debes especificar qué deseas buscar en YouTube."}
    q = urllib.parse.quote_plus(target_q.strip())
    url = f"https://www.youtube.com/results?search_query={q}"
    _open_in_browser(url)
    return {"ok": True, "result": f"Buscando '{target_q}' en YouTube."}


# First organic result of a YouTube search page (not ads or shelves): videoId and title
_YT_FIRST_VIDEO = re.compile(r'"videoRenderer":\{"videoId":"([\w-]{11})".*?"title":\{"runs":\[\{"text":"(.*?)"\}')
_YT_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36",
    "Accept-Language": "es-ES,es;q=0.9",
}


# When Miku last opened a YouTube video: only then is a YouTube tab "hers" to reuse
_last_youtube_open = float("-inf")
YT_TAB_REUSE_S = 3600.0
VK_CONTROL, VK_DELETE, VK_RETURN = 0x11, 0x2E, 0x0D


def _reuse_youtube_tab(url: str) -> bool:
    """Plays url in the YouTube tab Miku opened before, if it is still Opera's active tab: a new song used to
    open a second tab and the first one kept playing (user, 24-oct). False means: open a new tab instead."""
    if time.monotonic() - _last_youtube_open > YT_TAB_REUSE_S:
        return False
    from core.tools.apps import _find_window
    hwnd = _find_window("youtube", exe="opera")  # the window title is the active tab's: "... - YouTube - Opera"
    return bool(hwnd) and _navigate_in(hwnd, url)


def _navigate_in(hwnd: int, url: str) -> bool:
    """Loads url in the active tab of this Opera window (address bar). False: it typed nothing that mattered."""
    from core.tools.apps import _bring_to_front, _press, _type_into_foreground
    if not _bring_to_front(hwnd):
        return False
    _press(VK_CONTROL, ord("L"))  # address bar
    time.sleep(0.15)
    user32 = ctypes.windll.user32
    # Typing goes to whatever has the focus: if Opera lost it, stop rather than type a URL into another app
    if user32.GetForegroundWindow() != hwnd:
        return False
    _type_into_foreground(url)
    if user32.GetForegroundWindow() != hwnd:
        return False
    _press(VK_DELETE)  # drop the address bar's inline autocomplete, or Enter could open a URL from history
    _press(VK_RETURN)
    _last_page.update(time=time.monotonic(), hwnd=hwnd)
    logger.info("Reused the tab for %s", url)
    return True


# The Opera window where Miku last opened a page: "no, era otra web" replaces it there
_last_page: Dict[str, Any] = {"time": float("-inf"), "hwnd": None}
LAST_PAGE_REUSE_S = 600.0


def _remember_opera_window() -> None:
    """Runs right after opening a URL. Opera opens it in its last active window but does not come to the front
    (Windows keeps background processes from taking the focus): so "no, era otra" opened yet another tab (log,
    24-oct). Bring that window up, so the user sees the page, and remember it."""
    time.sleep(1.0)
    from core.tools.apps import _bring_to_front
    windows = _opera_windows()
    if windows:
        _bring_to_front(windows[0])
        _last_page.update(time=time.monotonic(), hwnd=windows[0])


def _opera_windows() -> List[int]:
    """Opera's main windows, front-most first (EnumWindows walks the z-order from the top)."""
    user32 = ctypes.windll.user32
    found: List[int] = []

    def callback(hwnd, _):
        if (user32.IsWindowVisible(hwnd) and user32.GetWindowTextLengthW(hwnd) and not user32.GetWindow(hwnd, 4)
                and not user32.GetWindowLongW(hwnd, -20) & 0x80 and _is_opera(hwnd)):  # unowned, no tool window
            found.append(hwnd)
        return True

    user32.EnumWindows(ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)(callback), 0)
    return found


def _open_page(url: str, replace: bool) -> None:
    """Opens url; with replace (the user corrects the last page), in the tab Miku used last, if it can."""
    hwnd = _last_page["hwnd"]
    if (replace and hwnd and time.monotonic() - _last_page["time"] < LAST_PAGE_REUSE_S
            and ctypes.windll.user32.IsWindow(hwnd) and _navigate_in(hwnd, url)):
        return
    _open_in_browser(url)
    threading.Thread(target=_remember_opera_window, daemon=True, name="miku-opera-window").start()


def _first_youtube_video(query: str) -> Optional[Tuple[str, str]]:
    """(videoId, title) of the first result, read from the search page: no API key needed (~1 s)."""
    url = "https://www.youtube.com/results?search_query=" + urllib.parse.quote_plus(query)
    req = urllib.request.Request(url, headers=_YT_HEADERS)
    with urllib.request.urlopen(req, timeout=6) as resp:
        html = resp.read(3_000_000).decode("utf-8", "replace")
    m = _YT_FIRST_VIDEO.search(html)
    return (m.group(1), m.group(2)) if m else None


@tool(
    name="youtube_play",
    description="Pone y reproduce en YouTube la primera canción o vídeo que encuentre (ej: query: 'More K/DA'). Úsala cuando el usuario pida poner, reproducir o escuchar algo en YouTube."
)
def youtube_play(query: str = "", search_query: str = "") -> Dict[str, Any]:
    """Abre directamente el primer vídeo de la búsqueda, que empieza a sonar solo."""
    target_q = (query or search_query).strip()
    if not target_q:
        return {"ok": False, "result": "Debes decirme qué quieres que ponga en YouTube."}
    try:
        found = _first_youtube_video(target_q)
    except (OSError, ValueError) as e:
        logger.warning("YouTube lookup failed for %r: %s", target_q, e)
        found = None
    if not found:
        # Better a results page than nothing: the user can click the video
        _open_in_browser("https://www.youtube.com/results?search_query=" + urllib.parse.quote_plus(target_q))
        return {"ok": True, "result": f"No pude ponerla directamente; te abrí la búsqueda de '{target_q}' en YouTube."}
    video_id, title = found
    url = f"https://www.youtube.com/watch?v={video_id}"
    global _last_youtube_open
    if not _reuse_youtube_tab(url):
        _open_in_browser(url)
    _last_youtube_open = time.monotonic()
    try:
        title = json.loads(f'"{title}"')  # the title comes JSON-escaped ("&")
    except ValueError:
        pass
    # "K/DA - MORE ft. Madison Beer, ... (Video oficial)" -> "K/DA - MORE": short enough to say
    short = re.split(r"\s(?:[(\[|]|ft\.|feat\.)", title)[0][:60].rstrip(" ,-:")
    if any(ord(c) > 0x24F for c in short):  # Japanese etc.: the Spanish voice cannot read it, say the request
        short = target_q
    return {"ok": True, "result": f"¡Poniendo {short} en YouTube!"}


VK_SHIFT, VK_MENU, VK_TAB, VK_LEFT, VK_RIGHT, VK_F5 = 0x10, 0x12, 0x09, 0x25, 0x27, 0x74
# Ctrl+PgDn/PgUp move by position; Ctrl+Tab can be set to "recently used" order, where repeated presses
# only flip between the last two tabs
VK_PRIOR, VK_NEXT = 0x21, 0x22
WM_CLOSE = 0x0010
# Opera's own shortcuts (same as Chrome's)
_BROWSER_KEYS = {
    "new_tab": (VK_CONTROL, ord("T")), "close_tab": (VK_CONTROL, ord("W")),
    "next_tab": (VK_CONTROL, VK_NEXT), "previous_tab": (VK_CONTROL, VK_PRIOR),
    "reopen_tab": (VK_CONTROL, VK_SHIFT, ord("T")), "new_window": (VK_CONTROL, ord("N")),
    "back": (VK_MENU, VK_LEFT),
    "forward": (VK_MENU, VK_RIGHT), "reload": (VK_F5,),
}
_BROWSER_DONE = {
    "new_tab": "Abrí una pestaña nueva", "close_tab": "Cerré la pestaña", "next_tab": "Pasé a la siguiente pestaña",
    "previous_tab": "Volví a la pestaña anterior", "reopen_tab": "Reabrí la última pestaña cerrada",
    "new_window": "Abrí una ventana nueva", "close_window": "Cerré la ventana", "back": "Volví atrás",
    "forward": "Fui hacia adelante", "reload": "Recargué la página", "go_to_tab": "Ya estás en la pestaña",
    "close_all_tabs": "Cerré todas las pestañas de esa ventana", "close_other_tabs": "Cerré las demás pestañas",
}
MAX_TABS_TO_CYCLE = 40


def _window_title(hwnd: int) -> str:
    user32 = ctypes.windll.user32
    buf = ctypes.create_unicode_buffer(512)
    user32.GetWindowTextW(hwnd, buf, 512)
    return buf.value


def _is_opera(hwnd: int) -> bool:
    import psutil
    pid = ctypes.c_ulong(0)
    ctypes.windll.user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    try:
        return psutil.Process(pid.value).name().lower().startswith("opera")
    except (psutil.Error, OSError):
        return False


def _keys_to(hwnd: int, *vks: int) -> bool:
    """Presses a chord only if hwnd still has the focus: keys must never land in another app."""
    from core.tools.apps import _press
    if ctypes.windll.user32.GetForegroundWindow() != hwnd:
        return False
    _press(*vks)
    time.sleep(0.12)
    return True


def _go_to_tab(hwnd: int, name: str) -> bool:
    """Ctrl+PgDn through the window's tabs until the active one's title (= window title) matches name, loosely:
    "T y T", "T&T", "TyT" and "t-soluciones" all failed against a "TyT Soluciones" tab (log 06:15)."""
    want = _norm_title(name)
    first = _window_title(hwnd)
    titles: List[str] = []
    for _ in range(MAX_TABS_TO_CYCLE):
        title = _window_title(hwnd)
        if want and want in _norm_title(title):
            return True
        titles.append(title)
        if not _keys_to(hwnd, VK_CONTROL, VK_NEXT):
            return False
        time.sleep(0.25)  # the window title follows the active tab with a small delay
        if _window_title(hwnd) == first:  # went all the way round
            break
    # No tab contains it: the clearly closest title, if any (it may be closed around, so only a clear match)
    scored = [(_closeness(want, _norm_title(t)), t) for t in titles]
    score, best = max(scored, default=(0.0, ""))
    if score < MIN_TAB_CLOSENESS:
        return False
    for _ in range(len(titles) + 1):
        if _window_title(hwnd) == best:
            return True
        if not _keys_to(hwnd, VK_CONTROL, VK_NEXT):
            return False
        time.sleep(0.25)
    return False


MIN_TAB_CLOSENESS = 0.75


def _norm_title(text: str) -> str:
    """'TyT Soluciones | Inicio - Opera' -> 'tytsolucionesinicio': no case, accents, spaces or symbols."""
    t = unicodedata.normalize("NFKD", text.lower().replace("+", "plus")).encode("ascii", "ignore").decode()
    t = re.sub(r"\s*-\s*opera$", "", t)  # Opera appends its name to the window title
    return re.sub(r"[^a-z0-9]", "", t)


def _closeness(want: str, title: str) -> float:
    """Share of `want` found as one piece in `title` ("tsoluciones" in "tytsoluciones..." -> 11/11)."""
    if not want or not title:
        return 0.0
    match = difflib.SequenceMatcher(None, want, title).find_longest_match(0, len(want), 0, len(title))
    return match.size / len(want)


def _close_window_tabs(hwnd: int) -> bool:
    """Closes the window by closing its tabs one by one: Ctrl+Shift+W made Opera ask "Confirmar el cierre"
    (live test). Stops as soon as the window is gone, or if it loses the focus (never another window's tabs).
    A pinned tab ignores Ctrl+W (Opera GX pins "GX Corner"): once only those are left, WM_CLOSE the window."""
    user32 = ctypes.windll.user32
    alive = lambda: user32.IsWindow(hwnd) and user32.IsWindowVisible(hwnd)
    for _ in range(MAX_TABS_TO_CYCLE * 2):
        if not alive():
            return True
        before = _window_title(hwnd)
        if not _keys_to(hwnd, VK_CONTROL, ord("W")):
            return not alive()
        time.sleep(0.25)
        if alive() and _window_title(hwnd) == before:  # did not close: pinned
            user32.PostMessageW(hwnd, WM_CLOSE, 0, 0)
            time.sleep(1.0)
            return not alive()
    return False


def _close_other_tabs(hwnd: int) -> Optional[int]:
    """Closes every tab of the window except the active one. Returns how many, or None if Opera lost the focus.
    Pinned tabs ignore Ctrl+W: they are skipped, not counted (the first version pressed Ctrl+W 78 times on
    Opera GX's pinned "GX Corner" and called them closed, live test)."""
    keep = _window_title(hwnd)
    closed = 0
    pinned: set = set()
    closed_since_keep = False
    for _ in range(MAX_TABS_TO_CYCLE * 2):
        title = _window_title(hwnd)
        if title == keep or title in pinned:
            if not _keys_to(hwnd, VK_CONTROL, VK_NEXT):
                return None
            time.sleep(0.25)
            if _window_title(hwnd) == keep:
                if not closed_since_keep:  # a full lap with nothing to close: only kept and pinned tabs remain
                    return closed
                closed_since_keep = False
            continue
        # Closing a tab activates the next one: close what is active now. Moving on first skipped every
        # other tab ("aún faltan por cerrar", log 24-oct)
        if not _keys_to(hwnd, VK_CONTROL, ord("W")):
            return None
        time.sleep(0.3)
        if _window_title(hwnd) == title:
            pinned.add(title)
        else:
            closed += 1
            closed_since_keep = True
    return closed


def _find_tab(name: str, first: int) -> Optional[int]:
    """The Opera window holding a tab whose title contains name, with that tab made active. Looks in the given
    window first, then in Opera's other windows (it used to look in one window only)."""
    from core.tools.apps import _bring_to_front
    for hwnd in [first] + [w for w in _opera_windows() if w != first]:
        if _bring_to_front(hwnd) and _go_to_tab(hwnd, name):
            return hwnd
    return None


@tool(
    name="browser_action",
    description=(
        "Controla Opera con sus atajos: action = new_tab | close_tab | close_other_tabs | close_all_tabs | next_tab | "
        "previous_tab | reopen_tab | go_to_tab | new_window | close_window | back | forward | reload. target: para "
        "new_tab, una web o lo que buscar; para go_to_tab y close_tab, parte del título de la pestaña (ej: "
        "'youtube'); para close_other_tabs, la pestaña que se QUEDA ('todas menos la de YouTube' -> 'youtube'); "
        "vacío = la actual. close_all_tabs cierra todas las de esa ventana."
    ),
)
def browser_action(action: str, target: str = "") -> Dict[str, Any]:
    """Acciones de pestañas y ventanas en Opera, solo si su ventana queda al frente."""
    from core.tools.apps import _bring_to_front, _find_window, _type_into_foreground
    act = action.strip().lower().replace(" ", "_")
    target = target.strip()
    if act not in _BROWSER_KEYS and act not in ("go_to_tab", "close_other_tabs", "close_all_tabs", "close_window"):
        return {"ok": False, "result": f"No sé hacer '{action}' en el navegador."}

    user32 = ctypes.windll.user32
    # The Opera window to act on: one whose active tab matches the target, else the one in front, else any
    hwnd = (_find_window(target, exe="opera") if target and act in ("go_to_tab", "close_tab", "close_other_tabs") else None)
    fg = user32.GetForegroundWindow()
    if not hwnd:
        hwnd = fg if fg and _is_opera(fg) else _find_window("", exe="opera")
    if not hwnd:
        if act in ("new_tab", "new_window"):
            _open_in_browser(_as_url(target) if target else "about:blank")
            return {"ok": True, "result": "Abrí Opera."}
        return {"ok": False, "result": "Opera no está abierto."}
    if not _bring_to_front(hwnd):
        return {"ok": False, "result": "No pude traer Opera al frente, así que no toqué nada."}

    if act in ("go_to_tab", "close_tab", "close_other_tabs") and target:
        found = _find_tab(target, first=hwnd)
        if not found:
            return {"ok": False, "result": f"No encontré ninguna pestaña con '{target}' en Opera."}
        hwnd = found
    if act == "close_other_tabs":
        closed = _close_other_tabs(hwnd)
        if closed is None:
            return {"ok": False, "result": "Opera perdió el foco, así que me detuve."}
        # "Todas menos esta" means all of Opera: its other windows too (they were left open, log 24-oct)
        windows = 0
        for other in _opera_windows():
            if other != hwnd and _bring_to_front(other) and _close_window_tabs(other):
                windows += 1
        _bring_to_front(hwnd)
        extra = f" y {windows} ventana{'s' if windows != 1 else ''} más" if windows else ""
        return {"ok": True, "result": f"Cerré {closed} pestaña{'s' if closed != 1 else ''}{extra}; dejé {target or 'la actual'}."}
    if act in ("close_all_tabs", "close_window"):
        if not _close_window_tabs(hwnd):
            return {"ok": False, "result": "Opera perdió el foco, así que dejé de cerrar pestañas."}
        return {"ok": True, "result": "Cerré esa ventana de Opera con todas sus pestañas."}
    if act != "go_to_tab" and not _keys_to(hwnd, *_BROWSER_KEYS[act]):
        return {"ok": False, "result": "Opera perdió el foco, así que me detuve."}
    if act == "new_tab" and target:
        # Opera GX animates the new tab and the address bar gets the focus late: typed letters were lost
        # (live test). Wait, then put the focus there ourselves
        time.sleep(0.5)
        if not _keys_to(hwnd, VK_CONTROL, ord("L")):
            return {"ok": False, "result": "Opera perdió el foco, así que no escribí nada."}
        _type_into_foreground(_as_url(target))
        if not (_keys_to(hwnd, VK_DELETE) and _keys_to(hwnd, VK_RETURN)):
            return {"ok": False, "result": "Opera perdió el foco, así que me detuve."}
    done = _BROWSER_DONE[act]
    return {"ok": True, "result": f"{done}{' con ' + target if act == 'new_tab' and target else ''}."}


def _as_url(target: str) -> str:
    """A web address as is (https added), anything else as a Google search."""
    t = target.strip()
    if re.match(r"^(https?://)?[\w-]+(\.[\w-]+)+(/\S*)?$", t):
        return t if t.startswith("http") else f"https://{t}"
    return "https://www.google.com/search?q=" + urllib.parse.quote_plus(t)


def _first_web_result(name: str) -> Optional[str]:
    """URL of the site DuckDuckGo's "!ducky" (I'm feeling lucky) picks for a name, read from its redirect page."""
    url = "https://duckduckgo.com/?q=" + urllib.parse.quote_plus("!ducky " + name)
    with urllib.request.urlopen(urllib.request.Request(url, headers=_YT_HEADERS), timeout=6) as resp:
        body = resp.read(400_000).decode("utf-8", "replace")
    m = re.search(r"uddg=([^&\"']+)", body) or re.search(r"url=(https?://[^'\"]+)", body)
    found = urllib.parse.unquote(m.group(1)) if m else None
    return found if found and found.startswith(("http://", "https://")) else None


@tool(
    name="open_website",
    description=(
        "Abre la web de algo por su NOMBRE cuando no sabes la dirección exacta (ej: 'banco de costa rica', 'steam', "
        "'tyt soluciones'). Si te dictan o deletrean una dirección con .com, .net..., usa open_url. replace: true si "
        "corrige la web que acabas de abrir (misma pestaña)."
    ),
)
def open_website(name: str, replace: bool = False) -> Dict[str, Any]:
    """Abre el primer resultado para un nombre y dice a qué dominio fue, para poder corregirlo."""
    target = name.strip()
    if not target:
        return {"ok": False, "result": "¿Qué página quieres que abra?"}
    try:
        url = _first_web_result(target)
    except (OSError, ValueError) as e:
        logger.warning("Site lookup failed for %r: %s", target, e)
        url = None
    if not url:
        _open_page("https://www.google.com/search?q=" + urllib.parse.quote_plus(target), replace)
        return {"ok": True, "result": f"No encontré una web clara para {target}; te abrí la búsqueda en Google."}
    _open_page(url, replace)
    host = (urllib.parse.urlparse(url).hostname or url).removeprefix("www.")
    # The first result is not always the one meant ("tyt soluciones" -> tytsolutions.com): say where it went
    return {"ok": True, "result": f"Abrí {host}."}
