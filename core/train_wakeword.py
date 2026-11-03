"""
Miku Assistant - Retrains "Hey Miku" with the user's own marks (panel › Palabra clave).

Training data: the user's clips ("era yo" = the phrase, "no era yo" = not it, near-silent ignored clips = not it),
four variations of each of their real calls, and synthetic speech from edge-tts (the phrase in other voices, plus
look-alikes like "mae", "mi amor", "Mike"), so the model learns the user's voice without forgetting the phrase.

The new model goes to cache/wake/hey_miku.onnx (core/wakeword.py prefers it) only if it beats the current one on the user's clips it never
trained on (hears at least as many real calls, fires on no more of the false ones); a previous retrained one stays as
hey_miku.onnx.bak. Both are scored the same way, on the clips' features; the live stream gives slightly different
numbers (it carries context from before each clip), but the comparison is fair.

    python -m core.train_wakeword [--check] [--dry]
--check: only whether there are enough marks and PyTorch; --dry: train and compare, never replace the model.
Progress: "@@{json}" lines, like installer/setup.ps1.
"""

from __future__ import annotations

import asyncio
import io
import json
import random
import shutil
import sys
import wave
from pathlib import Path
from typing import Any, Dict, List, Tuple

import numpy as np

from core.paths import PROGRAM
from core.wakeword import CLIPS_DIR, MIN_CLIP_PEAK, TRAINED, clip_peak

MIN_MARKS = 60
MIN_YOURS = 20
SAMPLES = 32000  # 2 s at 16 kHz, the clips' length
SHIPPED = PROGRAM / "models" / "wakeword" / "hey_miku.onnx"
VOICES = ["es-MX-JorgeNeural", "es-ES-AlvaroNeural", "es-AR-TomasNeural", "es-CO-GonzaloNeural", "es-US-AlonsoNeural",
          "es-CR-JuanNeural", "es-MX-DaliaNeural", "es-ES-ElviraNeural", "es-US-PalomaNeural", "es-CR-MariaNeural"]
POSITIVE = ["Hey Miku", "Hey Miku!", "Oye Miku", "Miku", "Miku!", "Ey, Miku"]
NEGATIVE = ["Mae", "Mae, qué pasó", "Mi amor", "Mira esto", "Mike", "Miko", "Mi casa", "Ay mi madre", "Hey Mike",
            "Oye mae", "Mi cuenta", "Mucho", "Muy bien", "Qué pasa", "Hola, cómo estás", "Abre YouTube",
            "Sube el volumen", "Gracias", "Ya voy", "Dale, mae", "Me quito", "Mi cumple", "Hey Siri", "Alexa"]


def say(step: str, state: str, pct: int, msg: str = "") -> None:
    print("@@" + json.dumps({"step": step, "state": state, "pct": pct, "msg": msg}, ensure_ascii=False), flush=True)


def _read(path: Path) -> np.ndarray:
    with wave.open(str(path)) as w:
        return np.frombuffer(w.readframes(w.getnframes()), np.int16)


