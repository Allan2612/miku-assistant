"""
Voice A/B for phase F (docs/plan-siguiente.md): the same phrases through every Miku RVC model and several
edge-tts base voices, as one local page to listen to and pick from. Uses the GPU for a minute or two.

Round 1 compares model x base voice at the current settings. Round 2 takes the winner and varies the pitch
(f0_up_key) and how much the model's own timbre is pulled in (index_rate).

Run:
  core\\.venv\\Scripts\\python.exe scratch\\voice_ab.py 1
  core\\.venv\\Scripts\\python.exe scratch\\voice_ab.py 2 --model miku_power --voice es-ES-XimenaNeural
Then open cache\\voice_ab\\round1\\index.html (or round2) in the browser.
"""

import argparse
import asyncio
import html
import sys
from pathlib import Path

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
}
CURRENT = {"rate": "+5%", "pitch": "+10Hz", "f0_up_key": 0, "index_rate": 0.25}  # config.yaml today


async def _base_voice(text: str, voice: str) -> bytes:
    audio = bytearray()
    async for chunk in edge_tts.Communicate(text, voice, rate=CURRENT["rate"], pitch=CURRENT["pitch"]).stream():
        if chunk["type"] == "audio":
            audio.extend(chunk["data"])
    return bytes(audio)


def _load(engine: RVCInferenceEngine, model: str) -> None:
    engine.index = None  # a model without an index must not keep the previous model's one
    index = MODELS[model]
    assert engine.load_models(f"models/rvc/{model}.pth", f"models/rvc/{index}" if index else ""), model


def _page(out: Path, title: str, rows: list) -> None:
    """rows: (phrase, [(label, file)])"""
    parts = [f"<!doctype html><meta charset='utf-8'><title>{html.escape(title)}</title>",
             "<style>body{font-family:sans-serif;max-width:900px;margin:2em auto}td{padding:4px 12px}</style>",
             f"<h1>{html.escape(title)}</h1>"]
    for phrase, samples in rows:
        parts.append(f"<h2>{html.escape(phrase)}</h2><table>")
        parts += [f"<tr><td>{html.escape(label)}</td><td><audio controls preload='none' src='{f}'></audio></td></tr>"
                  for label, f in samples]
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


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("round", type=int, choices=(1, 2))
    ap.add_argument("--model", choices=list(MODELS))
    ap.add_argument("--voice", choices=VOICES)
    args = ap.parse_args()
    out = ROOT / "cache" / "voice_ab" / f"round{args.round}"
    out.mkdir(parents=True, exist_ok=True)
    if args.round == 1:
        round1(out)
    else:
        if not (args.model and args.voice):
            ap.error("round 2 needs --model and --voice (the round 1 winner)")
        round2(out, args.model, args.voice)
    print(f"Listo: {out / 'index.html'}")
