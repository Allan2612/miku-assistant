"""Almacenamiento: what Miku's disk use adds up to, and that cleaning only ever touches the voice cache and Miku's
own unused speech models (never other programs' models, never the logs).

Works on temporary folders. Run: core\\.venv\\Scripts\\python.exe -m tests.test_storage  (or with pytest)
"""

import tempfile
from pathlib import Path

import core.storage as st


def _file(path: Path, n: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"x" * n)


def test_scan_and_clean():
    root = Path(tempfile.mkdtemp())
    st.CACHE, st.DATA, st.PROGRAM, st.RUNTIME, st.HUB = root / "cache", root, root, root / "venv", root / "hub"
    _file(root / "venv" / "Lib" / "site-packages" / "torch" / "a.dll", 500)
    _file(root / "venv" / "python.exe", 100)
    _file(root / "cache" / "core.log", 30)
    _file(root / "cache" / "core.log.1", 20)
    _file(root / "cache" / "voice" / "hola.mp3", 40)
    _file(root / "cache" / "wake" / "c.wav", 10)
    _file(root / "hub" / "models--lengyue233--content-vec-best" / "m.bin", 300)
    _file(root / "hub" / "models--Systran--faster-whisper-small" / "m.bin", 200)  # config.yaml uses "small"
    _file(root / "hub" / "models--Systran--faster-whisper-base" / "m.bin", 70)
    _file(root / "hub" / "models--someone--other-app" / "m.bin", 999)  # not Miku's: never counted or touched

    d = st.scan()
    got = {i["key"]: i for i in d["items"]}
    assert got["runtime"]["bytes"] == 600 and got["runtime"]["torch"] == 500
    assert got["speech"]["bytes"] == 500 and got["unused"]["bytes"] == 70
    assert (got["logs"]["bytes"], got["voice"]["bytes"], got["wake"]["bytes"]) == (50, 40, 10)
    assert "clean" not in got["logs"], "the logs are never offered for cleaning"

    assert st.clean("logs") == {"ok": False, "error": "No se puede borrar eso."}
    assert st.clean("voice") == {"ok": True, "freed": 40} and not list((root / "cache" / "voice").iterdir())
    assert st.clean("unused_models") == {"ok": True, "freed": 70}
    assert (root / "hub" / "models--someone--other-app").is_dir() and (root / "cache" / "core.log").is_file()
    assert (root / "hub" / "models--Systran--faster-whisper-small").is_dir(), "the model in use stays"


if __name__ == "__main__":
    test_scan_and_clean()
    print("ok")
