"""H-019: the WebSocket server must reject connections from web pages.

Run: core\\.venv\\Scripts\\python.exe -m tests.test_server_origin  (or with pytest)
"""

import asyncio

import websockets
from websockets.asyncio.client import connect

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
    server = MikuServer(port=PORT, brain=object(), tts=object())
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

        # Auto-hide: the frontend's idle_timeout makes Miku say goodbye; without a pipeline, just hide
        said = asyncio.Event()

        class Pipeline:
            async def say_goodbye(self):
                said.set()

        server.set_pipeline(Pipeline())
        async with connect(f"ws://127.0.0.1:{PORT}", origin="http://tauri.localhost") as ws:
            await ws.send('{"type": "idle_timeout"}')
            await asyncio.wait_for(said.wait(), 2)
        server.set_pipeline(None)
        async with connect(f"ws://127.0.0.1:{PORT}", origin="http://tauri.localhost") as ws:
            await ws.send('{"type": "idle_timeout"}')
            msg = await asyncio.wait_for(ws.recv(), 2)
            assert '"hide"' in msg, msg
    finally:
        await server.stop()


def test_origin_check():
    asyncio.run(_run())


if __name__ == "__main__":
    test_origin_check()
    print("ok")
