"""
Voice A/B for phase F (docs/plan-siguiente.md): the same phrases through every Miku RVC model and several
edge-tts base voices, as one local page to listen to and pick from. Uses the GPU for a minute or two.

Round 1 compares model x base voice at the current settings. Round 2 takes the winner and varies the pitch
(f0_up_key) and how much the model's own timbre is pulled in (index_rate). Round 3 makes the chosen voice
higher and younger (base voice pitch and speed, RVC semitones).

Run:
  core\\.venv\\Scripts\\python.exe scratch\\voice_ab.py 1
  core\\.venv\\Scripts\\python.exe scratch\\voice_ab.py 2 --model miku_power --voice es-ES-XimenaNeural
  core\\.venv\\Scripts\\python.exe scratch\\voice_ab.py 3
  core\\.venv\\Scripts\\python.exe scratch\\voice_ab.py 4   (MikuDiva against the current voice)
  core\\.venv\\Scripts\\python.exe scratch\\voice_ab.py 5   (Spanish read by a Japanese voice, scratch/kana.py)
Then open cache\\voice_ab\\roundN\\index.html: the audio is inside the page, so it plays anywhere.
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
VOICES = ["es-MX-DaliaNeural", "es-ES-XimenaNeural", "es-CR-MariaNeural", "es-US-PalomaNeural"]
MODELS = {  # name -> index ("" = none: v1 came without one)
    "miku": "miku.index",
    "miku_mellow": "miku_mellow.index",
    "miku_power": "miku_power.index",
    "miku_v1_MikuAI_e210_s6300": "",
    "miku_v2_mikuindex": "miku_v2_mikuindex.index",
    "miku_diva": "miku_diva.index",  # MikuDiva.zip (27-oct): 200 epochs; miku.pth has 30
}
CURRENT = {"rate": "+5%", "pitch": "+10Hz", "f0_up_key": 0, "index_rate": 0.25}  # config.yaml today


async def _base_voice(text: str, voice: str, rate: str = CURRENT["rate"], pitch: str = CURRENT["pitch"]) -> bytes:
    audio = bytearray()
    async for chunk in edge_tts.Communicate(text, voice, rate=rate, pitch=pitch).stream():
        if chunk["type"] == "audio":
            audio.extend(chunk["data"])
    return bytes(audio)


def _load(engine: RVCInferenceEngine, model: str) -> None:
    engine.index = None  # a model without an index must not keep the previous model's one
    index = MODELS[model]
    assert engine.load_models(f"models/rvc/{model}.pth", f"models/rvc/{index}" if index else ""), model


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
    """rows: (phrase, [(label, file)]). The audio goes inside the page (data: URIs): VS Code's preview, and
    some browsers, refused the separate files next to it ("no puedo darle reproducir")."""
    parts = [f"<!doctype html><meta charset='utf-8'><title>{html.escape(title)}</title>",
             "<style>body{font-family:sans-serif;max-width:900px;margin:2em auto}td{padding:4px 12px}</style>",
             f"<h1>{html.escape(title)}</h1>"]
    for phrase, samples in rows:
        parts.append(f"<h2>{html.escape(phrase)}</h2><table>")
        for label, f in samples:
            data = (out / f).read_bytes()
            data = data if f.endswith(".mp3") else _mp3(data)
            src = "data:audio/mpeg;base64," + base64.b64encode(data).decode("ascii")
            parts.append(f"<tr><td>{html.escape(label)}</td><td><audio controls src='{src}'></audio></td></tr>")
        parts.append("</table>")
    (out / "index.html").write_text("\n".join(parts), encoding="utf-8")


def round1(out: Path) -> None:
    engine = RVCInferenceEngine()
    bases = {(p, v): asyncio.run(_base_voice(p, v)) for p in PHRASES for v in VOICES}
    files = {p: [] for p in PHRASES}
    for p_i, p in enumerate(PHRASES):  # the base voices too, as reference
        for v in VOICES:
            name = f"p{p_i}_base_{v}.mp3"
            (out / name).write_bytes(bases[(p, v)])
            files[p].append((f"(voz base sin RVC) {v}", name))
    for model in MODELS:
        _load(engine, model)
        for p_i, p in enumerate(PHRASES):
            for v in VOICES:
                wav = engine.convert(bases[(p, v)], f0_up_key=CURRENT["f0_up_key"], index_rate=CURRENT["index_rate"])
                name = f"p{p_i}_{model}_{v}.wav"
                (out / name).write_bytes(wav)
                files[p].append((f"{model} + {v}", name))
        print("done", model, flush=True)
    _page(out, "Ronda 1: modelo x voz base (hoy: miku_mellow + es-MX-DaliaNeural)", [(p, files[p]) for p in PHRASES])


def round2(out: Path, model: str, voice: str) -> None:
    engine = RVCInferenceEngine()
    _load(engine, model)
    rows = []
    for p_i, p in enumerate(PHRASES):
        base = asyncio.run(_base_voice(p, voice))
        samples = []
        for key in (0, 2, 4):
            for index_rate in (0.25, 0.5, 0.75):
                name = f"p{p_i}_key{key}_idx{index_rate}.wav"
                (out / name).write_bytes(engine.convert(base, f0_up_key=key, index_rate=index_rate))
                samples.append((f"tono +{key} semitonos, índice {index_rate}", name))
        rows.append((p, samples))
    _page(out, f"Ronda 2: {model} + {voice}, tono e índice", rows)


# Round 3, from the winner (miku + Dalia, +4 semitones, index 0.25): higher and faster, toward a small girl's
# voice. The base voice's pitch and RVC's semitones both raise the final pitch; speed makes it sound younger
ROUND3 = [  # (label, edge-tts rate, edge-tts pitch, RVC semitones)
    ("A: la actual", "+5%", "+10Hz", 4),
    ("B: +6 semitonos", "+5%", "+10Hz", 6),
    ("C: +8 semitonos", "+5%", "+10Hz", 8),
    ("D: Dalia más aguda (+30 Hz), +4 semitonos", "+10%", "+30Hz", 4),
    ("E: Dalia más aguda (+30 Hz), +6 semitonos", "+10%", "+30Hz", 6),
    ("F: muy aguda (+50 Hz), +5 semitonos, más rápida", "+15%", "+50Hz", 5),
    ("G: +7 semitonos, más rápida", "+15%", "+30Hz", 7),
    ("H: la más chillona (+50 Hz, +8 semitonos, +20 %)", "+20%", "+50Hz", 8),
]


# Round 4: MikuDiva (200 epochs) against the current voice (A). (label, model, rate, base pitch, semitones, index)
ROUND4 = [
    ("A: la actual (miku)", "miku", "+5%", "+10Hz", 4, 0.25),
    ("B: MikuDiva, mismos ajustes", "miku_diva", "+5%", "+10Hz", 4, 0.25),
    ("C: MikuDiva, índice 0,5", "miku_diva", "+5%", "+10Hz", 4, 0.5),
    ("D: MikuDiva, índice 0,75", "miku_diva", "+5%", "+10Hz", 4, 0.75),
    ("E: MikuDiva, +2 semitonos, índice 0,5", "miku_diva", "+5%", "+10Hz", 2, 0.5),
    ("F: MikuDiva, +6 semitonos, índice 0,5", "miku_diva", "+5%", "+10Hz", 6, 0.5),
    ("G: MikuDiva, Dalia más aguda y rápida", "miku_diva", "+10%", "+30Hz", 4, 0.5),
    ("H: MikuDiva, más chillona", "miku_diva", "+15%", "+30Hz", 6, 0.5),
]


def _variants(out: Path, title: str, variants: list) -> None:
    """Each phrase through each (label, model, rate, base pitch, semitones, index) variant, on Dalia."""
    engine = RVCInferenceEngine()
    rendered = {}
    for model in dict.fromkeys(v[1] for v in variants):  # one model load each, in order
        _load(engine, model)
        for v_i, (label, m, rate, pitch, key, index_rate) in enumerate(variants):
            if m != model:
                continue
            for p_i, p in enumerate(PHRASES):
                base = asyncio.run(_base_voice(p, "es-MX-DaliaNeural", rate, pitch))
                name = f"p{p_i}_v{v_i}.wav"
                (out / name).write_bytes(engine.convert(base, f0_up_key=key, index_rate=index_rate))
                rendered[(p_i, v_i)] = (f"{label}  [velocidad {rate}, tono base {pitch}, RVC +{key}, índice {index_rate}]", name)
    _page(out, title, [(p, [rendered[(p_i, v_i)] for v_i in range(len(variants))]) for p_i, p in enumerate(PHRASES)])


def round3(out: Path) -> None:
    _variants(out, "Ronda 3: miku + Dalia, más aguda e infantil (A = la actual)",
              [(label, "miku", rate, pitch, key, 0.25) for label, rate, pitch, key in ROUND3])


def round4(out: Path) -> None:
    _variants(out, "Ronda 4: MikuDiva (200 épocas) contra la voz actual (A)", ROUND4)


# Round 5: a Japanese voice (Nanami) reads the Spanish text, so Miku speaks Spanish with a Japanese accent.
# Whisper understood 46 % of it with katakana and 36 % raw (Dalia: 100 %); the subtitles help a listener.
# (label, base voice, katakana?, rate, base pitch, RVC model or None, semitones, index)
ROUND5 = [
    ("A: la actual (Dalia + MikuDiva)", "es-MX-DaliaNeural", False, "+5%", "+10Hz", "miku_diva", 4, 0.25),
    ("B: Nanami katakana + MikuDiva", "ja-JP-NanamiNeural", True, "+5%", "+0Hz", "miku_diva", 0, 0.25),
    ("C: Nanami katakana + MikuDiva, +2, índice 0,5", "ja-JP-NanamiNeural", True, "+5%", "+0Hz", "miku_diva", 2, 0.5),
    ("D: Nanami katakana + miku (la anterior), +2", "ja-JP-NanamiNeural", True, "+5%", "+0Hz", "miku", 2, 0.25),
    ("E: Nanami texto en español + MikuDiva, +2", "ja-JP-NanamiNeural", False, "+5%", "+0Hz", "miku_diva", 2, 0.25),
    ("F: Nanami katakana, sin RVC (voz japonesa pura)", "ja-JP-NanamiNeural", True, "+5%", "+0Hz", None, 0, 0),
]


def round5(out: Path) -> None:
    from kana import to_katakana  # scratch/kana.py, next to this script
    engine = RVCInferenceEngine()
    loaded = None
    rendered = {}
    for v_i, (label, voice, kana, rate, pitch, model, key, index_rate) in enumerate(ROUND5):
        if model and model != loaded:
            _load(engine, model)
            loaded = model
        for p_i, p in enumerate(PHRASES):
            base = asyncio.run(_base_voice(to_katakana(p) if kana else p, voice, rate, pitch))
            name = f"p{p_i}_v{v_i}." + ("wav" if model else "mp3")
            (out / name).write_bytes(engine.convert(base, f0_up_key=key, index_rate=index_rate) if model else base)
            rendered[(p_i, v_i)] = (label, name)
    _page(out, "Ronda 5: Miku hablando español con acento japonés (A = la actual)",
          [(p, [rendered[(p_i, v_i)] for v_i in range(len(ROUND5))]) for p_i, p in enumerate(PHRASES)])


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("round", type=int, choices=(1, 2, 3, 4, 5))
    ap.add_argument("--model", choices=list(MODELS))
    ap.add_argument("--voice", choices=VOICES)
    args = ap.parse_args()
    out = ROOT / "cache" / "voice_ab" / f"round{args.round}"
    out.mkdir(parents=True, exist_ok=True)
    if args.round == 1:
        round1(out)
    elif args.round == 3:
        round3(out)
    elif args.round == 4:
        round4(out)
    elif args.round == 5:
        round5(out)
    else:
        if not (args.model and args.voice):
            ap.error("round 2 needs --model and --voice (the round 1 winner)")
        round2(out, args.model, args.voice)
    print(f"Listo: {out / 'index.html'}")
