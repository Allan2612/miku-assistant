"""
Miku Assistant - WebSocket Server
Provides local ws://127.0.0.1:8765 communication between core backend and UI frontend.
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Set, Dict, Any, Optional
import websockets
from websockets.server import WebSocketServerProtocol

from core.llm import MikuBrain
from core.tts import TTSManager

logger = logging.getLogger("miku.server")


class MikuServer:
    def __init__(
        self,
        host: str = "127.0.0.1",
        port: int = 8765,
        brain: Optional[MikuBrain] = None,
        tts: Optional[TTSManager] = None,
        pipeline: Optional[Any] = None,
    ):
        self.host = host
        self.port = port
        self.brain = brain or MikuBrain()
        self.tts = tts or TTSManager()
        self.pipeline = pipeline
        self.clients: Set[WebSocketServerProtocol] = set()
        self.server = None
        self._input_lock = asyncio.Lock()
        self._pending_farewell: bool = False

    def set_pipeline(self, pipeline: Any) -> None:
        """Sets or updates the orchestrator pipeline."""
        self.pipeline = pipeline

    async def broadcast(self, message: Dict[str, Any]) -> None:
        """Broadcasts a JSON message to all connected frontend clients."""
        if not self.clients:
            return
        payload = json.dumps(message, ensure_ascii=False)
        disconnected = set()
        for client in self.clients:
            try:
                await client.send(payload)
            except websockets.exceptions.ConnectionClosed:
                disconnected.add(client)
        self.clients -= disconnected

    async def handle_text_input(self, text: str) -> None:
        """Handles a user text query from the frontend sequentially."""
        async with self._input_lock:
            logger.info("Processing user text input: %s", text)

            # 1. Show user subtitle
            await self.broadcast({
                "type": "subtitle",
                "who": "user",
                "text": text,
            })

            # 2. Brief pause so user clearly sees their text
            await asyncio.sleep(0.4)

            # 3. Indicate thinking state
            await self.broadcast({
                "type": "state",
                "value": "thinking",
            })
            await self.broadcast({
                "type": "expression",
                "name": "thinking",
            })

            # 4. Request LLM response asynchronously
            emotion, answer, is_farewell = await self.brain.chat(text)
            self._pending_farewell = is_farewell
            logger.info("Miku answer [%s]: %s (farewell=%s)", emotion, answer, is_farewell)

            # 5. Synthesize TTS speech (with disk cache & graceful degradation)
            tts_res = await self.tts.synthesize(answer)

            if tts_res:
                audio_b64, mime = tts_res
                # Update expression, show subtitle and trigger speak with lip sync
                await self.broadcast({
                    "type": "expression",
                    "name": emotion,
                })
                await self.broadcast({
                    "type": "subtitle",
                    "who": "miku",
                    "text": answer,
                })
                await self.broadcast({
                    "type": "state",
                    "value": "speaking",
                })
                await self.broadcast({
                    "type": "speak",
                    "audio_b64": audio_b64,
                    "mime": mime,
                    "text": answer,
                    "emotion": emotion,
                })
            else:
                # Graceful degradation: subtitle only
                logger.warning("TTS unavailable. Degrading to subtitle only.")
                await self.broadcast({
                    "type": "expression",
                    "name": emotion,
                })
                await self.broadcast({
                    "type": "subtitle",
                    "who": "miku",
                    "text": answer,
                })
                await self.broadcast({
                    "type": "state",
                    "value": "idle",
                })
                if is_farewell:
                    await asyncio.sleep(3.5)
                    await self.broadcast({"type": "hide"})




    async def handle_client(self, websocket: WebSocketServerProtocol) -> None:
        """Handles individual client connection lifecycle."""
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
                        user_text = data.get("text", "")
                        if user_text:
                            if self.pipeline:
                                await self.pipeline.handle_text_input(user_text)
                            else:
                                await self.handle_text_input(user_text)

                    elif msg_type == "activate":
                        logger.info("Client requested activation.")
                        if self.pipeline:
                            asyncio.create_task(self.pipeline.handle_voice_activation())
                        else:
                            await self.broadcast({"type": "show"})

                    elif msg_type == "speak_done":
                        logger.info("Client reported speak_done.")
                        await self.broadcast({"type": "state", "value": "idle"})
                        farewell = False
                        if self.pipeline:
                            farewell = self.pipeline.handle_speak_done()
                        elif self._pending_farewell:
                            self._pending_farewell = False
                            farewell = True

                        if farewell:
                            await asyncio.sleep(1.0)
                            await self.broadcast({"type": "hide"})

                    elif msg_type == "dismiss":
                        logger.info("Client requested dismiss.")
                        await self.broadcast({"type": "hide"})

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
        self.server = await websockets.serve(self.handle_client, self.host, self.port)

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

