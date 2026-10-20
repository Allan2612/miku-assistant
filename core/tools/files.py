"""
Miku Assistant - Files and Folders Tools (tools/files.py)
"""

import logging
import os
from pathlib import Path
import time
from typing import Dict, List, Set, Any

from core.tools import tool

logger = logging.getLogger("miku.tools.files")

# Track files found during the current session to ensure safe opening
_SESSION_FOUND_FILES: Set[str] = set()

DEFAULT_SEARCH_ROOTS = [
    Path.home() / "Desktop",
    Path.home() / "Documents",
    Path.home() / "Downloads",
]


@tool(
    name="find_file",
    description="Busca un archivo por su nombre en las carpetas de usuario (Escritorio, Documentos, Descargas). Máx 10 resultados."
)
def find_file(name: str = "", filename: str = "", query: str = "") -> Dict[str, Any]:
    """Busca archivos con un límite de profundidad de 3 niveles y 3s de timeout."""
    global _SESSION_FOUND_FILES
    target_q = name or filename or query
    if not target_q:
        return {"ok": False, "result": "Debes especificar qué archivo deseas buscar."}
    query_str = target_q.strip().lower()
    results: List[str] = []
    start_time = time.monotonic()

    for root_dir in DEFAULT_SEARCH_ROOTS:
        if not root_dir.exists():
            continue

        try:
            for root, dirs, files in os.walk(root_dir):
                if time.monotonic() - start_time > 3.0 or len(results) >= 10:
                    break

                # Limit depth to 3 levels
                rel = Path(root).relative_to(root_dir)
                if len(rel.parts) >= 3:
                    dirs.clear()  # Do not descend further
                    continue

                # Filter hidden folders
                dirs[:] = [d for d in dirs if not d.startswith(".")]

                for f in files:
                    if query_str in f.lower():
                        full_path = os.path.join(root, f)
                        results.append(full_path)
                        _SESSION_FOUND_FILES.add(os.path.normpath(full_path))
                        if len(results) >= 10:
                            break
        except Exception as e:
            logger.debug("Error traversing %s: %s", root_dir, e)

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
        return {"ok": True, "result": f"He abierto la carpeta {name}."}

    return {"ok": False, "result": f"No reconozco la carpeta '{name}'. Las disponibles son: Escritorio, Descargas, Documentos, Imágenes, Música y Videos."}
