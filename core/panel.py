"""
Miku Assistant - What the panel shows: the state of each piece, Miku's processes and the quota. Read-only.

The panel asks over the same WebSocket ("panel_get"); every answer is built here, in a worker thread (process and
GPU counters block for a few ms).
"""

from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

import psutil

from core import quota
from core.browser import bridge

# Task Manager's grouping: what each process of the tree is, in the panel's words
_GROUPS = [
    ("app", "Miku Assistant", "ventana, bandeja y panel"),
    ("webview", "WebView2", "dibujo de Miku y del panel"),
    ("backend", "Backend", "Python · Whisper, Gemini, herramientas"),
    ("rvc", "Voz RVC", "Python · PyTorch en la GPU"),
]
_procs: Dict[int, psutil.Process] = {}  # kept between calls: cpu_percent() measures since the previous call
_gpu: Any = None
_gpu_failed = False
_obs_cache = (0.0, False)
_vram_size: Optional[int] = None


def _vram_total() -> int:
    """The graphics card's own memory, in bytes (0 if unknown): the scale of the panel's VRAM chart.
    From the display driver's registry key: WMI's AdapterRAM stops at 4 GB."""
    global _vram_size
    if _vram_size is None:
        _vram_size = 0
        try:
            import winreg

            key = r"SYSTEM\CurrentControlSet\Control\Class\{4d36e968-e325-11ce-bfc1-08002be10318}"
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, key) as root:
                for i in range(winreg.QueryInfoKey(root)[0]):
                    try:
                        with winreg.OpenKey(root, winreg.EnumKey(root, i)) as sub:
                            _vram_size = max(_vram_size, int(winreg.QueryValueEx(sub, "HardwareInformation.qwMemorySize")[0]))
                    except (OSError, ValueError):
                        continue
        except OSError:
            pass
    return _vram_size


def _gpu_counters() -> Any:
    global _gpu, _gpu_failed
    if _gpu is None and not _gpu_failed:
        try:
            from core.gpu_counters import GpuCounters
            _gpu = GpuCounters()
        except OSError:
            _gpu_failed = True  # no GPU counters on this PC: VRAM shows as unknown
    return _gpu


def _kind(p: psutil.Process) -> str:
    name = p.name().lower()
    if name == "msedgewebview2.exe":
        return "webview"
    if name.startswith("python"):
        return "rvc" if "rvc_worker" in " ".join(p.cmdline()) else "backend"
    return "app"


def processes() -> Dict[str, Any]:
    """Miku's process tree (from miku.exe when it started us), grouped like Task Manager, with CPU, memory and GPU."""
    root_pid = int(os.environ.get("MIKU_PARENT_PID") or os.getpid())
    try:
        root = psutil.Process(root_pid)
        tree = [root] + root.children(recursive=True)
    except psutil.Error:
        tree = [psutil.Process()]
    vram, gpu_use, gpu_total = _gpu_counters().read() if _gpu_counters() else ({}, {}, 0.0)
    cores = psutil.cpu_count() or 1
    totals = {key: {"cpu": 0.0, "ram": 0, "vram": 0.0, "gpu": 0.0, "count": 0} for key, _, _ in _GROUPS}
    alive = set()
    for p in tree:
        proc = _procs.setdefault(p.pid, p)
        alive.add(p.pid)
        try:
            with proc.oneshot():
                g = totals[_kind(proc)]
                g["cpu"] += proc.cpu_percent(None) / cores  # Task Manager's scale: % of the whole CPU
                try:
                    g["ram"] += proc.memory_full_info().uss  # ~ Task Manager's "Memoria" (private working set)
                except psutil.AccessDenied:
                    g["ram"] += proc.memory_info().rss
                g["vram"] += vram.get(proc.pid, 0.0)
                g["gpu"] += gpu_use.get(proc.pid, 0.0)
                g["count"] += 1
        except psutil.Error:
            continue
    for pid in list(_procs):
        if pid not in alive:
            del _procs[pid]
    groups = [{"key": key, "name": name, "what": what, **totals[key]} for key, name, what in _GROUPS
              if totals[key]["count"]]
    return {
        "groups": groups,
        "gpu_known": _gpu is not None,
        "gpu_total": gpu_total,
        "total": {k: sum(g[k] for g in groups) for k in ("cpu", "ram", "vram")},
        "ram_total": psutil.virtual_memory().total,
        "vram_total": _vram_total(),
    }


