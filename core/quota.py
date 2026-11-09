"""
Miku Assistant - Gemini requests used today, per model (free tier).

Google resets the daily quota at midnight Pacific time. Every request sent is counted, answered or not: Google
counts the ones that time out too (3-nov: gemini-3-flash-preview said "quota exhausted" after 20 sent, of which only
17 had answered). Saved in cache/quota.json, so a restart does not reset the count.
"""

from __future__ import annotations

import datetime
import json
import logging
from typing import Dict, Optional

from core.paths import CACHE

logger = logging.getLogger("miku.quota")

QUOTA_FILE = CACHE / "quota.json"
# Requests per day on the free tier (docs/mejoras.md, 24-oct). Unknown models are counted, not judged
DAILY_LIMITS = {
    "gemini-3.5-flash-lite": 500,
    "gemini-3.1-flash-lite": 500,
    "gemini-3-flash-preview": 20,
    "gemini-3.5-flash": 20,
    "gemini-3.8-flash": 20,
    "gemma-4-26b-a4b-it": 14400,
}
WARN_AT = 0.9
HISTORY_DAYS = 14


def _first_sunday(year: int, month: int) -> datetime.date:
    first = datetime.date(year, month, 1)
    return first + datetime.timedelta(days=(6 - first.weekday()) % 7)


def pacific_now(utc: Optional[datetime.datetime] = None) -> datetime.datetime:
    """Pacific time without tzdata (not installed): US daylight time runs from the second Sunday of March,
    2:00 local (10:00 UTC), to the first Sunday of November, 2:00 local (9:00 UTC)."""
    utc = (utc or datetime.datetime.now(datetime.timezone.utc)).replace(tzinfo=None)
    start = datetime.datetime.combine(_first_sunday(utc.year, 3) + datetime.timedelta(days=7), datetime.time(10))
    end = datetime.datetime.combine(_first_sunday(utc.year, 11), datetime.time(9))
    return utc + datetime.timedelta(hours=-7 if start <= utc < end else -8)


def _load() -> Dict:
    try:
        data = json.loads(QUOTA_FILE.read_text(encoding="utf-8"))
        if isinstance(data, dict) and isinstance(data.get("counts"), dict):
            return data
    except (OSError, ValueError):
        pass
    return {}


def _today(data: Dict) -> Dict:
    """The saved counts if they are today's (Pacific), else a fresh day."""
    day = pacific_now().date().isoformat()
    if data.get("day") != day:
        data = {"day": day, "counts": {}, "warned": [], "history": data.get("history") or {}}
    return data


def count(model: str, primary: str) -> Optional[str]:
    """Counts one request sent. Returns a warning to say once a day when the primary model reaches 90%."""
    data = _today(_load())
    data["counts"][model] = data["counts"].get(model, 0) + 1
    # Per day, for the panel's last-7-days chart
    history = data.setdefault("history", {})
    history[data["day"]] = dict(data["counts"])
    for old in sorted(history)[:-HISTORY_DAYS]:
        del history[old]
    used, limit = data["counts"][model], DAILY_LIMITS.get(model)
    warning = None
    if model == primary and limit and used >= limit * WARN_AT and model not in data.get("warned", []):
        data.setdefault("warned", []).append(model)
        warning = f"Ojo: ya usé {used} de las {limit} peticiones de hoy de mi modelo principal."
    try:
        QUOTA_FILE.parent.mkdir(parents=True, exist_ok=True)
        tmp = QUOTA_FILE.with_suffix(".tmp")
        tmp.write_text(json.dumps(data), encoding="utf-8")
        tmp.replace(QUOTA_FILE)
    except OSError as e:
        logger.warning("Could not save the quota count: %s", e)
    return warning


def spent(model: str) -> bool:
    """Today's bucket of this model is used up: trying it only wastes a request and the user's time."""
    limit = DAILY_LIMITS.get(model)
    return bool(limit) and _today(_load())["counts"].get(model, 0) >= limit


def snapshot() -> Dict:
    """Today's counts per model, the limits, the last 7 days and when the quota renews (for the panel)."""
    data = _today(_load())
    pacific = pacific_now()
    to_midnight = datetime.datetime.combine(pacific.date() + datetime.timedelta(days=1), datetime.time()) - pacific
    reset = datetime.datetime.now() + to_midnight + datetime.timedelta(seconds=30)
    days = [(pacific.date() - datetime.timedelta(days=n)).isoformat() for n in range(6, -1, -1)]
    history = data.get("history") or {}
    return {"day": data["day"], "counts": data["counts"], "limits": DAILY_LIMITS, "reset": f"{reset:%H:%M}",
            "week": [{"day": d, "counts": history.get(d, {})} for d in days]}


def describe(primary: str) -> str:
    """Today's use, said aloud: the primary model against its limit, the fallbacks together, and the reset time."""
    counts = _today(_load())["counts"]
    used = counts.get(primary, 0)
    limit = DAILY_LIMITS.get(primary)
    text = (f"Hoy llevo {used} de {limit} peticiones en mi modelo principal; me quedan {max(limit - used, 0)}."
            if limit else f"Hoy llevo {used} peticiones en mi modelo principal.")
    others = sum(n for m, n in counts.items() if m != primary)
    if others:
        text += f" Y {others} en los modelos de respaldo."
    # Next Pacific midnight, in the user's clock
    pacific = pacific_now()
    to_midnight = datetime.datetime.combine(pacific.date() + datetime.timedelta(days=1), datetime.time()) - pacific
    reset = datetime.datetime.now() + to_midnight + datetime.timedelta(seconds=30)  # whole minutes
    return f"{text} La cuota se renueva a las {reset:%H:%M}."
