"""H-030, H-031, H-032: pipeline flows with fake brain/TTS/server.

Run: core\\.venv\\Scripts\\python.exe -m tests.test_pipeline  (or with pytest)
"""

import asyncio

from core.pipeline import FILLER_PHRASES, MikuPipeline


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


def test_goodbye_on_inactivity():
    asyncio.run(_goodbye())


if __name__ == "__main__":
    test_pipeline_flows()
    test_goodbye_on_inactivity()
    test_filler_when_switching_model()
    test_activation_says_yes_then_listens()
    print("ok")
