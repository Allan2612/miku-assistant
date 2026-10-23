"""
Miku Assistant - Files and Folders Tools (tools/files.py)
"""

import logging
import os
from pathlib import Path
import time
import re
from typing import Dict, List, Optional, Set, Any

from core.config import load_config
from core.tools import tool

logger = logging.getLogger("miku.tools.files")

# Track files found during the current session to ensure safe opening
_SESSION_FOUND_FILES: Set[str] = set()

# os.startfile runs these instead of opening them (H-011)
_EXECUTABLE_EXTS = {
    ".exe", ".com", ".bat", ".cmd", ".ps1", ".psm1", ".vbs", ".vbe", ".js", ".jse", ".wsf", ".wsh",
    ".msi", ".msp", ".scr", ".pif", ".lnk", ".url", ".hta", ".cpl", ".jar", ".reg", ".appref-ms",
}

# config.yaml -> tools.file_search_roots (H-009)
DEFAULT_SEARCH_ROOTS = [Path(p).expanduser() for p in load_config().tools.file_search_roots]


def _search(query_str: str, limit: int = 10, exts: Optional[Set[str]] = None) -> List[str]:
    """Files under the search roots whose name contains query_str: depth 3, 3 s budget. Marks them openable."""
    results: List[str] = []
    start_time = time.monotonic()

    for root_dir in DEFAULT_SEARCH_ROOTS:
        if not root_dir.exists():
            continue

        try:
            for root, dirs, files in os.walk(root_dir):
                if time.monotonic() - start_time > 3.0 or len(results) >= limit:
                    break

                # Limit depth to 3 levels
                rel = Path(root).relative_to(root_dir)
                if len(rel.parts) >= 3:
                    dirs.clear()  # Do not descend further
                    continue

                # Filter hidden folders
                dirs[:] = [d for d in dirs if not d.startswith(".")]

                for f in files:
                    if query_str in f.lower() and (exts is None or Path(f).suffix.lower() in exts):
                        full_path = os.path.join(root, f)
                        results.append(full_path)
                        _SESSION_FOUND_FILES.add(os.path.normpath(full_path))
                        if len(results) >= limit:
                            break
        except Exception as e:
            logger.debug("Error traversing %s: %s", root_dir, e)
    return results


@tool(
    name="find_file",
    description="Busca un archivo por su nombre en las carpetas de usuario (Escritorio, Documentos, Descargas). Máx 10 resultados."
)
def find_file(name: str = "", filename: str = "", query: str = "") -> Dict[str, Any]:
    """Busca archivos con un límite de profundidad de 3 niveles y 3s de timeout."""
    target_q = name or filename or query
    if not target_q:
        return {"ok": False, "result": "Debes especificar qué archivo deseas buscar."}
    results = _search(target_q.strip().lower())

    if results:
        file_names = [f"• {Path(p).name} ({Path(p).parent.name})" for p in results[:5]]
        count_str = f"Encontré {len(results)} archivo(s):\n" + "\n".join(file_names)
        return {"ok": True, "result": count_str}

    return {"ok": False, "result": f"No encontré ningún archivo que contenga '{target_q}' en Escritorio, Documentos o Descargas."}


@tool(
    name="open_file",
    description="Abre un archivo encontrado previamente en la sesión por su nombre o ruta."
)
def open_file(path: str) -> Dict[str, Any]:
    """Abre un archivo si fue encontrado previamente en la sesión."""
    norm = os.path.normpath(path.strip())

    # Check if exact path or filename matches session files
    target = None
    if norm in _SESSION_FOUND_FILES and os.path.exists(norm):
        target = norm
    else:
        # Search by filename in session files
        q = Path(path).name.lower()
        for f in _SESSION_FOUND_FILES:
            if Path(f).name.lower() == q and os.path.exists(f):
                target = f
                break

    if target and Path(target).suffix.lower() in _EXECUTABLE_EXTS:
        return {"ok": False, "result": f"Por seguridad no abro programas ni scripts ({Path(target).name}). Ábrelo tú si confías en él."}

    if target:
        try:
            os.startfile(target)
            return {"ok": True, "result": f"He abierto el archivo {Path(target).name}."}
        except Exception as e:
            return {"ok": False, "result": f"Error al abrir {target}: {e}"}

    return {"ok": False, "result": f"No puedo abrir '{path}' porque no se encontró previamente en la sesión por seguridad."}


