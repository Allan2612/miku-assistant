"""
Miku Assistant - What the panel shows: the state of each piece, Miku's processes and the quota. Read-only.

The panel asks over the same WebSocket ("panel_get"); every answer is built here, in a worker thread (process and
GPU counters block for a few ms).
"""

from __future__ import annotations

import os
import time
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


def answer(pipeline: Any, what: str) -> Optional[Dict[str, Any]]:
    if what == "status":
        return status(pipeline)
    if what == "processes":
        return processes()
    if what == "quota":
        return quota_view(pipeline)
    return None
