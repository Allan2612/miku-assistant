"""H-030, H-031, H-032: pipeline flows with fake brain/TTS/server.

Run: core\\.venv\\Scripts\\python.exe -m tests.test_pipeline  (or with pytest)
"""

import asyncio

import numpy as np

import core.pipeline as pipeline_module
from core.llm import MikuBrain
from core.intent import says_miku
from core.pipeline import FILLER_PHRASES, FOLLOW_UP_DELAY_S, MikuPipeline

# Whatever is open on this PC while the tests run (a full-screen video) must not change them
FULLSCREEN = [False]
pipeline_module.fullscreen_app_in_front = lambda: FULLSCREEN[0]


class FakeServer:
    def __init__(self):
        self.sent = []
        self.clients = {1}

    async def broadcast(self, msg):
        self.sent.append(msg["type"])


class FakeBrain:
    def __init__(self, fail=False):
        self.fail = fail

    async def chat(self, text, audio=None):
        if self.fail:
            raise RuntimeError("boom")
        return "happy", "¡Hola!", False

    def note_announcement(self, message):
        self.announced = message


class FakeTTS:
    async def synthesize(self, text, cache=False):
        return "QUJD", "audio/mpeg"

    def words_for(self, text):
        return [[90, 340], [600, 850]]


class FakeWake:
    def __init__(self):
        self.paused = False

    def pause(self):
        self.paused = True

    def resume(self):
        self.paused = False


class FakeResources:
    def touch(self):
        pass


def _pipeline(brain):
    server = FakeServer()
    p = MikuPipeline(brain=brain, tts=FakeTTS(), stt=None, audio_in=None,
                     resources=FakeResources(), server=server, rvc=None)
    p.set_wakeword(FakeWake())
    return p, server


async def _run():
    p, server = _pipeline(FakeBrain())
    await p.handle_text_input("hola")
    assert "speak" in server.sent and p._is_speaking, server.sent
    assert p.wakeword.paused, "wake word paused while Miku speaks"
    p.handle_speak_done()
    assert not p.wakeword.paused

    # H-030: an error must not leave the wake word paused
    p, server = _pipeline(FakeBrain(fail=True))
    await p.handle_text_input("hola")
    assert not p.wakeword.paused and server.sent[-1] == "state", server.sent

    # H-031: a timer waits for the ongoing turn instead of speaking over it
    p, server = _pipeline(FakeBrain())
    async with p._pipeline_lock:
        task = asyncio.create_task(p.announce_timer("¡Tiempo!"))
        await asyncio.sleep(0.05)
        assert "speak" not in server.sent, "timer spoke during the conversation"
    await task
    assert "speak" in server.sent


class AckServer(FakeServer):
    """Plays the "¿Sí?" cue like the frontend: speak_done shortly after the speak message."""
    pipeline = None

    async def broadcast(self, msg):
        self.sent.append(msg["type"] if msg["type"] != "speak" else "speak:" + msg["text"])
        if msg["type"] == "speak":
            asyncio.get_running_loop().call_later(0.05, self.pipeline.ack_finished)


class FakeMic:
    def __init__(self, server):
        self.server, self.opened_after = server, None

    async def record_phrase(self, **_):
        self.opened_after = list(self.server.sent)
        return [0.0]


class FakeSTT:
    is_loaded = True

    def __init__(self, text):
        self.text = text

    async def transcribe(self, audio):
        return self.text


class RecordingBrain(FakeBrain):
    def __init__(self):
        super().__init__()
        self.heard = []

    async def chat(self, text, audio=None):
        self.heard.append(text)
        return await super().chat(text)


async def _activation(heard_text):
    server = AckServer()
    brain = RecordingBrain()
    p = MikuPipeline(brain=brain, tts=FakeTTS(), stt=FakeSTT(heard_text), audio_in=FakeMic(server),
                     resources=FakeResources(), server=server, rvc=None)
    server.pipeline = p
    p.set_wakeword(FakeWake())
    await p.handle_voice_activation()
    return server, brain, p.audio_in


