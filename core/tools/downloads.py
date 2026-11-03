"""
Miku Assistant - "Avísame cuando termine la descarga" (tools/downloads.py)

A download in progress is a temp file in the Downloads folder: Opera ".opdownload", Chrome/Edge ".crdownload",
Firefox ".part". When it disappears, the download ended: finished if the final file is there, cancelled if not.
The news goes out like a reminder (timers.announce).
"""

import logging
import threading
import time
from pathlib import Path
from typing import Dict, List, Set

from core.tools import tool
from core.tools.timers import announce

logger = logging.getLogger("miku.tools.downloads")

DOWNLOADS = Path.home() / "Downloads"
TEMP_SUFFIXES = (".opdownload", ".crdownload", ".part")
POLL_S = 2.0
MAX_WAIT_S = 4 * 3600
RECENT_S = 120  # a finished file renamed by the browser ("x (1).zip") is still this fresh

_watching: Set[Path] = set()
_lock = threading.Lock()


def _in_progress() -> List[Path]:
    try:
        return [p for p in DOWNLOADS.iterdir() if p.suffix.lower() in TEMP_SUFFIXES]
    except OSError:
        return []


def _final_name(temp: Path) -> str:
    return temp.name[: -len(temp.suffix)]  # "juego.zip.opdownload" -> "juego.zip"


def _finished(name: str) -> bool:
    """The final file is there, also as "name (1).ext" when one with that name already existed."""
    if (DOWNLOADS / name).exists():
        return True
    stem, now = Path(name).stem, time.time()
    try:
        return any(f.name.startswith(stem) and f.suffix.lower() not in TEMP_SUFFIXES and now - f.stat().st_mtime < RECENT_S
                   for f in DOWNLOADS.iterdir())
    except OSError:
        return False


def _watch(files: List[Path]) -> None:
    pending: Dict[Path, str] = {p: _final_name(p) for p in files}
    deadline = time.monotonic() + MAX_WAIT_S
    while pending and time.monotonic() < deadline:
        time.sleep(POLL_S)
        now_in_progress = _in_progress()
        for temp in [p for p in pending if not p.exists()]:
            name = pending.pop(temp)
            with _lock:
                _watching.discard(temp)
            if _finished(name):
                announce(f"¡Terminó la descarga de {name}!")
            elif not any(p not in pending and p not in _watching for p in now_in_progress):
                announce(f"La descarga de {name} se canceló.")
            # else: the browser renamed its temp file ("Unconfirmed 123.crdownload" -> "x.zip.crdownload")
            for p in now_in_progress:
                with _lock:
                    if p not in _watching:
                        _watching.add(p)
                        pending[p] = _final_name(p)
    with _lock:
        _watching.difference_update(pending)  # gave up after MAX_WAIT_S


@tool(
    name="watch_downloads",
    description="Avisa cuando terminen las descargas que están en curso en la carpeta Descargas "
                "('avísame cuando termine la descarga').",
)
def watch_downloads() -> Dict[str, object]:
    """Vigila las descargas en curso y avisa al terminar."""
    files = _in_progress()
    if not files:
        return {"ok": False, "result": "No veo ninguna descarga en curso en Descargas."}
    with _lock:
        new = [p for p in files if p not in _watching]
        _watching.update(new)
    if new:
        # shortcut: one polling thread per request (2 s), fine for a few downloads; a folder watcher if it grows
        threading.Thread(target=_watch, args=(new,), daemon=True, name="miku-downloads").start()
    names = ", ".join(_final_name(p) for p in files)
    return {"ok": True, "result": f"¡Vale! Te aviso cuando termine {names}." if len(files) == 1
            else f"¡Vale! Te aviso cuando terminen: {names}."}
