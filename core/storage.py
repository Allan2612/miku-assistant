"""
Miku Assistant - How much disk Miku uses (panel › Almacenamiento), and the two things that can be freed safely:
the voice cache (it is made again when needed) and speech models Miku no longer uses. The logs are never offered.

    python -m core.storage scan              -> JSON
    python -m core.storage clean voice|unused_models
"""

from __future__ import annotations

import json
import os
import shutil
import sys
from pathlib import Path
from typing import Any, Dict, List

from core.paths import CACHE, DATA, PROGRAM

INSTALLED = DATA != PROGRAM
RUNTIME = Path(sys.prefix).parent if INSTALLED else Path(sys.prefix)  # installed: uv's Python + the libraries
try:
    from huggingface_hub.constants import HF_HUB_CACHE

    HUB = Path(HF_HUB_CACHE)
except ImportError:
    HUB = Path.home() / ".cache" / "huggingface" / "hub"
# Downloaded by Miku at some point; the ones she does not load now can go (the cache is shared with other programs:
# only these names are ever touched)
WHISPER = "models--Systran--faster-whisper-"
KNOWN_MODELS = ("models--lengyue233--content-vec-best", "models--facebook--hubert-base-ls960")


def size(path: Path) -> int:
    """Bytes under a file or folder (links not followed). A missing one is 0."""
    if path.is_file():
        return path.stat().st_size
    total, stack = 0, [path]
    while stack:
        try:
            with os.scandir(stack.pop()) as it:
                for entry in it:
                    if entry.is_dir(follow_symlinks=False):
                        stack.append(Path(entry.path))
                    else:
                        total += entry.stat(follow_symlinks=False).st_size
        except OSError:
            continue
    return total


def _speech_models() -> tuple[List[Path], List[Path]]:
    """(the Hugging Face models Miku loads, the ones of hers she does not load any more)."""
    from core.config import load_config

    whisper = load_config().stt.model
    used, unused = [], []
    for d in sorted(HUB.glob("models--*")) if HUB.is_dir() else []:
        mine = d.name.startswith(WHISPER) or d.name in KNOWN_MODELS
        if not mine:
            continue
        in_use = d.name == f"{WHISPER}{whisper}" or d.name == KNOWN_MODELS[0]
        (used if in_use else unused).append(d)
    return used, unused


def scan() -> Dict[str, Any]:
    used, unused = _speech_models()
    logs = sorted(CACHE.glob("*.log*"))
    torch = next(iter(RUNTIME.glob("**/site-packages/torch")), None) if RUNTIME.is_dir() else None
    data_total = size(CACHE) + sum(size(DATA / f) for f in ("config.yaml", ".env"))
    special = size(CACHE / "wake") + size(CACHE / "voice") + sum(size(p) for p in logs)
    program = size(PROGRAM) - size(PROGRAM / "models") if INSTALLED else size(PROGRAM / "core") - size(PROGRAM / "core" / ".venv")
    items = [
        {"key": "runtime", "name": "Python y librerías", "path": str(RUNTIME), "bytes": size(RUNTIME),
         "what": "incluye PyTorch, para la voz de Miku" if torch else "sin PyTorch (no hay GPU NVIDIA)",
         "torch": size(torch) if torch else 0},
        {"key": "speech", "name": "Modelos de voz", "path": str(HUB), "bytes": sum(size(d) for d in used),
         "what": "Whisper (te entiende) y ContentVec (voz de Miku)"},
        {"key": "models", "name": "Voz de Miku y palabra clave", "path": str(PROGRAM / "models"),
         "bytes": size(PROGRAM / "models"), "what": "modelos RVC y «Hey Miku»"},
        {"key": "program", "name": "Programa", "path": str(PROGRAM), "bytes": program, "what": "Miku y su panel"},
        {"key": "wake", "name": "Clips de «Hey Miku»", "path": str(CACHE / "wake"), "bytes": size(CACHE / "wake"),
         "what": "se borran solos: guarda los 200 últimos de cada tipo"},
        {"key": "logs", "name": "Logs", "path": str(CACHE), "bytes": sum(size(p) for p in logs),
         "what": "core.log rota solo: como mucho unos 8 MB"},
        {"key": "voice", "name": "Caché de voz", "path": str(CACHE / "voice"), "bytes": size(CACHE / "voice"),
         "what": "frases fijas ya dichas; se vuelve a crear sola", "clean": "voice"},
        {"key": "data", "name": "Tus datos", "path": str(DATA), "bytes": max(0, data_total - special),
         "what": "ajustes, memoria, conversaciones y recordatorios"},
    ]
    if unused:
        items.append({"key": "unused", "name": "Modelos que Miku ya no usa", "path": str(HUB),
                      "bytes": sum(size(d) for d in unused), "what": ", ".join(d.name.split("--")[-1] for d in unused),
                      "clean": "unused_models"})
    disk = shutil.disk_usage(DATA)
    return {"items": items, "total": sum(i["bytes"] for i in items), "free": disk.free, "disk": disk.total,
            "drive": DATA.anchor, "installed": INSTALLED}


def clean(what: str) -> Dict[str, Any]:
    """Frees one of the two safe things; the bytes freed. Anything else is refused."""
    if what == "voice":
        targets = [p for p in (CACHE / "voice").glob("*") if p.is_file()]
    elif what == "unused_models":
        targets = _speech_models()[1]
    else:
        return {"ok": False, "error": "No se puede borrar eso."}
    freed = 0
    for path in targets:
        n = size(path)
        try:
            shutil.rmtree(path) if path.is_dir() else path.unlink()
            freed += n
        except OSError:
            continue
    return {"ok": True, "freed": freed}


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    args = sys.argv[1:]
    if args[:1] == ["scan"]:
        print(json.dumps(scan(), ensure_ascii=False))
    elif args[:1] == ["clean"] and len(args) == 2:
        print(json.dumps(clean(args[1])))
    else:
        print("uso: python -m core.storage scan | clean voice|unused_models", file=sys.stderr)
        sys.exit(2)
