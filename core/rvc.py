"""
Miku Assistant - RVC Subprocess Lifecycle & Voice Conversion Manager
Strict adherence to GEMINI.md:
- Prohibido importar `torch` en el proceso principal de `core`.
- Spawns and manages the isolated `rvc_worker.py` subprocess over stdin/stdout pipes.
- Supports pre-calentamiento (asynchronous warmup while user speaks).
- Supports graceful termination (kill/terminate) on inactivity timeout to return to 0 MB VRAM.
- Graceful degradation: If RVC conversion fails, returns None so caller falls back to base edge-tts.
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
        self._lock = asyncio.Lock()
        self._is_warming_up: bool = False

        logger.info(
            "RVCManager initialized (enabled=%s, model=%s, index=%s, f0_up_key=%d)",
            self.enabled,
            self.model_path,
            self.index_path,
            self.f0_up_key,
        )

    @property
    def is_warming_up(self) -> bool:
        return self._is_warming_up

    @property
    def is_running(self) -> bool:
        """Returns True if the worker subprocess is currently active and alive."""
        return self._proc is not None and self._proc.returncode is None

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
                ok = await self._ensure_worker()
                if not ok:
                    return False

                resp = await self._send_command({
                    "cmd": "warmup",
                    "model": self.model_path,
                    "index": self.index_path,
                }, timeout=LOAD_TIMEOUT_S)

                if resp and resp.get("status") == "ok":
                    logger.info("RVC worker warmed up and ready in GPU VRAM.")
                    return True
                else:
                    logger.warning("RVC worker warmup returned non-ok status: %s", resp)
                    return False
            except Exception as e:
                logger.error("Error warming up RVC worker: %s", e)
                return False
            finally:
                self._is_warming_up = False

    async def convert(self, audio_b64: str) -> Optional[Tuple[str, str]]:
        """
        Converts edge-tts audio into character voice using RVC.
        Returns (converted_audio_b64, "audio/wav") or None on failure.
        """
        if not self.enabled or not audio_b64:
            return None

        # A load takes 35-80 s: answer now with the base voice instead of waiting for it (H-028)
        if self._is_warming_up:
            logger.info("RVC still loading. Using the base voice for this answer.")
            return None

        async with self._lock:
            # 1. Ensure worker process is alive
            if not self.is_running:
                logger.info("RVC worker not running. Launching and warming up on-demand...")
                ok = await self._ensure_worker()
                if not ok:
                    return None
                # Load models; if that fails, converting would only wait for another timeout
                resp = await self._send_command({
                    "cmd": "load",
                    "model": self.model_path,
                    "index": self.index_path,
                }, timeout=LOAD_TIMEOUT_S)
                if not resp or resp.get("status") != "ok":
                    logger.warning("RVC worker failed to load models: %s", resp)
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
        if self._proc is not None:
            pid = self._proc.pid
            logger.info("Terminating RVC worker subprocess (PID: %d)...", pid)
            try:
                self._proc.terminate()
            except ProcessLookupError:
                pass
            except Exception as e:
                logger.warning("Error terminating RVC worker (PID %d): %s", pid, e)

            # Ensure cleanup
            self._proc = None
            logger.info("RVC worker terminated. GPU VRAM reclaimed by OS (0 MB idle).")
