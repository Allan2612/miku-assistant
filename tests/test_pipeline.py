"""H-030, H-031, H-032: pipeline flows with fake brain/TTS/server.

Run: core\\.venv\\Scripts\\python.exe -m tests.test_pipeline  (or with pytest)
"""

import asyncio

import numpy as np

from core.pipeline import _SAYS_MIKU, FILLER_PHRASES, FOLLOW_UP_DELAY_S, MikuPipeline


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
    # Frontend auto-hide fired: Miku says a goodbye, and its speak_done hides her
    p, server = _pipeline(FakeBrain())
    await p.say_goodbye()
    assert server.sent.count("speak") == 1, server.sent
    assert p.handle_speak_done() is True, "the goodbye must end in a hide"

    # Barge-in on the goodbye: the user's answer must not hide Miku afterwards
    p, server = _pipeline(FakeBrain())
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


async def _wake(clip_text, phrase, mic_cls=FakeMic, clip=True):
    server = AckServer()
    brain = RecordingBrain()
    stt = SeqSTT(clip_text, phrase) if clip else FakeSTT(phrase)
    p = MikuPipeline(brain=brain, tts=FakeTTS(), stt=stt, audio_in=mic_cls(server),
                     resources=FakeResources(), server=server, rvc=None)
    server.pipeline = p
    p.set_wakeword(FakeWake())
    await p.handle_voice_activation(wake_clip=np.zeros(32000, dtype=np.int16) if clip else None)
    return server, brain, p


def test_false_wake_words_never_reach_gemini():
    # What Whisper heard in the 4 false activations of 26-oct
    for text in ("¡Suscríbete!", "Discrúan", "Mike, que buena corta", "", "mi cuerpo", "Mikel"):
        assert not _SAYS_MIKU.search(text), text
    for text in ("Hey Miku.", "Ey, Micu", "Oye Miko", "¡Hey, Mikú!", "En Miku necesito"):
        assert _SAYS_MIKU.search(text), text

    server, brain, p = asyncio.run(_wake("Mike, que buena corta", "abre spotify"))
    assert brain.heard == [] and "hide" in server.sent and not p.wakeword.paused, server.sent
    server, brain, _ = asyncio.run(_wake("", "", mic_cls=SilentMic))
    assert brain.heard == [] and "hide" in server.sent, "a false one with silence after hides too"

    _, brain, _ = asyncio.run(_wake("Hey Miku.", "abre spotify"))
    assert brain.heard == ["abre spotify"]
    _, brain, _ = asyncio.run(_wake("", "Miku, abre spotify"))  # the name landed in the phrase
    assert brain.heard == ["Miku, abre spotify"]
    server, brain, _ = asyncio.run(_wake("", "abre spotify", clip=False))  # hotkey or click: no check
    assert brain.heard == ["abre spotify"] and "hide" not in server.sent


def test_reminders_only_speak():
    asyncio.run(_reminders_only_speak())


def test_hide_without_a_word():
    asyncio.run(_hide_now())


def test_conversation_mode():
    asyncio.run(_conversation())


def test_goodbye_on_inactivity():
    asyncio.run(_goodbye())


if __name__ == "__main__":
    test_pipeline_flows()
    test_goodbye_on_inactivity()
    test_filler_when_switching_model()
    test_conversation_mode()
    test_activation_says_yes_then_listens()
    test_reminders_only_speak()
    test_hide_without_a_word()
    test_false_wake_words_never_reach_gemini()
    print("ok")
