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
    # "Recordatorio: X" is how reminders are saved (also by older runs): said as a reminder, never as a timer
    msg = (f"¡Oye, recuerda: {label.removeprefix('Recordatorio:').strip()}!" if label.startswith("Recordatorio")
           else f"¡Tu temporizador de {label} ha terminado!")
    if _TIMER_NOTIFIER:
        try:
            await _TIMER_NOTIFIER(msg)
        except Exception as e:
            logger.error("Error triggering timer speech notification: %s", e)


def _add(label: str, seconds: float) -> Dict[str, Any]:
    """Registers and schedules one timer; returns its entry, or an error result if there are too many."""
    global _NEXT_TIMER_ID
    if len(_TIMERS) >= MAX_TIMERS:
        return {"ok": False, "result": f"Ya hay {MAX_TIMERS} temporizadores activos; cancela alguno primero."}
    timer_id = _NEXT_TIMER_ID
    _NEXT_TIMER_ID += 1
    end_time = datetime.datetime.now() + datetime.timedelta(seconds=seconds)
    # Register before scheduling: a very short timer could finish (and pop itself) first (H-017)
    _TIMERS[timer_id] = {
        "id": timer_id,
        "label": label,
        "minutes": round(seconds / 60.0, 1),
        "end_time": end_time.strftime("%H:%M"),
        "due": time.time() + seconds,
        "task": None,
    }
    _TIMERS[timer_id]["task"] = _schedule_worker(timer_id, seconds, label)
    _save()
    return _TIMERS[timer_id]


@tool(
    name="set_timer",
    description=(
        "Temporizador de cuenta atrás en minutos (ej: minutes: 5, label: 'el té'). Para que Miku le RECUERDE algo "
        "al usuario ('recuérdame...', 'ponme un recordatorio...'), usa remind."
    ),
)
def set_timer(minutes: float, label: str = "Temporizador") -> Dict[str, Any]:
    """Crea un temporizador asíncrono."""
    if minutes <= 0:
        return {"ok": False, "result": "La duración del temporizador debe ser mayor a 0 minutos."}
    label = label.strip()
    clean_label = label if label and label.lower() != "temporizador" else f"{minutes:g} minutos"
    t = _add(clean_label, minutes * 60.0)
    if "id" not in t:
        return t
    return {"ok": True, "result": f"Temporizador #{t['id']} de {minutes:g} minuto(s) para '{clean_label}' configurado (sonará a las {t['end_time']})."}


@tool(
    name="remind",
    description=(
        "Recuerda algo al usuario más tarde. Usa minutes para 'en N minutos/horas' (horas = minutos x 60) o at "
        "('HH:MM', 24 h) para una hora del día; no los dos. Ej: text: 'tomar agua', minutes: 1."
    ),
)
def remind(text: str, minutes: float = 0, at: str = "") -> Dict[str, Any]:
    """Programa un recordatorio en N minutos o a una hora (hoy, o mañana si ya pasó)."""
    what = text.strip()
    if not what:
        return {"ok": False, "result": "¿Qué quieres que te recuerde?"}
    now = datetime.datetime.now()
    if minutes and minutes > 0:
        seconds = minutes * 60.0
    elif at:
        try:
            hour, minute = (int(x) for x in at.strip().split(":")[:2])
            target = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        except ValueError:
            return {"ok": False, "result": f"Hora '{at}' inválida. Usa HH:MM (ej: '15:30')."}
        # The current minute is "now", not tomorrow: the model wrote 10:10 for "in a minute" at 10:09:41
        if target <= now - datetime.timedelta(minutes=1):
            target += datetime.timedelta(days=1)
        seconds = max((target - now).total_seconds(), 1.0)
    else:
        return {"ok": False, "result": "Dime cuándo: en cuántos minutos o a qué hora."}
    t = _add(f"Recordatorio: {what}", seconds)
    if "id" not in t:
        return t
    day = " de mañana" if datetime.datetime.fromtimestamp(t["due"]).date() > now.date() else ""
    return {"ok": True, "result": f"Recordatorio #{t['id']} para las {t['end_time']}{day}: {what}."}


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
