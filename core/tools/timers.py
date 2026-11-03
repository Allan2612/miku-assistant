"""
Miku Assistant - Timers and Reminders Tools (tools/timers.py)
Timers survive a restart: each one is saved with its absolute due time in cache/timers.json.
Reminders can be on a date ("el viernes a las 8") and repeat ("todos los días a las 9", "cada 2 horas").
"""

import asyncio
import datetime
import difflib
import json
import logging
import time
from pathlib import Path
from typing import Dict, List, Optional, Callable, Awaitable, Any

from core.tools import tool

logger = logging.getLogger("miku.tools.timers")

# Registry: id -> {id, label, minutes, end_time, due (epoch s), every (s, 0 = once), task}
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
DAY_S, WEEK_S = 86400, 7 * 86400
DUPLICATE_WINDOW_S = 90

_WEEKDAYS = ("lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo")
_MONTHS = ("enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre", "octubre",
           "noviembre", "diciembre")


def _spoken_when(t: Dict[str, Any]) -> str:
    """When it sounds, as said aloud: "a las 18:30", "mañana a las 08:00", "todos los días a las 09:00"."""
    due = datetime.datetime.fromtimestamp(t["due"])
    every = t.get("every", 0)
    at = f"a las {due:%H:%M}"
    if every == DAY_S:
        return f"todos los días {at}"
    if every == WEEK_S:
        return f"cada {_WEEKDAYS[due.weekday()]} {at}"
    if every:
        minutes = every / 60
        step = f"cada {minutes / 60:g} horas" if minutes % 60 == 0 else f"cada {minutes:g} minutos"
        return f"{step}, la próxima {at}"
    days = (due.date() - datetime.date.today()).days
    if days <= 0:
        return at
    if days == 1:
        return f"mañana {at}"
    if days < 7:
        return f"el {_WEEKDAYS[due.weekday()]} {at}"
    return f"el {due.day} de {_MONTHS[due.month - 1]} {at}"


def describe_timers() -> str:
    """The active timers and reminders as one spoken line ("" if none)."""
    return "; ".join(f"el {t['id']}, {t['label']}, {_spoken_when(t)}" for t in _TIMERS.values())


def describe_today() -> str:
    """Today's timers and reminders still to come, in time order, as one spoken line ("" if none)."""
    today = datetime.date.today()
    due_today = sorted((t["due"], t["label"]) for t in _TIMERS.values()
                       if datetime.date.fromtimestamp(t["due"]) == today)
    return "; ".join(f"{label.removeprefix('Recordatorio:').strip()} a las {datetime.datetime.fromtimestamp(due):%H:%M}"
                     for due, label in due_today)


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
            tid, due, label, every = int(t["id"]), float(t["due"]), str(t["label"]), float(t.get("every", 0))
        except (KeyError, TypeError, ValueError):
            continue
        if every > 0 and due < now - MISSED_GRACE_S:
            while due < now:  # a repeating one missed long ago: on to its next time, it is not dropped
                due += every
        if tid in _TIMERS or due < now - MISSED_GRACE_S:
            continue
        _TIMERS[tid] = {**t, "id": tid, "due": due, "every": every, "task": None}
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


def announce(message: str) -> None:
    """Says something out of turn, like a reminder (shown or not, no mic after it). From any thread."""
    if _TIMER_NOTIFIER is None or _MAIN_LOOP is None or _MAIN_LOOP.is_closed():
        logger.warning("Nothing can announce '%s' (no notifier yet).", message)
        return
    asyncio.run_coroutine_threadsafe(_TIMER_NOTIFIER(message), _MAIN_LOOP)


def _schedule_worker(timer_id: int, duration_sec: float, label: str) -> Any:
    # Tools run in worker threads (asyncio.to_thread): from there the worker goes to the pipeline's loop
    try:
        running = asyncio.get_running_loop()
    except RuntimeError:
        running = None
    loop = _MAIN_LOOP if _MAIN_LOOP is not None and not _MAIN_LOOP.is_closed() else running
    if loop is None:
        return None
    coro = _timer_worker(timer_id, duration_sec, label)
    if loop is running:
        return loop.create_task(coro)
    return asyncio.run_coroutine_threadsafe(coro, loop)


