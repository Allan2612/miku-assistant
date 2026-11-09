"""
Miku Assistant - Resource Manager
- Monitors inactivity timer (default 10 minutes).
- Keeps the CPU STT model loaded (RAM is cheap for this user; reloading it delayed the next answer).
- (Phase 6 hook) Kills RVC GPU worker subprocess to guarantee 0 MB VRAM at rest.
"""

from __future__ import annotations

import asyncio
import gc
import logging
import time
from typing import Optional, Any

logger = logging.getLogger("miku.resources")


class ResourceManager:
    """Manages resource lifetimes, inactivity timeouts, and memory reclaiming."""

    def __init__(self, unload_after_minutes: int = 10) -> None:
        self.unload_after_seconds: float = max(60.0, unload_after_minutes * 60.0)
        self.last_activity: float = time.monotonic()
        self._rvc = None
        self._monitor_task: Optional[asyncio.Task] = None
        self._running: bool = False
        logger.info(
            "ResourceManager initialized (inactivity timeout: %.1f minutes)",
            self.unload_after_seconds / 60.0,
        )

    def register_rvc(self, rvc_manager: Any) -> None:
        """Registers the RVCManager instance (for Phase 6 worker shutdown)."""
        self._rvc = rvc_manager

    def touch(self) -> None:
        """Marks current timestamp as the latest user activity."""
        self.last_activity = time.monotonic()

    async def _monitor_loop(self) -> None:
        """Periodic loop checking for resource unloading on inactivity."""
        logger.debug("Resource inactivity monitor loop started.")
        while self._running:
            try:
                await asyncio.sleep(20.0)
                if not self._running:
                    break

                idle_duration = time.monotonic() - self.last_activity
                if idle_duration >= self.unload_after_seconds:
                    unloaded_anything = False

                    # Whisper stays loaded: it only takes RAM, which the user is fine spending, and reloading it
                    # cost ~1.5 s on the first phrase after a pause. VRAM is what matters: the RVC worker goes.

                    # Kill RVC worker subprocess if running (Phase 6)
                    if self._rvc is not None and getattr(self._rvc, "is_loaded", False):
                        logger.info(
                            "Inactivity timeout reached (%.1f min idle). Terminating RVC worker.",
                            idle_duration / 60.0,
                        )
                        self._rvc.terminate_worker()
                        # A fresh worker waits with its imports done (RAM only): reloading is then 3-5 s,
                        # not 10-48 s in which she answered with the base voice ("otra voz", 26-oct)
                        await self._rvc.standby()
                        unloaded_anything = True

                    if unloaded_anything:
                        gc.collect()
                        logger.info("Resource cleanup completed. Memory reclaimed.")

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("Error in resource monitor loop: %s", e)

    def start(self) -> None:
        """Starts background inactivity monitoring."""
        if self._monitor_task is None or self._monitor_task.done():
            self._running = True
            self.last_activity = time.monotonic()
            self._monitor_task = asyncio.create_task(self._monitor_loop())

    async def stop(self) -> None:
        """Stops background inactivity monitoring."""
        self._running = False
        if self._monitor_task and not self._monitor_task.done():
            self._monitor_task.cancel()
            try:
                await self._monitor_task
            except asyncio.CancelledError:
                pass
            self._monitor_task = None
        logger.debug("Resource monitor stopped.")
