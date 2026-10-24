"""
Miku Assistant - Web and Search Tools (tools/web.py)

Tabs go through Miku's Opera extension (core/browser.py): exact tab ids, never simulated keystrokes. Without the
extension, pages still open (opera.exe <url>), but tabs cannot be listed, reused or closed.
"""

import json
import logging
import os
import re
import socket
import subprocess
import threading
import urllib.parse
import urllib.request
import webbrowser
from typing import Any, Dict, List, Optional, Tuple

from core.browser import bridge
from core.tools import tool
from core.tools._win import find_opera_gx as _find_opera_gx

logger = logging.getLogger("miku.tools.web")

NO_EXTENSION = "Para manejar pestañas necesito la extensión de Miku en Opera (carpeta browser-extension)."


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


def _open_page(url: str, tab_id: int = 0) -> None:
    """Opens url through the extension (in tab_id, or a new tab) and brings Opera up; without it, opera.exe <url>."""
    if bridge.connected and bridge.run("open", url=url, tab_id=tab_id or None).get("ok"):
        return
    _open_in_browser(url)


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


_TAB_ID_HELP = (
    "tab_id: número de una pestaña del estado del PC para cargarla ahí en vez de abrir otra (p. ej. la 'abierta por "
    "Miku' cuando el usuario corrige: 'no, era otra'); 0 = pestaña nueva."
)


@tool(
    name="open_url",
    description=f"Abre una web (solo http/https) en Opera GX. {_TAB_ID_HELP}",
)
def open_url(url: str = "", uri: str = "", tab_id: int = 0) -> Dict[str, Any]:
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
        _open_page("https://www.google.com/search?q=" + urllib.parse.quote_plus(bare), tab_id)
        return {"ok": True, "result": f"No existe {bare}; abrí la búsqueda en Google por si se escribe distinto."}

    _open_page(clean_url, tab_id)
    return {"ok": True, "result": f"Abrí {bare}."}


@tool(
    name="web_search",
    description=(
        "Abre en el navegador una búsqueda de Google. Solo si el usuario pide buscar algo; si te hace una pregunta, "
        f"respóndela tú. {_TAB_ID_HELP}"
    ),
)
def web_search(query: str = "", search_query: str = "", tab_id: int = 0) -> Dict[str, Any]:
    """Busca en Google y abre los resultados."""
    # "busca X en Opera": where to search is not part of what to search
    target_q = re.sub(r"\s+en\s+(?:opera|ópera|el\s+navegador|internet|google)$", "", (query or search_query).strip(),
                      flags=re.IGNORECASE)
    if not target_q:
        return {"ok": False, "result": "Debes especificar qué deseas buscar en Google."}
    _open_page("https://www.google.com/search?q=" + urllib.parse.quote_plus(target_q), tab_id)
    return {"ok": True, "result": f"Busqué '{target_q}' en Google."}


@tool(
    name="youtube_search",
    description="Abre la página de resultados de una búsqueda en YouTube (no reproduce nada). Para poner o reproducir algo, usa youtube_play."
)
def youtube_search(query: str = "", search_query: str = "", tab_id: int = 0) -> Dict[str, Any]:
    """Busca en YouTube y abre los resultados."""
    target_q = (query or search_query).strip()
    if not target_q:
        return {"ok": False, "result": "Debes especificar qué deseas buscar en YouTube."}
    _open_page("https://www.youtube.com/results?search_query=" + urllib.parse.quote_plus(target_q), tab_id)
    return {"ok": True, "result": f"Busqué '{target_q}' en YouTube."}


