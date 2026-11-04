"""
Miku Assistant - Measures this PC at the end of the install (installer/setup.ps1) and adapts Miku to it.

Whisper and Miku's voice (RVC) run on the CPU when there is no NVIDIA card. This times both on one spoken phrase
and picks the Whisper model that keeps her quick: "small" (more accurate) if it transcribes faster than the phrase
lasts, else "base" (about twice as fast). The summary goes to the wizard (an "@@" line) and to cache/bench.json.

    python -m core.bench [--dry]     --dry: measure and report, change nothing
"""

from __future__ import annotations

import asyncio
import io
import json
import os
import sys
import time

import numpy as np

from core.paths import CACHE

SAMPLE = "Hola Miku, ¿me dices qué tiempo va a hacer mañana por la tarde?"
TYPICAL_ANSWER_S = 4.0  # an answer of hers lasts about this long


def say(state: str, pct: int, msg: str) -> None:
    print("@@" + json.dumps({"step": "bench", "state": state, "pct": pct, "msg": msg}, ensure_ascii=False), flush=True)


def pick_whisper(seconds: float, audio_s: float) -> str:
    """"small" while it keeps up with speech; "base" when the user would wait longer than they spoke."""
    return "small" if seconds <= max(audio_s, 2.5) else "base"


def _sample(voice: str, rate: str, pitch: str) -> tuple[bytes, np.ndarray]:
    """The phrase in her base voice: the mp3 (for RVC) and 16 kHz float audio (for Whisper)."""
    import av
    import edge_tts

    async def get() -> bytes:
        com = edge_tts.Communicate(SAMPLE, voice, rate=rate, pitch=pitch)
        return b"".join([c["data"] async for c in com.stream() if c["type"] == "audio"])

    mp3 = asyncio.run(get())
    resampler = av.AudioResampler(format="flt", layout="mono", rate=16000)
    frames = [r.to_ndarray() for f in av.open(io.BytesIO(mp3)).decode(audio=0) for r in resampler.resample(f)]
    return mp3, np.concatenate(frames, axis=1).squeeze(0).astype(np.float32)


def _whisper_seconds(model: str, audio: np.ndarray, threads: int) -> float:
    from faster_whisper import WhisperModel

    w = WhisperModel(model, device="cpu", compute_type="int8", cpu_threads=threads)
    list(w.transcribe(np.zeros(16000, np.float32), language="es")[0])  # the first run loads things: not counted
    t = time.perf_counter()
    list(w.transcribe(audio, language="es", beam_size=1)[0])
    return time.perf_counter() - t


def _voice_seconds(mp3: bytes, model: str, index: str, key: int, rate: float) -> tuple[float, str]:
    """Seconds to turn the phrase into Miku's voice, and where it ran ("cuda" or "cpu")."""
    from core import rvc_worker

    engine = rvc_worker.RVCInferenceEngine()
    if not engine.load_models(model, index):
        raise RuntimeError("no se pudo cargar la voz")
    t = time.perf_counter()
    if not engine.convert(mp3, f0_up_key=key, index_rate=rate):
        raise RuntimeError("la voz no convirtió la frase")
    return time.perf_counter() - t, engine.device


def main() -> None:
    from core.config import load_config

    dry = "--dry" in sys.argv
    c = load_config()
    say("run", 96, "Probando la velocidad de tu PC con una frase")
    mp3, audio = _sample(c.tts.voice, c.tts.rate, c.tts.pitch)
    audio_s = len(audio) / 16000
    threads = c.stt.cpu_threads or max(2, (os.cpu_count() or 4) // 2)
    whisper_s = _whisper_seconds("small", audio, threads)
    model = pick_whisper(whisper_s, audio_s)
    if model == "base":
        whisper_s = _whisper_seconds("base", audio, threads)  # also downloads it, so the first answer does not wait
    say("run", 98, "Probando su voz")
    voice_s, device = _voice_seconds(mp3, c.rvc.model, c.rvc.index, c.rvc.f0_up_key, c.rvc.index_rate)
    summary = {
        "audio_s": round(audio_s, 1),
        "whisper": {"model": model, "seconds": round(whisper_s, 1)},
        "voice": {"device": device, "seconds": round(voice_s, 1),
                  "extra_s": round(voice_s / audio_s * TYPICAL_ANSWER_S, 1)},
        "cpu_count": os.cpu_count(),
    }
    if not dry:
        if model != c.stt.model:
            from core import settings

            res = settings.set_({"stt_model": model})
            if not res.get("ok"):
                raise RuntimeError(res.get("error"))
        (CACHE / "bench.json").write_text(json.dumps(summary), encoding="utf-8")
    say("done", 99, json.dumps(summary))


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    main()
