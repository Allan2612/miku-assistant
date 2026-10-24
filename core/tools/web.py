"""
Miku Assistant - Web and Search Tools (tools/web.py)
"""

import json
import logging
import os
import re
import subprocess
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
    _open_in_browser(f"https://www.youtube.com/watch?v={video_id}")
    try:
        title = json.loads(f'"{title}"')  # the title comes JSON-escaped ("&")
    except ValueError:
        pass
    # "K/DA - MORE ft. Madison Beer, ... (Video oficial)" -> "K/DA - MORE": short enough to say
    short = re.split(r"\s(?:[(\[|]|ft\.|feat\.)", title)[0][:60].rstrip(" ,-:")
    if any(ord(c) > 0x24F for c in short):  # Japanese etc.: the Spanish voice cannot read it, say the request
        short = target_q
    return {"ok": True, "result": f"¡Poniendo {short} en YouTube!"}