def test_activation_says_yes_then_listens():
    server, brain, mic = asyncio.run(_activation("qué hora es"))
    ack = next(m for m in server.sent if m.startswith("speak:"))
    assert ack[6:] in ("¿Sí?", "¿Dime?", "¿Mm?", "¿Qué pasa?", "¡Aquí estoy!"), ack
    assert ack in mic.opened_after and "state" in mic.opened_after, "mic must open after the cue"
    assert brain.heard == ["qué hora es"], brain.heard

    # The cue itself picked up by the mic must not reach Gemini ("sí" could confirm a shutdown)
    _, brain, _ = asyncio.run(_activation("Sí."))
    assert brain.heard == [], brain.heard


def test_pipeline_flows():
    asyncio.run(_run())


async def _goodbye():
    import time
    # Frontend auto-hide fired after a conversation: Miku says a goodbye, and its speak_done hides her
    p, server = _pipeline(FakeBrain())
    p._last_turn_at = time.monotonic()
    await p.say_goodbye()
    assert server.sent.count("speak") == 1, server.sent
    assert p.handle_speak_done() is True, "the goodbye must end in a hide"

    # Nothing said with the user (she showed up at startup): no goodbye out of nowhere, she just hides
    p, server = _pipeline(FakeBrain())
    await p.say_goodbye()
    assert server.sent == ["hide"], server.sent

    # Barge-in on the goodbye: the user's answer must not hide Miku afterwards
    p, server = _pipeline(FakeBrain())
    p._last_turn_at = time.monotonic()
    await p.say_goodbye()
    await p.handle_text_input("hola")
    assert p.handle_speak_done() is False

    # Busy: no goodbye (the frontend hides on its own fallback)
    p, server = _pipeline(FakeBrain())
    async with p._pipeline_lock:
        await p.say_goodbye()
    assert "speak" not in server.sent, server.sent


async def _filler():
    # The brain switches model: Miku says "Un momento..." and waits for it to finish, swallowing its speak_done
    server = AckServer()
    p = MikuPipeline(brain=FakeBrain(), tts=FakeTTS(), stt=None, audio_in=None,
                     resources=FakeResources(), server=server, rvc=None)
    server.pipeline = p
    assert p.brain.on_model_switch == p._say_filler, "the pipeline hooks itself into the brain"
    await asyncio.wait_for(p.brain.on_model_switch(), 2)
    said = [m[6:] for m in server.sent if m.startswith("speak:")]
    assert len(said) == 1 and said[0] in FILLER_PHRASES, server.sent
    assert p._ack_done is None, "its speak_done was consumed: the answer's own speak_done is not swallowed"

    # No frontend connected: no cue, and no 3 s wait for a speak_done that never comes
    server.clients = set()
    start = asyncio.get_running_loop().time()
    await p._say_filler()
    assert asyncio.get_running_loop().time() - start < 0.5


def test_filler_when_switching_model():
    asyncio.run(_filler())


class SilentMic(FakeMic):
    async def record_phrase(self, **_):
        return None


