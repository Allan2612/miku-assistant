"""RVC worker lifecycle: a standby worker (imports done, no models) loads on demand, and an answer waits a
little for a load in progress instead of switching to the base voice ("otra voz", 26-oct).

Fake worker: no process, no GPU.
Run: core\\.venv\\Scripts\\python.exe -m tests.test_rvc_manager  (or with pytest)
"""

import asyncio
import types

import core.rvc as rvc


class FakeProc:
    returncode = None
    pid = 1
    stdin = None

    def terminate(self):
        self.returncode = 0

    async def wait(self):
        return 0


def manager(load_s=0.0):
    cfg = types.SimpleNamespace(enabled=True, model="m.pth", index="m.index", f0_up_key=0, index_rate=0.25)
    m = rvc.RVCManager(cfg)
    m.sent = []

    async def ensure():
        if not m.is_running:
            m._proc, m._loaded = FakeProc(), False
        return True

    async def send(payload, timeout=30.0):
        m.sent.append(payload["cmd"])
        if payload["cmd"] == "load":
            await asyncio.sleep(load_s)
            return {"status": "ok"}
        return {"status": "ok", "audio_b64": "TUlLVQ==", "mime": "audio/wav"}

    m._ensure_worker, m._send_command = ensure, send
    return m


async def _flow():
    # Standby: the process is up but holds no models (no VRAM); the first answer loads them, then converts
    m = manager()
    await m.standby()
    assert m.is_running and not m.is_loaded and m.sent == []
    assert await m.convert("QUJD") == ("TUlLVQ==", "audio/wav")
    assert m.sent == ["load", "convert"] and m.is_loaded

    # Unload: back to no models
    m.terminate_worker()
    assert not m.is_loaded and not m.is_running

    # A short load in progress: the answer waits for it and keeps Miku's voice
    m = manager(load_s=0.3)
    warm = asyncio.create_task(m.warmup())
    await asyncio.sleep(0.05)
    assert await m.convert("QUJD") is not None, "fell back to the base voice for a 0.3 s load"
    await warm

    # A long cold start too: the answer waits for her voice instead of using another one (26-oct)
    m = manager(load_s=1.0)
    warm = asyncio.create_task(m.warmup())
    await asyncio.sleep(0.05)
    assert await m.convert("QUJD") == ("TUlLVQ==", "audio/wav")
    await warm
    assert m.sent == ["load", "convert"], "loaded once, by the warmup"


def test_standby_and_waiting_for_a_load():
    asyncio.run(_flow())


if __name__ == "__main__":
    test_standby_and_waiting_for_a_load()
    print("ok")
