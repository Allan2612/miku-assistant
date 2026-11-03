"""Timers survive a backend restart: saved on set/cancel/expire, restored at startup, kept on shutdown.

Uses a temp timers file; nothing touches cache/timers.json.
Run: core\\.venv\\Scripts\\python.exe -m tests.test_timers  (or with pytest)
"""

import asyncio
import datetime
import json
import tempfile
import time
from pathlib import Path

import core.tools.timers as timers

timers.TIMERS_FILE = Path(tempfile.mkdtemp()) / "timers.json"


def saved():
    return json.loads(timers.TIMERS_FILE.read_text(encoding="utf-8"))


async def _flow():
    heard = []

    async def notify(msg):
        heard.append(msg)

    timers.set_timer_notifier(notify, loop=asyncio.get_running_loop())
    timers.set_timer(10, "pizza")
    timers.set_timer(0.001, "huevo")  # 60 ms
    assert [t["label"] for t in saved()] == ["pizza", "huevo"]
    assert "Tienes 2 avisos" in timers.list_timers()["result"]

    await asyncio.sleep(0.3)
    assert heard == ["¡Tu temporizador de huevo ha terminado!"] and [t["label"] for t in saved()] == ["pizza"]

    # Shutdown cancels the task: the timer must stay saved for the next start
    timers._TIMERS[1]["task"].cancel()
    await asyncio.sleep(0)
    assert [t["label"] for t in saved()] == ["pizza"]


async def _restart():
    heard = []

    async def notify(msg):
        heard.append(msg)

    timers._TIMERS.clear()
    now = time.time()
    timers.TIMERS_FILE.write_text(json.dumps([
        {"id": 7, "label": "pizza", "minutes": 10, "end_time": "15:00", "due": now + 600},
        {"id": 8, "label": "viejo", "minutes": 1, "end_time": "01:00", "due": now - 2 * timers.MISSED_GRACE_S},
    ]), encoding="utf-8")
    timers.set_timer_notifier(notify, loop=asyncio.get_running_loop())
    timers.restore_timers()
    assert list(timers._TIMERS) == [7], "too-old missed timers are dropped"
    assert [t["id"] for t in saved()] == [7]
    assert timers.set_timer(1, "té")["result"].startswith("Temporizador #8"), "ids continue after restored ones"
    assert timers.cancel_timer(7)["ok"] and [t["label"] for t in saved()] == ["té"]


async def _reminders():
    heard = []

    async def notify(msg):
        heard.append(msg)

    timers._TIMERS.clear()
    timers.set_timer_notifier(notify, loop=asyncio.get_running_loop())
    # Minutes or a clock time, one tool; announced as a reminder, never "tu temporizador de..." (log, 26-oct)
    assert timers.remind("tomar agua", minutes=0.001)["ok"]
    await asyncio.sleep(0.3)
    assert heard == ["¡Oye, recuerda: tomar agua!"], heard

    now = datetime.datetime.now()
    this_minute = now.strftime("%H:%M")  # what the model wrote for "in a minute": now, not tomorrow
    res = timers.remind("estirar", at=this_minute)
    assert res["ok"] and "mañana" not in res["result"], res
    passed = (now - datetime.timedelta(minutes=5)).strftime("%H:%M")
    assert "mañana a las" in timers.remind("cita", at=passed)["result"] or now.hour == 0
    assert not timers.remind("x", at="25:99")["ok"] and not timers.remind("x")["ok"] and not timers.remind(" ", minutes=1)["ok"]
    for tid in list(timers._TIMERS):
        timers.cancel_timer(tid)


async def _dates_and_repeats():
    heard = []

    async def notify(msg):
        heard.append(msg)

    timers._TIMERS.clear()
    timers.set_timer_notifier(notify, loop=asyncio.get_running_loop())
    now = datetime.datetime.now()
    in_3_days = (now + datetime.timedelta(days=3)).date()

    # A date: "el viernes a las 8" (the model works out the date from today's)
    res = timers.remind("la cita", at="08:00", date=in_3_days.isoformat())
    weekday = timers._WEEKDAYS[in_3_days.weekday()]
    assert res["ok"] and f"el {weekday} a las 08:00" in res["result"], res
    assert not timers.remind("x", at="08:00", date="2020-01-01")["ok"], "a past date is an error, not tomorrow"
    assert not timers.remind("x", at="08:00", date="el viernes")["ok"]

    # Repeating: "todos los días a las 9" and "cada 2 horas"
    assert "todos los días a las 09:00" in timers.remind("vitaminas", at="09:00", every_minutes=1440)["result"]
    assert "cada 2 horas" in timers.remind("estirar", every_minutes=120)["result"]
    assert "Tienes 3 avisos" in timers.list_timers()["result"]

    # A repeating one fires and stays, same id, next time one period later (not removed like a one-off)
    tid = timers._add("Recordatorio: parpadear", 0.05, every=3600)["id"]
    await asyncio.sleep(0.3)
    assert heard == ["¡Oye, recuerda: parpadear!"] and tid in timers._TIMERS, heard
    assert 3500 < timers._TIMERS[tid]["due"] - time.time() <= 3600
    assert tid in [t["id"] for t in saved()]

    # Restarted after a long time off: a repeating one moves on to its next time instead of being dropped
    for t in list(timers._TIMERS):
        timers.cancel_timer(t)
    long_ago = time.time() - 3 * timers.DAY_S
    timers.TIMERS_FILE.write_text(json.dumps([
        {"id": 40, "label": "Recordatorio: vitaminas", "due": long_ago, "every": timers.DAY_S},
        {"id": 41, "label": "Recordatorio: viejo", "due": long_ago, "every": 0},
    ]), encoding="utf-8")
    timers.restore_timers()
    assert list(timers._TIMERS) == [40] and 0 < timers._TIMERS[40]["due"] - time.time() <= timers.DAY_S
    timers.cancel_timer(40)


