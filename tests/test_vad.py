"""H-034: the streaming VAD must tell speech from silence, noise and music-like tones.

Uses the voice samples in app/public/samples/ (speech) and synthetic signals.
Run: core\\.venv\\Scripts\\python.exe -m tests.test_vad  (or with pytest)
"""

from pathlib import Path

import numpy as np

from core.vad import CHUNK, StreamingVAD

ROOT = Path(__file__).resolve().parent.parent


def _load_16k(path: Path) -> np.ndarray:
    import av

    container = av.open(str(path))
    resampler = av.AudioResampler(format="flt", layout="mono", rate=16000)
    parts = [f.to_ndarray().reshape(-1) for frame in container.decode(audio=0) for f in resampler.resample(frame)]
    container.close()
    return np.concatenate(parts)


def _speech_ratio(vad: StreamingVAD, audio: np.ndarray) -> float:
    vad.reset()
    n = len(audio) // CHUNK
    probs = [vad(audio[i * CHUNK:(i + 1) * CHUNK]) for i in range(n)]
    return float(np.mean(np.array(probs) > 0.5))


def test_vad_separates_speech_from_noise():
    vad = StreamingVAD()
    rng = np.random.default_rng(0)
    t = np.arange(16000 * 3) / 16000
    silence = np.zeros(16000 * 3, dtype=np.float32)
    noise = (rng.standard_normal(16000 * 3) * 0.02).astype(np.float32)
    chord = (0.2 * (np.sin(2 * np.pi * 220 * t) + np.sin(2 * np.pi * 277 * t) + np.sin(2 * np.pi * 330 * t))).astype(np.float32)

    speech = _speech_ratio(vad, _load_16k(ROOT / "app/public/samples/sample_miku_mellow.wav"))
    others = {name: _speech_ratio(vad, a) for name, a in (("silence", silence), ("noise", noise), ("chord", chord))}
    print(f"speech={speech:.2f}", {k: round(v, 2) for k, v in others.items()})
    assert speech > 0.4, speech
    assert all(v < 0.1 for v in others.values()), others


if __name__ == "__main__":
    test_vad_separates_speech_from_noise()
    print("ok")
