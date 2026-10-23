"""
Miku Assistant - Pipeline Orchestrator
Strict adherence to GEMINI.md:
- Coordinates audio input, STT, LLM, TTS, RVC, and WebSocket events.
- Fires STT and RVC worker pre-warming concurrently during activation while user begins speaking.
- Enforces strict latency (< 3 s response) and mic stream closure immediately after speech.
- Zero torch imports in the main core pipeline!
- Seamless fallback to edge-tts if RVC fails or is disabled.
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import logging
import os
import random
from datetime import datetime, date
from pathlib import Path
from typing import Optional, Any, Tuple
import numpy as np

from core.llm import MikuBrain
from core.tts import TTSManager
from core.stt import STTManager
from core.rvc import RVCManager
from core.audio_in import AudioInput
from core.resources import ResourceManager
from core.tools.timers import set_timer_notifier

logger = logging.getLogger("miku.pipeline")

ROOT_DIR = Path(__file__).resolve().parent.parent

# Spoken right after activation so it is obvious Miku is listening; kept very short
ACK_PHRASES = ("¿Sí?", "¿Dime?", "¿Mm?", "¿Qué pasa?", "¡Aquí estoy!")
ACK_WAIT_S = 3.0  # max wait for the frontend to finish playing the cue
# Said before hiding on inactivity (fixed phrases: voice cached on disk, 0 Gemini requests)
GOODBYE_PHRASES = ("¡Adiós!", "¡Chao!", "¡Nos vemos!", "¡Hasta luego!", "Me voy, ¡llámame si me necesitas!")


def _normalize(text: str) -> str:
    return "".join(c for c in text.lower() if c.isalnum() or c == " ").strip()


_ACK_NORMALIZED = {_normalize(p) for p in ACK_PHRASES} | {"si"}


def _trim_silence(wav_bytes: bytes, threshold: float = 0.01, keep_s: float = 0.08) -> bytes:
    """edge-tts pads short phrases to ~1.9 s: trim it so the mic opens right after the cue."""
    import io
    import soundfile as sf

    audio, sr = sf.read(io.BytesIO(wav_bytes), dtype="float32")
    loud = np.flatnonzero(np.abs(audio) > threshold)
    if loud.size == 0:
        return wav_bytes
    keep = int(keep_s * sr)
    audio = audio[max(0, loud[0] - keep):loud[-1] + keep]
    out = io.BytesIO()
    sf.write(out, audio, sr, format="WAV", subtype="PCM_16")
    return out.getvalue()


class MikuPipeline:
    """Orchestrates end-to-end voice and text interactions."""

    def __init__(
        self,
        brain: MikuBrain,
        tts: TTSManager,
        stt: STTManager,
        audio_in: AudioInput,
        resources: ResourceManager,
        server: Any,  # MikuServer
        rvc: Optional[RVCManager] = None,
        silence_ms: int = 800,
        max_record_seconds: int = 15,
    ) -> None:
        self.brain = brain
        self.tts = tts
        self.stt = stt
        self.audio_in = audio_in
        self.resources = resources
        self.server = server
        self.rvc = rvc
        self.silence_ms = silence_ms
        self.max_record_seconds = max_record_seconds
        self.wakeword: Optional[Any] = None

        self._pipeline_lock = asyncio.Lock()
        self._pending_farewell = False
        self._is_listening = False
        self._is_speaking = False
        self._last_text = ""
        self._last_text_time = 0.0
        self._speak_watchdog_task: Optional[asyncio.Task] = None
        self._ack_done: Optional[asyncio.Event] = None
        self._bg_tasks: set = set()

        # Register callback for async timer announcements
        try:
            set_timer_notifier(self.announce_timer, loop=asyncio.get_running_loop())
        except RuntimeError:
            set_timer_notifier(self.announce_timer)

    def _schedule_speak_done_watchdog(self, text: str) -> None:
        """Schedules a safety watchdog in case frontend never sends speak_done (e.g. dropped packet or muted)."""
        if self._speak_watchdog_task and not self._speak_watchdog_task.done():
            self._speak_watchdog_task.cancel()

        # Generous allowance: 0.15s per character + 6.0s grace period
        timeout_sec = max(7.0, len(text) * 0.15 + 6.0)

        async def _watchdog() -> None:
            try:
                await asyncio.sleep(timeout_sec)
                logger.info("Watchdog: speak_done timeout reached (%.1fs). Auto-resuming idle state & wakeword.", timeout_sec)
                await self.server.broadcast({"type": "state", "value": "idle"})
                self.handle_speak_done()
            except asyncio.CancelledError:
                pass

        self._speak_watchdog_task = asyncio.create_task(_watchdog())

    async def say_goodbye(self) -> None:
        """The frontend's auto-hide timer fired: say a short goodbye, then the server hides Miku on its speak_done.

        Busy (listening, thinking, speaking): do nothing; the frontend hides on its own after a fallback wait.
        """
        if self._pipeline_lock.locked() or self._is_speaking or self._is_listening:
            return
        async with self._pipeline_lock:
            self._pending_farewell = True
            await self._speak(random.choice(GOODBYE_PHRASES), "happy", farewell=True, cache=True)

    def _new_activity(self) -> None:
        # A goodbye cut off by barge-in must not hide Miku after the next answer
        self._pending_farewell = False

    def set_wakeword(self, wakeword: Any) -> None:
        """Attaches the wakeword listener to pause/resume during active interactions."""
        self.wakeword = wakeword

    async def _synthesize_voice(self, text: str, cache: bool = False) -> Optional[Tuple[str, str]]:
        """
        Synthesizes speech with edge-tts and converts to Miku voice via RVC.
        Gracefully falls back to edge-tts if RVC fails or is disabled.
        """
        tts_res = await self.tts.synthesize(text, cache=cache)
        if not tts_res:
            return None

        audio_b64, mime = tts_res

        # If RVC is enabled, convert audio timbre & pitch to Miku
        if self.rvc is not None and self.rvc.enabled:
            try:
                rvc_res = await self.rvc.convert(audio_b64)
                if rvc_res:
                    return rvc_res
                else:
                    logger.info("RVC returned None. Falling back to edge-tts voice.")
            except Exception as e:
                logger.warning("RVC conversion failed (%s). Falling back to edge-tts voice.", e)

        return audio_b64, mime

    def _spawn_bg(self, coro: Any) -> None:
        """Fire-and-forget task with a strong reference (unreferenced tasks can be collected)."""
        task = asyncio.create_task(coro)
        self._bg_tasks.add(task)
        task.add_done_callback(self._bg_tasks.discard)

    @staticmethod
    def _ack_file(phrase: str) -> Path:
        digest = hashlib.md5(phrase.encode("utf-8")).hexdigest()
        return ROOT_DIR / "cache" / "voice" / f"ack_{digest}.wav"

    async def _ack_audio(self, phrase: str) -> Optional[Tuple[str, str]]:
        """Miku's voice (RVC, cached on disk) if ready; otherwise the cached base voice."""
        rvc_file = self._ack_file(phrase)
        if rvc_file.exists():
            return base64.b64encode(rvc_file.read_bytes()).decode("ascii"), "audio/wav"
        base = await self.tts.synthesize(phrase, cache=True)
        if base and self.rvc is not None and self.rvc.enabled and self.rvc.is_running and not self.rvc.is_warming_up:
            self._spawn_bg(self._convert_ack(base[0], rvc_file))
        return base

    async def _convert_ack(self, base_b64: str, rvc_file: Path) -> None:
        res = await self.rvc.convert(base_b64)
        if res:
            tmp = rvc_file.with_suffix(".tmp")
            tmp.write_bytes(_trim_silence(base64.b64decode(res[0])))
            os.replace(tmp, rvc_file)
            logger.info("Cached Miku-voice acknowledgement: %s", rvc_file.name)

    async def prepare_acks(self) -> None:
        """Pre-generates every acknowledgement (base voice now, Miku's voice once RVC is loaded)."""
        try:
            for phrase in ACK_PHRASES:
                await self.tts.synthesize(phrase, cache=True)
            if self.rvc is None or not self.rvc.enabled:
                return
            for _ in range(240):  # the first RVC load can take minutes
                if self.rvc.is_running and not self.rvc.is_warming_up:
                    break
                await asyncio.sleep(1)
            for phrase in ACK_PHRASES:
                if not self._ack_file(phrase).exists():
                    base = await self.tts.synthesize(phrase, cache=True)
                    if base:
                        await self._convert_ack(base[0], self._ack_file(phrase))
        except Exception:
            logger.exception("Could not prepare acknowledgement phrases")

    async def _acknowledge(self) -> None:
        """Short spoken cue ("¿Sí?") on activation; returns once it has finished playing."""
        phrase = random.choice(ACK_PHRASES)
        audio = await self._ack_audio(phrase)
        if not audio:
            return
        audio_b64, mime = audio
        self._ack_done = asyncio.Event()
        try:
            await self.server.broadcast({
                "type": "speak", "audio_b64": audio_b64, "mime": mime, "text": phrase, "emotion": "happy",
            })
            await asyncio.wait_for(self._ack_done.wait(), ACK_WAIT_S)
        except asyncio.TimeoutError:
            logger.info("No speak_done for the acknowledgement; listening anyway.")
        finally:
            self._ack_done = None

    def ack_finished(self) -> bool:
        """Called by the server on speak_done: True if it belonged to the acknowledgement cue."""
        if self._ack_done is not None and not self._ack_done.is_set():
            self._ack_done.set()
            return True
        return False

    async def _speak(self, text: str, emotion: str, farewell: bool = False, cache: bool = False) -> None:
        """Shows Miku's answer and speaks it, or degrades to subtitle only. Shared by every path (H-032)."""
        voice_res = await self._synthesize_voice(text, cache=cache)
        self.resources.touch()
        await self.server.broadcast({"type": "expression", "name": emotion})
        await self.server.broadcast({"type": "subtitle", "who": "miku", "text": text})
        if voice_res:
            audio_b64, mime = voice_res
            # Paused while speaking: Miku's own voice must not trigger the wake word
            if self.wakeword is not None:
                self.wakeword.pause()
            self._is_speaking = True
            await self.server.broadcast({"type": "state", "value": "speaking"})
            await self.server.broadcast({
                "type": "speak",
                "audio_b64": audio_b64,
                "mime": mime,
                "text": text,
                "emotion": emotion,
            })
            self._schedule_speak_done_watchdog(text)
        else:
            logger.warning("Voice unavailable. Degrading to text subtitle.")
            await self.server.broadcast({"type": "state", "value": "idle"})
            if self.wakeword is not None:
                self.wakeword.resume()
            if farewell:
                await asyncio.sleep(3.5)
                await self.server.broadcast({"type": "hide"})

    async def announce_timer(self, message: str) -> None:
        """Invoked asynchronously when a timer or reminder expires."""
        logger.info("Announcing timer: %s", message)
        # Wait for any ongoing conversation instead of talking over it (H-031)
        async with self._pipeline_lock:
            self._new_activity()
            self.resources.touch()
            await self.server.broadcast({"type": "show"})
            await self._speak(message, "happy")

    async def handle_voice_activation(self) -> None:
        """
        Triggered when user activates Miku via hotkey, wakeword, or click.
        Supports instant barge-in: interrupts Miku immediately if she is currently speaking.
        Pre-warms STT and RVC in background concurrently while user speaks.
        """
        self._new_activity()
        # Instant Barge-In: if Miku is currently speaking, cut off voice and switch to listening immediately
        if self._is_speaking:
            logger.info("Barge-in: User activated while Miku is speaking. Cutting off speech immediately.")
            self._is_speaking = False
            if self._speak_watchdog_task and not self._speak_watchdog_task.done():
                self._speak_watchdog_task.cancel()
            await self.server.broadcast({"type": "stop_speaking"})
            await self.server.broadcast({"type": "state", "value": "listening"})
            await self.server.broadcast({"type": "expression", "name": "neutral"})

        if self._is_listening or self._pipeline_lock.locked():
            logger.info("Voice activation ignored: already listening or processing.")
            return

        async with self._pipeline_lock:
            self._is_listening = True
            self.resources.touch()
            if self.wakeword is not None:
                self.wakeword.pause()

            try:
                # 1. Concurrently pre-warm STT and RVC worker while the user begins speaking
                stt_warmup = None if self.stt.is_loaded else asyncio.create_task(self.stt.warmup())
                if self.rvc is not None and self.rvc.enabled and not self.rvc.is_running:
                    self._spawn_bg(self.rvc.warmup())

                # 2. Show Miku, say a short "¿Sí?" so the user knows she is listening, then listen.
                # The mic opens only after the cue has finished playing, so it is not recorded.
                await self.server.broadcast({"type": "show"})
                await self.server.broadcast({"type": "expression", "name": "happy"})
                await self._acknowledge()
                await self.server.broadcast({"type": "state", "value": "listening"})
                await self.server.broadcast({"type": "expression", "name": "neutral"})

                # 3. Capture phrase from microphone with VAD
                # Mic opens here and closes immediately upon silence
                audio: Optional[np.ndarray] = await self.audio_in.record_phrase(
                    silence_ms=self.silence_ms,
                    max_seconds=self.max_record_seconds,
                    initial_timeout=5.5,
                )

                if audio is None:
                    logger.info("No speech captured. Returning to idle.")
                    await self.server.broadcast({"type": "state", "value": "idle"})
                    if self.wakeword is not None:
                        self.wakeword.resume()
                    return

                # 4. Indicate thinking state to UI
                await self.server.broadcast({"type": "state", "value": "thinking"})
                await self.server.broadcast({"type": "expression", "name": "thinking"})

                # Wait for Whisper only: waiting for the RVC load (35-80 s) here delayed every
                # first answer after an unload; RVC falls back to the base voice while it loads
                if stt_warmup is not None:
                    await asyncio.gather(stt_warmup, return_exceptions=True)

                # 5. Transcribe audio with faster-whisper on CPU
                transcribed_text = await self.stt.transcribe(audio)

                # Miku's own cue picked up by the mic must never reach Gemini: "sí" would confirm
                # a pending destructive action
                if _normalize(transcribed_text) in _ACK_NORMALIZED:
                    logger.info("Transcription is just the acknowledgement cue (%r). Ignoring.", transcribed_text)
                    transcribed_text = ""

                if not transcribed_text:
                    logger.info("Empty transcription. Returning to idle.")
                    await self.server.broadcast({"type": "state", "value": "idle"})
                    if self.wakeword is not None:
                        self.wakeword.resume()
                    return

                # 6. One Gemini request hears the audio itself (Whisper's text only gates and drives the fast path)
                self.resources.touch()
                emotion, answer, is_farewell = await self.brain.chat(transcribed_text, audio=audio)
                self._pending_farewell = is_farewell

                # 7. User subtitle: what Gemini understood, which beats Whisper's guess
                await self.server.broadcast({
                    "type": "subtitle",
                    "who": "user",
                    "text": getattr(self.brain, "last_heard", "") or transcribed_text,
                })

                # 8. Synthesize speech (edge-tts -> RVC) and speak
                await self._speak(answer, emotion, farewell=is_farewell)

            except Exception:
                logger.exception("Error in voice activation pipeline")
                await self.server.broadcast({"type": "state", "value": "idle"})
                if self.wakeword is not None:
                    self.wakeword.resume()
            finally:
                self._is_listening = False

    async def handle_text_input(self, text: str) -> None:
        """Processes sequential text chat from the frontend."""
        clean = text.strip()
        if not clean:
            return

        import time
        now = time.monotonic()
        if clean == self._last_text and (now - self._last_text_time) < 2.0:
            logger.info("Dropping duplicate text input within 2.0s: '%s'", clean)
            return

        if self._pipeline_lock.locked():
            logger.info("Pipeline busy. Dropping overlapping text input: '%s'", clean)
            return

        self._new_activity()
        async with self._pipeline_lock:
            self._last_text = clean
            self._last_text_time = now
            self.resources.touch()
            if self.wakeword is not None:
                self.wakeword.pause()
            logger.info("Processing text input: %s", clean)
            try:
                await self._process_text(text)
            except Exception:
                # Without this the wake word stayed paused and the UI stuck on "thinking" (H-030)
                logger.exception("Error in text input pipeline")
                await self.server.broadcast({"type": "state", "value": "idle"})
                if self.wakeword is not None:
                    self.wakeword.resume()

    async def _process_text(self, text: str) -> None:
        """Body of handle_text_input; runs under the pipeline lock."""

        # Pre-warm RVC in background if needed
        if self.rvc is not None and self.rvc.enabled and not self.rvc.is_running:
            asyncio.create_task(self.rvc.warmup())

        # 1. User subtitle
        await self.server.broadcast({
            "type": "subtitle",
            "who": "user",
            "text": text,
        })

        # 2. Indicate thinking state
        await self.server.broadcast({"type": "state", "value": "thinking"})
        await self.server.broadcast({"type": "expression", "name": "thinking"})

        # 3. LLM completion
        emotion, answer, is_farewell = await self.brain.chat(text)
        self._pending_farewell = is_farewell
        self.resources.touch()

        # 4. Synthesize speech (edge-tts -> RVC) and speak
        await self._speak(answer, emotion, farewell=is_farewell)

    def handle_speak_done(self) -> bool:
        """Returns True if there is a pending farewell animation to trigger."""
        self._is_speaking = False
        if self._speak_watchdog_task and not self._speak_watchdog_task.done():
            self._speak_watchdog_task.cancel()
        farewell = self._pending_farewell
        self._pending_farewell = False
        if self.wakeword is not None:
            self.wakeword.resume()
        return farewell

    async def check_startup_greeting(self) -> None:
        """
        Greets the user according to the time of day (Fase 8).
        Runs when Miku Assistant boots up and frontend connects.
        """
        # Once per day, as persona.md says: restarting the backend must not greet again (H-032)
        marker = ROOT_DIR / "cache" / "last_greeting.txt"
        today = date.today().isoformat()
        try:
            if marker.exists() and marker.read_text(encoding="ascii").strip() == today:
                logger.info("Startup greeting already played today. Skipping.")
                return
            marker.write_text(today, encoding="ascii")

            # Wait up to 15s for frontend client to connect
            for _ in range(30):
                if self.server.clients:
                    break
                await asyncio.sleep(0.5)

            # Allow 1.2s for Live2D model assets to initialize and window appear animation
            await asyncio.sleep(1.2)

            now_hour = datetime.now().hour
            if 5 <= now_hour < 12:
                greeting = "¡Buenos días! ¿Qué vamos a hacer hoy?"
            elif 12 <= now_hour < 20:
                greeting = "¡Buenas tardes! ¿En qué puedo ayudarte?"
            else:
                greeting = "¡Buenas noches! ¿Qué necesitas hoy?"

            logger.info("Playing startup greeting: %s", greeting)
            async with self._pipeline_lock:
                await self.server.broadcast({"type": "show"})
                await self._speak(greeting, "happy", cache=True)  # fixed phrase
        except Exception:
            logger.exception("Startup greeting failed")
