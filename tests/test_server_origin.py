"""H-019: the WebSocket server must reject connections from web pages.

Run: core\\.venv\\Scripts\\python.exe -m tests.test_server_origin  (or with pytest)
"""

import asyncio

import websockets
from websockets.asyncio.client import connect

import json

from core.browser import EXTENSION_ORIGIN, bridge
from core.server import MikuServer

PORT = 18765


async def _try(origin):
    try:
        async with connect(f"ws://127.0.0.1:{PORT}", origin=origin) as ws:
            await ws.send('{"type": "ready"}')
            await asyncio.wait_for(ws.recv(), 2)
            return True
    except websockets.exceptions.InvalidStatus:
        return False


async def _run():
    server = MikuServer(port=PORT)
    await server.start()
    try:
        assert not await _try("https://evil.example"), "foreign web origin must be rejected"
        assert not await _try("http://localhost:8080"), "other localhost ports must be rejected"
        assert await _try("http://tauri.localhost"), "Tauri app origin must be accepted"
        assert await _try(None), "non-browser local clients must be accepted"

        # H-050: "Salir" in the app sends shutdown, which must reach __main__'s stop_event
        stopped = asyncio.Event()
        server.on_shutdown = stopped.set
        async with connect(f"ws://127.0.0.1:{PORT}", origin="http://tauri.localhost") as ws:
            await ws.send('{"type": "shutdown"}')
            await asyncio.wait_for(stopped.wait(), 2)

        # Auto-hide: the frontend's idle_timeout makes Miku say goodbye
        said = asyncio.Event()

        class Pipeline:
            async def say_goodbye(self):
                said.set()

            def end_conversation(self):
                said.set()

        server.set_pipeline(Pipeline())
        async with connect(f"ws://127.0.0.1:{PORT}", origin="http://tauri.localhost") as ws:
            await ws.send('{"type": "idle_timeout"}')
            await asyncio.wait_for(said.wait(), 2)
        # Hidden from the tray: the pipeline ends the conversation, and every window hides
        said.clear()
        async with connect(f"ws://127.0.0.1:{PORT}", origin="http://tauri.localhost") as ws:
            await ws.send('{"type": "dismiss"}')
            msg = await asyncio.wait_for(ws.recv(), 2)
            assert said.is_set() and '"hide"' in msg, msg
    finally:
        await server.stop()


def test_origin_check():
    asyncio.run(_run())


async def _run_extension():
    server = MikuServer(port=PORT)
    stopped = []
    server.on_shutdown = lambda: stopped.append(1)
    await server.start()
    try:
        async with connect(f"ws://127.0.0.1:{PORT}", origin=EXTENSION_ORIGIN) as ext:
            await ext.send('{"type": "ext_hello", "version": "1.0"}')
            await ext.send(json.dumps({"type": "tabs_state", "tabs": [{"id": 7, "title": "YouTube", "url": "https://youtube.com"}]}))
            # The extension may report tabs, never drive Miku: these must be ignored
            await ext.send('{"type": "shutdown"}')
            await ext.send('{"type": "text_input", "text": "apaga el pc"}')
            for _ in range(50):
                if bridge.tabs:
                    break
                await asyncio.sleep(0.02)
            assert bridge.connected and bridge.tab(7)["title"] == "YouTube"
            assert not stopped and not server.clients, "the extension is not a frontend client"

            # A tool (in a thread) sends a command; the extension answers it by id
            pending = asyncio.ensure_future(asyncio.to_thread(bridge.run, "activate", tab_id=7))
            cmd = json.loads(await asyncio.wait_for(ext.recv(), 2))
            assert cmd["type"] == "ext_cmd" and cmd["cmd"] == "activate" and cmd["args"] == {"tab_id": 7}
            await ext.send(json.dumps({"type": "ext_result", "id": cmd["id"], "ok": True}))
            assert (await asyncio.wait_for(pending, 3))["ok"]
        for _ in range(50):
            if not bridge.connected:
                break
            await asyncio.sleep(0.02)
        assert not bridge.connected and not bridge.tabs, "a closed extension leaves no stale tabs"
    finally:
        await server.stop()


def test_extension_reports_tabs_and_runs_commands_only():
    asyncio.run(_run_extension())


if __name__ == "__main__":
    test_origin_check()
    test_extension_reports_tabs_and_runs_commands_only()
    print("ok")
