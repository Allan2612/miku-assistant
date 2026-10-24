"""
Miku Assistant - Web and Search Tools (tools/web.py)
"""

import ctypes
import json
import logging
import os
import re
import subprocess
import time
import urllib.parse
import urllib.request
import webbrowser
from typing import Dict, Any, Optional, Tuple

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


@tool(
    name="open_url",
    description="Abre una URL web válida (solo http/https) en Opera GX si está instalado, si no en el navegador predeterminado."
)
def open_url(url: str = "", uri: str = "") -> Dict[str, Any]:
    """Abre una URL en el navegador."""
    target_url = url or uri
    if not target_url:
        return {"ok": False, "result": "Debes especificar una URL para abrir."}
    clean_url = target_url.strip()
    if not clean_url.startswith(("http://", "https://")):
        clean_url = f"https://{clean_url}"

    parsed = urllib.parse.urlparse(clean_url)
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        return {"ok": False, "result": f"La URL '{target_url}' no es válida."}

    _open_in_browser(clean_url)
    return {"ok": True, "result": f"He abierto {clean_url} en tu navegador."}


@tool(
    name="web_search",
    description="Abre en el navegador una búsqueda de Google. Solo si el usuario pide buscar algo; si te hace una pregunta, respóndela tú."
)
def web_search(query: str = "", search_query: str = "") -> Dict[str, Any]:
    """Busca en Google y abre los resultados."""
    target_q = query or search_query
    if not target_q:
        return {"ok": False, "result": "Debes especificar qué deseas buscar en Google."}
    q = urllib.parse.quote_plus(target_q.strip())
    url = f"https://www.google.com/search?q={q}"
    _open_in_browser(url)
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
    from core.tools.apps import _bring_to_front, _find_window, _press, _type_into_foreground
    hwnd = _find_window("youtube", exe="opera")  # the window title is the active tab's: "... - YouTube - Opera"
    if not hwnd or not _bring_to_front(hwnd):
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
    logger.info("Reused the YouTube tab for %s", url)
    return True


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
# Opera's own shortcuts (same as Chrome's)
_BROWSER_KEYS = {
    "new_tab": (VK_CONTROL, ord("T")), "close_tab": (VK_CONTROL, ord("W")),
    "next_tab": (VK_CONTROL, VK_TAB), "previous_tab": (VK_CONTROL, VK_SHIFT, VK_TAB),
    "reopen_tab": (VK_CONTROL, VK_SHIFT, ord("T")), "new_window": (VK_CONTROL, ord("N")),
    "close_window": (VK_CONTROL, VK_SHIFT, ord("W")), "back": (VK_MENU, VK_LEFT),
    "forward": (VK_MENU, VK_RIGHT), "reload": (VK_F5,),
}
_BROWSER_DONE = {
    "new_tab": "Abrí una pestaña nueva", "close_tab": "Cerré la pestaña", "next_tab": "Pasé a la siguiente pestaña",
    "previous_tab": "Volví a la pestaña anterior", "reopen_tab": "Reabrí la última pestaña cerrada",
    "new_window": "Abrí una ventana nueva", "close_window": "Cerré la ventana", "back": "Volví atrás",
    "forward": "Fui hacia adelante", "reload": "Recargué la página", "go_to_tab": "Ya estás en la pestaña",
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
    """Ctrl+Tab through the window's tabs until the active one's title (= window title) contains name."""
    name = name.lower()
    first = _window_title(hwnd)
    for _ in range(MAX_TABS_TO_CYCLE):
        if name in _window_title(hwnd).lower():
            return True
        if not _keys_to(hwnd, VK_CONTROL, VK_TAB):
            return False
        time.sleep(0.25)  # the window title follows the active tab with a small delay
        if _window_title(hwnd) == first:  # went all the way round
            return name in first.lower()
    return False


@tool(
    name="browser_action",
    description=(
        "Controla Opera con sus atajos: action = new_tab | close_tab | next_tab | previous_tab | reopen_tab | "
        "go_to_tab | new_window | close_window | back | forward | reload. target: para new_tab, una web o lo que "
        "buscar; para go_to_tab y close_tab, parte del título de la pestaña (ej: 'youtube'); vacío = la actual."
    ),
)
def browser_action(action: str, target: str = "") -> Dict[str, Any]:
    """Acciones de pestañas y ventanas en Opera, solo si su ventana queda al frente."""
    from core.tools.apps import _bring_to_front, _find_window, _type_into_foreground
    act = action.strip().lower().replace(" ", "_")
    target = target.strip()
    if act not in _BROWSER_KEYS and act != "go_to_tab":
        return {"ok": False, "result": f"No sé hacer '{action}' en el navegador."}

    user32 = ctypes.windll.user32
    # The Opera window to act on: one whose active tab matches the target, else the one in front, else any
    hwnd = (_find_window(target, exe="opera") if target and act in ("go_to_tab", "close_tab") else None)
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

    if act in ("go_to_tab", "close_tab") and target and not _go_to_tab(hwnd, target):
        return {"ok": False, "result": f"No encontré ninguna pestaña con '{target}'."}
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