@tool(
    name="open_folder",
    description="Abre una carpeta principal en el Explorador de Windows (escritorio, descargas, documentos, imagenes, musica o videos)."
)
def open_folder(name: str = "", folder: str = "", folder_name: str = "") -> Dict[str, Any]:
    """Abre carpetas estándar del usuario en el explorador."""
    target_name = name or folder or folder_name
    if not target_name:
        return {"ok": False, "result": "Debes especificar qué carpeta abrir."}
    q = target_name.strip().lower()

    folder_map = {
        "escritorio": Path.home() / "Desktop",
        "desktop": Path.home() / "Desktop",
        "descargas": Path.home() / "Downloads",
        "downloads": Path.home() / "Downloads",
        "documentos": Path.home() / "Documents",
        "documents": Path.home() / "Documents",
        "imagenes": Path.home() / "Pictures",
        "imágenes": Path.home() / "Pictures",
        "pictures": Path.home() / "Pictures",
        "musica": Path.home() / "Music",
        "música": Path.home() / "Music",
        "music": Path.home() / "Music",
        "videos": Path.home() / "Videos",
        "vídeos": Path.home() / "Videos",
    }

    target = folder_map.get(q)
    if target and target.exists():
        os.startfile(str(target))
        return {"ok": True, "result": f"He abierto la carpeta {target_name}."}

    return {"ok": False, "result": f"No reconozco la carpeta '{target_name}'. Las disponibles son: Escritorio, Descargas, Documentos, Imágenes, Música y Videos."}


_TEXT_EXTS = {".txt", ".md", ".csv", ".log"}


@tool(
    name="create_text_file",
    description="Crea un archivo de texto nuevo en el Escritorio con el contenido indicado (nunca sobrescribe uno existente). name: nombre del archivo."
)
def create_text_file(name: str, content: str = "") -> Dict[str, Any]:
    """Crea un .txt/.md nuevo en el Escritorio."""
    # Only a bare file name: no folders, no "..", nothing outside the Desktop
    stem = re.sub(r'[<>:"/\|?*]', "", Path(name.strip()).name).strip(" .")
    if not stem:
        return {"ok": False, "result": "Necesito un nombre para el archivo."}
    if Path(stem).suffix.lower() not in _TEXT_EXTS:
        stem += ".txt"
    target = Path.home() / "Desktop" / stem
    try:
        with open(target, "x", encoding="utf-8") as f:  # "x": fails instead of overwriting the user's file
            f.write(content)
    except FileExistsError:
        return {"ok": False, "result": f"Ya existe un archivo llamado {stem} en el Escritorio; no lo sobrescribo."}
    except OSError as e:
        return {"ok": False, "result": f"No pude crear {stem}: {e}"}
    _SESSION_FOUND_FILES.add(os.path.normpath(str(target)))
    return {"ok": True, "result": f"Creé {stem} en el Escritorio."}


@tool(
    name="read_text_file",
    description="Lee en voz alta el contenido de un archivo de texto (.txt, .md, .csv, .log) de Escritorio, Documentos o Descargas, buscándolo por su nombre."
)
def read_text_file(name: str) -> Dict[str, Any]:
    """Lee los primeros 600 caracteres de un archivo de texto."""
    found = _search(name.strip().lower(), limit=1, exts=_TEXT_EXTS)
    if not found:
        return {"ok": False, "result": f"No encontré ningún archivo de texto llamado '{name}'."}
    try:
        text = Path(found[0]).read_text(encoding="utf-8", errors="replace").strip()
    except OSError as e:
        return {"ok": False, "result": f"No pude leer {Path(found[0]).name}: {e}"}
    if not text:
        return {"ok": True, "result": f"{Path(found[0]).name} está vacío."}
    return {"ok": True, "result": f"{Path(found[0]).name} dice: " + text[:600] + ("..." if len(text) > 600 else "")}