def _obs_running() -> bool:
    global _obs_cache
    at, running = _obs_cache
    if time.monotonic() - at > 10:  # a process scan: not every 2 s
        from core.tools.obs import obs_open
        _obs_cache = (time.monotonic(), obs_open())
    return _obs_cache[1]


def status(pipeline: Any) -> Dict[str, Any]:
    """Each piece of Miku, the model in use and the last turns."""
    from core.tools.windows import fullscreen_app_in_front

    brain, rvc, ww = pipeline.brain, pipeline.rvc, pipeline.wakeword
    now = time.monotonic()
    cooldowns = {m: round(t - now) for m, t in brain._model_cooldown.items() if t > now}
    snap = quota.snapshot()
    return {
        "pid": os.getpid(),
        "busy": pipeline.busy,
        "fullscreen": fullscreen_app_in_front(),
        "rvc": {"enabled": bool(rvc and rvc.enabled), "loaded": bool(rvc and rvc.is_loaded)},
        "wakeword": {"enabled": bool(ww and ww.enabled), "listening": bool(ww and ww._running and not ww._paused),
                     "threshold": getattr(ww, "threshold", None)},
        "opera": {"connected": bridge.connected, "tabs": len(bridge.tabs)},
        "obs": _obs_running(),
        "gemini": {"primary": brain.primary_model, "last_model": brain.last_model, "cooldowns": cooldowns,
                   "used": snap["counts"].get(brain.primary_model, 0),
                   "limit": quota.DAILY_LIMITS.get(brain.primary_model), "reset": snap["reset"]},
        "recent": list(brain.recent_turns)[:8],
    }


def quota_view(pipeline: Any) -> Dict[str, Any]:
    """Today per model in the fallback order, with their cooldowns, plus the last 7 days."""
    brain = pipeline.brain
    snap = quota.snapshot()
    now = time.monotonic()
    models: List[Dict[str, Any]] = []
    for m in brain.all_models:
        left = brain._model_cooldown.get(m, 0.0) - now
        models.append({"model": m, "used": snap["counts"].get(m, 0), "limit": quota.DAILY_LIMITS.get(m),
                       "cooldown": round(left) if left > 0 else 0, "primary": m == brain.primary_model})
    return {"models": models, "reset": snap["reset"], "week": snap["week"], "primary": brain.primary_model}


def timers_view() -> Dict[str, Any]:
    """Active timers and reminders, soonest first, and the pending notes."""
    import datetime

    from core.tools import timers
    from core.tools.notes import _notes

    items = []
    for t in sorted(timers._TIMERS.values(), key=lambda t: t["due"]):
        label = str(t["label"])
        items.append({"id": t["id"], "reminder": label.startswith("Recordatorio"),
                      "text": label.removeprefix("Recordatorio:").strip(), "when": timers._spoken_when(t),
                      "at": datetime.datetime.fromtimestamp(t["due"]).strftime("%H:%M"), "repeats": bool(t.get("every"))})
    try:
        pending = [text for _, text in _notes()]
    except OSError:
        pending = []
    return {"timers": items, "pending": pending}


def memory_view() -> Dict[str, Any]:
    """What she remembers about the user, and the days with an archived conversation (newest first)."""
    from core.tools.memory import CONVERSATIONS_DIR, memory_facts

    days = sorted((p.stem for p in CONVERSATIONS_DIR.glob("*.jsonl")), reverse=True) if CONVERSATIONS_DIR.exists() else []
    return {"facts": memory_facts(), "days": days}


def conversation(day: str) -> Dict[str, Any]:
    import json
    import re

    from core.tools.memory import CONVERSATIONS_DIR

    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", day or ""):  # a file name from the panel: never a path
        return {"day": day, "turns": []}
    path = CONVERSATIONS_DIR / f"{day}.jsonl"
    turns = []
    if path.is_file():
        for line in path.read_text(encoding="utf-8").splitlines():
            try:
                turns.append(json.loads(line))
            except ValueError:
                continue
    return {"day": day, "turns": turns}


