"""Retraining "Hey Miku": the marks are read the way the panel writes them, and silent clips are not marks.

Works on a temporary folder: the real cache/wake is never touched.
Run: core\\.venv\\Scripts\\python.exe -m tests.test_train_wakeword  (or with pytest)
"""

import json
import tempfile
import wave
from pathlib import Path

import numpy as np

import core.train_wakeword as tw


def _clip(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(16000)
        w.writeframes(np.zeros(16000, np.int16).tobytes())


def test_marks_and_check():
    tw.CLIPS_DIR = Path(tempfile.mkdtemp())
    names = [f"20261103-1200{i:02d}_0.900.wav" for i in range(4)]
    for n in names:
        _clip(tw.CLIPS_DIR / n)
    _clip(tw.CLIPS_DIR / "near" / "20261103-130000_0.200.wav")
    _clip(tw.CLIPS_DIR / "silent" / "20261103-140000_0.990.wav")
    labels = {names[0]: "yes", names[1]: "yes", names[2]: "no", "near/20261103-130000_0.200.wav": "yes",
              "20261101-000000_0.500.wav": "yes"}  # the last one's clip was rotated away: not counted
    (tw.CLIPS_DIR / "labels.json").write_text(json.dumps(labels), encoding="utf-8")

    yes, no, silent = tw.marks()
    assert (len(yes), len(no), len(silent)) == (3, 1, 1)
    state = tw.check()
    assert (state["yours"], state["marks"], state["ready"]) == (3, 4, False), state

    # A silent clip the user marked is one mark, not a mark plus a "silent" clip; marked "yes", it is never a "no"
    labels["silent/20261103-140000_0.990.wav"] = "yes"
    (tw.CLIPS_DIR / "labels.json").write_text(json.dumps(labels), encoding="utf-8")
    yes, no, silent = tw.marks()
    assert (len(yes), len(no), len(silent)) == (4, 1, 0)

    # Clips under 2 s apart share audio: never one in training and the other in the comparison
    audio = lambda v: np.full(10, v, np.int16)
    clips = [("20261103-120000_0.9.wav", audio(1)), ("20261103-120001_0.9.wav", audio(1)), ("20261103-120002_0.9.wav", audio(1)),
             ("20261103-130000_0.9.wav", audio(2)), ("20261103-140000_0.9.wav", audio(3)), ("20261103-150000_0.9.wav", audio(4))]
    for seed in range(20):
        tw.random.seed(seed)
        test, train = tw._held_out(clips, 1)
        assert len(test) + len(train) == 6 and test, (len(test), len(train))
        assert not ({int(a[0]) for a in test} & {int(a[0]) for a in train}), seed

    # The clips the current model never saw; and the rule that picks a model (real numbers of 4-nov first)
    assert [c[0][:15] for c in tw._newer(clips, "20261103-140000")] == ["20261103-140000", "20261103-150000"]
    assert tw._newer(clips, "") == []
    assert tw.wins(5, 3, 7, 12, 8, 21), "2 calls lost, 9 false triggers gone"
    assert not tw.wins(4, 12, 7, 12, 8, 21) and not tw.wins(7, 12, 7, 12, 8, 21), "worse, or the same: the old one stays"

    assert tw._fit(np.ones(40000, np.int16)).shape == (tw.SAMPLES,)
    short = tw._fit(np.ones(100, np.int16))
    assert short.shape == (tw.SAMPLES,) and short[-1] == 1 and short[0] == 0, "padded at the start, the end kept"


if __name__ == "__main__":
    test_marks_and_check()
    print("ok")