async def _conversation():
    def make(heard, mic_cls=FakeMic, follow_up_s=2.0):
        server = FakeServer()
        brain = RecordingBrain()
        p = MikuPipeline(brain=brain, tts=FakeTTS(), stt=FakeSTT(heard), audio_in=mic_cls(server),
                         resources=FakeResources(), server=server, rvc=None, follow_up_s=follow_up_s)
        p.set_wakeword(FakeWake())
        return p, server, brain

    wait = FOLLOW_UP_DELAY_S + 0.2

    # After an answer the mic opens again without the wake word, and the follow-up gets answered
    p, server, brain = make("¿y mañana?")
    p.handle_speak_done()
    await asyncio.sleep(wait)
    assert server.sent[0] == "state" and brain.heard == ["¿y mañana?"], (server.sent, brain.heard)

    # Silence: back to idle, wake word listening again
    p, server, brain = make("", mic_cls=SilentMic)
    p.handle_speak_done()
    await asyncio.sleep(wait)
    assert brain.heard == [] and not p.wakeword.paused and not p._is_listening

    # The tail of her own answer picked up by the mic is not a question
    p, server, brain = make("hace sol en Madrid")
    p._last_answer = "¡Hoy hace sol en Madrid!"
    p.handle_speak_done()
    await asyncio.sleep(wait)
    assert brain.heard == [], brain.heard

    # Whisper's YouTube-outro hallucination in noise is not a request (it reopened a web page, log 24-oct)
    p, server, brain = make("¡Suscríbete!")
    p.handle_speak_done()
    await asyncio.sleep(wait)
    assert brain.heard == [], brain.heard

    # After a goodbye, or with the mode off: no follow-up
    p, server, brain = make("hola")
    p._pending_farewell = True
    p.handle_speak_done()
    p2, server2, brain2 = make("hola", follow_up_s=0)
    p2.handle_speak_done()
    await asyncio.sleep(wait)
    assert brain.heard == [] and brain2.heard == [] and server.sent == [] and server2.sent == []


async def _reminders_only_speak():
    def make():
        server = FakeServer()
        brain = RecordingBrain()
        p = MikuPipeline(brain=brain, tts=FakeTTS(), stt=FakeSTT("gracias"), audio_in=FakeMic(server),
                         resources=FakeResources(), server=server, rvc=None, follow_up_s=2.0)
        p.set_wakeword(FakeWake())
        return p, server, brain

    # A reminder shows her, speaks, and hides on its speak_done: the mic never opens (log 26-oct)
    p, server, brain = make()
    await p.announce_timer("¡Oye, recuerda: tomar agua!")
    assert server.sent[0] == "show" and "speak" in server.sent
    assert p.handle_speak_done() is True, "the reminder ends in a hide"
    await asyncio.sleep(FOLLOW_UP_DELAY_S + 0.2)
    assert brain.heard == [] and p.audio_in.opened_after is None, "no conversation mode after a reminder"

    # In the middle of a conversation she says it and the conversation goes on (mic opens as after any answer)
    p, server, brain = make()
    await p.handle_text_input("hola")
    p.handle_speak_done()
    await asyncio.sleep(FOLLOW_UP_DELAY_S + 0.2)  # the follow-up after "hola" heard "gracias"
    p.handle_speak_done()
    await asyncio.sleep(FOLLOW_UP_DELAY_S + 0.2)
    brain.heard.clear()
    await p.announce_timer("¡Oye, recuerda: tomar agua!")
    assert p.handle_speak_done() is False, "she stays on screen"
    await asyncio.sleep(FOLLOW_UP_DELAY_S + 0.2)
    assert brain.heard == ["gracias"], brain.heard

    # Hidden by hand (click): the conversation is over, the next reminder hides her again
    p.end_conversation()
    await p.announce_timer("¡Oye, recuerda: estirar!")
    assert p.handle_speak_done() is True

    # She is still talking (the lock is already free): the reminder waits for her speak_done
    p, server, brain = make()
    p._is_speaking = True
    task = asyncio.create_task(p.announce_timer("¡Oye, recuerda: estirar!"))
    await asyncio.sleep(0.3)
    assert "speak" not in server.sent, "the reminder talked over her answer"
    p._is_speaking = False
    await asyncio.wait_for(task, 3)
    assert "speak" in server.sent


async def _hide_now():
    # "Ocúltate": empty answer + farewell = hide at once, no voice, no mic
    class HideBrain(RecordingBrain):
        async def chat(self, text, audio=None):
            self.heard.append(text)
            return "happy", "", True

    server = FakeServer()
    p = MikuPipeline(brain=HideBrain(), tts=FakeTTS(), stt=FakeSTT("ocúltate"), audio_in=FakeMic(server),
                     resources=FakeResources(), server=server, rvc=None, follow_up_s=2.0)
    p.set_wakeword(FakeWake())
    async with p._pipeline_lock:
        await p._listen_and_answer(initial_timeout=1)
    assert "hide" in server.sent and "speak" not in server.sent, server.sent
    assert not p.wakeword.paused and not p._pending_farewell


