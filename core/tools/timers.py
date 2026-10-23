"""
Miku Assistant - Timers and Reminders Tools (tools/timers.py)
Timers survive a restart: each one is saved with its absolute due time in cache/timers.json.
"""

import asyncio
import datetime
import json
import logging
import time
from pathlib import Path
from typing import Dict, List, Optional, Callable, Awaitable, Any

from core.tools import tool

logger = logging.getLogger("miku.tools.timers")

# Registry: id -> {id, label, minutes, end_time, due (epoch s), task}
_TIMERS: Dict[int, Dict[str, Any]] = {}
_NEXT_TIMER_ID: int = 1
_TIMER_NOTIFIER: Optional[Callable[[str], Awaitable[None]]] = None
_MAIN_LOOP: Optional[asyncio.AbstractEventLoop] = None
MAX_TIMERS = 20

TIMERS_FILE = Path(__file__).resolve().parents[2] / "cache" / "timers.json"
# Missed while Miku was off: still announced at startup if it was due less than this long ago
MISSED_GRACE_S = 6 * 3600
# Missed ones wait this long at startup, so the frontend has connected and can show Miku
MISSED_DELAY_S = 15.0


def _save() -> None:
    try:
        data = [{k: v for k, v in t.items() if k != "task"} for t in _TIMERS.values()]
        TIMERS_FILE.parent.mkdir(parents=True, exist_ok=True)
        tmp = TIMERS_FILE.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        tmp.replace(TIMERS_FILE)
    except OSError as e:
        logger.warning("Could not save timers: %s", e)


