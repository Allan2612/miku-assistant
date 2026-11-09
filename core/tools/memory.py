"""
Miku Assistant - Long-term Memory Tools (tools/memory.py)
Facts about the user, saved locally and added to every prompt. Remembering is a tool call inside the
turn's single request, so memory costs no extra Gemini request.
"""

import datetime
import json
import logging
from typing import Dict, Any, List

from core.paths import CACHE
from core.tools import tool

logger = logging.getLogger("miku.tools.memory")

MEMORY_FILE = CACHE / "memory.json"
# Every conversation, one file per day: searched only when the user asks about it (no daily summary request)
CONVERSATIONS_DIR = MEMORY_FILE.parent / "conversations"
MAX_RECALL_CHARS = 1500
# Every fact rides along in every request: keep the prompt (and its tokens) bounded
MAX_FACTS = 50


def memory_facts() -> List[str]:
    """Returns the saved facts, oldest first. A missing or broken file means no memory, never a crash."""
    try:
        facts = json.loads(MEMORY_FILE.read_text(encoding="utf-8"))
        return [str(f) for f in facts] if isinstance(facts, list) else []
    except (OSError, ValueError):
        return []


def _save(facts: List[str]) -> None:
    MEMORY_FILE.parent.mkdir(parents=True, exist_ok=True)
    tmp = MEMORY_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(facts, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(MEMORY_FILE)  # atomic: a crash mid-write cannot wipe the memory


@tool(
    name="remember",
    description="Guarda para siempre un dato sobre el usuario que valga la pena recordar en futuras conversaciones (gustos, nombres, cumpleaños, datos personales que te cuente). Una frase corta en tercera persona, ej: 'Le gusta el anime Frieren'."
)
def remember(fact: str) -> Dict[str, Any]:
    """Añade un dato a la memoria a largo plazo."""
    clean = " ".join(fact.split())
    if not clean:
        return {"ok": False, "result": "No hay nada que recordar."}
    facts = [f for f in memory_facts() if f.lower() != clean.lower()]
    facts.append(clean)
    _save(facts[-MAX_FACTS:])
    return {"ok": True, "result": f"Lo recordaré: {clean}."}


@tool(
    name="forget",
    description="Olvida los datos guardados sobre el usuario que contengan el texto indicado (cuando pide que olvides algo)."
)
def forget(text: str) -> Dict[str, Any]:
    """Borra de la memoria los datos que contienen el texto."""
    q = text.strip().lower()
    facts = memory_facts()
    kept = [f for f in facts if q not in f.lower()] if q else facts
    if len(kept) == len(facts):
        return {"ok": False, "result": f"No tenía nada guardado sobre '{text}'."}
    _save(kept)
    return {"ok": True, "result": f"Olvidé {len(facts) - len(kept)} dato(s) sobre '{text}'."}


def archive_turn(user_text: str, model_text: str) -> None:
    """Appends one exchange to today's conversation file. Never raises: losing a log line beats losing a turn."""
    try:
        CONVERSATIONS_DIR.mkdir(parents=True, exist_ok=True)
        now = datetime.datetime.now()
        line = json.dumps({"at": now.strftime("%H:%M"), "user": user_text, "miku": model_text}, ensure_ascii=False)
        with open(CONVERSATIONS_DIR / f"{now:%Y-%m-%d}.jsonl", "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except OSError as e:
        logger.warning("Could not archive the conversation turn: %s", e)


@tool(
    name="recall_conversation",
    description=(
        "Busca en las conversaciones de otros días cuando el usuario pregunta qué hablaron ('¿de qué hablamos ayer?', "
        "'¿qué te dije del banco?'). date: 'AAAA-MM-DD' (vacío = el último día anterior a hoy con conversación); "
        "text: palabras a buscar en todos los días (vacío = todo ese día)."
    ),
)
def recall_conversation(date: str = "", text: str = "") -> Dict[str, Any]:
    """Devuelve lo hablado un día, o los turnos que mencionan algo."""
    days = sorted(CONVERSATIONS_DIR.glob("*.jsonl")) if CONVERSATIONS_DIR.exists() else []
    if date:
        days = [d for d in days if d.stem == date.strip()]
    elif not text:
        today = datetime.date.today().isoformat()
        days = [d for d in days if d.stem < today][-1:]
    words = text.lower().split()
    found: List[str] = []
    for day in reversed(days):  # newest first: the budget goes to the most recent
        for raw in day.read_text(encoding="utf-8").splitlines():
            try:
                t = json.loads(raw)
            except ValueError:
                continue
            said = f"{t.get('user', '')} {t.get('miku', '')}".lower()
            if all(w in said for w in words):
                found.append(f"{day.stem} {t.get('at', '')}: el usuario dijo '{t.get('user', '')}' y Miku '{t.get('miku', '')}'")
    if not found:
        return {"ok": True, "result": "No encontré nada de eso en conversaciones anteriores."}
    out = ""
    for line in found:
        if len(out) + len(line) > MAX_RECALL_CHARS:
            break
        out += line + "\n"
    return {"ok": True, "result": out.strip()}
