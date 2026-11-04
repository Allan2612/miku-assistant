"""The install's speed test: which Whisper model keeps Miku quick on this PC.

Run: core\\.venv\\Scripts\\python.exe -m tests.test_bench  (or with pytest)
"""

from core.bench import pick_whisper


def test_pick_whisper():
    assert pick_whisper(2.8, 4.1) == "small", "this PC (3-nov): faster than the phrase lasts"
    assert pick_whisper(2.4, 1.5) == "small", "a short phrase: 2.5 s is still quick enough"
    assert pick_whisper(6.0, 4.1) == "base", "a slow laptop: the user would wait longer than they spoke"


if __name__ == "__main__":
    test_pick_whisper()
    print("ok")
