"""
Miku Assistant - Notes Tools (tools/notes.py)

Notes are a to-do list in ~/Documents/notes.md, one line each: "- [2026-10-26 10:30] text". Done ones get a
check mark ("- ✔ [2026-10-26 10:30] text"): they stay in the file, but are no longer read out as pending.
"""

import datetime
import logging
import re
import unicodedata
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from core.tools import tool

logger = logging.getLogger("miku.tools.notes")

NOTES_FILE = Path.home() / "Documents" / "notes.md"

DUPLICATE_WINDOW = datetime.timedelta(minutes=30)
DONE = "✔"
_NOTE_RE = re.compile(r"^-\s*(✔\s*)?\[(\d{4}-\d{2}-\d{2} \d{2}:\d{2})\]\s*(.+)$")
MAX_IN_STATE = 8


def _lines() -> List[str]:
    return NOTES_FILE.read_text(encoding="utf-8").splitlines() if NOTES_FILE.exists() else []


def _write(lines: List[str]) -> None:
    tmp = NOTES_FILE.with_suffix(".tmp")
    tmp.write_text("\n".join(lines) + "\n", encoding="utf-8")
    tmp.replace(NOTES_FILE)  # atomic: a crash mid-write cannot wipe the notes


def _notes(include_done: bool = False) -> List[Tuple[int, str]]:
    """(line number, text) of the notes, oldest first; only pending ones unless include_done."""
    found = []
    for i, line in enumerate(_lines()):
        m = _NOTE_RE.match(line.strip())
        if m and (include_done or not m.group(1)):
            found.append((i, m.group(3).strip()))
    return found


def _plain(text: str) -> str:
    """Lowercase, no accents or punctuation: "Subir el PR." matches "subir el pr"."""
    text = unicodedata.normalize("NFD", text.lower())
    return " ".join("".join(c for c in text if c.isalnum() or c == " ").split())  # accents split off: not alnum


_FILLER = {"lo", "la", "el", "los", "las", "de", "del", "que", "un", "una", "y", "a", "al", "en", "con", "para",
           "por", "mi", "mis", "ya", "nota", "pendiente"}


def _matching(query: str, include_done: bool = False) -> List[Tuple[int, str]]:
    """Notes with every meaningful word of the query, whole or as a word start: "ya subí lo del PR" finds
    "subir el PR" ("subi" starts "subir"), and "pr" does not match inside "comprar"."""
    words = [w for w in _plain(query).split() if w not in _FILLER] or _plain(query).split()

    def has(note_words: List[str], w: str) -> bool:
        return any(nw == w or (len(w) >= 3 and nw.startswith(w)) for nw in note_words)

    return [(i, t) for i, t in _notes(include_done) if words and all(has(_plain(t).split(), w) for w in words)]


def describe_pending() -> str:
    """Pending notes for the PC state ("" if none)."""
    pending = [t for _, t in _notes()]
    if not pending:
        return ""
    shown = "; ".join(pending[-MAX_IN_STATE:])
    more = f" (y {len(pending) - MAX_IN_STATE} más antiguos)" if len(pending) > MAX_IN_STATE else ""
    return f"{shown}{more}"


def _last_note() -> Optional[Tuple[datetime.datetime, str]]:
    """(time, text) of the last note in the file, if it has the usual "- [YYYY-MM-DD HH:MM] text" shape."""
    lines = [l.strip() for l in _lines() if l.strip()]
    m = _NOTE_RE.match(lines[-1]) if lines else None
    return (datetime.datetime.strptime(m.group(2), "%Y-%m-%d %H:%M"), m.group(3).strip()) if m else None


@tool(
    name="take_note",
    description="Apunta una nota o un pendiente en la lista del usuario (notes.md en Documentos)."
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
    description="Lee los pendientes y notas que el usuario aún no ha hecho ('qué pendientes tengo', 'qué me falta')."
)
def read_notes(last_n: int = 5) -> Dict[str, Any]:
    """Lee las notas pendientes más recientes de ~/Documents/notes.md."""
    try:
        pending = [t.rstrip(".") for _, t in _notes()]
    except OSError as e:
        return {"ok": False, "result": f"Error al leer las notas: {e}"}
    if not pending:
        return {"ok": True, "result": "No tienes pendientes."}
    count = max(1, min(20, int(last_n)))
    # Read aloud: no "- [2026-10-20 02:58]" prefix, TTS spelled it out symbol by symbol
    recent = pending[-count:]
    head = "Tienes un pendiente" if len(pending) == 1 else f"Tienes {len(pending)} pendientes"
    if len(recent) < len(pending):
        head += f"; los últimos {len(recent)}"
    return {"ok": True, "result": f"{head}: " + ". ".join(recent) + "."}


def _ambiguous(found: List[Tuple[int, str]], query: str) -> Optional[Dict[str, Any]]:
    if not found:
        pending = "; ".join(t for _, t in _notes()) or "ninguno"
        return {"ok": False, "result": f"No encontré una nota con '{query}'. Pendientes: {pending}."}
    if len(found) > 1:
        return {"ok": False, "result": "Hay varias: " + "; ".join(t for _, t in found) + ". ¿Cuál?"}
    return None


@tool(
    name="complete_note",
    description=(
        "Marca como hecho un pendiente de la lista cuando el usuario dice que ya lo hizo ('ya subí el PR'). "
        "text: palabras del pendiente tal como aparece en el estado del PC."
    ),
)
def complete_note(text: str) -> Dict[str, Any]:
    """Marca una nota pendiente como hecha (✔), sin borrarla."""
    found = _matching(text)
    if error := _ambiguous(found, text):
        return error
    i, done = found[0]
    lines = _lines()
    lines[i] = lines[i].replace("- [", f"- {DONE} [", 1)
    _write(lines)
    return {"ok": True, "result": f"Marqué como hecho: {done.rstrip('.')}."}


@tool(
    name="delete_note",
    description="Borra una nota de la lista (hecha o no) cuando el usuario pide quitarla o borrarla."
)
def delete_note(text: str) -> Dict[str, Any]:
    """Borra una nota del archivo."""
    found = _matching(text, include_done=True)
    if error := _ambiguous(found, text):
        return error
    i, gone = found[0]
    lines = _lines()
    del lines[i]
    _write(lines)
    return {"ok": True, "result": f"Borré la nota: {gone.rstrip('.')}."}


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
