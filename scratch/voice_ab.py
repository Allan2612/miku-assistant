"""
Voice A/B (phase F, docs/plan-siguiente.md): the same phrases through several voice settings, as one page to
listen to and pick from. Uses the GPU for about a minute.

The voice in use was chosen by ear on 27-oct over six rounds (5 RVC models x 4 base voices, then pitch, index,
speed): MikuDiva, the only model kept. "tune" varies it in small steps; "japanese" has a Japanese voice read the
Spanish text (Whisper understood 46 % of it, against 100 % for Dalia).

Run:
  core\\.venv\\Scripts\\python.exe scratch\\voice_ab.py tune
  core\\.venv\\Scripts\\python.exe scratch\\voice_ab.py japanese   (uses scratch/kana.py)
Then open cache\\voice_ab\\<name>\\index.html: the audio is inside the page, so it plays anywhere.
"""

import argparse
import asyncio
import base64
import html
import io
import sys
from pathlib import Path

import av
import edge_tts

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from core.rvc_worker import RVCInferenceEngine  # noqa: E402

PHRASES = [
    "¡Hola! ¿Qué vamos a hacer hoy?",
    "¡Listo! Ya te puse la canción en YouTube, ¡a disfrutar!",
    "Mmm... no encontré esa nota. ¿Me la repites, porfa?",
    "¡Oye, recuerda: tomar agua! No te olvides, ¿eh?",
]
MODEL, INDEX = "models/rvc/miku_diva.pth", "models/rvc/miku_diva.index"

# (label, base voice, katakana?, rate, base pitch, RVC on?, semitones, index). A is config.yaml today
TUNE = [
    ("A: la actual", "es-MX-DaliaNeural", False, "+15%", "+30Hz", True, 6, 0.5),
    ("B: índice 0,4 (más claro)", "es-MX-DaliaNeural", False, "+15%", "+30Hz", True, 6, 0.4),
    ("C: índice 0,6 (más timbre de Miku)", "es-MX-DaliaNeural", False, "+15%", "+30Hz", True, 6, 0.6),
    ("D: +5 semitonos (un poco más grave)", "es-MX-DaliaNeural", False, "+15%", "+30Hz", True, 5, 0.5),
    ("E: +7 semitonos (un poco más aguda)", "es-MX-DaliaNeural", False, "+15%", "+30Hz", True, 7, 0.5),
    ("F: un poco más lenta (+12 %)", "es-MX-DaliaNeural", False, "+12%", "+30Hz", True, 6, 0.5),
    ("G: un poco más rápida (+18 %)", "es-MX-DaliaNeural", False, "+18%", "+30Hz", True, 6, 0.5),
    ("H: Dalia un poco más aguda (+40 Hz)", "es-MX-DaliaNeural", False, "+15%", "+40Hz", True, 6, 0.5),
]
JAPANESE = [
    ("A: la actual", "es-MX-DaliaNeural", False, "+15%", "+30Hz", True, 6, 0.5),
    ("B: Nanami katakana + MikuDiva", "ja-JP-NanamiNeural", True, "+5%", "+0Hz", True, 0, 0.25),
    ("C: Nanami katakana + MikuDiva, +2, índice 0,5", "ja-JP-NanamiNeural", True, "+5%", "+0Hz", True, 2, 0.5),
    ("D: Nanami texto en español + MikuDiva, +2", "ja-JP-NanamiNeural", False, "+5%", "+0Hz", True, 2, 0.25),
    ("E: Nanami katakana, sin RVC (voz japonesa pura)", "ja-JP-NanamiNeural", True, "+5%", "+0Hz", False, 0, 0),
]
ROUNDS = {"tune": ("Afinar la voz actual (A)", TUNE),
          "japanese": ("Miku hablando español con acento japonés (A = la actual)", JAPANESE)}


async def _base_voice(text: str, voice: str, rate: str, pitch: str) -> bytes:
    audio = bytearray()
    async for chunk in edge_tts.Communicate(text, voice, rate=rate, pitch=pitch).stream():
        if chunk["type"] == "audio":
            audio.extend(chunk["data"])
    return bytes(audio)


def _mp3(wav: bytes) -> bytes:
    """WAV -> MP3 (44.1 kHz mono), about 10x smaller to embed in the page."""
    src, buf = av.open(io.BytesIO(wav)), io.BytesIO()
    dst = av.open(buf, "w", format="mp3")
    stream = dst.add_stream("mp3", rate=44100)
    resampler = av.AudioResampler(format="fltp", layout="mono", rate=44100)
    for frame in src.decode(audio=0):
        frame.pts = None
        for f in resampler.resample(frame):
            dst.mux(stream.encode(f))
    for f in resampler.resample(None):
        dst.mux(stream.encode(f))
    dst.mux(stream.encode(None))
    dst.close()
    return buf.getvalue()


def _page(out: Path, title: str, rows: list) -> None:
    """rows: (phrase, [(label, mp3 bytes)]). The audio goes inside the page (data: URIs): VS Code's preview, and
    some browsers, refused the separate files next to it ("no puedo darle reproducir")."""
    parts = [f"<!doctype html><meta charset='utf-8'><title>{html.escape(title)}</title>",
             "<style>body{font-family:sans-serif;max-width:900px;margin:2em auto}td{padding:4px 12px}</style>",
             f"<h1>{html.escape(title)}</h1>"]
    for phrase, samples in rows:
        parts.append(f"<h2>{html.escape(phrase)}</h2><table>")
        for label, data in samples:
            src = "data:audio/mpeg;base64," + base64.b64encode(data).decode("ascii")
            parts.append(f"<tr><td>{html.escape(label)}</td><td><audio controls src='{src}'></audio></td></tr>")
        parts.append("</table>")
    (out / "index.html").write_text("\n".join(parts), encoding="utf-8")


def run(out: Path, title: str, variants: list) -> None:
    from kana import to_katakana  # scratch/kana.py, next to this script
    engine = RVCInferenceEngine()
    assert engine.load_models(MODEL, INDEX)
    rows = []
    for p in PHRASES:
        samples = []
        for label, voice, kana, rate, pitch, rvc, key, index_rate in variants:
            base = asyncio.run(_base_voice(to_katakana(p) if kana else p, voice, rate, pitch))
            audio = _mp3(engine.convert(base, f0_up_key=key, index_rate=index_rate)) if rvc else base
            samples.append((f"{label}  [velocidad {rate}, tono base {pitch}" + (f", RVC +{key}, índice {index_rate}]" if rvc else "]"), audio))
        rows.append((p, samples))
    _page(out, title, rows)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("round", choices=list(ROUNDS))
    name = ap.parse_args().round
    out = ROOT / "cache" / "voice_ab" / name
    out.mkdir(parents=True, exist_ok=True)
    run(out, *ROUNDS[name])
    print(f"Listo: {out / 'index.html'}")
