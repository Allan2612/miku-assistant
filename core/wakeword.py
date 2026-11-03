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
import collections
import logging
import os
import threading
import time
import wave
from datetime import datetime
from pathlib import Path
from typing import Callable, Coroutine, Optional, Any

import numpy as np
import sounddevice as sd
from openwakeword.model import Model

from core.config import WakewordConfig

logger = logging.getLogger("miku.wakeword")

BUILTIN_MODELS = {"alexa", "hey_mycroft", "hey_jarvis", "hey_rhasspy", "timer", "weather"}

# What it heard at each activation, to find what triggers the false ones (plan B, 26-oct). Real and false
# activations can't be told apart by score (false: 0.988; real: 0.355), so the audio is the evidence
CLIPS_DIR = Path(__file__).resolve().parents[1] / "cache" / "wake"
CLIP_CHUNKS = 25  # x 80 ms = the last 2 s
MAX_CLIPS = 200
# A trigger whose clip never gets this loud is not a voice (3-nov: 15 of 61 false triggers were near silence; the
# quietest real "Hey Miku" of 28 peaked at 0.0128). Loudest 0.2 s, as a fraction of full scale
MIN_CLIP_PEAK = 0.006
# Scores this high but under the threshold are kept too (cache/wake/near/): the only way to see missed calls
NEAR_MISS = 0.15
NEAR_MISS_EVERY_S = 5.0


def clip_peak(audio: np.ndarray) -> float:
    """Loudest 0.2 s (0.05 s steps) of 16 kHz int16 audio, as a fraction of full scale."""
    a = audio.astype(np.float32) / 32768.0
    windows = [a[i:i + 3200] for i in range(0, max(len(a) - 3200, 0) + 1, 800)]
    return max((float(np.sqrt(np.mean(w ** 2))) for w in windows if len(w)), default=0.0)


def _save_clip(audio: np.ndarray, score: float, sub: str = "") -> None:
    folder = CLIPS_DIR / sub if sub else CLIPS_DIR
    try:
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / f"{datetime.now():%Y%m%d-%H%M%S}_{score:.3f}.wav"
        with wave.open(str(path), "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(16000)
            w.writeframes(audio.astype(np.int16).tobytes())
        for old in sorted(folder.glob("*.wav"))[:-MAX_CLIPS]:
            old.unlink(missing_ok=True)
        logger.info("Wake clip saved: %s", path.name)
    except OSError as e:
        logger.warning("Could not save the wake clip: %s", e)


class WakeWordListener:
    """Manages real-time wake word detection on CPU via openWakeWord."""

    def __init__(
        self,
        config: WakewordConfig,
        on_wake: Callable[[np.ndarray], Coroutine[Any, Any, None]],
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
        self._last_near_miss: float = 0.0
        self._cooldown_seconds: float = 3.0
        self._consecutive_hits: int = 0
        self._recent: collections.deque = collections.deque(maxlen=CLIP_CHUNKS)
        self._lock = threading.Lock()

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
                self._recent.append(audio_data.copy())

                # Every chunk, silent or not: the model reads the last ~1.3 s as one continuous window. Skipping the
                # quiet ones glued audio from minutes ago to the present, and it fired at 0.99 on near silence
                # (3-nov: 12 such clips score 0.000 when replayed with the audio in one piece)
                predictions = self._model.predict(audio_data)
                score = predictions.get(self._target_key, 0.0)

                # Also inspect any other loaded model if target_key was missing
                if self._target_key not in predictions and predictions:
                    best_key = max(predictions, key=predictions.get)
                    score = predictions[best_key]

                now = time.time()
                if NEAR_MISS <= score < self.threshold and now - self._last_near_miss >= NEAR_MISS_EVERY_S:
                    self._last_near_miss = now
                    near = np.concatenate(self._recent)
                    threading.Thread(target=_save_clip, args=(near, score, "near"), daemon=True,
                                     name="miku-wake-near").start()
                # Consecutive frame debouncing: eliminates isolated 1-frame spikes (clics, keyboard, noise)
                if score >= self.threshold:
                    self._consecutive_hits += 1
                else:
                    self._consecutive_hits = 0

                if self._consecutive_hits >= self.patience and (now - self._last_trigger_time) >= self._cooldown_seconds:
                    self._last_trigger_time = now
                    self._consecutive_hits = 0
                    clip = np.concatenate(self._recent)
                    peak = clip_peak(clip)
                    if peak < MIN_CLIP_PEAK:
                        logger.info("Wake word ignored: score %.3f but the clip is near silence (peak %.4f).", score, peak)
                        threading.Thread(target=_save_clip, args=(clip, score, "silent"), daemon=True,
                                         name="miku-wake-clip").start()
                        return
                    logger.info(
                        "Wake word '%s' detected! Score: %.3f (>= %.2f, hits=%d)",
                        self._target_key,
                        score,
                        self.threshold,
                        self.patience,
                    )
                    # Off the audio thread: a disk write here would drop audio
                    threading.Thread(target=_save_clip, args=(clip, score), daemon=True, name="miku-wake-clip").start()
                    # Automatically pause listening during subsequent conversation
                    self._paused = True
                    self._model.reset()

                    if self._loop and not self._loop.is_closed():
                        try:
                            coro = self._on_wake(clip)  # the pipeline checks it really was "Miku"
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
                self._recent.clear()  # a clip must not start with Miku's own voice from before the pause
                self._paused = False
                logger.debug("WakeWord listener resumed.")

    def stop(self) -> None:
        """Stops the audio stream and releases resources."""
        with self._lock:
            self._running = False
            self._paused = False
            self._consecutive_hits = 0
            stream, self._stream = self._stream, None
            self._model = None
        # Outside the lock: stream.stop() waits for the callback, which takes the lock (deadlock)
        if stream is not None:
            try:
                stream.stop()
                stream.close()
            except Exception as e:
                logger.debug("Error closing wakeword stream: %s", e)
        logger.info("WakeWord listener stopped.")
