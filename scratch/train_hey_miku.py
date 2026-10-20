"""
Miku Assistant - Local Lightweight Hey Miku Wake Word Trainer
Generates synthetic positive samples ("Hey Miku", "Oye Miku") and negative samples,
extracts openWakeWord 16x96 audio embeddings, trains the official FCN architecture,
and exports directly to `models/wakeword/hey_miku.onnx`.
"""

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

VOICES = [
    "es-MX-DaliaNeural", "es-MX-JorgeNeural", "es-ES-XimenaNeural", "es-ES-AlvaroNeural",
    "es-AR-TomasNeural", "es-CO-GonzaloNeural", "es-US-PalomaNeural",
    "en-US-JennyNeural", "en-US-GuyNeural", "en-US-AriaNeural", "en-US-DavisNeural",
    "ja-JP-NanamiNeural", "ja-JP-KeitaNeural"
]

POSITIVE_PHRASES = [
    "Hey Miku", "Hey Miku!", "Oye Miku", "Oye Miku!", "Hey Miku, estás ahí?",
    "Miku", "Hola Miku", "Hey Miku, despierta", "Hey, Miku"
]

NEGATIVE_PHRASES = [
    "Hola, ¿cómo estás?", "Abre Google Chrome", "Pausa la música", "Qué hora es?",
    "Silencio por favor", "Hey Google", "Hey Siri", "Alexa", "Buenos días",
    "Buenas tardes", "Reproduce una canción", "Apaga la computadora", "Música pop",
    "Muchas gracias", "Hasta luego", "Bloc de notas", "Calculadora", "Subir volumen"
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
    print("=== Generating Synthetic Audio Dataset for 'Hey Miku' ===")
    feature_extractor = AudioFeatures(device="cpu")

    X = []
    y = []

    # 1. Synthesize Positive Clips
    print("Generating positive samples ('Hey Miku', 'Oye Miku')...")
    pos_audios = []
    for _ in range(75):
        phrase = random.choice(POSITIVE_PHRASES)
        voice = random.choice(VOICES)
        rate = f"{random.randint(-15, 20):+d}%"
        pitch = f"{random.randint(-15, 25):+d}Hz"
        try:
            audio = await synth_sample(phrase, voice, rate, pitch)
            if len(audio) > 8000:
                pos_audios.append(audio)
        except Exception as e:
            pass

    print(f"Generated {len(pos_audios)} positive audio clips.")

    # 2. Synthesize Negative Clips
    print("Generating negative samples (general speech, commands)...")
    neg_audios = []
    for _ in range(85):
        phrase = random.choice(NEGATIVE_PHRASES)
        voice = random.choice(VOICES)
        rate = f"{random.randint(-10, 15):+d}%"
        pitch = f"{random.randint(-10, 20):+d}Hz"
        try:
            audio = await synth_sample(phrase, voice, rate, pitch)
            if len(audio) > 8000:
                neg_audios.append(audio)
        except Exception as e:
            pass

    # Add background noise / silence negatives
    for _ in range(25):
        dur = random.randint(16000, 32000)
        noise = np.random.randint(-500, 500, dur, dtype=np.int16)
        neg_audios.append(noise)

    print(f"Generated {len(neg_audios)} negative audio clips.")

    # 3. Extract OpenWakeWord (16, 96) Embeddings
    print("Extracting AudioFeatures embeddings...")
    target_samples = 32000  # 2.0s at 16kHz

    def pad_or_crop(arr: np.ndarray) -> np.ndarray:
        if len(arr) < target_samples:
            pad_before = (target_samples - len(arr)) // 2
            pad_after = target_samples - len(arr) - pad_before
            return np.pad(arr, (pad_before, pad_after), mode="constant")
        return arr[:target_samples]

    for audio in pos_audios:
        padded = pad_or_crop(audio)
        feats = feature_extractor._get_embeddings(padded)
        if feats.shape == (16, 96):
            X.append(feats)
            y.append(1.0)
            # Add slight time-shifted augmentation
            shift = int(random.uniform(-0.15, 0.15) * 16000)
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
    print(f"Total dataset shape: X={X_arr.shape}, y={y_arr.shape} (Positive: {int(np.sum(y_arr))}, Negative: {len(y_arr) - int(np.sum(y_arr))})")

    # 4. Train Neural Network
    print("Training PyTorch classifier...")
    model = OpenWakeWordNet(input_shape=(16, 96), layer_dim=128, n_blocks=1)
    criterion = nn.BCELoss()
    optimizer = torch.optim.AdamW(model.parameters(), lr=0.001, weight_decay=1e-4)

    X_tensor = torch.from_numpy(X_arr)
    y_tensor = torch.from_numpy(y_arr)

    model.train()
    for epoch in range(120):
        permutation = torch.randperm(X_tensor.size(0))
        epoch_loss = 0.0
        for i in range(0, X_tensor.size(0), 32):
            indices = permutation[i:i + 32]
            batch_x, batch_y = X_tensor[indices], y_tensor[indices]

            optimizer.zero_grad()
            preds = model(batch_x)
            loss = criterion(preds, batch_y)
            loss.backward()
            optimizer.step()
            epoch_loss += loss.item()

        if (epoch + 1) % 30 == 0:
            print(f"Epoch {epoch+1}/120 - Loss: {epoch_loss:.4f}")

    # 5. Export to ONNX
    os.makedirs("models/wakeword", exist_ok=True)
    out_onnx = "models/wakeword/hey_miku.onnx"
    model.eval()

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
    print(f"SUCCESS! Exported custom wake word model to: {out_onnx} ({os.path.getsize(out_onnx) // 1024} KB)")

if __name__ == "__main__":
    asyncio.run(main())
