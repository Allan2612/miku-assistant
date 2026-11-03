"""
Miku Assistant - WebSocket Server
Provides local ws://127.0.0.1:8765 communication between core backend and UI frontend.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import Callable, Set, Dict, Any, Optional
import websockets
from websockets.asyncio.server import ServerConnection

from core.browser import EXTENSION_ORIGIN, bridge

logger = logging.getLogger("miku.server")

# Browsers always send Origin, so this blocks any web page from driving Miku.
# None allows local non-browser clients (scripts, tests), which send no Origin.
ALLOWED_ORIGINS = [
    "http://tauri.localhost",   # Tauri v2 on Windows (production)
    "https://tauri.localhost",
    "http://localhost:1420",    # vite dev server
    EXTENSION_ORIGIN,           # Miku's Opera extension (fixed id): tab state and commands only
    None,
]

MAX_TEXT_INPUT = 1000  # characters sent to Gemini per message


class MikuServer:
    def __init__(
        self,
        host: str = "127.0.0.1",
        port: int = 8765,
    ):
        self.host = host
        self.port = port
        # MikuPipeline, set by __main__ before start(): every answer goes through it (one voice, RVC)
        self.pipeline: Any = None
        self.clients: Set[ServerConnection] = set()
        self.server = None
        # Set by __main__: lets the app's "Salir" stop the whole backend (H-050)
        self.on_shutdown: Optional[Callable[[], None]] = None
        # Strong refs: un-referenced tasks can be garbage-collected and lose their errors (H-021)
        self._tasks: Set[asyncio.Task] = set()

    def _spawn(self, coro: Any) -> None:
        """Runs a coroutine without blocking the client's message loop."""
        task = asyncio.create_task(coro)
        self._tasks.add(task)
        task.add_done_callback(self._task_done)

    def _task_done(self, task: asyncio.Task) -> None:
        self._tasks.discard(task)
        if not task.cancelled() and task.exception():
            logger.error("Background task failed", exc_info=task.exception())

    def set_pipeline(self, pipeline: Any) -> None:
        """Sets or updates the orchestrator pipeline."""
        self.pipeline = pipeline

    async def broadcast(self, message: Dict[str, Any]) -> None:
        """Broadcasts a JSON message to all connected frontend clients."""
        if not self.clients:
            return
        if message.get("type") == "show":
            message = {**message, "sent_at": time.time()}  # the frontend reports back how long showing took
        payload = json.dumps(message, ensure_ascii=False)
        disconnected = set()
        # Copy: handle_client may add/remove clients while we await send()
        for client in list(self.clients):
            try:
                await client.send(payload)
            except Exception:
                disconnected.add(client)
        self.clients -= disconnected

    async def _handle_extension(self, websocket: ServerConnection) -> None:
        """Miku's Opera extension: it may only report tabs and answer commands, never drive Miku."""
        try:
            async for raw_message in websocket:
                try:
                    data = json.loads(raw_message)
                except json.JSONDecodeError:
                    continue
                msg_type = data.get("type") if isinstance(data, dict) else None
                if msg_type == "ext_hello":
                    bridge.attach(websocket)
                elif msg_type == "tabs_state":
                    bridge.update(data)
                elif msg_type == "ext_result":
                    bridge.resolve(data)
                elif msg_type != "ext_ping":
                    logger.warning("Ignoring '%s' from the Opera extension.", msg_type)
        except websockets.exceptions.ConnectionClosed:
            pass
        finally:
            bridge.detach(websocket)

    async def handle_client(self, websocket: ServerConnection) -> None:
        """Handles individual client connection lifecycle."""
        if websocket.request.headers.get("Origin") == EXTENSION_ORIGIN:
            await self._handle_extension(websocket)
            return
        self.clients.add(websocket)
        client_addr = websocket.remote_address
        logger.info("Frontend client connected: %s (total clients: %d)", client_addr, len(self.clients))

        try:
            async for raw_message in websocket:
                try:
                    data = json.loads(raw_message)
                    msg_type = data.get("type")

                    if msg_type == "ready":
                        logger.info("Client is ready.")
                        await websocket.send(json.dumps({"type": "state", "value": "idle"}))

                    elif msg_type == "text_input":
                        user_text = str(data.get("text", ""))[:MAX_TEXT_INPUT]
                        if user_text:
                            # As a task: dismiss/speak_done from this client must not wait for the answer
                            self._spawn(self.pipeline.handle_text_input(user_text))

                    elif msg_type == "activate":
                        logger.info("Client requested activation.")
                        self._spawn(self.pipeline.handle_voice_activation())

                    elif msg_type == "speak_done":
                        logger.info("Client reported speak_done.")
                        # End of the "¿Sí?" cue: the pipeline now opens the mic, nothing else to do
                        if self.pipeline.ack_finished():
                            continue
                        await self.broadcast({"type": "state", "value": "idle"})
                        if self.pipeline.handle_speak_done():
                            await asyncio.sleep(1.0)
                            await self.broadcast({"type": "hide"})

                    elif msg_type == "dismiss":
                        logger.info("Client requested dismiss.")
                        self.pipeline.end_conversation()
                        await self.broadcast({"type": "hide"})

                    elif msg_type == "timing":
                        logger.info("Frontend timing [%s]: %s", data.get("what"),
                                    {k: v for k, v in data.items() if k not in ("type", "what")})

                    elif msg_type == "idle_timeout":
                        # Frontend auto-hide: Miku says goodbye, then hides on its speak_done
                        self._spawn(self.pipeline.say_goodbye())

                    elif msg_type == "shutdown":
                        logger.info("Client requested backend shutdown.")
                        if self.on_shutdown:
                            self.on_shutdown()

                    else:
                        logger.debug("Unhandled client message: %s", data)


                except json.JSONDecodeError:
                    logger.warning("Invalid JSON received from client: %s", raw_message)
                except Exception as e:
                    logger.error("Error processing client message: %s", e)

        except websockets.exceptions.ConnectionClosed:
            pass
        finally:
            self.clients.discard(websocket)
            logger.info("Frontend client disconnected: %s", client_addr)

    async def start(self) -> None:
        """Starts the WebSocket server."""
        logger.info("Starting WebSocket server on ws://%s:%d", self.host, self.port)
        self.server = await websockets.serve(
            self.handle_client, self.host, self.port, origins=ALLOWED_ORIGINS
        )

    async def stop(self) -> None:
        """Stops the WebSocket server and closes active client connections."""
        for client in list(self.clients):
            try:
                await client.close()
            except Exception:
                pass
        self.clients.clear()

        if self.server:
            self.server.close()
            await self.server.wait_closed()
            logger.info("WebSocket server stopped.")

