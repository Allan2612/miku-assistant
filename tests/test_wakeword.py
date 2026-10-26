"""Each wake word activation leaves a clip of the last 2 s, to find what triggers the false ones.

Fake model and audio: no microphone. Clips go to a temp folder.
Run: core\\.venv\\Scripts\\python.exe -m tests.test_wakeword  (or with pytest)
"""

import tempfile
import time
import types
import wave
from pathlib import Path

import numpy as np

import core.wakeword as ww

ww.CLIPS_DIR = Path(tempfile.mkdtemp())


class FakeModel:
    def __init__(self):
        self.score = 0.0

    def predict(self, audio):
        return {"hey_miku": self.score}

    def reset(self):
        pass


def test_activation_saves_the_last_two_seconds():
    woke = []
    cfg = types.SimpleNamespace(enabled=True, model="hey_miku.onnx", threshold=0.35, patience=1)
    listener = ww.WakeWordListener(cfg, on_wake=lambda: woke.append(1))
    listener._model, listener._running, listener._target_key = FakeModel(), True, "hey_miku"
    loud = np.full(1280, 500, dtype=np.int16)

    for _ in range(40):  # 3.2 s of sound, no wake word
        listener._process_chunk(loud)
    assert not list(ww.CLIPS_DIR.glob("*.wav"))

    listener._model.score = 0.9
    listener._process_chunk(loud)
    for _ in range(50):
        clips = list(ww.CLIPS_DIR.glob("*.wav"))
        if clips:
            break
        time.sleep(0.02)
    assert len(clips) == 1 and clips[0].name.endswith("_0.900.wav"), clips
    with wave.open(str(clips[0])) as w:
        assert w.getframerate() == 16000 and w.getnframes() == ww.CLIP_CHUNKS * 1280

    # After a pause (Miku spoke) the buffer starts over: her voice is not in the next clip
    listener.resume()
    assert not listener._recent


if __name__ == "__main__":
    test_activation_saves_the_last_two_seconds()
    print("ok")
