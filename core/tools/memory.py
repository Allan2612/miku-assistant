"""
Miku Assistant - Long-term Memory Tools (tools/memory.py)
Facts about the user, saved locally and added to every prompt. Remembering is a tool call inside the
turn's single request, so memory costs no extra Gemini request.
"""

import json
import logging
from pathlib import Path
from typing import Dict, Any, List

from core.tools import tool

logger = logging.getLogger("miku.tools.memory")

MEMORY_FILE = Path(__file__).resolve().parents[2] / "cache" / "memory.json"
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
