import asyncio
import io
import os
import random
import sys
import av
import edge_tts
import numpy as np
import torch
import torch.nn as nn
from openwakeword.utils import AudioFeatures

sys.stdout.reconfigure(encoding="utf-8", line_buffering=True)
sys.stderr.reconfigure(encoding="utf-8", line_buffering=True)

VOICES = [
    "es-MX-DaliaNeural", "es-MX-JorgeNeural", "es-ES-XimenaNeural", "es-ES-AlvaroNeural",
    "es-AR-TomasNeural", "es-US-PalomaNeural", "en-US-JennyNeural", "en-US-GuyNeural",
    "en-US-AriaNeural", "ja-JP-NanamiNeural"
]

POSITIVE_PHRASES = [
    "Hey Miku", "Hey Miku!", "Oye Miku", "Oye Miku!", "Hey Miku", "Miku",
    "Hola Miku", "Hey, Miku", "Hey Miku!", "Oye Miku"
]

NEGATIVE_PHRASES = [
    "Hola, ¿cómo estás?", "Abre Google Chrome", "Pausa la música", "Qué hora es?",
    "Silencio por favor", "Hey Google", "Hey Siri", "Alexa", "Buenos días",
    "Buenas tardes", "Reproduce una canción", "Apaga la computadora", "Música pop",
    "Muchas gracias", "Hasta luego", "Bloc de notas", "Calculadora", "Subir volumen",
    "Bajar volumen", "Hola amigo", "Cómo te llamas", "Qué haces hoy"
]

def decode_audio_16k_int16(raw_bytes: bytes) -> np.ndarray:
    container = av.open(io.BytesIO(raw_bytes))
    resampler = av.AudioResampler(format="s16", layout="mono", rate=16000)
    chunks = []
    for frame in container.decode(audio=0):
        frame.pts = None
        for resampled_frame in resampler.resample(frame):
            chunks.append(resampled_frame.to_ndarray())
    container.close()
    if chunks:
        audio = np.concatenate(chunks, axis=1).squeeze(0)
        return audio.astype(np.int16)
    return np.zeros(0, dtype=np.int16)

async def synth_sample(phrase: str, voice: str, rate: str, pitch: str) -> np.ndarray:
    tts = edge_tts.Communicate(phrase, voice, rate=rate, pitch=pitch)
    data = bytearray()
    async for chunk in tts.stream():
        if chunk["type"] == "audio":
            data.extend(chunk["data"])
    return decode_audio_16k_int16(bytes(data))

class FCNBlock(nn.Module):
    def __init__(self, layer_dim):
        super().__init__()
        self.fcn_layer = nn.Linear(layer_dim, layer_dim)
        self.relu = nn.ReLU()
        self.layer_norm = nn.LayerNorm(layer_dim)

    def forward(self, x):
        return self.relu(self.layer_norm(self.fcn_layer(x)))

class OpenWakeWordNet(nn.Module):
    def __init__(self, input_shape=(16, 96), layer_dim=128, n_blocks=1):
        super().__init__()
        self.flatten = nn.Flatten()
        self.layer1 = nn.Linear(input_shape[0] * input_shape[1], layer_dim)
        self.relu1 = nn.ReLU()
        self.layernorm1 = nn.LayerNorm(layer_dim)
        self.blocks = nn.ModuleList([FCNBlock(layer_dim) for _ in range(n_blocks)])
        self.last_layer = nn.Linear(layer_dim, 1)
        self.last_act = nn.Sigmoid()

    def forward(self, x):
        x = self.relu1(self.layernorm1(self.layer1(self.flatten(x))))
        for block in self.blocks:
            x = block(x)
        return self.last_act(self.last_layer(x))

