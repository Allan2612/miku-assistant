"""
Miku Assistant - Notes Tools (tools/notes.py)
"""

import datetime
import logging
from pathlib import Path
from typing import Dict, Any

from core.tools import tool

logger = logging.getLogger("miku.tools.notes")

NOTES_FILE = Path.home() / "Documents" / "notes.md"


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

    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    entry = f"- [{timestamp}] {clean_text}\n"

    try:
        NOTES_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(NOTES_FILE, "a", encoding="utf-8") as f:
            f.write(entry)
        return {"ok": True, "result": f"Nota guardada: '{clean_text}'."}
    except Exception as e:
        return {"ok": False, "result": f"Error al guardar la nota: {e}"}


@tool(
    name="read_notes",
    description="Lee las últimas notas guardadas en tu archivo de notas (notes.md en Documentos). Por defecto muestra las últimas 5."
)
def read_notes(last_n: int = 5) -> Dict[str, Any]:
    """Lee las últimas notas de ~/Documents/notes.md."""
    if not NOTES_FILE.exists():
        return {"ok": True, "result": "Aún no tienes ninguna nota guardada."}

    try:
        with open(NOTES_FILE, "r", encoding="utf-8") as f:
            lines = [line.strip() for line in f if line.strip()]

        if not lines:
            return {"ok": True, "result": "Tu archivo de notas está vacío."}

        count = max(1, min(20, int(last_n)))
        recent = lines[-count:]
        result_text = f"Tus últimas {len(recent)} nota(s):\n" + "\n".join(recent)
        return {"ok": True, "result": result_text}
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