def search(text: str, limit: int = 40) -> Dict[str, Any]:
    """Turns of every archived day whose words contain `text` (the panel's search in Memoria), newest first."""
    import json

    from core.tools.memory import CONVERSATIONS_DIR

    q = (text or "").strip().lower()
    hits: List[Dict[str, Any]] = []
    if len(q) < 2 or not CONVERSATIONS_DIR.exists():
        return {"q": text, "hits": hits}
    for path in sorted(CONVERSATIONS_DIR.glob("*.jsonl"), reverse=True):
        for line in reversed(path.read_text(encoding="utf-8").splitlines()):
            try:
                turn = json.loads(line)
            except ValueError:
                continue
            if q in f"{turn.get('user', '')} {turn.get('miku', '')}".lower():
                hits.append({"day": path.stem, **turn})
                if len(hits) >= limit:
                    return {"q": text, "hits": hits}
    return {"q": text, "hits": hits}


def act(action: str, args: Dict[str, Any]) -> Dict[str, Any]:
    """Changes made from the panel, through the same tools Miku uses: the same checks, the same files."""
    from core.tools import memory, notes, timers

    text = str(args.get("text", "")).strip()
    if action == "remind":
        def num(key: str) -> float:
            try:
                return float(args.get(key) or 0)
            except (TypeError, ValueError):
                return 0.0
        return timers.remind(text, minutes=num("minutes"), at=str(args.get("at") or ""), date=str(args.get("date") or ""),
                             every_minutes=num("every_minutes"))
    if action == "cancel_timer":
        return timers.cancel_timer(int(args.get("id", 0)))
    if action == "note_add":
        return notes.take_note(text)
    if action == "note_done":
        return notes.complete_note(text)
    if action == "note_delete":
        return notes.delete_note(text)
    if action == "fact_add":
        return memory.remember(text)
    if action in ("fact_delete", "fact_edit"):
        facts = memory.memory_facts()
        old = str(args.get("old", text))
        if old not in facts:
            return {"ok": False, "result": "Ese dato ya no estaba guardado."}
        new = str(args.get("new", "")).strip()
        memory._save([new if f == old else f for f in facts if new or f != old])  # exact fact, not "contains"
        return {"ok": True, "result": "Dato cambiado." if new else "Dato borrado."}
    return {"ok": False, "result": f"Acción desconocida: {action}"}


CLIP_NAME = r"\d{8}-\d{6}_\d\.\d{3}\.wav"
CLIP_FOLDERS = ("", "near", "silent")


def clip_path(folder: str, name: str) -> Optional[Path]:
    """A wake word clip from the panel: a known folder and the clip name pattern, never a path."""
    import re

    from core.wakeword import CLIPS_DIR

    if folder not in CLIP_FOLDERS or not re.fullmatch(CLIP_NAME, name or ""):
        return None
    path = (CLIPS_DIR / folder / name) if folder else CLIPS_DIR / name
    return path if path.is_file() else None


async def transcribe_clip(pipeline: Any, args: Dict[str, Any]) -> Dict[str, Any]:
    """What Whisper hears in a wake word clip ("¿Qué oyó?" on the panel), kept in cache/wake/heard.json."""
    import asyncio
    import json
    import wave

    import numpy as np

    from core.wakeword import CLIPS_DIR

    folder, name = str(args.get("folder", "")), str(args.get("name", ""))
    path = clip_path(folder, name)
    if path is None:
        return {"ok": False, "result": "No encuentro ese clip."}

    def load() -> Any:
        with wave.open(str(path)) as w:
            return np.frombuffer(w.readframes(w.getnframes()), np.int16).astype(np.float32) / 32768.0

    heard = await pipeline.stt.transcribe(await asyncio.to_thread(load))
    store = CLIPS_DIR / "heard.json"
    try:
        known = json.loads(store.read_text(encoding="utf-8")) if store.is_file() else {}
    except ValueError:
        known = {}
    known[f"{folder}/{name}" if folder else name] = heard
    store.write_text(json.dumps(known, ensure_ascii=False), encoding="utf-8")
    return {"ok": True, "result": heard}


def answer(pipeline: Any, what: str, args: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
    args = args or {}
    if what == "status":
        return status(pipeline)
    if what == "processes":
        return processes()
    if what == "quota":
        return quota_view(pipeline)
    if what == "timers":
        return timers_view()
    if what == "memory":
        return memory_view()
    if what == "conversation":
        return conversation(str(args.get("day", "")))
    if what == "search":
        return search(str(args.get("q", "")))
    if what.startswith("do:"):
        return act(what[3:], args)
    return None