def test_a_replayed_reminder_is_not_added_twice():
    async def run():
        timers._TIMERS.clear()
        timers.set_timer_notifier(lambda m: asyncio.sleep(0), loop=asyncio.get_running_loop())
        first = timers.remind("Jarolito es muy playo", minutes=2)
        again = timers.remind("Harolito es muy playo", minutes=2)  # log 3-nov: replayed on "gracias mi amor"
        assert len(timers._TIMERS) == 1 and first["result"].split(",")[0] == again["result"].split(",")[0], again
        timers.remind("Jarolito es muy playo", minutes=10)  # another time: a real second reminder
        timers.remind("tomar agua", minutes=2)
        assert len(timers._TIMERS) == 3
        for t in list(timers._TIMERS):
            timers.cancel_timer(t)

    asyncio.run(run())


def test_rings_after_the_pc_slept():
    """Suspended PC: asyncio's clock may stop, the wall clock does not. A reminder due while it slept rings within
    WAKE_CHECK_S of waking up, not an hour later."""
    async def run():
        heard = []

        async def notify(msg):
            heard.append(msg)

        timers._TIMERS.clear()
        timers.set_timer_notifier(notify, loop=asyncio.get_running_loop())
        check, real = timers.WAKE_CHECK_S, timers.time.time
        timers.WAKE_CHECK_S = 0.05
        try:
            timers.set_timer(60, "pizza")
            await asyncio.sleep(0.1)
            assert heard == []
            timers.time.time = lambda: real() + 3601  # the PC slept an hour
            await asyncio.sleep(0.3)
        finally:
            timers.time.time, timers.WAKE_CHECK_S = real, check
        assert heard == ["¡Tu temporizador de pizza ha terminado!"], heard

    asyncio.run(run())


def test_my_day():
    """"¿Qué tengo hoy?": today's reminders in time order, then the pending notes."""
    import core.tools.notes as notes

    today, tomorrow = datetime.date.today(), datetime.date.today() + datetime.timedelta(days=1)

    def at(day, hh, mm):
        return datetime.datetime.combine(day, datetime.time(hh, mm)).timestamp()

    timers._TIMERS.clear()
    timers._TIMERS.update({
        1: {"id": 1, "label": "Recordatorio: la cita", "due": at(today, 23, 59), "every": 0},
        2: {"id": 2, "label": "el té", "due": at(today, 0, 1), "every": 0},
        3: {"id": 3, "label": "Recordatorio: vitaminas", "due": at(tomorrow, 9, 0), "every": timers.DAY_S},
    })
    assert timers.describe_today() == "el té a las 00:01; la cita a las 23:59", timers.describe_today()

    notes.NOTES_FILE = Path(tempfile.mkdtemp()) / "notes.md"
    assert notes.my_day()["result"] == "Hoy tienes: el té a las 00:01; la cita a las 23:59."
    notes.NOTES_FILE.write_text("- [2026-10-20 02:58] comprar pan\n- ✔ [2026-10-21 10:00] hecho\n", encoding="utf-8")
    assert notes.my_day()["result"].endswith("Y un pendiente: comprar pan."), notes.my_day()
    timers._TIMERS.clear()
    assert notes.my_day()["result"] == "Tienes un pendiente: comprar pan."
    notes.NOTES_FILE.unlink()
    assert "Día libre" in notes.my_day()["result"]


def test_timers_persist():
    asyncio.run(_flow())
    asyncio.run(_restart())
    asyncio.run(_reminders())
    asyncio.run(_dates_and_repeats())


if __name__ == "__main__":
    test_timers_persist()
    test_my_day()
    test_rings_after_the_pc_slept()
    test_a_replayed_reminder_is_not_added_twice()
    print("ok")
