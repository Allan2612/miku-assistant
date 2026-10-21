"""
Miku Assistant - Web and Search Tools (tools/web.py)
"""

import logging
import os
import subprocess
import urllib.parse
import webbrowser
from typing import Dict, Any

from core.tools import tool
from core.tools._win import find_opera_gx as _find_opera_gx

logger = logging.getLogger("miku.tools.web")


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
    description="Realiza una búsqueda en Google con la consulta indicada y la abre en el navegador."
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
    description="Realiza una búsqueda de videos en YouTube con la consulta indicada y la abre en el navegador."
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