async def _timer_worker(timer_id: int, duration_seconds: float, label: str) -> None:
    """Async background task that sleeps for duration_seconds and notifies user."""
    try:
        await asyncio.sleep(duration_seconds)
    except asyncio.CancelledError:
        # cancel_timer already removed it; on backend shutdown it stays saved and comes back next start
        logger.info("Timer #%d was cancelled.", timer_id)
        return

    info = _TIMERS.get(timer_id)
    if info and info.get("every"):
        # Repeating: same id, next time (skipping the ones that passed while the PC slept)
        now, due = time.time(), info["due"]
        while due <= now:
            due += info["every"]
        info.update(due=due, end_time=datetime.datetime.fromtimestamp(due).strftime("%H:%M"))
        info["task"] = _schedule_worker(timer_id, due - now, label)
    else:
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


def _add(label: str, seconds: float, every: float = 0) -> Dict[str, Any]:
    """Registers and schedules one timer; returns its entry, or an error result if there are too many."""
    global _NEXT_TIMER_ID
    # The model sometimes replays the last order on a "gracias" (log 3-nov: "Jarolito" then "Harolito", same 2
    # minutes): an almost equal one due at about the same time is the same reminder
    due = time.time() + seconds
    for t in _TIMERS.values():
        if (abs(t["due"] - due) < DUPLICATE_WINDOW_S and t.get("every", 0) == every
                and difflib.SequenceMatcher(None, t["label"].lower(), label.lower()).ratio() > 0.8):
            logger.info("Timer '%s' is a repeat of #%d: not added twice.", label, t["id"])
            return t
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
        "every": every,
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
        "Recuerda algo al usuario más tarde. Cuándo: minutes ('en N minutos/horas', horas = minutos x 60) o at "
        "('HH:MM', 24 h), con date ('AAAA-MM-DD') si no es hoy: calcula 'mañana' o 'el viernes' desde la fecha "
        "actual. Para repetir, every_minutes: 1440 = todos los días, 10080 = cada semana, 120 = cada 2 horas. "
        "Ej: text: 'tomar agua', minutes: 1. Ej: text: 'la cita', at: '08:00', date: '2026-10-30'."
    ),
)
def remind(text: str, minutes: float = 0, at: str = "", date: str = "", every_minutes: float = 0) -> Dict[str, Any]:
    """Programa un recordatorio: en N minutos o a una hora (hoy, en una fecha o mañana si ya pasó), quizá repetido."""
    what = text.strip()
    if not what:
        return {"ok": False, "result": "¿Qué quieres que te recuerde?"}
    every = max(float(every_minutes or 0), 0.0) * 60
    now = datetime.datetime.now()
    if minutes and minutes > 0:
        seconds = minutes * 60.0
    elif at or date:
        try:
            hour, minute = (int(x) for x in (at or "09:00").strip().split(":")[:2])
            day = datetime.date.fromisoformat(date.strip()) if date else now.date()
            target = datetime.datetime.combine(day, datetime.time(hour, minute))
        except ValueError:
            return {"ok": False, "result": f"Fecha u hora inválida ('{date}' '{at}'). Usa AAAA-MM-DD y HH:MM."}
        late = now - datetime.timedelta(minutes=1)  # the current minute is "now": 10:10 said at 10:09:41
        if date and target < late and not every:
            return {"ok": False, "result": f"Esa fecha ya pasó ({target:%Y-%m-%d %H:%M})."}
        while target < late:
            target += datetime.timedelta(seconds=every) if every else datetime.timedelta(days=1)
        seconds = max((target - now).total_seconds(), 1.0)
    elif every:
        seconds = every  # "cada 2 horas": the first one in 2 hours
    else:
        return {"ok": False, "result": "Dime cuándo: en cuántos minutos o a qué hora."}
    t = _add(f"Recordatorio: {what}", seconds, every)
    if "id" not in t:
        return t
    return {"ok": True, "result": f"Recordatorio #{t['id']}, {_spoken_when(t)}: {what}."}


@tool(
    name="list_timers",
    description="Dice los temporizadores y recordatorios activos, con cuándo suenan."
)
def list_timers() -> Dict[str, Any]:
    """Devuelve la lista de temporizadores pendientes."""
    if not _TIMERS:
        return {"ok": True, "result": "No tienes temporizadores ni recordatorios activos."}
    # Read aloud: no bullets or "#", which TTS spelled out
    head = "Tienes un aviso" if len(_TIMERS) == 1 else f"Tienes {len(_TIMERS)} avisos"
    return {"ok": True, "result": f"{head}: {describe_timers()}."}


@tool(
    name="cancel_timer",
    description="Cancela un temporizador o recordatorio activo (también uno que se repite) por su ID numérico."
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
