"""
Miku Assistant - RVC Subprocess Lifecycle & Voice Conversion Manager
Strict adherence to GEMINI.md:
- Prohibido importar `torch` en el proceso principal de `core`.
- Spawns and manages the isolated `rvc_worker.py` subprocess over stdin/stdout pipes.
- Supports pre-calentamiento (asynchronous warmup while user speaks).
- Supports graceful termination (kill/terminate) on inactivity timeout to return to 0 MB VRAM.
- If RVC conversion fails it returns None: the answer goes out as a subtitle, never in another voice.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import sys
from pathlib import Path
from typing import Optional, Tuple

from core.config import RVCConfig

logger = logging.getLogger("miku.rvc")

ROOT_DIR = Path(__file__).resolve().parent.parent

# First load may download ContentVec from Hugging Face; a timeout now restarts the worker,
# so a short limit would never let that first download finish (H-041).
LOAD_TIMEOUT_S = 180.0
# Measured on the RTX 3050: 6-20 s for a 7 s phrase when another program shares the GPU.
# A timeout restarts the worker (35-80 s reload), so it must not fire on a merely slow conversion.
CONVERT_TIMEOUT_S = 60.0


class RVCManager:
    """Manages the isolated GPU RVC worker subprocess from the main core process."""

    def __init__(self, config: RVCConfig) -> None:
        self.config = config
        self.enabled: bool = config.enabled
        self.model_path: str = config.model
        self.index_path: str = config.index
        self.f0_up_key: int = config.f0_up_key
        self.index_rate: float = getattr(config, "index_rate", 0.2)

        self._proc: Optional[asyncio.subprocess.Process] = None
        self._reaping: set = set()  # strong refs to proc.wait() tasks of terminated workers
        self._lock = asyncio.Lock()
        self._is_warming_up: bool = False
        self._loaded: bool = False  # models in VRAM; the process alone (standby) holds none

        logger.info(
            "RVCManager initialized (enabled=%s, model=%s, index=%s, f0_up_key=%d)",
            self.enabled,
            self.model_path,
            self.index_path,
            self.f0_up_key,
        )

    @property
    def is_running(self) -> bool:
        """Returns True if the worker subprocess is currently active and alive."""
        return self._proc is not None and self._proc.returncode is None

    @property
    def is_loaded(self) -> bool:
        """The models are in VRAM and a conversion can start right away."""
        return self.is_running and self._loaded

    @staticmethod
    def _log_file():
        log_path = ROOT_DIR / "cache" / "rvc_worker.log"
        log_path.parent.mkdir(parents=True, exist_ok=True)
        return open(log_path, "ab")

    async def _ensure_worker(self) -> bool:
        """Spawns the worker subprocess if not currently running."""
        if not self.enabled:
            return False

        if self.is_running:
            return True

        worker_script = ROOT_DIR / "core" / "rvc_worker.py"
        python_exe = sys.executable

        log_file = self._log_file()
        try:
            logger.info("Spawning isolated RVC worker subprocess (%s)...", worker_script.name)
            self._proc = await asyncio.create_subprocess_exec(
                python_exe,
                str(worker_script),
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=log_file,  # worker logs to stderr; keep them (H-039)
                cwd=str(ROOT_DIR),
                limit=10 * 1024 * 1024,  # 10 MB line buffer for base64 audio responses
            )
            self._loaded = False
            logger.info("RVC worker process spawned with PID %d", self._proc.pid)
            return True
        except Exception as e:
            logger.error("Failed to spawn RVC worker subprocess: %s", e)
            self._proc = None
            return False
        finally:
            log_file.close()  # the child keeps its own handle

    async def _send_command(self, payload: dict, timeout: float = 30.0) -> Optional[dict]:
        """Sends a JSON-RPC line to the worker and awaits a single-line JSON response."""
        if not self.is_running:
            return None

        proc = self._proc
        if proc is None or proc.stdin is None or proc.stdout is None:
            return None

        try:
            data = json.dumps(payload) + "\n"
            proc.stdin.write(data.encode("utf-8"))
            await proc.stdin.drain()

            line_bytes = await asyncio.wait_for(proc.stdout.readline(), timeout=timeout)
            if not line_bytes:
                logger.warning("RVC worker pipe returned EOF.")
                self.terminate_worker()
                return None

            resp = json.loads(line_bytes.decode("utf-8").strip())
            return resp
        except asyncio.TimeoutError:
            # The worker would answer later and every following reply would be off by one (H-038)
            logger.error("Timeout (%.1fs) waiting for RVC worker response. Restarting worker.", timeout)
            self.terminate_worker()
            return None
        except Exception as e:
            logger.error("Error communicating with RVC worker: %s. Restarting worker.", e)
            self.terminate_worker()
            return None

    async def warmup(self) -> bool:
        """
        Pre-warms the RVC worker in the background.
        Dispatched concurrently upon voice activation while user speaks.
        """
        if not self.enabled:
            return False

        if self._is_warming_up:
            return True

        async with self._lock:
            self._is_warming_up = True
            try:
                ok = await self._load()
                if ok:
                    logger.info("RVC worker warmed up and ready in GPU VRAM.")
                return ok
            except Exception as e:
                logger.error("Error warming up RVC worker: %s", e)
                return False
            finally:
                self._is_warming_up = False

    async def _load(self) -> bool:
        """Starts the worker if needed and loads the models into VRAM. Call with the lock held."""
        if not await self._ensure_worker():
            return False
        if self._loaded:
            return True
        resp = await self._send_command({
            "cmd": "load",
            "model": self.model_path,
            "index": self.index_path,
        }, timeout=LOAD_TIMEOUT_S)
        self._loaded = bool(resp and resp.get("status") == "ok")
        if not self._loaded:
            logger.warning("RVC worker failed to load models: %s", resp)
        return self._loaded

    async def standby(self) -> None:
        """Starts a worker that only imports torch & co. (10-48 s, RAM only, no VRAM) and waits: the next
        load then takes 3-5 s instead of a full process start."""
        if not self.enabled:
            return
        async with self._lock:
            if await self._ensure_worker():
                logger.info("RVC worker on standby (no models in VRAM).")

    async def convert(self, audio_b64: str) -> Optional[Tuple[str, str]]:
        """
        Converts edge-tts audio into character voice using RVC.
        Returns (converted_audio_b64, "audio/wav") or None on failure.
        """
        if not self.enabled or not audio_b64:
            return None

        # A load in progress holds the lock: the answer waits for it. She has one voice only; the base voice
        # while RVC loaded was the "otra voz" the user heard (26-oct). With the standby worker it is 3-5 s
        if self._is_warming_up:
            logger.info("RVC still loading: the answer waits for Miku's voice.")
        async with self._lock:
            # 1. Worker alive and models loaded (a standby worker loads them now: 3-5 s)
            if not await self._load():
                return None

            # 2. Dispatch conversion
            try:
                resp = await self._send_command({
                    "cmd": "convert",
                    "audio_b64": audio_b64,
                    "f0_up_key": self.f0_up_key,
                    "index_rate": self.index_rate,
                    "protect": 0.33,
                }, timeout=CONVERT_TIMEOUT_S)

                if resp and resp.get("status") == "ok" and resp.get("audio_b64"):
                    return resp["audio_b64"], resp.get("mime", "audio/wav")
                else:
                    err = resp.get("error", "Unknown error") if resp else "No response"
                    logger.warning("RVC conversion failed: %s", err)
                    return None
            except Exception as e:
                logger.error("Exception during RVC conversion: %s", e)
                return None

    def terminate_worker(self) -> None:
        """
        Terminates the isolated worker subprocess immediately.
        Invoked by ResourceManager after inactivity timeout to ensure 0 MB VRAM at rest.
        """
        self._loaded = False
        if self._proc is not None:
            proc, self._proc = self._proc, None
            pid = proc.pid
            logger.info("Terminating RVC worker subprocess (PID: %d)...", pid)
            try:
                proc.terminate()
            except ProcessLookupError:
                pass
            except Exception as e:
                logger.warning("Error terminating RVC worker (PID %d): %s", pid, e)
            if proc.stdin is not None:
                proc.stdin.close()
            # Reap it in the background: once it exits asyncio closes its pipes, so no "unclosed transport"
            # warnings (H-039). No running loop means the backend is exiting and the process goes with it.
            try:
                task = asyncio.get_running_loop().create_task(proc.wait())
                self._reaping.add(task)
                task.add_done_callback(self._reaping.discard)
            except RuntimeError:
                pass
            logger.info("RVC worker terminated. GPU VRAM reclaimed by OS (0 MB idle).")
