"""
Miku Assistant - Routines (tools/routines.py)
Named lists of tool calls from config.yaml -> routines, run locally one after another.
"modo trabajo" goes through the fast path, so a routine costs 0 Gemini requests.
"""

import logging
import unicodedata
from typing import Dict, Any, Optional

from core.config import load_config
from core.tools import tool, get_tool_metadata

logger = logging.getLogger("miku.tools.routines")


def _norm(name: str) -> str:
    """'Modo Música' and 'musica' name the same routine."""
    key = name.strip().lower().removeprefix("modo ").strip()
    return unicodedata.normalize("NFKD", key).encode("ascii", "ignore").decode()


ROUTINES = {_norm(k): v for k, v in load_config().routines.items()}


def find_routine(name: str) -> Optional[str]:
    """Returns the routine's key if it exists."""
    key = _norm(name)
    return key if key in ROUTINES else None


@tool(
    name="run_routine",
    description="Ejecuta una rutina guardada (varias acciones seguidas) por su nombre, ej: 'trabajo'. Rutinas disponibles: "
    + (", ".join(ROUTINES) or "ninguna") + "."
)
def run_routine(name: str) -> Dict[str, Any]:
    """Ejecuta los pasos de una rutina de config.yaml."""
    key = find_routine(name)
    steps = ROUTINES.get(key) if key else None
    if not steps:
        return {"ok": False, "result": f"No tengo ninguna rutina llamada '{name}'."}

    failed = []
    for step in steps:
        tool_name = str(step.get("tool", ""))
        meta = get_tool_metadata(tool_name)
        # Destructive tools would only ask for confirmation mid-routine; routines are for harmless steps
        if meta is None or meta["destructive"] or tool_name == "run_routine":
            failed.append(tool_name or "?")
            continue
        res = meta["function"](**dict(step.get("args") or {}))
        if not res.get("ok"):
            failed.append(tool_name)
    if failed:
        return {"ok": False, "result": f"Rutina {key}: fallaron {', '.join(failed)}."}
    return {"ok": True, "result": f"¡Modo {key} activado!"}
