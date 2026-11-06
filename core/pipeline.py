"""
Miku Assistant - Pipeline Orchestrator
Strict adherence to GEMINI.md:
- Coordinates audio input, STT, LLM, TTS, RVC, and WebSocket events.
- Fires STT and RVC worker pre-warming concurrently during activation while user begins speaking.
- Enforces strict latency (< 3 s response) and mic stream closure immediately after speech.
- Zero torch imports in the main core pipeline!
- One voice: if RVC fails the answer is a subtitle only; the base edge-tts voice only when RVC is off in config.
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import logging
import os
import random
import re
import time
from datetime import datetime, date
from pathlib import Path
from typing import Optional, Any, Tuple
import numpy as np

from core import intent
from core import wakeword as wakeword_mod
from core.llm import MikuBrain
from core.tts import TTSManager
from core.stt import STTManager
from core.rvc import RVCManager
from core.audio_in import AudioInput
from core.resources import ResourceManager
from core.tools.timers import describe_today, set_timer_notifier
from core.tools.windows import fullscreen_app_in_front

logger = logging.getLogger("miku.pipeline")

from core.paths import CACHE

# Spoken right after activation so it is obvious Miku is listening; kept very short
ACK_PHRASES = ("¿Sí?", "¿Dime?", "¿Mm?", "¿Qué pasa?", "¡Aquí estoy!")
ACK_WAIT_S = 3.0  # max wait for the frontend to finish playing the cue
# Conversation mode: the mic opens this long after she stops talking (her voice must not be recorded)
FOLLOW_UP_DELAY_S = 0.35
ANNOUNCE_WAIT_S = 30.0  # a reminder waits at most this long for her current answer to finish
GREETING_VOICE_WAIT_S = 90.0  # the startup greeting waits this long for RVC (cold start)
GOODBYE_WINDOW_S = 15.0  # a goodbye only if she answered the user within hide_after_s + this
# Said when a Gemini model fails (per-minute quota, 503) and the next one is tried: the user knows she is on it
FILLER_PHRASES = ("Un momento...", "Mmm...", "Déjame pensar...", "Dame un segundito...", "A ver...")
# Said before hiding on inactivity (fixed phrases: voice cached on disk, 0 Gemini requests)
GOODBYE_PHRASES = ("¡Adiós!", "¡Chao!", "¡Nos vemos!", "¡Hasta luego!", "Me voy, ¡llámame si me necesitas!")


# False wake word activations score up to 0.99, so Whisper checks the 2 s clip while she listens. But it often
# mishears a short real "Hey Miku" ("Maes.", "Más", nothing): 22 clips of 26-oct showed that rejecting every
# clip without "Miku" hid her from real calls. Only clear cases are false: near silence, or a sentence of
# other talk (the user chatting while gaming: "cuatro más, el mejor de cinco")
WAKE_CHECK_TIMEOUT_S = 6.0
# Loudest 0.2 s of the clip below this: nobody spoke. False ones measured 0.0008-0.002; a real, quiet "Hey Miku"
# measured 0.0043 (27-oct 13:12, rejected at 0.005 while the user then gave a clear order)
WAKE_SILENCE_RMS = 0.003
# This many words without "Miku" is someone talking about something else. 3 dropped a real call: a "Hey Miku" heard
# as "¡Granza de la..." (log 1-nov)
WAKE_SENTENCE_WORDS = 4
# A reply that only sends her away
DISMISSAL = re.compile(r"(no+|na+|nada|nah|no era (a ti|para ti)|no te llam[eé]|c[aá]llate|sh+|olv[ií]dalo)")

# RVC takes about as long as the audio it makes (1.1 s per second on a CPU, log 5-nov), and a whole answer had to be
# ready before it sounded. Sentence by sentence the first one sounds much sooner. False: the whole answer at once
VOICE_BY_SENTENCE = True
VOICE_PIECE_MIN_CHARS = 25  # shorter sentences join a neighbour: "¡Listo!" alone would only add a pause
VOICE_PIECE_WAIT_S = 75.0  # past RVC's own 60 s limit: never a stuck answer
_SENTENCE_END = re.compile(r"(?<=[.!?…])\s+")


def split_for_voice(text: str) -> list[str]:
    """The answer in the pieces her voice is made in, one sentence each unless it is too short to stand alone."""
    pieces: list[str] = []
    for sentence in _SENTENCE_END.split(text.strip()):
        if pieces and len(pieces[-1]) < VOICE_PIECE_MIN_CHARS:
            pieces[-1] += " " + sentence
        else:
            pieces.append(sentence)
    if len(pieces) > 1 and len(pieces[-1]) < VOICE_PIECE_MIN_CHARS:
        last = pieces.pop()
        pieces[-1] += " " + last
    return pieces


class _VoiceChain:
    """The rest of an answer being spoken: its pieces are made ahead, and each is sent on the last one's speak_done."""

    def __init__(self, text: str, emotion: str, farewell: bool, left: int) -> None:
        self.text, self.emotion, self.farewell, self.left = text, emotion, farewell, left
        self.ready: asyncio.Queue = asyncio.Queue()


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
        follow_up_s: float = 0.0,
        hide_after_s: float = 20.0,
        over_fullscreen: bool = True,
    ) -> None:
        self.brain = brain
        self.brain.on_model_switch = self._say_filler
        self.tts = tts
        self.stt = stt
        self.audio_in = audio_in
        self.resources = resources
        self.server = server
        self.rvc = rvc
        self.silence_ms = silence_ms
        self.max_record_seconds = max_record_seconds
        self.follow_up_s = follow_up_s  # conversation mode: seconds the mic waits after each answer (0 = off)
        self._text_takes_over = False  # a typed message closed the mic: that wait says nothing about the wake word
        self._last_answer = ""
        # The frontend hides her after hide_after_s without activity: an answer newer than that means she is
        # still on screen, talking with the user
        self.hide_after_s = hide_after_s
        self.over_fullscreen = over_fullscreen
        self._last_turn_at = float("-inf")
        self._heard_user = False  # someone already talked to her: the startup greeting is skipped
        self.wakeword: Optional[Any] = None

        self._pipeline_lock = asyncio.Lock()
        self._pending_farewell = False
        self._is_listening = False
        self._is_speaking = False
        self._hidden = False  # hidden by hand: a turn still running must not talk or open the mic
        self._wake_clip_name = ""  # the clip of the activation being checked
        self._last_text = ""
        self._last_text_time = 0.0
        self._speak_watchdog_task: Optional[asyncio.Task] = None
        self._voice_chain: Optional[_VoiceChain] = None  # None: nothing left to say after the current audio
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
                self._speak_watchdog_task = None  # or handle_speak_done cancels this task and the hide below
                if self.handle_speak_done():  # a goodbye: she hides now, not 20 s later on inactivity
                    await self.server.broadcast({"type": "hide"})
            except asyncio.CancelledError:
                pass

        self._speak_watchdog_task = asyncio.create_task(_watchdog())

    async def say_goodbye(self) -> None:
        """The frontend's auto-hide timer fired: say a short goodbye, then the server hides Miku on its speak_done.

        Busy (listening, thinking, speaking): do nothing; the frontend hides on its own after a fallback wait.
        """
        if self.busy:
            return
        # Nothing said with the user this time (she shows up at startup, or was called and nobody spoke): a
        # goodbye out of nowhere is odd (log 27-oct, 20 s after a restart). She just hides
        if time.monotonic() - self._last_turn_at > self.hide_after_s + GOODBYE_WINDOW_S:
            await self.server.broadcast({"type": "hide"})
            return
        async with self._pipeline_lock:
            self._pending_farewell = True
            await self._speak(random.choice(GOODBYE_PHRASES), "happy", farewell=True, cache=True)

    @property
    def busy(self) -> bool:
        """Listening, thinking or speaking."""
        return self._pipeline_lock.locked() or self._is_speaking or self._is_listening

    def end_conversation(self) -> None:
        """She was hidden by hand: the next reminder must not reopen a conversation, and an answer cut off by the hide
        must not open the mic with her hidden (its speak_done never comes; the watchdog did it)."""
        self._last_turn_at = float("-inf")
        self._pending_farewell = False
        self._hidden = True
        self._voice_chain = None
        if self._speak_watchdog_task and not self._speak_watchdog_task.done():
            self._speak_watchdog_task.cancel()
        if self._is_speaking:
            self._is_speaking = False
            if self.wakeword is not None:
                self.wakeword.resume()

    def voice_only(self) -> bool:
        """Turned off in the panel: with a game or a video at full screen she does not show herself. On by default
        ("que se muestre siempre", 4-nov), though a window over a game in exclusive full screen can minimize it."""
        return not self.over_fullscreen and fullscreen_app_in_front()

    async def _show(self) -> None:
        self._hidden = False
        if self.voice_only():
            logger.info("Full-screen app in front: voice only, Miku stays hidden.")
            return
        await self.server.broadcast({"type": "show"})

    def _new_activity(self) -> None:
        # A goodbye cut off by barge-in must not hide Miku after the next answer
        self._pending_farewell = False

    def set_wakeword(self, wakeword: Any) -> None:
        """Attaches the wakeword listener to pause/resume during active interactions."""
        self.wakeword = wakeword

    async def _synthesize_voice(self, text: str, cache: bool = False) -> Optional[Tuple[str, str]]:
        """
        Synthesizes speech with edge-tts and converts it to Miku's voice via RVC.
        One voice only: if RVC is on and fails, None (the answer goes out as a subtitle), never the base voice.
        """
        tts_res = await self.tts.synthesize(text, cache=cache)
        if not tts_res:
            return None

        audio_b64, mime = tts_res
        if self.rvc is None or not self.rvc.enabled:
            return audio_b64, mime  # RVC off in config.yaml: the base voice is her voice

        try:
            rvc_res = await self.rvc.convert(audio_b64)
        except Exception as e:
            logger.warning("RVC conversion failed (%s).", e)
            rvc_res = None
        if not rvc_res:
            logger.warning("No Miku voice for this answer: subtitle only, never another voice.")
        return rvc_res

    def _spawn_bg(self, coro: Any) -> None:
        """Fire-and-forget task with a strong reference (unreferenced tasks can be collected)."""
        task = asyncio.create_task(coro)
        self._bg_tasks.add(task)
        task.add_done_callback(self._bg_tasks.discard)

    def _ack_file(self, phrase: str) -> Path:
        # Every voice setting is part of the name, base voice included: a cue cached with another model, pitch or
        # speed must never be played (26-27 oct)
        base = "|".join(str(getattr(self.tts, k, "")) for k in ("voice", "rate", "pitch"))
        voice = f"{base}|{self.rvc.model_path}|{self.rvc.f0_up_key}|{self.rvc.index_rate}" if self.rvc is not None else base
        digest = hashlib.md5(f"{phrase}|{voice}".encode("utf-8")).hexdigest()
        return CACHE / "voice" / f"ack_{digest}.wav"

    async def _ack_audio(self, phrase: str) -> Optional[Tuple[str, str]]:
        """The cue in Miku's voice (RVC, cached on disk). Not cached yet: converted now if RVC is loaded,
        otherwise skipped (the listening tone still plays): never in another voice."""
        if self.rvc is None or not self.rvc.enabled:
            return await self.tts.synthesize(phrase, cache=True)
        rvc_file = self._ack_file(phrase)
        if not rvc_file.exists() and self.rvc.is_loaded:
            base = await self.tts.synthesize(phrase, cache=True)
            if base:
                await self._convert_ack(base[0], rvc_file)
        if rvc_file.exists():
            return base64.b64encode(rvc_file.read_bytes()).decode("ascii"), "audio/wav"
        return None

    async def _convert_ack(self, base_b64: str, rvc_file: Path) -> None:
        res = await self.rvc.convert(base_b64)
        if res:
            rvc_file.parent.mkdir(parents=True, exist_ok=True)
            tmp = rvc_file.with_suffix(".tmp")
            tmp.write_bytes(_trim_silence(base64.b64decode(res[0])))
            os.replace(tmp, rvc_file)
            logger.info("Cached Miku-voice acknowledgement: %s", rvc_file.name)

    async def prepare_acks(self) -> None:
        """Pre-generates every cue (base voice now, Miku's voice once RVC is loaded)."""
        try:
            for phrase in ACK_PHRASES + FILLER_PHRASES:
                await self.tts.synthesize(phrase, cache=True)
            if self.rvc is None or not self.rvc.enabled:
                return
            for _ in range(240):  # the first RVC load can take minutes
                if self.rvc.is_loaded:
                    break
                await asyncio.sleep(1)
            for phrase in ACK_PHRASES + FILLER_PHRASES:
                if not self._ack_file(phrase).exists():
                    base = await self.tts.synthesize(phrase, cache=True)
                    if base:
                        await self._convert_ack(base[0], self._ack_file(phrase))
        except Exception:
            logger.exception("Could not prepare acknowledgement phrases")

    async def _acknowledge(self) -> None:
        """Short spoken cue ("¿Sí?") on activation; returns once it has finished playing."""
        await self._play_cue(ACK_PHRASES, "happy")

    async def _say_filler(self) -> None:
        """"Un momento...": a model failed and the brain tries the next one, so the wait does not feel dead."""
        await self._play_cue(FILLER_PHRASES, "thinking")

    async def _play_cue(self, phrases: Tuple[str, ...], emotion: str) -> None:
        """Plays one cached short phrase and returns once it has finished (its speak_done is swallowed)."""
        if not self.server.clients:
            return  # nobody to play it: do not wait ACK_WAIT_S for a speak_done that never comes
        phrase = random.choice(phrases)
        audio = await self._ack_audio(phrase)
        if not audio:
            return
        audio_b64, mime = audio
        self._ack_done = asyncio.Event()
        try:
            await self.server.broadcast({
                "type": "speak", "audio_b64": audio_b64, "mime": mime, "text": phrase, "emotion": emotion,
            })
            await asyncio.wait_for(self._ack_done.wait(), ACK_WAIT_S)
        except asyncio.TimeoutError:
            logger.info("No speak_done for the cue '%s'; going on.", phrase)
        finally:
            self._ack_done = None

    def ack_finished(self) -> bool:
        """Called by the server on speak_done: True if it belonged to the acknowledgement cue."""
        if self._ack_done is not None and not self._ack_done.is_set():
            self._ack_done.set()
            return True
        return False

    async def _speak(
        self, text: str, emotion: str, farewell: bool = False, cache: bool = False, gesture: Optional[str] = None,
        quiet: bool = False,
    ) -> None:
        """Shows Miku's answer and speaks it, or degrades to subtitle only. Shared by every path (H-032).
        `gesture` asks the avatar for a specific one ("attention" for a reminder, "greet"); otherwise she picks
        from the emotion and from how this turn's actions went. `quiet`: text only, asked from the panel's chat
        (no voice, no GPU work)."""
        self._last_turn_at = float("-inf") if farewell else time.monotonic()
        if not text and farewell:
            # "Ocúltate": she goes at once, without a word and without opening the mic again
            self._pending_farewell = False
            await self.server.broadcast({"type": "state", "value": "idle"})
            await self.server.broadcast({"type": "hide"})
            if self.wakeword is not None:
                self.wakeword.resume()
            return
        if self._hidden:
            # Hidden from the tray while she listened or thought: she must not talk, nor open the mic, unseen
            logger.info("Hidden by hand during the turn. Not speaking: %s", text)
            self._pending_farewell = False
            await self.server.broadcast({"type": "state", "value": "idle"})
            if self.wakeword is not None:
                self.wakeword.resume()
            return
        self._last_answer = text
        self._voice_chain = None  # a newer answer replaces what was left of the last one
        by_sentence = VOICE_BY_SENTENCE and not quiet and not cache and self.rvc is not None and self.rvc.enabled
        pieces = split_for_voice(text) if by_sentence else [text]
        voice_res = None if quiet else await self._synthesize_voice(pieces[0], cache=cache)
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
            rest = pieces[1:]
            if rest:
                logger.info("Voice by sentence: %d pieces.", len(pieces))
                self._voice_chain = _VoiceChain(text, emotion, farewell, len(rest))
                self._spawn_bg(self._prepare_pieces(self._voice_chain, rest))
            await self.server.broadcast({
                "type": "speak",
                "audio_b64": audio_b64,
                "mime": mime,
                "text": text,
                "emotion": emotion,
                # Body language: word timings for the mouth and head beats, the goodbye wave, the gesture
                "words": self.tts.words_for(pieces[0]),
                "farewell": farewell and not rest,
                "gesture": gesture,
                "outcome": getattr(self.brain, "last_outcome", None),
            })
            self._schedule_speak_done_watchdog(pieces[0])
        else:
            if not quiet:
                logger.warning("Voice unavailable. Degrading to text subtitle.")
            await self.server.broadcast({"type": "state", "value": "idle"})
            if self.wakeword is not None:
                self.wakeword.resume()
            if farewell:
                await asyncio.sleep(3.5)
                await self.server.broadcast({"type": "hide"})

    async def _prepare_pieces(self, chain: _VoiceChain, pieces: list[str]) -> None:
        """Makes the rest of the answer while the first piece plays. A conversion in progress is left to finish, not
        cancelled: the RVC worker answers one command at a time, and its late reply would land on the next one."""
        for piece in pieces:
            if chain is not self._voice_chain:
                return  # cut off
            try:
                voice = await self._synthesize_voice(piece)
            except Exception:
                logger.exception("Error making a piece of the voice")
                voice = None
            await chain.ready.put((piece, voice))
            if voice is None:
                return

    def advance_voice(self) -> bool:
        """Called by the server on speak_done: True if more of this answer follows, so her turn is not over."""
        chain = self._voice_chain
        if chain is None:
            return False
        if self._speak_watchdog_task and not self._speak_watchdog_task.done():
            self._speak_watchdog_task.cancel()
        self._spawn_bg(self._play_next_piece(chain))
        return True

    async def _play_next_piece(self, chain: _VoiceChain) -> None:
        asked_at = time.monotonic()
        try:
            piece, voice = await asyncio.wait_for(chain.ready.get(), VOICE_PIECE_WAIT_S)
        except asyncio.TimeoutError:
            piece, voice = "", None
        if chain is not self._voice_chain:
            return  # cut off while it was being made
        if voice is None:
            logger.warning("No voice for the rest of the answer: it stays in the subtitle.")
            await self.server.broadcast({"type": "state", "value": "idle"})
            if self.handle_speak_done():
                await self.server.broadcast({"type": "hide"})
            return
        logger.info("Next piece of the voice sent after a %.1fs pause.", time.monotonic() - asked_at)
        chain.left -= 1
        last = chain.left == 0
        if last:
            self._voice_chain = None
        self.resources.touch()
        audio_b64, mime = voice
        await self.server.broadcast({
            "type": "speak",
            "audio_b64": audio_b64,
            "mime": mime,
            "text": chain.text,  # the subtitle keeps the whole answer
            "emotion": chain.emotion,
            "words": self.tts.words_for(piece),
            "farewell": chain.farewell and last,
        })
        self._schedule_speak_done_watchdog(piece)

    async def announce_timer(self, message: str) -> None:
        """Invoked asynchronously when a timer or reminder expires."""
        logger.info("Announcing timer: %s", message)
        # Wait for any ongoing conversation instead of talking over it (H-031)
        async with self._pipeline_lock:
            # The lock is free once an answer is sent, not once it is heard: wait for her to finish talking
            # (log 26-oct: the reminder played over "¡Con gusto!"), then for a goodbye's hide to go through
            waited = False
            for _ in range(int(ANNOUNCE_WAIT_S / 0.2)):
                if not self._is_speaking:
                    break
                waited = True
                await asyncio.sleep(0.2)
            if waited:
                await asyncio.sleep(1.5)
            self.resources.touch()
            # Hidden: she shows up, says it and hides again, no mic afterwards (log 26-oct: the mic opened after
            # every reminder). In the middle of a conversation: she says it and the conversation goes on
            talking = time.monotonic() - self._last_turn_at < self.hide_after_s
            await self._show()
            self._pending_farewell = not talking
            self.brain.note_announcement(message)
            await self._speak(message, "happy", farewell=not talking, gesture="attention")

    async def handle_voice_activation(self, wake_clip: Optional[np.ndarray] = None) -> None:
        """
        Triggered when user activates Miku via hotkey, wakeword, or click.
        Supports instant barge-in: interrupts Miku immediately if she is currently speaking.
        Pre-warms STT and RVC in background concurrently while user speaks.
        """
        # Her window is not connected yet (first seconds): she would listen and answer unseen and unheard (log 3-nov)
        if not self.server.clients:
            logger.info("Voice activation ignored: her window is not connected yet.")
            return
        self._new_activity()
        # Instant Barge-In: if Miku is currently speaking, cut off voice and switch to listening immediately
        if self._is_speaking:
            logger.info("Barge-in: User activated while Miku is speaking. Cutting off speech immediately.")
            self._is_speaking = False
            self._voice_chain = None
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
                # The wake word's 2 s clip is transcribed while she says "¿Sí?" and listens: no added delay, and
                # nothing reaches Gemini until it says "Miku"
                wake_check = None
                if wake_clip is not None:
                    wake_check = asyncio.create_task(self._clip_text(wake_clip, stt_warmup))
                    self._wake_clip_name = getattr(self.wakeword, "last_clip", "")
                if self.rvc is not None and self.rvc.enabled and not self.rvc.is_loaded:
                    self._spawn_bg(self.rvc.warmup())

                # 2. Show Miku, say a short "¿Sí?" so the user knows she is listening, then listen.
                # The mic opens only after the cue has finished playing, so it is not recorded.
                await self._show()
                await self.server.broadcast({"type": "expression", "name": "happy"})
                await self._acknowledge()
                await self.server.broadcast({"type": "state", "value": "listening"})
                await self.server.broadcast({"type": "expression", "name": "neutral"})

                # 8 s: at 5.5 s the user often started late, and what they said went nowhere
                await self._listen_and_answer(
                    initial_timeout=8.0, stt_warmup=stt_warmup, wake_check=wake_check, after_cue=True)

            except Exception:
                logger.exception("Error in voice activation pipeline")
                await self.server.broadcast({"type": "state", "value": "idle"})
                if self.wakeword is not None:
                    self.wakeword.resume()
            finally:
                self._is_listening = False

    async def _clip_text(self, clip: np.ndarray, stt_warmup: Optional[asyncio.Task]) -> Tuple[str, float]:
        """What Whisper hears in the wake word clip, and how loud its loudest 0.2 s is."""
        audio = clip.astype(np.float32) / 32768.0
        windows = [audio[i:i + 3200] for i in range(0, max(len(audio) - 3200, 0) + 1, 800)]
        peak = max((float(np.sqrt(np.mean(w ** 2))) for w in windows if len(w)), default=0.0)
        if stt_warmup is not None:
            await asyncio.gather(stt_warmup, return_exceptions=True)
        return await self.stt.transcribe(audio), peak

    async def _wake_was_real(self, wake_check: Optional[asyncio.Task], heard: str = "") -> bool:
        """False (and she hides at once, silently) only for a clearly false activation. Fails open: an unclear
        clip, an error or a slow check never blocks a real request."""
        if wake_check is None:
            return True
        try:
            clip_text, peak = await asyncio.wait_for(asyncio.shield(wake_check), WAKE_CHECK_TIMEOUT_S)
        except Exception:
            return True
        name = self._wake_clip_name
        # "Miku, abre Spotify" in one breath: the name may land in the phrase instead of the clip
        if intent.says_miku(clip_text) or intent.says_miku(heard):
            if name:
                wakeword_mod.suggest(name, "yes")
            return True
        # "Adiós", "No", "Nada" after a clip without her name: the user sending away a wake word nobody said (log
        # 3-nov: 36 of 134 such wakes ended like this, and she answered "¡Vale! Aquí estaré")
        dismissed = bool(heard) and (intent.is_farewell(heard) or bool(DISMISSAL.fullmatch(heard.lower().strip(" ¡!¿?.,"))))
        # An order in the first words is said to her whatever the clip sounded like (log 27-oct: a quiet "Hey Miku"
        # then "Cierra me OBS Studio" was dropped as a false wake word)
        if not dismissed and intent.starts_with_order(heard):
            return True
        silent = peak < WAKE_SILENCE_RMS
        if not dismissed and not silent and len(re.findall(r"\w+", clip_text)) < WAKE_SENTENCE_WORDS:
            return True  # empty or a word or two: what a misheard "Hey Miku" looks like
        logger.info("False wake word (%s): the clip said %r. Hiding without answering.",
                    "dismissed" if dismissed else "silence" if silent else "other talk", clip_text)
        if name:
            wakeword_mod.suggest(name, "no")
        await self.server.broadcast({"type": "state", "value": "idle"})
        await self.server.broadcast({"type": "hide"})
        if self.wakeword is not None:
            self.wakeword.resume()
        return False

    async def _listen_and_answer(
        self, initial_timeout: float, stt_warmup: Optional[asyncio.Task] = None, wake_check: Optional[asyncio.Task] = None,
        after_cue: bool = False,
    ) -> None:
        """Records one phrase, transcribes it and answers it. Runs under the pipeline lock, mic state already shown."""
        # 3. Capture phrase from microphone with VAD
        # Mic opens here and closes immediately upon silence
        audio: Optional[np.ndarray] = await self.audio_in.record_phrase(
            silence_ms=self.silence_ms,
            max_seconds=self.max_record_seconds,
            initial_timeout=initial_timeout,
            on_speech_start=lambda: self._spawn_bg(self.server.broadcast({"type": "user_speech"})),
        )

        if audio is None:
            if not self._text_takes_over and not await self._wake_was_real(wake_check):
                return
            logger.info("No speech captured. Returning to idle.")
            await self.server.broadcast({"type": "state", "value": "idle"})
            if self.wakeword is not None:
                self.wakeword.resume()
            return

        # 4. Indicate thinking state to UI
        heard_at = time.monotonic()
        await self.server.broadcast({"type": "state", "value": "thinking"})
        await self.server.broadcast({"type": "expression", "name": "thinking"})

        # Wait for Whisper only: waiting for the RVC load (35-80 s) here delayed every
        # first answer after an unload; RVC falls back to the base voice while it loads
        if stt_warmup is not None:
            await asyncio.gather(stt_warmup, return_exceptions=True)

        # 5. Transcribe audio with faster-whisper on CPU
        transcribed_text = await self.stt.transcribe(audio)

        # Noise, or her own voice picked up by the mic, must never reach Gemini: her cue "¿Sí?" would confirm
        # a pending destructive action
        kind = intent.classify(transcribed_text, cues=ACK_PHRASES if after_cue else (), last_answer=self._last_answer)
        if transcribed_text and kind in ("noise", "echo"):
            logger.info("Transcription is %s (%r). Ignoring.",
                        "a known Whisper hallucination" if kind == "noise" else "Miku's own voice", transcribed_text)
            transcribed_text = ""

        if not await self._wake_was_real(wake_check, transcribed_text):
            return
        if not transcribed_text:
            logger.info("Empty transcription. Returning to idle.")
            await self.server.broadcast({"type": "state", "value": "idle"})
            if self.wakeword is not None:
                self.wakeword.resume()
            return

        # 6. Show transcribed text as user subtitle (Gemini never sent back what it heard, live test)
        await self.server.broadcast({
            "type": "subtitle",
            "who": "user",
            "text": transcribed_text,
        })

        if self._hidden:
            logger.info("Hidden by hand while listening. Dropping: %s", transcribed_text)
            await self.server.broadcast({"type": "state", "value": "idle"})
            if self.wakeword is not None:
                self.wakeword.resume()
            return

        # 7. One Gemini request hears the audio itself (Whisper's text only gates and drives the fast path)
        self._heard_user = True
        self.resources.touch()
        brain_at = time.monotonic()
        emotion, answer, is_farewell = await self.brain.chat(transcribed_text, audio=audio)
        self._pending_farewell = is_farewell

        # 8. Synthesize speech (edge-tts -> RVC) and speak
        voice_at = time.monotonic()
        await self._speak(answer, emotion, farewell=is_farewell)
        # Where the wait goes, turn by turn ("tarda mucho en responder", 2-nov)
        done = time.monotonic()
        logger.info("Turn timing: transcription %.1fs, answer %.1fs, voice %.1fs = %.1fs from the end of speech.",
                    brain_at - heard_at, voice_at - brain_at, done - voice_at, done - heard_at)

    async def _follow_up(self) -> None:
        """Conversation mode: after an answer the mic stays open a few seconds, no wake word needed."""
        await asyncio.sleep(FOLLOW_UP_DELAY_S)  # the echo of her last word dies out before the mic opens
        if (self._is_listening or self._is_speaking or self._hidden or self._pipeline_lock.locked()
                or not self.server.clients):
            return
        async with self._pipeline_lock:
            self._is_listening = True
            if self.wakeword is not None:
                self.wakeword.pause()
            try:
                await self.server.broadcast({"type": "state", "value": "listening"})
                await self._listen_and_answer(initial_timeout=self.follow_up_s)
            except Exception:
                logger.exception("Error in conversation follow-up")
                await self.server.broadcast({"type": "state", "value": "idle"})
                if self.wakeword is not None:
                    self.wakeword.resume()
            finally:
                self._is_listening = False

    async def handle_text_input(self, text: str, quiet: bool = False) -> None:
        """Processes sequential text chat from the frontend."""
        clean = text.strip()
        if not clean:
            return

        now = time.monotonic()
        if clean == self._last_text and (now - self._last_text_time) < 2.0:
            logger.info("Dropping duplicate text input within 2.0s: '%s'", clean)
            return

        if self._pipeline_lock.locked():
            # The mic waiting for speech must not eat what the user types instead (log 5-nov: 4 messages lost)
            if self.audio_in is None or not self.audio_in.stop_waiting():
                logger.info("Pipeline busy. Dropping overlapping text input: '%s'", clean)
                return
            self._text_takes_over = True

        self._last_text = clean
        self._last_text_time = now
        self._new_activity()
        self._hidden = False
        async with self._pipeline_lock:
            self._text_takes_over = False
            self.resources.touch()
            if self.wakeword is not None:
                self.wakeword.pause()
            logger.info("Processing text input: %s", clean)
            try:
                await self._process_text(clean, quiet)
            except Exception:
                # Without this the wake word stayed paused and the UI stuck on "thinking" (H-030)
                logger.exception("Error in text input pipeline")
                await self.server.broadcast({"type": "state", "value": "idle"})
                if self.wakeword is not None:
                    self.wakeword.resume()

    async def _process_text(self, text: str, quiet: bool = False) -> None:
        """Body of handle_text_input; runs under the pipeline lock."""

        # Pre-warm RVC in background if needed
        if self.rvc is not None and self.rvc.enabled and not self.rvc.is_loaded:
            self._spawn_bg(self.rvc.warmup())

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
        await self._speak(answer, emotion, farewell=is_farewell, quiet=quiet)

    def handle_speak_done(self) -> bool:
        """Returns True if there is a pending farewell animation to trigger."""
        self._is_speaking = False
        self._voice_chain = None
        if self._speak_watchdog_task and not self._speak_watchdog_task.done():
            self._speak_watchdog_task.cancel()
        farewell = self._pending_farewell
        self._pending_farewell = False
        if self.wakeword is not None:
            self.wakeword.resume()
        if not farewell and self.follow_up_s > 0:
            self._spawn_bg(self._follow_up())
        return farewell

    async def check_startup_greeting(self) -> None:
        """
        Greets the user according to the time of day (Fase 8).
        Runs when Miku Assistant boots up and frontend connects.
        """
        # Once per day, as persona.md says: restarting the backend must not greet again (H-032)
        marker = CACHE / "last_greeting.txt"
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
            # Her first words of the day in her own voice: a cold start imports torch & co. for up to ~50 s,
            # and the greeting used to come out in the base voice (log, 26-oct)
            if self.rvc is not None and self.rvc.enabled:
                for _ in range(int(GREETING_VOICE_WAIT_S / 0.5)):
                    if self.rvc.is_loaded:
                        break
                    await asyncio.sleep(0.5)

            if self.voice_only():
                logger.info("Startup greeting skipped: a full-screen app (a game, a video) is in front.")
                return
            now_hour = datetime.now().hour
            fixed = True
            if 5 <= now_hour < 12:
                greeting = "¡Buenos días! ¿Qué vamos a hacer hoy?"
                if today_items := describe_today():
                    greeting, fixed = f"¡Buenos días! Hoy tienes: {today_items}.", False
            elif 12 <= now_hour < 20:
                greeting = "¡Buenas tardes! ¿En qué puedo ayudarte?"
            else:
                greeting = "¡Buenas noches! ¿Qué necesitas hoy?"

            async with self._pipeline_lock:
                # Called before the greeting was ready: the greeting would cut her answer off (log 1-nov)
                if self._heard_user:
                    logger.info("Startup greeting skipped: the user already talked to her.")
                    return
                logger.info("Playing startup greeting: %s", greeting)
                await self._show()
                await self._speak(greeting, "happy", cache=fixed, gesture="greet")  # a fixed phrase is cached
        except Exception:
            logger.exception("Startup greeting failed")
