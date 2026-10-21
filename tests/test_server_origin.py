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
    finally:
        await server.stop()


def test_origin_check():
    asyncio.run(_run())


if __name__ == "__main__":
    test_origin_check()
    print("ok")
