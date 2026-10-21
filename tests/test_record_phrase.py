"""H-034: with music after the phrase, recording must end at the end of speech, not at max_seconds.

The microphone is replaced by a fake stream that plays a voice sample followed by a chord.
Run: core\\.venv\\Scripts\\python.exe -m tests.test_record_phrase  (or with pytest)
"""

import asyncio
import threading
import time

import numpy as np

import core.audio_in as audio_in
from tests.test_vad import ROOT, _load_16k

# One continuous phrase of the sample (it holds three phrases separated by ~1 s of digital silence)
speech = _load_16k(ROOT / "app/public/samples/sample_miku_mellow.wav")[int(1.54 * 16000):int(4.1 * 16000)]
t = np.arange(16000 * 8) / 16000
music = (0.2 * (np.sin(2 * np.pi * 220 * t) + np.sin(2 * np.pi * 277 * t))).astype(np.float32)
SIGNAL = np.concatenate([np.zeros(8000, np.float32), speech, music])


class FakeStream:
    def __init__(self, callback, blocksize, **_):
        self.callback, self.block, self.running = callback, blocksize, False

    def start(self):
        self.running = True

        def feed():
            for i in range(0, len(SIGNAL) - self.block, self.block):
                if not self.running:
                    return
                self.callback(SIGNAL[i:i + self.block].reshape(-1, 1), self.block, None, None)
                time.sleep(0.002)  # faster than real time; durations are counted per chunk

        threading.Thread(target=feed, daemon=True).start()

    def stop(self):
        self.running = False

    def close(self):
        pass


def test_music_does_not_keep_recording():
    audio_in.sd.InputStream = FakeStream
    rec = asyncio.run(audio_in.AudioInput().record_phrase(silence_ms=700, max_seconds=60, initial_timeout=10))
    got, expected = len(rec) / 16000, len(speech) / 16000
    print(f"recorded {got:.1f}s for {expected:.1f}s of speech (+8s of music after it)")
    assert rec is not None and expected - 0.3 < got < expected + 1.5, got


if __name__ == "__main__":
    test_music_does_not_keep_recording()
    print("ok")
