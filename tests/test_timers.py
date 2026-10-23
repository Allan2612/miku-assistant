"""Timers survive a backend restart: saved on set/cancel/expire, restored at startup, kept on shutdown.

Uses a temp timers file; nothing touches cache/timers.json.
Run: core\\.venv\\Scripts\\python.exe -m tests.test_timers  (or with pytest)
"""

import asyncio
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
    assert "Tienes 2 temporizadores" in timers.list_timers()["result"]

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


def test_timers_persist():
    asyncio.run(_flow())
    asyncio.run(_restart())


if __name__ == "__main__":
    test_timers_persist()
    print("ok")
