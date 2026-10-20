"""
Miku Assistant - Timers and Reminders Tools (tools/timers.py)
"""

import asyncio
import datetime
import logging
import time
from typing import Dict, List, Optional, Callable, Awaitable, Any

from core.tools import tool

logger = logging.getLogger("miku.tools.timers")

# In-memory timer registry
_TIMERS: Dict[int, Dict[str, Any]] = {}
_NEXT_TIMER_ID: int = 1
_TIMER_NOTIFIER: Optional[Callable[[str], Awaitable[None]]] = None
_MAIN_LOOP: Optional[asyncio.AbstractEventLoop] = None


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
        logger.info("Timer #%d '%s' expired!", timer_id, label)

        msg = f"¡Tu temporizador de {label} ha terminado!"
        if _TIMER_NOTIFIER:
            try:
                await _TIMER_NOTIFIER(msg)
            except Exception as e:
                logger.error("Error triggering timer speech notification: %s", e)

    except asyncio.CancelledError:
        logger.info("Timer #%d was cancelled.", timer_id)
    finally:
        _TIMERS.pop(timer_id, None)


@tool(
    name="set_timer",
    description="Programa un temporizador en minutos con una etiqueta opcional (ej: minutes: 5, label: 'hacer café'). Al terminar, Miku te avisará con voz."
)
def set_timer(minutes: float, label: str = "Temporizador") -> Dict[str, Any]:
    """Crea un temporizador asíncrono."""
    global _NEXT_TIMER_ID

    if minutes <= 0:
        return {"ok": False, "result": "La duración del temporizador debe ser mayor a 0 minutos."}

    duration_sec = minutes * 60.0
    timer_id = _NEXT_TIMER_ID
    _NEXT_TIMER_ID += 1

    clean_label = label.strip() or f"Temporizador de {minutes} min"
    end_time = datetime.datetime.now() + datetime.timedelta(seconds=duration_sec)

    task = _schedule_worker(timer_id, duration_sec, clean_label)

    _TIMERS[timer_id] = {
        "id": timer_id,
        "label": clean_label,
        "minutes": minutes,
        "end_time": end_time.strftime("%H:%M:%S"),
        "task": task,
    }

    return {"ok": True, "result": f"Temporizador #{timer_id} de {minutes} minuto(s) para '{clean_label}' configurado (sonará a las {end_time.strftime('%H:%M')})."}


@tool(
    name="set_reminder",
    description="Programa un recordatorio para una hora específica del día (formato HH:MM) con un texto (ej: time_str: '18:30', text: 'tomar agua')."
)
def set_reminder(time_str: str, text: str) -> Dict[str, Any]:
    """Programa un recordatorio a una hora fija en formato HH:MM."""
    global _NEXT_TIMER_ID
    clean_time = time_str.strip()

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
    task = _schedule_worker(timer_id, diff_sec, label)

    _TIMERS[timer_id] = {
        "id": timer_id,
        "label": label,
        "minutes": round(diff_sec / 60.0, 1),
        "end_time": target_dt.strftime("%H:%M:%S"),
        "task": task,
    }

    return {"ok": True, "result": f"Recordatorio #{timer_id} configurado para las {clean_time} ({round(diff_sec/60)} minutos a partir de ahora)."}


@tool(
    name="list_timers",
    description="Muestra todos los temporizadores y recordatorios activos actualmente."
)
def list_timers() -> Dict[str, Any]:
    """Devuelve la lista de temporizadores pendientes."""
    if not _TIMERS:
        return {"ok": True, "result": "No tienes temporizadores activos en este momento."}

    lines = []
    for tid, info in _TIMERS.items():
        lines.append(f"• #{tid}: {info['label']} (suena a las {info['end_time']})")

    return {"ok": True, "result": "Temporizadores activos:\n" + "\n".join(lines)}


@tool(
    name="cancel_timer",
    description="Cancela un temporizador o recordatorio activo por su ID numérico."
)
def cancel_timer(timer_id: int) -> Dict[str, Any]:
    """Cancela un temporizador por su ID."""
    info = _TIMERS.get(int(timer_id))
    if not info:
        return {"ok": False, "result": f"No existe ningún temporizador activo con el ID #{timer_id}."}

    task: asyncio.Task = info["task"]
    task.cancel()
    _TIMERS.pop(int(timer_id), None)

    return {"ok": True, "result": f"Temporizador #{timer_id} ({info['label']}) cancelado."}