# First organic result of a YouTube search page (not ads or shelves): videoId and title
_YT_FIRST_VIDEO = re.compile(r'"videoRenderer":\{"videoId":"([\w-]{11})".*?"title":\{"runs":\[\{"text":"(.*?)"\}')
_YT_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36",
    "Accept-Language": "es-ES,es;q=0.9",
}


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
    description=(
        "Pone y reproduce en YouTube la primera canción o vídeo que encuentre (ej: query: 'More K/DA'). Úsala cuando "
        "el usuario pida poner, reproducir o escuchar algo. Reutiliza sola la pestaña de YouTube que abrió Miku."
    ),
)
def youtube_play(query: str = "", search_query: str = "", tab_id: int = 0) -> Dict[str, Any]:
    """Abre directamente el primer vídeo de la búsqueda, que empieza a sonar solo."""
    target_q = (query or search_query).strip()
    if not target_q:
        return {"ok": False, "result": "Debes decirme qué quieres que ponga en YouTube."}
    # The next song replaces the one Miku put on: otherwise both kept playing (user, 24-oct)
    mine = bridge.tab(bridge.last_opened_tab)
    if not tab_id and mine and "youtube.com" in mine.get("url", ""):
        tab_id = mine["id"]
    try:
        found = _first_youtube_video(target_q)
    except (OSError, ValueError) as e:
        logger.warning("YouTube lookup failed for %r: %s", target_q, e)
        found = None
    if not found:
        # Better a results page than nothing: the user can click the video
        _open_page("https://www.youtube.com/results?search_query=" + urllib.parse.quote_plus(target_q), tab_id)
        return {"ok": True, "result": f"No pude ponerla directamente; abrí la búsqueda de '{target_q}' en YouTube."}
    video_id, title = found
    _open_page(f"https://www.youtube.com/watch?v={video_id}", tab_id)
    try:
        title = json.loads(f'"{title}"')  # the title comes JSON-escaped ("&")
    except ValueError:
        pass
    # "K/DA - MORE ft. Madison Beer, ... (Video oficial)" -> "K/DA - MORE": short enough to say
    short = re.split(r"\s(?:[(\[|]|ft\.|feat\.)", title)[0][:60].rstrip(" ,-:")
    if any(ord(c) > 0x24F for c in short):  # Japanese etc.: the Spanish voice cannot read it, say the request
        short = target_q
    return {"ok": True, "result": f"Puse {short} en YouTube."}


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
        "Abre la web de algo por su NOMBRE cuando no sabes la dirección exacta (ej: 'banco de costa rica', 'steam'). "
        f"Si te dictan o deletrean una dirección con .com, .net..., usa open_url. {_TAB_ID_HELP}"
    ),
)
def open_website(name: str, tab_id: int = 0) -> Dict[str, Any]:
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
        _open_page("https://www.google.com/search?q=" + urllib.parse.quote_plus(target), tab_id)
        return {"ok": True, "result": f"No encontré una web clara para {target}; abrí la búsqueda en Google."}
    _open_page(url, tab_id)
    host = (urllib.parse.urlparse(url).hostname or url).removeprefix("www.")
    # The first result is not always the one meant ("tyt soluciones" -> tytsolutions.com): say where it went
    return {"ok": True, "result": f"Abrí {host}."}


_TAB_ACTIONS = {"close": "Cerré", "activate": "Te puse en", "reload": "Recargué", "back": "Volví atrás en",
                "forward": "Fui hacia adelante en"}


@tool(
    name="browser_tabs",
    description=(
        "Maneja pestañas de Opera por su número (tab_id) del estado del PC. action = close | activate | reload | "
        "back | forward. tab_ids: una o varias (close acepta varias: para 'cierra todas menos X', pasa todas las "
        "demás; las fijadas también se cierran). Para abrir webs usa open_url, web_search u open_website."
    ),
)
def browser_tabs(action: str, tab_ids: List[int]) -> Dict[str, Any]:
    """Cierra, activa, recarga o navega pestañas concretas por su id."""
    act = action.strip().lower()
    if act not in _TAB_ACTIONS:
        return {"ok": False, "result": f"No sé hacer '{action}' con pestañas (close, activate, reload, back, forward)."}
    if not bridge.connected:
        return {"ok": False, "result": NO_EXTENSION}
    ids = [int(i) for i in tab_ids or []]
    unknown = [i for i in ids if not bridge.tab(i)]
    if not ids or unknown:
        return {"ok": False, "result": f"No hay pestañas con esos números ({unknown or 'ninguno'}); mira el estado."}
    titles = [bridge.tab(i).get("title", "") for i in ids]
    res = bridge.run("close", tab_ids=ids) if act == "close" else bridge.run(act, tab_id=ids[0])
    if not res.get("ok"):
        return {"ok": False, "result": f"Opera no pudo: {res.get('error', 'error desconocido')}"}
    what = f"{len(ids)} pestañas" if len(ids) > 1 else f"'{titles[0][:50]}'"
    return {"ok": True, "result": f"{_TAB_ACTIONS[act]} {what}."}