def marks() -> Tuple[List[np.ndarray], List[np.ndarray], List[np.ndarray]]:
    """(the user's real calls, the clips they marked as not them, near-silent triggers)."""
    try:
        labels: Dict[str, str] = json.loads((CLIPS_DIR / "labels.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        labels = {}
    yes, no = [], []
    for key, label in labels.items():
        path = CLIPS_DIR / key
        if path.is_file() and label in ("yes", "no"):
            (yes if label == "yes" else no).append(_read(path))
    silent = [_read(p) for p in sorted((CLIPS_DIR / "silent").glob("*.wav"))[-60:]]
    return yes, no, silent


def check() -> Dict[str, Any]:
    yes, no, _ = marks()
    labeled = len(yes) + len(no)
    try:
        import torch  # noqa: F401  (only the training needs it; without an NVIDIA GPU the installer skips it)
        has_torch = True
    except ImportError:
        has_torch = False
    ready = len(yes) >= MIN_YOURS and labeled >= MIN_MARKS and has_torch
    return {"ready": ready, "yours": len(yes), "marks": labeled, "torch": has_torch}


def _fit(a: np.ndarray) -> np.ndarray:
    """Exactly 2 s, the end kept (the clips end where the wake word was heard)."""
    a = a[-SAMPLES:]
    return np.pad(a, (SAMPLES - len(a), 0)) if len(a) < SAMPLES else a


def _variations(a: np.ndarray, noise: List[np.ndarray]) -> List[np.ndarray]:
    a = _fit(a).astype(np.float32)
    out = [a, a * random.uniform(0.4, 0.6), np.clip(a * random.uniform(1.3, 1.6), -32767, 32767),
           np.roll(a, -int(random.uniform(0.02, 0.12) * 16000))]
    if noise:
        out.append(np.clip(a + random.choice(noise).astype(np.float32) * random.uniform(0.5, 1.5), -32767, 32767))
    return [x.astype(np.int16) for x in out]


async def _synth(phrases: List[str]) -> List[np.ndarray]:
    import av
    import edge_tts

    sem = asyncio.Semaphore(10)

    async def one(text: str, voice: str) -> np.ndarray:
        async with sem:
            try:
                rate, pitch = f"{random.choice([-10, 0, 12]):+d}%", f"{random.randint(-10, 15):+d}Hz"
                data = b"".join([c["data"] async for c in edge_tts.Communicate(text, voice, rate=rate, pitch=pitch).stream()
                                 if c["type"] == "audio"])
                container = av.open(io.BytesIO(data))
                resampler = av.AudioResampler(format="s16", layout="mono", rate=16000)
                frames = [r.to_ndarray() for f in container.decode(audio=0) for r in resampler.resample(f)]
                return np.concatenate(frames, axis=1).squeeze(0).astype(np.int16) if frames else np.zeros(0, np.int16)
            except Exception:
                return np.zeros(0, np.int16)  # one voice failing must not stop the training

    return [a for a in await asyncio.gather(*(one(t, v) for t in phrases for v in VOICES)) if len(a) > 4000]


def _room_noise(a: np.ndarray, noise: List[np.ndarray]) -> np.ndarray:
    """Synthetic speech placed at the end of 2 s of the user's own room noise (never digital silence)."""
    base = random.choice(noise).astype(np.float32) if noise else np.random.normal(0, 8, SAMPLES)
    a = a[-SAMPLES:].astype(np.float32)
    base[-len(a):] += a
    return np.clip(base, -32767, 32767).astype(np.int16)


def main() -> None:
    if "--check" in sys.argv:
        print(json.dumps(check()), flush=True)
        return
    state = check()
    if not state["ready"]:
        say("error", "error", 0, f"Faltan marcas o PyTorch: {state}")
        sys.exit(1)
    import onnxruntime as ort
    import torch
    import torch.nn as nn
    from openwakeword.utils import AudioFeatures

    random.seed(7)
    torch.manual_seed(7)
    say("marks", "run", 5, "Leyendo tus marcas")
    yes, no, silent = marks()
    no += silent
    random.shuffle(yes)
    random.shuffle(no)
    # Clips it never trains on, to compare both models fairly
    test_yes, train_yes = yes[: max(4, len(yes) // 4)], yes[max(4, len(yes) // 4):]
    test_no, train_no = no[: max(6, len(no) // 4)], no[max(6, len(no) // 4):]
    quiet = [_fit(a) for a in train_no if clip_peak(a) < MIN_CLIP_PEAK]  # the user's room, for the backgrounds

    say("synth", "run", 15, "Generando voces de ejemplo (necesita internet)")
    pos_syn = asyncio.run(_synth(POSITIVE))
    neg_syn = asyncio.run(_synth(NEGATIVE))
    say("synth", "done", 45, f"{len(pos_syn)} + {len(neg_syn)} frases sintéticas")

    say("features", "run", 50, "Calculando lo que oye el modelo")
    feats = AudioFeatures(device="cpu")

    def emb(clips: List[np.ndarray]) -> np.ndarray:
        out = [feats._get_embeddings(_fit(c)) for c in clips]
        return np.array([e for e in out if e.shape == (16, 96)], np.float32)

    X_pos = emb([v for a in train_yes for v in _variations(a, quiet)] + [_room_noise(a, quiet) for a in pos_syn])
    X_neg = emb(train_no + [_room_noise(a, quiet) for a in neg_syn])
    T_yes, T_no = emb(test_yes), emb(test_no)

    say("train", "run", 65, f"Entrenando con {len(X_pos)} ejemplos de la frase y {len(X_neg)} que no lo son")
    model = nn.Sequential(nn.Flatten(), nn.Linear(16 * 96, 128), nn.LayerNorm(128), nn.ReLU(), nn.Dropout(0.15),
                          nn.Linear(128, 128), nn.LayerNorm(128), nn.ReLU(), nn.Dropout(0.15), nn.Linear(128, 1), nn.Sigmoid())
    X = torch.from_numpy(np.concatenate([X_pos, X_neg]))
    y = torch.from_numpy(np.array([1.0] * len(X_pos) + [0.0] * len(X_neg), np.float32))[:, None]
    weight = torch.where(y > 0, len(X_neg) / max(1, len(X_pos)), 1.0)  # as many "yes" as "no", in effect
    opt = torch.optim.AdamW(model.parameters(), lr=1e-3, weight_decay=1e-4)
    model.train()
    for epoch in range(80):
        for idx in torch.randperm(len(X)).split(64):
            opt.zero_grad()
            loss = nn.functional.binary_cross_entropy(model(X[idx]), y[idx], weight=weight[idx])
            loss.backward()
            opt.step()

    say("eval", "run", 90, "Comparando con el modelo actual en clips tuyos que no vio")
    model.eval()
    from core.config import load_config

    threshold = load_config().wakeword.threshold
    with torch.no_grad():
        new = lambda E: model(torch.from_numpy(E)).numpy().ravel() if len(E) else np.zeros(0)
        new_yes, new_no = new(T_yes), new(T_no)
    current = TRAINED if TRAINED.is_file() else SHIPPED
    old_sess = ort.InferenceSession(str(current), providers=["CPUExecutionProvider"]) if current.is_file() else None
    old = lambda E: (old_sess.run(None, {old_sess.get_inputs()[0].name: E})[0].ravel() if old_sess is not None and len(E)
                     else np.zeros(len(E)))
    old_yes, old_no = old(T_yes), old(T_no)
    score = lambda ys, ns: (int((ys >= threshold).sum()), int((ns >= threshold).sum()))
    (n_hit, n_false), (o_hit, o_false) = score(new_yes, new_no), score(old_yes, old_no)
    better = n_hit >= o_hit and n_false <= o_false and (n_hit, -n_false) != (o_hit, -o_false)
    summary = (f"de {len(T_yes)} llamadas tuyas: nuevo {n_hit}, actual {o_hit}; "
               f"de {len(T_no)} falsas: nuevo se dispara con {n_false}, actual con {o_false}")
    if not better or "--dry" in sys.argv:
        say("done", "done", 100, ("Lo mantengo: el actual no es peor. " if not better else "Prueba: no se cambió. ") + summary)
        return

    tmp = TRAINED.with_suffix(".new.onnx")
    torch.onnx.export(model, torch.zeros((1, 16, 96)), str(tmp), opset_version=13, input_names=["input"],
                      output_names=["output"], dynamic_axes={"input": {0: "batch"}, "output": {0: "batch"}}, dynamo=False)
    if TRAINED.is_file():
        shutil.copy2(TRAINED, TRAINED.with_suffix(".onnx.bak"))
    tmp.replace(TRAINED)
    say("done", "done", 100, "Modelo nuevo instalado; se usa al encender a Miku. " + summary)


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    main()
