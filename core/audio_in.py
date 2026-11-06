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
from typing import Callable, List, Optional
import numpy as np
import sounddevice as sd

from core.vad import StreamingVAD

logger = logging.getLogger("miku.audio_in")

VAD_SPEECH = 0.5    # speech probability that starts the phrase
VAD_SILENCE = 0.35  # below this, the chunk counts as silence



def list_inputs() -> List[str]:
    """The microphones, as the panel offers them: Windows' default API only (every API lists each device again)."""
    try:
        api = sd.query_devices(kind="input")["hostapi"]
        names = [d["name"] for d in sd.query_devices() if d["max_input_channels"] > 0 and d["hostapi"] == api]
    except Exception as e:
        logger.warning("Could not list the microphones: %s", e)
        return []
    return list(dict.fromkeys(names))


def find_input(name: str) -> Optional[int]:
    """The microphone called `name` (config.yaml -> audio.input_device), or None for Windows' default. One that is
    gone (an unplugged headset) falls back to the default instead of leaving Miku deaf."""
    if not name:
        return None
    try:
        api = sd.query_devices(kind="input")["hostapi"]
        for i, d in enumerate(sd.query_devices()):
            if d["max_input_channels"] > 0 and d["hostapi"] == api and d["name"] == name:
                return i
    except Exception as e:
        logger.warning("Could not look for the microphone %r: %s", name, e)
        return None
    logger.warning("Microphone %r not found: using Windows' default.", name)
    return None

class AudioInput:
    """Handles on-demand microphone capture with VAD and instant stream teardown."""

    def __init__(self, sample_rate: int = 16000, channels: int = 1, device_name: str = "") -> None:
        self.sample_rate = sample_rate
        self.channels = channels
        self.device_name = device_name  # config.yaml -> audio.input_device ("" = Windows' default)
        self._block_size = 512  # 32ms at 16kHz (also the silero-vad chunk size)
        self._vad: Optional[StreamingVAD] = None
        self._vad_failed = False
        self._waiting_for_speech = False  # the mic is open and nobody has started talking yet
        self._stop_waiting = False

    def stop_waiting(self) -> bool:
        """Gives up the wait for speech, for a typed message. False if no wait is on, or the user is already talking."""
        if not self._waiting_for_speech:
            return False
        self._stop_waiting = True
        return True

    def _get_vad(self) -> Optional[StreamingVAD]:
        """Silero VAD, loaded once; None (energy fallback) if it cannot load."""
        if self._vad is None and not self._vad_failed:
            try:
                self._vad = StreamingVAD()
            except Exception as e:
                self._vad_failed = True
                logger.warning("Silero VAD unavailable (%s). Falling back to energy-based detection.", e)
        if self._vad is not None:
            self._vad.reset()
        return self._vad

    async def record_phrase(
        self,
        silence_ms: int = 800,
        max_seconds: int = 15,
        initial_timeout: float = 6.0,
        min_speech_duration: float = 0.35,
        on_speech_start: Optional[Callable[[], None]] = None,
    ) -> Optional[np.ndarray]:
        """
        Opens the microphone, records audio until `silence_ms` of silence is detected
        after speech has begun (or until `max_seconds`), then IMMEDIATELY closes the stream.

        Returns:
            np.ndarray: 1D float32 array normalized [-1, 1] at 16kHz, or None if no speech.
        `on_speech_start` runs once when the user starts talking (Miku nods along while listening).
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

        vad = self._get_vad()
        start_time = time.monotonic()
        stream = None

        logger.info(
            "Opening microphone stream (16kHz mono)... Waiting for speech (timeout=%.1fs)...",
            initial_timeout,
        )

        try:
            stream = sd.InputStream(
                device=find_input(self.device_name),
                samplerate=self.sample_rate,
                channels=self.channels,
                dtype="float32",
                blocksize=self._block_size,
                callback=audio_callback,
            )
            stream.start()
            self._stop_waiting = False

            # max_seconds counts speech, not the wait before it: a late start was cut after a few seconds.
            # The wall-clock bound only matters if the stream stops delivering audio
            while speech_accumulated < max_seconds and (time.monotonic() - start_time) < initial_timeout + max_seconds:
                self._waiting_for_speech = not speech_started
                if self._stop_waiting and not speech_started:
                    logger.info("Stopped waiting for speech: a typed message came in.")
                    break
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

                # Silero decides speech vs. not-speech: music or a fan no longer keep the
                # recording open until max_seconds (H-034). Energy is only the fallback.
                if vad is not None:
                    prob = vad(chunk.reshape(-1))
                    if not speech_started:
                        pre_buffer.append(chunk)
                        if (time.monotonic() - start_time) > initial_timeout:
                            logger.info("No speech detected within %.1fs timeout.", initial_timeout)
                            break
                        if prob > VAD_SPEECH:
                            speech_started = True
                            speech_accumulated = chunk_duration
                            silence_accumulated = 0.0
                            recorded_chunks.extend(list(pre_buffer))
                            logger.info("Speech start detected (VAD p=%.2f)", prob)
                            if on_speech_start:
                                on_speech_start()
                    else:
                        recorded_chunks.append(chunk)
                        speech_accumulated += chunk_duration
                        if prob < VAD_SILENCE:
                            silence_accumulated += chunk_duration
                            if silence_accumulated >= silence_limit:
                                logger.info(
                                    "Silence of %.2fs detected after %.2fs of speech (VAD). Ending recording.",
                                    silence_accumulated,
                                    speech_accumulated,
                                )
                                break
                        else:
                            silence_accumulated = max(0.0, silence_accumulated - chunk_duration * 0.5)
                    continue

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
                        if on_speech_start:
                            on_speech_start()
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
            self._waiting_for_speech = False
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
