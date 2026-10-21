"""
Miku Assistant - Wake Word Detection (openWakeWord)
Strict adherence to GEMINI.md:
- Runs in CPU mode via ONNXRuntime (< 2% CPU in idle).
- When `wakeword.enabled` is false, NO stream is ever opened (zero mic usage, zero CPU).
- When `wakeword.enabled` is true, continuously listens for the wake phrase and triggers activation.
- Automatically pauses during voice interaction (to avoid self-triggering and mic contention).
- Supports custom ONNX models (e.g. `models/wakeword/hey_miku.onnx`) with graceful fallback to built-in models.
"""

from __future__ import annotations

import asyncio
import logging
import os
import threading
import time
from pathlib import Path
from typing import Callable, Coroutine, Optional, Any

import numpy as np
import sounddevice as sd
from openwakeword.model import Model

from core.config import WakewordConfig

logger = logging.getLogger("miku.wakeword")

BUILTIN_MODELS = {"alexa", "hey_mycroft", "hey_jarvis", "hey_rhasspy", "timer", "weather"}


class WakeWordListener:
    """Manages real-time wake word detection on CPU via openWakeWord."""

    def __init__(
        self,
        config: WakewordConfig,
        on_wake: Callable[[], Coroutine[Any, Any, None]],
        loop: Optional[asyncio.AbstractEventLoop] = None,
    ) -> None:
        self.enabled: bool = config.enabled
        self.model_path: str = config.model
        self.threshold: float = config.threshold
        self.patience: int = getattr(config, "patience", 2)
        self.vad_threshold: float = getattr(config, "vad_threshold", 0.0)
        self._errors = 0
        self._on_wake = on_wake
        self._loop = loop

        self._running: bool = False
        self._paused: bool = False
        self._stream: Optional[sd.InputStream] = None
        self._model: Optional[Model] = None
        self._target_key: str = "hey_jarvis"
        self._last_trigger_time: float = 0.0
        self._cooldown_seconds: float = 3.0
        self._consecutive_hits: int = 0
        self._lock = threading.Lock()

    @property
    def is_listening(self) -> bool:
        """Returns True if the listener is running and not currently paused."""
        return self._running and not self._paused

    def _resolve_model(self) -> tuple[str, str]:
        """
        Resolves the wakeword model to load.
        Returns (model_identifier, target_key_name).
        """
        candidate_path = Path(self.model_path)
        if candidate_path.is_file():
            target_key = candidate_path.stem
            logger.info("Found custom wakeword model file: %s (key: '%s')", candidate_path, target_key)
            return str(candidate_path), target_key

        # Check if the name corresponds directly to an openWakeWord built-in model
        name_lower = candidate_path.stem.lower()
        if name_lower in BUILTIN_MODELS:
            logger.info("Using built-in openWakeWord model: '%s'", name_lower)
            return name_lower, name_lower

        # Fallback to hey_jarvis for immediate testing
        logger.warning(
            "Custom wakeword model '%s' not found on disk. "
            "Falling back to built-in 'hey_jarvis' for testing. "
            "Place your custom 'hey_miku.onnx' in models/wakeword/ to activate Miku by name.",
            self.model_path,
        )
        return "hey_jarvis", "hey_jarvis"

    def start(self) -> bool:
        """Starts wake word listening if enabled."""
        if not self.enabled:
            logger.info("WakeWord detection is disabled in config. Zero microphone usage in idle.")
            return False

        if self._running:
            return True

        if self._loop is None:
            try:
                self._loop = asyncio.get_running_loop()
            except RuntimeError:
                try:
                    self._loop = asyncio.get_event_loop()
                except RuntimeError:
                    self._loop = asyncio.new_event_loop()

        try:
            model_id, target_key = self._resolve_model()
            self._target_key = target_key

            logger.info(
                "Initializing openWakeWord (model: %s, threshold: %.2f, patience: %d frames)...",
                model_id,
                self.threshold,
                self.patience,
            )
            self._model = Model(
                wakeword_models=[model_id],
                inference_framework="onnx",
                vad_threshold=self.vad_threshold,
            )

            def audio_callback(indata: np.ndarray, frames: int, time_info: dict, status: sd.CallbackFlags) -> None:
                if status:
                    logger.debug("WakeWord audio status: %s", status)
                self._process_chunk(indata)

            # openWakeWord expects 16kHz, 16-bit PCM mono, blocksize 1280 (80 ms chunk)
            self._stream = sd.InputStream(
                samplerate=16000,
                channels=1,
                dtype="int16",
                blocksize=1280,
                callback=audio_callback,
            )
            self._stream.start()
            self._running = True
            self._paused = False

            logger.info("WakeWord listener started successfully. Listening for '%s'...", self._target_key)
            return True

        except Exception as e:
            logger.exception("Failed to start WakeWord listener: %s", e)
            self.stop()
            return False

    def _process_chunk(self, chunk: np.ndarray) -> None:
        """Processes an 80ms chunk in the audio callback thread."""
        with self._lock:
            if not self._running or self._paused or self._model is None:
                return

            try:
                audio_data = chunk[:, 0] if chunk.ndim > 1 else chunk
                if audio_data.dtype != np.int16:
                    audio_data = audio_data.astype(np.int16)

                # Pure electrical silence floor check (< 6 RMS): skip to save CPU without corrupting buffer
                rms = float(np.sqrt(np.mean(audio_data.astype(np.float32) ** 2)))
                if rms < 6.0:
                    self._consecutive_hits = 0
                    return

                predictions = self._model.predict(audio_data)
                score = predictions.get(self._target_key, 0.0)

                # Also inspect any other loaded model if target_key was missing
                if self._target_key not in predictions and predictions:
                    best_key = max(predictions, key=predictions.get)
                    score = predictions[best_key]

                now = time.time()
                # Consecutive frame debouncing: eliminates isolated 1-frame spikes (clics, keyboard, noise)
                if score >= self.threshold:
                    self._consecutive_hits += 1
                else:
                    self._consecutive_hits = 0

                if self._consecutive_hits >= self.patience and (now - self._last_trigger_time) >= self._cooldown_seconds:
                    self._last_trigger_time = now
                    self._consecutive_hits = 0
                    logger.info(
                        "Wake word '%s' detected! Score: %.3f (>= %.2f, hits=%d)",
                        self._target_key,
                        score,
                        self.threshold,
                        self.patience,
                    )
                    # Automatically pause listening during subsequent conversation
                    self._paused = True
                    self._model.reset()

                    if self._loop and not self._loop.is_closed():
                        try:
                            coro = self._on_wake()
                            if asyncio.iscoroutine(coro):
                                asyncio.run_coroutine_threadsafe(coro, self._loop)
                        except RuntimeError:
                            pass

            except Exception as e:
                # Visible in the normal log, but not 12 times per second (H-037)
                self._errors += 1
                if self._errors == 1 or self._errors % 500 == 0:
                    logger.warning("Wake word prediction failing (%d errors so far): %s", self._errors, e)

    def pause(self) -> None:
        """Temporarily pauses listening (e.g. while Miku is speaking or user is talking)."""
        with self._lock:
            self._consecutive_hits = 0
            if self._running and not self._paused:
                self._paused = True
                if self._model:
                    self._model.reset()
                logger.debug("WakeWord listener paused.")

    def resume(self) -> None:
        """Resumes listening after interaction completes."""
        with self._lock:
            self._consecutive_hits = 0
            if self._running and self._paused:
                if self._model:
                    self._model.reset()
                self._paused = False
                logger.debug("WakeWord listener resumed.")

    def stop(self) -> None:
        """Stops the audio stream and releases resources."""
        with self._lock:
            self._running = False
            self._paused = False
            self._consecutive_hits = 0
            if self._stream is not None:
                try:
                    self._stream.stop()
                    self._stream.close()
                except Exception as e:
                    logger.debug("Error closing wakeword stream: %s", e)
                self._stream = None

            self._model = None
            logger.info("WakeWord listener stopped.")