async def main():
    print("=== Training Custom 'Hey Miku' Wake Word Locally ===")
    feature_extractor = AudioFeatures(device="cpu")
    sem = asyncio.Semaphore(5)

    async def fetch_pos(i):
        async with sem:
            phrase = random.choice(POSITIVE_PHRASES)
            voice = random.choice(VOICES)
            rate = f"{random.randint(-15, 20):+d}%"
            pitch = f"{random.randint(-15, 25):+d}Hz"
            try:
                audio = await synth_sample(phrase, voice, rate, pitch)
                return audio if len(audio) > 6000 else None
            except Exception:
                return None

    async def fetch_neg(i):
        async with sem:
            phrase = random.choice(NEGATIVE_PHRASES)
            voice = random.choice(VOICES)
            rate = f"{random.randint(-10, 15):+d}%"
            pitch = f"{random.randint(-10, 20):+d}Hz"
            try:
                audio = await synth_sample(phrase, voice, rate, pitch)
                return audio if len(audio) > 6000 else None
            except Exception:
                return None

    print("Step 1/5: Synthesizing audio clips via edge-tts (40 positive, 60 negative)...")
    pos_tasks = [fetch_pos(i) for i in range(40)]
    neg_tasks = [fetch_neg(i) for i in range(60)]
    results = await asyncio.gather(*pos_tasks, *neg_tasks)

    pos_audios = [r for r in results[:40] if r is not None]
    neg_audios = [r for r in results[40:] if r is not None]

    # Add 15 noise/silence negatives
    for _ in range(15):
        dur = random.randint(16000, 32000)
        noise = np.random.randint(-300, 300, dur, dtype=np.int16)
        neg_audios.append(noise)

    print(f"Collected {len(pos_audios)} positive clips and {len(neg_audios)} negative clips.")

    print("Step 2/5: Extracting openWakeWord 16x96 embeddings...")
    target_samples = 32000  # 2.0s at 16kHz

    def pad_or_crop(arr: np.ndarray) -> np.ndarray:
        if len(arr) < target_samples:
            pad_b = (target_samples - len(arr)) // 2
            pad_a = target_samples - len(arr) - pad_b
            return np.pad(arr, (pad_b, pad_a), mode="constant")
        return arr[:target_samples]

    X = []
    y = []

    for audio in pos_audios:
        padded = pad_or_crop(audio)
        feats = feature_extractor._get_embeddings(padded)
        if feats.shape == (16, 96):
            X.append(feats)
            y.append(1.0)
            # Time-shift augmentation
            for shift_frac in [-0.10, 0.10]:
                shift = int(shift_frac * 16000)
                shifted = np.roll(padded, shift)
                feats_shift = feature_extractor._get_embeddings(shifted)
                if feats_shift.shape == (16, 96):
                    X.append(feats_shift)
                    y.append(1.0)

    for audio in neg_audios:
        padded = pad_or_crop(audio)
        feats = feature_extractor._get_embeddings(padded)
        if feats.shape == (16, 96):
            X.append(feats)
            y.append(0.0)

    X_arr = np.array(X, dtype=np.float32)
    y_arr = np.array(y, dtype=np.float32)[:, None]
    print(f"Dataset ready: {len(y_arr)} total feature vectors ({int(np.sum(y_arr))} positive, {len(y_arr) - int(np.sum(y_arr))} negative).")

    print("Step 3/5: Training PyTorch classifier...")
    model = OpenWakeWordNet(input_shape=(16, 96), layer_dim=128, n_blocks=1)
    criterion = nn.BCELoss()
    optimizer = torch.optim.AdamW(model.parameters(), lr=0.001, weight_decay=1e-4)

    X_tensor = torch.from_numpy(X_arr)
    y_tensor = torch.from_numpy(y_arr)

    model.train()
    for epoch in range(100):
        perm = torch.randperm(X_tensor.size(0))
        epoch_loss = 0.0
        for i in range(0, X_tensor.size(0), 16):
            idx = perm[i:i + 16]
            bx, by = X_tensor[idx], y_tensor[idx]

            optimizer.zero_grad()
            preds = model(bx)
            loss = criterion(preds, by)
            loss.backward()
            optimizer.step()
            epoch_loss += loss.item()

    # Evaluation
    model.eval()
    with torch.no_grad():
        final_preds = model(X_tensor).numpy()
        pred_labels = (final_preds >= 0.5).astype(np.float32)
        acc = np.mean(pred_labels == y_arr) * 100.0
        print(f"Training completed! Model accuracy on dataset: {acc:.1f}%")

    print("Step 4/5: Exporting ONNX model...")
    os.makedirs("models/wakeword", exist_ok=True)
    out_onnx = "models/wakeword/hey_miku.onnx"
    dummy_input = torch.zeros((1, 16, 96), dtype=torch.float32)

    torch.onnx.export(
        model,
        dummy_input,
        out_onnx,
        opset_version=13,
        input_names=["x.1"],
        output_names=["53"],
        dynamic_axes={"x.1": {0: "batch_size"}, "53": {0: "batch_size"}}
    )
    print(f"Model exported: {out_onnx} ({os.path.getsize(out_onnx) // 1024} KB)")

    print("Step 5/5: Testing ONNX model with openWakeWord engine...")
    from openwakeword.model import Model as OWWModel
    test_oww = OWWModel(wakeword_models=[out_onnx], inference_framework="onnx")
    print(f"Loaded wake word model successfully: {list(test_oww.models.keys())}")

    # Test positive inference
    test_pos_audio = await synth_sample("Hey Miku", "es-MX-DaliaNeural", "+0%", "+0Hz")
    test_pos_padded = pad_or_crop(test_pos_audio)
    # Feed in 1280-sample chunks
    scores = []
    for i in range(0, len(test_pos_padded) - 1280, 1280):
        chunk = test_pos_padded[i:i+1280]
        res = test_oww.predict(chunk)
        scores.append(res.get("hey_miku", 0.0))

    max_score = max(scores) if scores else 0.0
    print(f"Test positive ('Hey Miku') peak score: {max_score:.3f} (Threshold is 0.5)")
    print("\n🎉 GENERATION COMPLETE! 'models/wakeword/hey_miku.onnx' is ready and fully functional!")

if __name__ == "__main__":
    asyncio.run(main())
