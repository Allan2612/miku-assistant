"""H-030, H-031, H-032: pipeline flows with fake brain/TTS/server.

Run: core\\.venv\\Scripts\\python.exe -m tests.test_pipeline  (or with pytest)
"""

import asyncio

from core.pipeline import MikuPipeline


class FakeServer:
    def __init__(self):
        self.sent = []
        self.clients = {1}

    async def broadcast(self, msg):
        self.sent.append(msg["type"])


class FakeBrain:
    def __init__(self, fail=False):
        self.fail = fail

    async def chat(self, text):
        if self.fail:
            raise RuntimeError("boom")
        return "happy", "¡Hola!", False


class FakeTTS:
    async def synthesize(self, text):
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


def test_pipeline_flows():
    asyncio.run(_run())


if __name__ == "__main__":
    test_pipeline_flows()
    print("ok")
