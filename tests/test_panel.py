"""The panel window: it asks the backend for data and hears only the light events (state, subtitles), never Miku's
audio, and it never counts as "someone is there" for conversation mode.

Run: core\\.venv\\Scripts\\python.exe -m tests.test_panel  (or with pytest)
"""

import asyncio
import json
import types
from collections import deque

from websockets.asyncio.client import connect

from core import panel
from core.server import MikuServer

PORT = 18766


def _pipeline():
    brain = types.SimpleNamespace(
        primary_model="gemini-3.5-flash-lite", last_model="gemini-3.1-flash-lite",
        all_models=["gemini-3.5-flash-lite", "gemini-3.1-flash-lite"],
        _model_cooldown={}, recent_turns=deque([{"at": "13:22", "user": "hola", "answer": "¡Hola!", "kind": "local"}]),
    )
    ww = types.SimpleNamespace(enabled=True, _running=True, _paused=False, threshold=0.35)
    rvc = types.SimpleNamespace(enabled=True, is_loaded=False)
    return types.SimpleNamespace(brain=brain, rvc=rvc, wakeword=ww, busy=False)


async def _run():
    server = MikuServer(port=PORT)
    server.set_pipeline(_pipeline())
    panel._obs_cache = (float("inf"), False)  # no process scan for OBS in a test
    await server.start()
    try:
        async with connect(f"ws://127.0.0.1:{PORT}", origin="http://tauri.localhost") as ws:
            await ws.send('{"type": "panel_hello"}')
            await asyncio.sleep(0.1)
            assert not server.clients and len(server.panels) == 1, "the panel is not Miku's window"

            for what in ("status", "quota", "processes"):
                await ws.send(json.dumps({"type": "panel_get", "id": what, "what": what}))
                reply = json.loads(await asyncio.wait_for(ws.recv(), 5))
                assert reply["type"] == "panel_reply" and reply["id"] == what and reply["data"], reply
                if what == "status":
                    assert reply["data"]["gemini"]["last_model"] == "gemini-3.1-flash-lite"
                    assert reply["data"]["recent"][0]["kind"] == "local"
                if what == "processes":
                    assert any(g["key"] == "backend" for g in reply["data"]["groups"]), reply["data"]

            # Miku's audio never reaches it; her state does (the equalizer)
            await server.broadcast({"type": "speak", "audio_b64": "QUJD"})
            await server.broadcast({"type": "state", "value": "speaking"})
            msg = json.loads(await asyncio.wait_for(ws.recv(), 2))
            assert msg == {"type": "state", "value": "speaking"}, msg
    finally:
        await server.stop()


def test_panel_changes_go_through_mikus_tools():
    import tempfile
    from pathlib import Path

    from core.tools import memory, notes, timers

    tmp = Path(tempfile.mkdtemp())
    timers.TIMERS_FILE, notes.NOTES_FILE = tmp / "timers.json", tmp / "notes.md"
    memory.MEMORY_FILE, memory.CONVERSATIONS_DIR = tmp / "memory.json", tmp / "conversations"

    async def run():
        timers.set_timer_notifier(lambda m: asyncio.sleep(0), loop=asyncio.get_running_loop())
        timers._TIMERS.clear()
        # Called from a thread, as the server does
        res = await asyncio.to_thread(panel.act, "remind", {"text": "estirar", "minutes": "30"})
        assert res["ok"], res
        view = await asyncio.to_thread(panel.timers_view)
        assert view["timers"][0]["text"] == "estirar" and view["timers"][0]["reminder"], view
        assert (await asyncio.to_thread(panel.act, "cancel_timer", {"id": view["timers"][0]["id"]}))["ok"]
        assert panel.timers_view()["timers"] == []

    asyncio.run(run())

    assert panel.act("note_add", {"text": "subir el PR"})["ok"]
    assert panel.timers_view()["pending"] == ["subir el PR"]
    assert panel.act("note_done", {"text": "subir el PR"})["ok"] and panel.timers_view()["pending"] == []

    panel.act("fact_add", {"text": "Le gusta Frieren"})
    panel.act("fact_add", {"text": "Le gusta el café"})
    assert panel.act("fact_edit", {"old": "Le gusta Frieren", "new": "Le encanta Frieren"})["ok"]
    assert panel.act("fact_delete", {"text": "Le gusta el café"})["ok"]
    assert panel.memory_view()["facts"] == ["Le encanta Frieren"]

    memory.CONVERSATIONS_DIR.mkdir()
    (memory.CONVERSATIONS_DIR / "2026-11-03.jsonl").write_text('{"at": "12:00", "user": "hola", "miku": "¡Hola!"}\n', encoding="utf-8")
    assert panel.memory_view()["days"] == ["2026-11-03"]
    assert panel.conversation("2026-11-03")["turns"][0]["user"] == "hola"
    assert panel.conversation("../../config")["turns"] == [], "a day, never a path"
    # Wake word clips: a known folder and the clip name pattern only
    assert panel.clip_path("", "../../.env") is None and panel.clip_path("..", "20261103-122416_0.984.wav") is None


def test_panel_asks_and_listens():
    asyncio.run(_run())


if __name__ == "__main__":
    test_panel_asks_and_listens()
    test_panel_changes_go_through_mikus_tools()
    print("ok")
