"""
Train an improved, robust Hey Miku wake word model for openWakeWord.
Runs concurrent audio synthesis via asyncio.gather and Semaphore for fast execution (~20-30s).
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
    # Male voices
    "es-MX-JorgeNeural", "es-ES-AlvaroNeural", "es-AR-TomasNeural",
    "es-CO-GonzaloNeural", "es-US-AlonsoNeural", "en-US-GuyNeural",
    # Female voices
    "es-MX-DaliaNeural", "es-ES-ElviraNeural", "es-ES-XimenaNeural",
    "es-US-PalomaNeural", "en-US-JennyNeural", "en-US-AriaNeural"
]

POSITIVE_PHRASES = [
    "Hey Miku", "Hey Miku!", "Hey Miku.",
    "Oye Miku", "Oye Miku!",
    "Miku", "Miku!",
    "Hola Miku", "Hola Miku!",
    "Ey Miku", "Ey, Miku"
]

NEGATIVE_PHRASES = [
    "Hola, ¿cómo estás?", "¿Qué pasa?", "¿Qué pasa hoy?", "¿Qué hora es?",
    "Abre Google Chrome", "Abre el bloc de notas", "Abre la calculadora",
    "Pausa la música", "Reproduce una canción", "Sube el volumen", "Baja el volumen",
    "Silencio por favor", "Hey Google", "Hey Siri", "Alexa", "Hey Cortana",
    "Buenos días", "Buenas tardes", "Buenas noches", "¿Cómo te va?",
    "Muchas gracias", "Hasta luego", "Adiós", "Nos vemos",
    "Cancela", "Espera un momento", "¿Me puedes escuchar?", "No me escuchas",
    "Quiero saber qué tiempo hace", "Pon la alarma a las ocho", "Dime un chiste",
    "Cuéntame una historia", "Abre YouTube", "Busca en internet", "Música clásica",
    "Tengo una pregunta", "Apaga la pantalla", "Abre la terminal", "Todo bien",
    "Claro que sí", "Por favor", "De acuerdo", "Entendido", "Gracias"
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

async def synth_sample(sem: asyncio.Semaphore, phrase: str, voice: str, rate: str, pitch: str) -> np.ndarray:
    async with sem:
        try:
            tts = edge_tts.Communicate(phrase, voice, rate=rate, pitch=pitch)
            data = bytearray()
            async for chunk in tts.stream():
                if chunk["type"] == "audio":
                    data.extend(chunk["data"])
            return decode_audio_16k_int16(bytes(data))
        except Exception:
            return np.zeros(0, dtype=np.int16)

class FCNBlock(nn.Module):
    def __init__(self, layer_dim):
        super().__init__()
        self.fcn_layer = nn.Linear(layer_dim, layer_dim)
        self.relu = nn.ReLU()
        self.layer_norm = nn.LayerNorm(layer_dim)
        self.dropout = nn.Dropout(0.15)

    def forward(self, x):
        return self.dropout(self.relu(self.layer_norm(self.fcn_layer(x))))

class OpenWakeWordNet(nn.Module):
    def __init__(self, input_shape=(16, 96), layer_dim=128, n_blocks=1):
        super().__init__()
        self.flatten = nn.Flatten()
        self.layer1 = nn.Linear(input_shape[0] * input_shape[1], layer_dim)
        self.relu1 = nn.ReLU()
        self.layernorm1 = nn.LayerNorm(layer_dim)
        self.dropout1 = nn.Dropout(0.15)
        self.blocks = nn.ModuleList([FCNBlock(layer_dim) for _ in range(n_blocks)])
        self.last_layer = nn.Linear(layer_dim, 1)
        self.last_act = nn.Sigmoid()

    def forward(self, x):
        x = self.dropout1(self.relu1(self.layernorm1(self.layer1(self.flatten(x)))))
        for block in self.blocks:
            x = block(x)
        return self.last_act(self.last_layer(x))

async def main():
    print("=== Generating Synthetic Audio Dataset for 'Hey Miku' v2 ===", flush=True)
    feature_extractor = AudioFeatures(device="cpu")
    target_samples = 32000  # 2.0s at 16kHz
    sem = asyncio.Semaphore(12)

    # 1. Synthesize Positive Clips concurrently
    print("Synthesizing positive clips...", flush=True)
    pos_tasks = []
    for voice in VOICES:
        for phrase in POSITIVE_PHRASES:
            rate = f"{random.choice([-15, 0, 15]):+d}%"
            pitch = f"{random.randint(-12, 18):+d}Hz"
            pos_tasks.append(synth_sample(sem, phrase, voice, rate, pitch))

    pos_results = await asyncio.gather(*pos_tasks)
    pos_audios = [a for a in pos_results if len(a) > 6000]
    print(f"Generated {len(pos_audios)} positive audio clips.", flush=True)

    # 2. Synthesize Negative Clips concurrently
    print("Synthesizing negative speech clips...", flush=True)
    neg_tasks = []
    for _ in range(160):
        phrase = random.choice(NEGATIVE_PHRASES)
        voice = random.choice(VOICES)
        rate = f"{random.randint(-15, 15):+d}%"
        pitch = f"{random.randint(-15, 15):+d}Hz"
        neg_tasks.append(synth_sample(sem, phrase, voice, rate, pitch))

    neg_results = await asyncio.gather(*neg_tasks)
    neg_audios = [a for a in neg_results if len(a) > 6000]
    print(f"Generated {len(neg_audios)} negative audio clips.", flush=True)

    # 3. Add Silence and Noise Negatives
    print("Adding silence and room-noise negatives...", flush=True)
    for _ in range(50):
        neg_audios.append(np.zeros(target_samples, dtype=np.int16))
    for _ in range(50):
        noise = np.random.normal(0, random.uniform(15, 75), target_samples).astype(np.int16)
        neg_audios.append(noise)
    for _ in range(30):
        t = np.linspace(0, 2.0, target_samples)
        freq = random.uniform(50, 250)
        hum = (np.sin(2 * np.pi * freq * t) * random.uniform(20, 100)).astype(np.int16)
        neg_audios.append(hum)

    print(f"Total negative clips: {len(neg_audios)}", flush=True)

    # 4. Extract Audio Features with Augmentations
    print("Extracting AudioFeatures embeddings with volume and timing augmentations...", flush=True)

    def pad_or_crop(arr: np.ndarray) -> np.ndarray:
        if len(arr) < target_samples:
            pad_before = (target_samples - len(arr)) // 2
            pad_after = target_samples - len(arr) - pad_before
            return np.pad(arr, (pad_before, pad_after), mode="constant")
        return arr[:target_samples]

    X = []
    y = []

    # Process positive samples with augmentations (4x expansion)
    for audio in pos_audios:
        padded = pad_or_crop(audio)
        # Normal volume
        f = feature_extractor._get_embeddings(padded)
        if f.shape == (16, 96):
            X.append(f)
            y.append(1.0)

        # Soft voice (gain 0.35 - 0.55)
        soft = (padded * random.uniform(0.35, 0.55)).astype(np.int16)
        f_soft = feature_extractor._get_embeddings(soft)
        if f_soft.shape == (16, 96):
            X.append(f_soft)
            y.append(1.0)

        # Loud voice (gain 1.2 - 1.5)
        loud = np.clip(padded * random.uniform(1.2, 1.5), -32767, 32767).astype(np.int16)
        f_loud = feature_extractor._get_embeddings(loud)
        if f_loud.shape == (16, 96):
            X.append(f_loud)
            y.append(1.0)

        # Slight time shift (+-100ms)
        shift = int(random.uniform(-0.12, 0.12) * 16000)
        shifted = np.roll(padded, shift)
        f_shift = feature_extractor._get_embeddings(shifted)
        if f_shift.shape == (16, 96):
            X.append(f_shift)
            y.append(1.0)

    # Process negative samples
    for audio in neg_audios:
        padded = pad_or_crop(audio)
        f = feature_extractor._get_embeddings(padded)
        if f.shape == (16, 96):
            X.append(f)
            y.append(0.0)

    X_arr = np.array(X, dtype=np.float32)
    y_arr = np.array(y, dtype=np.float32)[:, None]
    num_pos = int(np.sum(y_arr))
    num_neg = len(y_arr) - num_pos
    print(f"Extracted dataset: {len(X_arr)} total samples (Positive: {num_pos}, Negative: {num_neg})", flush=True)

    # 5. Train Neural Network with AdamW
    print("Training PyTorch classifier...", flush=True)
    torch.manual_seed(42)
    model = OpenWakeWordNet(input_shape=(16, 96), layer_dim=128, n_blocks=1)

    # Train model directly with BCE
    criterion = nn.BCELoss()
    optimizer = torch.optim.AdamW(model.parameters(), lr=0.001, weight_decay=1e-4)

    X_tensor = torch.from_numpy(X_arr)
    y_tensor = torch.from_numpy(y_arr)

    model.train()
    for epoch in range(80):
        perm = torch.randperm(X_tensor.size(0))
        epoch_loss = 0.0
        batches = 0
        for i in range(0, X_tensor.size(0), 48):
            idx = perm[i:i + 48]
            bx, by = X_tensor[idx], y_tensor[idx]
            optimizer.zero_grad()
            preds = model(bx)
            loss = criterion(preds, by)
            loss.backward()
            optimizer.step()
            epoch_loss += loss.item()
            batches += 1

        if (epoch + 1) % 20 == 0:
            print(f"Epoch {epoch+1}/80 - Loss: {epoch_loss / batches:.4f}", flush=True)

    # 6. Export to ONNX
    os.makedirs("models/wakeword", exist_ok=True)
    out_onnx = "models/wakeword/hey_miku.onnx"
    model.eval()

    dummy_input = torch.zeros((1, 16, 96), dtype=torch.float32)
    torch.onnx.export(
        model,
        dummy_input,
        out_onnx,
        opset_version=13,
        input_names=["input"],
        output_names=["output"],
        dynamic_axes={"input": {0: "batch_size"}, "output": {0: "batch_size"}},
        dynamo=False,
    )
    print(f"SUCCESS! Exported v2 wake word model to: {out_onnx} ({os.path.getsize(out_onnx) // 1024} KB)", flush=True)

if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    asyncio.run(main())