class SeqSTT(FakeSTT):
    """First call: the wake word clip; then the user's phrase."""

    def __init__(self, clip_text, phrase):
        super().__init__(phrase)
        self.texts = [clip_text]

    async def transcribe(self, audio):
        return self.texts.pop(0) if self.texts else self.text


async def _wake(clip_text, phrase, mic_cls=FakeMic, clip=True, loud=True):
    server = AckServer()
    brain = RecordingBrain()
    stt = SeqSTT(clip_text, phrase) if clip else FakeSTT(phrase)
    p = MikuPipeline(brain=brain, tts=FakeTTS(), stt=stt, audio_in=mic_cls(server),
                     resources=FakeResources(), server=server, rvc=None)
    server.pipeline = p
    p.set_wakeword(FakeWake())
    audio = np.full(32000, 800 if loud else 30, dtype=np.int16)  # RMS 0.024 (a voice) or 0.001 (silence)
    await p.handle_voice_activation(wake_clip=audio if clip else None)
    return server, brain, p


def test_false_wake_words_never_reach_gemini():
    for text in ("¡Suscríbete!", "Discrúan", "Mike, que buena corta", "", "mi cuerpo", "Mikel"):
        assert not says_miku(text), text
    for text in ("Hey Miku.", "Ey, Micu", "Oye Miko", "¡Hey, Mikú!", "En Miku necesito"):
        assert says_miku(text), text

    # Clearly false (clips of 26-oct): a sentence of other talk, or near silence
    server, brain, p = asyncio.run(_wake("Cuatro más, el mejor de cinco.", "y entonces ganamos la partida"))
    assert brain.heard == [] and "hide" in server.sent and not p.wakeword.paused, server.sent
    server, brain, _ = asyncio.run(_wake("", "y entonces le dije que no", loud=False))
    assert brain.heard == [] and "hide" in server.sent, "nobody spoke to her"
    # A quiet "Hey Miku" then an order or a goodbye is a real call (log 27-oct: "Cierra me OBS Studio." dropped)
    for heard in ("Cierra me OBS Studio.", "Abreme Opera y cierro todas las pestañas.", "Adiós."):
        _, brain, _ = asyncio.run(_wake("", heard, loud=False))
        assert brain.heard == [heard], heard
    server, brain, _ = asyncio.run(_wake("", "", mic_cls=SilentMic, loud=False))
    assert brain.heard == [] and "hide" in server.sent, "a false one with silence after hides too"

    # Real calls Whisper misheard in the clip (13:17 "Maes.", 13:26 nothing): she must listen, not hide
    _, brain, _ = asyncio.run(_wake("Maes.", "ciérrame todas las pestañas"))
    assert brain.heard == ["ciérrame todas las pestañas"]
    _, brain, _ = asyncio.run(_wake("", "abre spotify"))
    assert brain.heard == ["abre spotify"]
    _, brain, _ = asyncio.run(_wake("Hey Miku.", "abre spotify"))
    assert brain.heard == ["abre spotify"]
    _, brain, _ = asyncio.run(_wake("Tenía que explotar la", "Miku, abre spotify"))  # the name is in the phrase
    assert brain.heard == ["Miku, abre spotify"]
    # Log 1-nov: "Hey Miku" heard as three words, then the order
    _, brain, _ = asyncio.run(_wake("¡Granza de la...", "qué hora es"))
    assert brain.heard == ["qué hora es"]
    # An order right after, whatever the clip said
    _, brain, _ = asyncio.run(_wake("Cuatro más, el mejor de cinco.", "abre spotify"))
    assert brain.heard == ["abre spotify"]
    # Right after her "¿Sí?" cue a "sí" is its echo; in a conversation it answers her question (log 1-nov)
    _, brain, _ = asyncio.run(_wake("", "¡Sí!", clip=False))
    assert brain.heard == []
    _, brain, p = asyncio.run(_wake("", "abre spotify", clip=False))
    p.stt = FakeSTT("¡Sí!")
    asyncio.run(p._listen_and_answer(initial_timeout=1.0))
    assert brain.heard == ["abre spotify", "¡Sí!"], brain.heard
    server, brain, _ = asyncio.run(_wake("", "abre spotify", clip=False))  # hotkey or click: no check
    assert brain.heard == ["abre spotify"] and "hide" not in server.sent