def restore_timers() -> None:
    """Re-schedules the timers saved by a previous run. Called once at startup, after set_timer_notifier."""
    global _NEXT_TIMER_ID
    try:
        saved = json.loads(TIMERS_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return
    now = time.time()
    for t in saved if isinstance(saved, list) else []:
        try:
            tid, due, label = int(t["id"]), float(t["due"]), str(t["label"])
        except (KeyError, TypeError, ValueError):
            continue
        if tid in _TIMERS or due < now - MISSED_GRACE_S:
            continue
        _TIMERS[tid] = {**t, "id": tid, "task": None}
        _TIMERS[tid]["task"] = _schedule_worker(tid, max(due - now, MISSED_DELAY_S), label)
        _NEXT_TIMER_ID = max(_NEXT_TIMER_ID, tid + 1)
        logger.info("Restored timer #%d '%s' (due in %.0fs).", tid, label, max(due - now, MISSED_DELAY_S))
    _save()  # drops the ones too old to announce


def set_timer_notifier(callback: Callable[[str], Awaitable[None]], loop: Optional[asyncio.AbstractEventLoop] = None) -> None:
    """Sets the async callback used to notify user via Miku speech when a timer finishes."""
    global _TIMER_NOTIFIER, _MAIN_LOOP
    _TIMER_NOTIFIER = callback
    if loop is not None:
        _MAIN_LOOP = loop


def _schedule_worker(timer_id: int, duration_sec: float, label: str) -> Any:
    global _MAIN_LOOP
    target_loop = _MAIN_LOOP
    if target_loop is None or target_loop.is_closed():
        try:
            target_loop = asyncio.get_running_loop()
            _MAIN_LOOP = target_loop
        except RuntimeError:
            try:
                target_loop = asyncio.get_event_loop()
                _MAIN_LOOP = target_loop
            except RuntimeError:
                target_loop = None

    if target_loop is not None and not target_loop.is_closed():
        try:
            curr = asyncio.get_running_loop()
            if curr is target_loop:
                return target_loop.create_task(_timer_worker(timer_id, duration_sec, label))
        except RuntimeError:
            pass
        return asyncio.run_coroutine_threadsafe(_timer_worker(timer_id, duration_sec, label), target_loop)
    return None


async def _timer_worker(timer_id: int, duration_seconds: float, label: str) -> None:
    """Async background task that sleeps for duration_seconds and notifies user."""
    try:
        await asyncio.sleep(duration_seconds)
    except asyncio.CancelledError:
        # cancel_timer already removed it; on backend shutdown it stays saved and comes back next start
        logger.info("Timer #%d was cancelled.", timer_id)
        return

    _TIMERS.pop(timer_id, None)
    _save()
    logger.info("Timer #%d '%s' expired!", timer_id, label)
    msg = f"¡{label}!" if label.startswith("Recordatorio") else f"¡Tu temporizador de {label} ha terminado!"
    if _TIMER_NOTIFIER:
        try:
            await _TIMER_NOTIFIER(msg)
        except Exception as e:
            logger.error("Error triggering timer speech notification: %s", e)


@tool(
    name="set_timer",
    description="Programa un temporizador en minutos con una etiqueta opcional (ej: minutes: 5, label: 'hacer café'). Al terminar, Miku te avisará con voz."
)
def set_timer(minutes: float, label: str = "Temporizador") -> Dict[str, Any]:
    """Crea un temporizador asíncrono."""
    global _NEXT_TIMER_ID

    if minutes <= 0:
        return {"ok": False, "result": "La duración del temporizador debe ser mayor a 0 minutos."}
    if len(_TIMERS) >= MAX_TIMERS:
        return {"ok": False, "result": f"Ya hay {MAX_TIMERS} temporizadores activos; cancela alguno primero."}

    duration_sec = minutes * 60.0
    timer_id = _NEXT_TIMER_ID
    _NEXT_TIMER_ID += 1

    label = label.strip()
    clean_label = label if label and label.lower() != "temporizador" else f"{minutes:g} minutos"
    end_time = datetime.datetime.now() + datetime.timedelta(seconds=duration_sec)

    # Register before scheduling: a very short timer could finish (and pop itself) first (H-017)
    _TIMERS[timer_id] = {
        "id": timer_id,
        "label": clean_label,
        "minutes": minutes,
        "end_time": end_time.strftime("%H:%M"),
        "due": time.time() + duration_sec,
        "task": None,
    }
    _TIMERS[timer_id]["task"] = _schedule_worker(timer_id, duration_sec, clean_label)
    _save()

    return {"ok": True, "result": f"Temporizador #{timer_id} de {minutes} minuto(s) para '{clean_label}' configurado (sonará a las {end_time.strftime('%H:%M')})."}


@tool(
    name="set_reminder",
    description="Programa un recordatorio para una hora específica del día (formato HH:MM) con un texto (ej: time_str: '18:30', text: 'tomar agua')."
)
def set_reminder(time_str: str, text: str) -> Dict[str, Any]:
    """Programa un recordatorio a una hora fija en formato HH:MM."""
    global _NEXT_TIMER_ID
    clean_time = time_str.strip()

    if len(_TIMERS) >= MAX_TIMERS:
        return {"ok": False, "result": f"Ya hay {MAX_TIMERS} temporizadores activos; cancela alguno primero."}

    try:
        parts = clean_time.split(":")
        target_h = int(parts[0])
        target_m = int(parts[1])
    except Exception:
        return {"ok": False, "result": f"Formato de hora '{time_str}' inválido. Usa el formato HH:MM (ej: '15:30')."}

    now = datetime.datetime.now()
    target_dt = now.replace(hour=target_h, minute=target_m, second=0, microsecond=0)
    if target_dt <= now:
        target_dt += datetime.timedelta(days=1)  # Tomorrow

    diff_sec = (target_dt - now).total_seconds()
    timer_id = _NEXT_TIMER_ID
    _NEXT_TIMER_ID += 1

    label = f"Recordatorio: {text}"
    _TIMERS[timer_id] = {
        "id": timer_id,
        "label": label,
        "minutes": round(diff_sec / 60.0, 1),
        "end_time": target_dt.strftime("%H:%M"),
        "due": time.time() + diff_sec,
        "task": None,
    }
    _TIMERS[timer_id]["task"] = _schedule_worker(timer_id, diff_sec, label)
    _save()

    return {"ok": True, "result": f"Recordatorio #{timer_id} configurado para las {clean_time} ({round(diff_sec/60)} minutos a partir de ahora)."}


@tool(
    name="list_timers",
    description="Muestra todos los temporizadores y recordatorios activos actualmente."
)
def list_timers() -> Dict[str, Any]:
    """Devuelve la lista de temporizadores pendientes."""
    if not _TIMERS:
        return {"ok": True, "result": "No tienes temporizadores activos en este momento."}

    # Read aloud: no bullets or "#", which TTS spelled out
    items = [f"el {tid}, {info['label']}, a las {info['end_time']}" for tid, info in _TIMERS.items()]
    head = "Tienes un temporizador" if len(items) == 1 else f"Tienes {len(items)} temporizadores"
    return {"ok": True, "result": f"{head}: " + "; ".join(items) + "."}


@tool(
    name="cancel_timer",
    description="Cancela un temporizador o recordatorio activo por su ID numérico."
)
def cancel_timer(timer_id: int) -> Dict[str, Any]:
    """Cancela un temporizador por su ID."""
    info = _TIMERS.get(int(timer_id))
    if not info:
        return {"ok": False, "result": f"No existe ningún temporizador activo con el ID #{timer_id}."}

    task = info["task"]
    _TIMERS.pop(int(timer_id), None)
    _save()
    if task is not None:
        task.cancel()

    return {"ok": True, "result": f"Temporizador #{timer_id} ({info['label']}) cancelado."}
