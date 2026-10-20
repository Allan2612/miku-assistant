"""
Miku Assistant - Audio Input Manager
Strict adherence to GEMINI.md:
- Stream is opened ONLY upon user activation.
- Stream is closed IMMEDIATELY after phrase completion (silence detection) or timeout.
- Guaranteed zero microphone usage when idle.
"""

from __future__ import annotations

import asyncio
from collections import deque
import logging
import time
from typing import Optional, List
import numpy as np
import sounddevice as sd

logger = logging.getLogger("miku.audio_in")


class AudioInput:
    """Handles on-demand microphone capture with VAD and instant stream teardown."""

    def __init__(self, sample_rate: int = 16000, channels: int = 1) -> None:
        self.sample_rate = sample_rate
        self.channels = channels
        self._block_size = 512  # 32ms at 16kHz

    async def record_phrase(
        self,
        silence_ms: int = 800,
        max_seconds: int = 15,
        initial_timeout: float = 6.0,
        min_speech_duration: float = 0.35,
    ) -> Optional[np.ndarray]:
        """
        Opens the microphone, records audio until `silence_ms` of silence is detected
        after speech has begun (or until `max_seconds`), then IMMEDIATELY closes the stream.

        Returns:
            np.ndarray: 1D float32 array normalized [-1, 1] at 16kHz, or None if no speech.
        """
        loop = asyncio.get_running_loop()
        queue: asyncio.Queue[np.ndarray] = asyncio.Queue()

        def audio_callback(indata: np.ndarray, frames: int, time_info: dict, status: sd.CallbackFlags) -> None:
            if status:
                logger.debug("Microphone status callback: %s", status)
            try:
                loop.call_soon_threadsafe(queue.put_nowait, indata.copy())
            except (RuntimeError, asyncio.QueueFull):
                pass

        chunk_duration = self._block_size / self.sample_rate  # 0.032s
        silence_limit = silence_ms / 1000.0  # e.g. 0.8s

        # Rolling pre-buffer of ~320ms (10 chunks) to prevent clipping first syllable
        pre_buffer: deque[np.ndarray] = deque(maxlen=10)
        recorded_chunks: List[np.ndarray] = []

        speech_started = False
        silence_accumulated = 0.0
        speech_accumulated = 0.0
        smoothed_rms = 0.0

        # Calibration parameters
        calibrated = False
        ambient_noise_samples: List[float] = []
        energy_threshold = 0.0020
        silence_threshold = 0.0015

        start_time = time.monotonic()
        stream = None

        logger.info(
            "Opening microphone stream (16kHz mono)... Waiting for speech (timeout=%.1fs)...",
            initial_timeout,
        )

        try:
            stream = sd.InputStream(
                samplerate=self.sample_rate,
                channels=self.channels,
                dtype="float32",
                blocksize=self._block_size,
                callback=audio_callback,
            )
            stream.start()

            while (time.monotonic() - start_time) < max_seconds:
                try:
                    chunk = await asyncio.wait_for(queue.get(), timeout=0.2)
                except asyncio.TimeoutError:
                    if not speech_started and (time.monotonic() - start_time) > initial_timeout:
                        logger.info("Microphone timed out without detecting speech (%.1fs).", initial_timeout)
                        break
                    continue

                rms = float(np.sqrt(np.mean(chunk**2)))
                if smoothed_rms == 0.0:
                    smoothed_rms = rms
                else:
                    smoothed_rms = 0.65 * smoothed_rms + 0.35 * rms

                # First 200ms (6 chunks) used to adapt to ambient noise floor
                if not calibrated:
                    if rms > 0.0035:
                        # Immediate speech detected upon activation: do not contaminate noise floor
                        calibrated = True
                        energy_threshold = 0.0020
                        silence_threshold = 0.0017
                        speech_started = True
                        speech_accumulated = chunk_duration
                        silence_accumulated = 0.0
                        recorded_chunks.append(chunk)
                        logger.info("Immediate speech start detected during calibration (RMS: %.4f)", rms)
                    else:
                        ambient_noise_samples.append(rms)
                        if len(ambient_noise_samples) >= 6:
                            avg_noise = float(np.mean(ambient_noise_samples))
                            # Adapt dynamically to microphone noise floor
                            energy_threshold = max(0.0013, min(0.015, avg_noise * 1.5 + 0.0004))
                            # Silence cutoff: speech ends when energy drops back towards ambient level
                            silence_threshold = max(0.0010, energy_threshold * 0.90)
                            calibrated = True
                            logger.info(
                                "Calibrated ambient noise: %.4f | Trigger threshold: %.4f | Silence cutoff: %.4f",
                                avg_noise,
                                energy_threshold,
                                silence_threshold,
                            )

                if not speech_started:
                    pre_buffer.append(chunk)

                    if (time.monotonic() - start_time) > initial_timeout:
                        logger.info("No speech detected within %.1fs timeout.", initial_timeout)
                        break

                    if rms > energy_threshold or smoothed_rms > energy_threshold:
                        speech_started = True
                        speech_accumulated = chunk_duration
                        silence_accumulated = 0.0
                        # Flush pre-buffer so first phoneme is fully intact
                        recorded_chunks.extend(list(pre_buffer))
                        logger.info("Speech start detected (RMS: %.4f > %.4f)", rms, energy_threshold)
                else:
                    recorded_chunks.append(chunk)
                    speech_accumulated += chunk_duration

                    # Smooth silence detection: chunks below silence_threshold count toward silence
                    if smoothed_rms < silence_threshold:
                        silence_accumulated += chunk_duration
                        if silence_accumulated >= silence_limit:
                            logger.info(
                                "Silence of %.2fs detected after %.2fs of speech. Ending recording cleanly.",
                                silence_accumulated,
                                speech_accumulated,
                            )
                            break
                    else:
                        # Gentle decay rather than instant wipe to zero on single minor acoustic glitch
                        silence_accumulated = max(0.0, silence_accumulated - chunk_duration * 0.5)

        except Exception as e:
            logger.error("Error capturing audio from microphone: %s", e)
            return None
        finally:
            # STRICT REQUIREMENT: Mic stream MUST be closed immediately
            if stream is not None:
                try:
                    stream.stop()
                    stream.close()
                except Exception as ex:
                    logger.warning("Error closing microphone stream: %s", ex)
                logger.info("Microphone stream closed successfully.")

        if speech_started and recorded_chunks and speech_accumulated >= min_speech_duration:
            audio_data = np.concatenate(recorded_chunks, axis=0).flatten()
            logger.info("Captured speech audio: %.2fs (%d samples).", len(audio_data) / self.sample_rate, len(audio_data))
            return audio_data

        logger.info("No actionable speech recorded.")
        return None