class FakeRVC:
    enabled, model_path, f0_up_key, index_rate = True, "models/rvc/miku.pth", 4, 0.25

    def __init__(self, works=True, loaded=True):
        self.works, self.is_loaded = works, loaded

    async def convert(self, audio_b64):
        import base64
        import io
        import soundfile as sf
        buf = io.BytesIO()
        sf.write(buf, np.full(4000, 0.3, dtype=np.float32), 40000, format="WAV")  # a real WAV: cues get trimmed
        return (base64.b64encode(buf.getvalue()).decode("ascii"), "audio/wav") if self.works else None


async def _one_voice():
    import tempfile
    from pathlib import Path
    import core.pipeline as pl
    pl.ROOT_DIR = Path(tempfile.mkdtemp())  # cue cache in a temp folder

    # RVC fails: the answer is a subtitle, never the base voice
    server = AckServer()
    p = MikuPipeline(brain=FakeBrain(), tts=FakeTTS(), stt=None, audio_in=None,
                     resources=FakeResources(), server=server, rvc=FakeRVC(works=False))
    server.pipeline = p
    p.set_wakeword(FakeWake())
    await p._speak("¡Hola!", "happy")
    assert not any(m.startswith("speak") for m in server.sent) and "subtitle" in server.sent, server.sent

    # A cue with no Miku-voice copy while RVC loads: skipped, not played in the base voice
    p.rvc = FakeRVC(loaded=False)
    assert await p._ack_audio("¿Sí?") is None
    # Loaded: converted now and cached under a name that includes the voice settings
    p.rvc = FakeRVC()
    assert await p._ack_audio("¿Sí?") is not None
    first = p._ack_file("¿Sí?")
    p.rvc.f0_up_key = 2
    second = p._ack_file("¿Sí?")
    assert second != first, "another voice setting must not reuse the cached cue"
    p.tts.rate = "+15%"  # the base voice's speed too (27-oct: "¿Sí?" kept the old speed)
    assert p._ack_file("¿Sí?") != second


class MsgServer(FakeServer):
    async def broadcast(self, msg):
        self.sent.append(msg)


async def _body_language():
    server = MsgServer()
    brain = FakeBrain()
    brain.last_outcome = "fail"
    p = MikuPipeline(brain=brain, tts=FakeTTS(), stt=None, audio_in=None,
                     resources=FakeResources(), server=server, rvc=None)
    p.set_wakeword(FakeWake())
    await p._speak("No pude, perdón.", "sad")
    speak = next(m for m in server.sent if m["type"] == "speak")
    assert speak["words"] == [[90, 340], [600, 850]] and speak["outcome"] == "fail" and not speak["farewell"], speak
    server.sent.clear()
    brain.note_announcement = lambda m: None
    p._last_turn_at = float("-inf")  # hidden for a while
    await p.announce_timer("Hora de la pastilla")
    speak = next(m for m in server.sent if m["type"] == "speak")
    assert speak["gesture"] == "attention" and speak["farewell"], "a reminder while hidden: attention, then goodbye"


