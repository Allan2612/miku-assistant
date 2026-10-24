"""
Miku Assistant - Notes Tools (tools/notes.py)
"""

import datetime
import logging
import re
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

from core.tools import tool

logger = logging.getLogger("miku.tools.notes")

NOTES_FILE = Path.home() / "Documents" / "notes.md"


DUPLICATE_WINDOW = datetime.timedelta(minutes=30)


def _last_note() -> Optional[Tuple[datetime.datetime, str]]:
    """(time, text) of the last note in the file, if it has the usual "- [YYYY-MM-DD HH:MM] text" shape."""
    if not NOTES_FILE.exists():
        return None
    lines = [l.strip() for l in NOTES_FILE.read_text(encoding="utf-8").splitlines() if l.strip()]
    m = re.match(r"^-\s*\[(\d{4}-\d{2}-\d{2} \d{2}:\d{2})\]\s*(.+)$", lines[-1]) if lines else None
    return (datetime.datetime.strptime(m.group(1), "%Y-%m-%d %H:%M"), m.group(2).strip()) if m else None


@tool(
    name="take_note",
    description="Anota un recordatorio, apunte o nota personal con fecha y hora en el archivo de notas (notes.md en Documentos)."
)
def take_note(text: str = "", note: str = "", content: str = "") -> Dict[str, Any]:
    """Guarda una nota con timestamp en ~/Documents/notes.md."""
    target_text = text or note or content
    clean_text = target_text.strip()
    if not clean_text:
        return {"ok": False, "result": "La nota no puede estar vacía."}

    now = datetime.datetime.now()
    entry = f"- [{now.strftime('%Y-%m-%d %H:%M')}] {clean_text}\n"

    try:
        # Asked "¿la guardaste?", the model saved the same note again (log 06:16): one copy is enough
        last = _last_note()
        if last and last[1].lower() == clean_text.lower() and now - last[0] < DUPLICATE_WINDOW:
            return {"ok": True, "result": f"Esa nota ya estaba guardada: '{clean_text}'."}
        NOTES_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(NOTES_FILE, "a", encoding="utf-8") as f:
            f.write(entry)
        return {"ok": True, "result": f"Nota guardada: '{clean_text}'."}
    except Exception as e:
        return {"ok": False, "result": f"Error al guardar la nota: {e}"}


@tool(
    name="read_notes",
    description="Lee las últimas notas guardadas en tu archivo de notas (notes.md en Documentos). Por defecto lee las últimas 3."
)
def read_notes(last_n: int = 3) -> Dict[str, Any]:
    """Lee las últimas notas de ~/Documents/notes.md."""
    if not NOTES_FILE.exists():
        return {"ok": True, "result": "Aún no tienes ninguna nota guardada."}

    try:
        with open(NOTES_FILE, "r", encoding="utf-8") as f:
            lines = [line.strip() for line in f if line.strip()]

        if not lines:
            return {"ok": True, "result": "Tu archivo de notas está vacío."}

        count = max(1, min(20, int(last_n)))
        # Read aloud: drop the "- [2026-10-20 02:58] " prefix, TTS spelled it out symbol by symbol
        recent = [re.sub(r"^-\s*\[[^\]]*\]\s*", "", line).rstrip(".") for line in lines[-count:] if not line.startswith("#")]
        if not recent:
            return {"ok": True, "result": "Tu archivo de notas está vacío."}
        head = "Tu última nota" if len(recent) == 1 else f"Tus últimas {len(recent)} notas"
        return {"ok": True, "result": f"{head}: " + ". ".join(recent) + "."}
    except Exception as e:
        return {"ok": False, "result": f"Error al leer las notas: {e}"}


@tool(
    name="open_notes",
    description="Abre el archivo de notas personales (notes.md) en el Bloc de notas para ver o editar todas tus notas en pantalla."
)
def open_notes() -> Dict[str, Any]:
    """Abre ~/Documents/notes.md en el editor predeterminado de Windows."""
    import os
    try:
        NOTES_FILE.parent.mkdir(parents=True, exist_ok=True)
        if not NOTES_FILE.exists():
            with open(NOTES_FILE, "w", encoding="utf-8") as f:
                f.write("# Notas de Miku\n\n")
        os.startfile(str(NOTES_FILE))
        return {"ok": True, "result": "He abierto tu archivo de notas en pantalla."}
    except Exception as e:
        return {"ok": False, "result": f"Error al abrir notas: {e}"}
