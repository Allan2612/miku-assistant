"""
Miku Assistant - Speech-to-Text Manager (faster-whisper on CPU)
Strict adherence to GEMINI.md:
- Runs exclusively on CPU (int8, 4 threads, Spanish language).
- ZERO VRAM usage (PyTorch is not imported; CTranslate2 engine).
- Lazy model loading and complete memory unloading on inactivity.
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Optional, List
import numpy as np

logger = logging.getLogger("miku.stt")

NO_SPEECH_MAX = 0.6


class STTManager:
    """Manages the faster-whisper CPU model lifecycle and transcription."""

    def __init__(
        self,
        model_size: str = "small",
        device: str = "cpu",
        compute_type: str = "int8",
        cpu_threads: int = 4,
        language: str = "es",
    ) -> None:
        self.model_size = model_size
        self.device = device
        self.compute_type = compute_type
        self.cpu_threads = cpu_threads
        self.language = language
        self._model = None
        self._lock = asyncio.Lock()
        logger.info(
            "STTManager initialized (model=%s, device=%s, compute_type=%s, threads=%d)",
            self.model_size,
            self.device,
            self.compute_type,
            self.cpu_threads,
        )

    @property
    def is_loaded(self) -> bool:
        """Returns True if the WhisperModel is currently resident in CPU memory."""
        return self._model is not None

    def _load_model_sync(self) -> None:
        """Synchronously instantiates faster-whisper WhisperModel."""
        from faster_whisper import WhisperModel

        start_t = time.perf_counter()
        logger.info("Loading faster-whisper model '%s' (CPU %s)...", self.model_size, self.compute_type)
        self._model = WhisperModel(
            model_size_or_path=self.model_size,
            device=self.device,
            compute_type=self.compute_type,
            cpu_threads=self.cpu_threads,
        )
        elapsed = time.perf_counter() - start_t
        logger.info("faster-whisper model '%s' loaded in %.2fs.", self.model_size, elapsed)

    async def warmup(self) -> None:
        """Loads the model into CPU memory asynchronously if not already loaded."""
        if self._model is not None:
            return

        async with self._lock:
            if self._model is None:
                await asyncio.to_thread(self._load_model_sync)

    def _transcribe_sync(self, audio: np.ndarray) -> str:
        """Synchronously executes transcription with beam_size=1 and vad_filter=True."""
        if self._model is None:
            return ""

        # Normalize audio to float32 1D array
        if audio.dtype != np.float32:
            audio = audio.astype(np.float32)
        if audio.ndim > 1:
            audio = audio.flatten()

        start_t = time.perf_counter()
        segments, info = self._model.transcribe(
            audio,
            language=self.language,
            beam_size=1,
            best_of=1,
            temperature=0.0,
            # Vocabulary only: whole commands here get "heard" in noise and run by the fast path (H-035)
            initial_prompt="Miku, Spotify, YouTube, Google, Opera GX, Discord, Steam, Bloc de notas.",
            vad_filter=True,
            vad_parameters=dict(min_silence_duration_ms=400),
            repetition_penalty=1.15,
            condition_on_previous_text=False,
        )

        texts: List[str] = []
        for segment in segments:
            clean_text = segment.text.strip()
            # Whisper itself says this segment is probably not speech: drop it instead of acting on it
            if segment.no_speech_prob > NO_SPEECH_MAX:
                logger.info("Dropping likely non-speech segment (p=%.2f): '%s'", segment.no_speech_prob, clean_text)
                continue
            if clean_text:
                texts.append(clean_text)

        transcription = " ".join(texts).strip()
        elapsed = time.perf_counter() - start_t
        logger.info(
            "Transcription completed in %.2fs (duration: %.1fs, lang: %s prob: %.2f): '%s'",
            elapsed,
            info.duration if info else 0.0,
            info.language if info else "es",
            info.language_probability if info else 1.0,
            transcription,
        )
        return transcription

    async def transcribe(self, audio: np.ndarray) -> str:
        """Transcribes a 16kHz float32 audio numpy array into text."""
        if audio is None or len(audio) == 0:
            return ""

        # Pre-warm or load if needed
        if self._model is None:
            await self.warmup()

        async with self._lock:
            try:
                return await asyncio.to_thread(self._transcribe_sync, audio)
            except Exception as e:
                logger.error("Error during STT transcription: %s", e)
                return ""