async def _no_speak_done():
    orig_sleep = asyncio.sleep
    asyncio.sleep = lambda s, *a: orig_sleep(min(s, 0.01))  # the watchdog's 7 s, made short
    try:
        # A goodbye whose speak_done never came: the watchdog hides her (log 1-nov: she stayed 20 s)
        p, server = _pipeline(FakeBrain())
        p._pending_farewell = True
        await p._speak("¡Adiós!", "happy", farewell=True)
        await orig_sleep(0.1)
        assert server.sent[-1] == "hide" and not p._is_speaking, server.sent

        # Hidden from the tray mid-answer: no speak_done, and the mic must not open with her hidden
        server = FakeServer()
        brain = RecordingBrain()
        p = MikuPipeline(brain=brain, tts=FakeTTS(), stt=FakeSTT("hola"), audio_in=FakeMic(server),
                         resources=FakeResources(), server=server, rvc=None, follow_up_s=2.0)
        p.set_wakeword(FakeWake())
        await p._speak("Te cuento una historia larga...", "happy")
        p.end_conversation()
        await orig_sleep(0.1)
        assert not p._is_speaking and not p.wakeword.paused and p.audio_in.opened_after is None

        # Hidden from the tray while she thinks: the answer is not spoken and no mic opens (audit 3-nov)
        class HiddenMidTurn(RecordingBrain):
            async def chat(self, text, audio=None):
                p.end_conversation()
                return await super().chat(text)

        server = FakeServer()
        p = MikuPipeline(brain=HiddenMidTurn(), tts=FakeTTS(), stt=FakeSTT("hola"), audio_in=FakeMic(server),
                         resources=FakeResources(), server=server, rvc=None, follow_up_s=2.0)
        p.set_wakeword(FakeWake())
        await p.handle_text_input("hola")
        assert "speak" not in server.sent and not p._is_speaking and not p.wakeword.paused, server.sent
        # Shown again (a reminder): she talks normally
        await p.announce_timer("¡Oye, recuerda: estirar!")
        assert "speak" in server.sent, server.sent
    finally:
        asyncio.sleep = orig_sleep


def test_without_speak_done():
    asyncio.run(_no_speak_done())


def test_speak_carries_body_language():
    asyncio.run(_body_language())


def test_only_one_voice():
    asyncio.run(_one_voice())


def test_reminders_only_speak():
    asyncio.run(_reminders_only_speak())


def test_hide_without_a_word():
    asyncio.run(_hide_now())


def test_conversation_mode():
    asyncio.run(_conversation())


def test_goodbye_on_inactivity():
    asyncio.run(_goodbye())


async def _fullscreen():
    FULLSCREEN[0] = True
    try:
        # A game or a video at full screen: called by voice, she answers without showing herself
        server = AckServer()
        p = MikuPipeline(brain=RecordingBrain(), tts=FakeTTS(), stt=FakeSTT("hola"), audio_in=FakeMic(server),
                         resources=FakeResources(), server=server, rvc=None, follow_up_s=0)
        server.pipeline = p
        p.set_wakeword(FakeWake())
        await p.handle_voice_activation()
        assert "show" not in server.sent and any(m.startswith("speak:") for m in server.sent), server.sent
        assert p.brain.heard == ["hola"]
        # A reminder too: said, not shown
        server.sent.clear()
        await p.announce_timer("¡Oye, recuerda: estirar!")
        assert "show" not in server.sent and "speak:¡Oye, recuerda: estirar!" in server.sent, server.sent
    finally:
        FULLSCREEN[0] = False


def test_quiet_text_answers_without_voice():
    # The panel's chat, "Solo texto": the answer as a subtitle, no voice, nothing for the GPU
    async def run():
        p, server = _pipeline(FakeBrain())
        await p.handle_text_input("hola", quiet=True)
        assert "subtitle" in server.sent and "speak" not in server.sent and not p._is_speaking, server.sent
        assert not p.wakeword.paused

    asyncio.run(run())


def test_fullscreen_means_voice_only():
    asyncio.run(_fullscreen())


if __name__ == "__main__":
    test_pipeline_flows()
    test_goodbye_on_inactivity()
    test_filler_when_switching_model()
    test_conversation_mode()
    test_activation_says_yes_then_listens()
    test_reminders_only_speak()
    test_hide_without_a_word()
    test_false_wake_words_never_reach_gemini()
    test_only_one_voice()
    test_speak_carries_body_language()
    test_without_speak_done()
    test_fullscreen_means_voice_only()
    test_quiet_text_answers_without_voice()
    print("ok")
