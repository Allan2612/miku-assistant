import asyncio
import io
import time
import edge_tts
import torch
import numpy as np
import soundfile as sf
import av
import faiss
from transformers import HubertModel
import os
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "core"))

from infer_pack.models import SynthesizerTrnMs768NSFsid
from rmvpe import RMVPE

def decode_audio_bytes(raw_bytes: bytes, target_sr: int = 16000) -> np.ndarray:
    container = av.open(io.BytesIO(raw_bytes))
    resampler = av.AudioResampler(format="fltp", layout="mono", rate=target_sr)
    chunks = []
    for frame in container.decode(audio=0):
        frame.pts = None
        for resampled_frame in resampler.resample(frame):
            chunks.append(resampled_frame.to_ndarray())
    container.close()
    if chunks:
        audio = np.concatenate(chunks, axis=1).squeeze(0)
        return audio.astype(np.float32)
    return np.zeros(0, dtype=np.float32)

async def main():
    print("Generating sample edge-tts speech...")
    tts = edge_tts.Communicate("¡Hola, maestro! Soy Hatsune Miku, tu asistente virtual.", "es-ES-XimenaNeural")
    mp3_bytes = bytearray()
    async for chunk in tts.stream():
        if chunk["type"] == "audio":
            mp3_bytes.extend(chunk["data"])
    print(f"Edge-tts audio generated: {len(mp3_bytes)} bytes")

    device = "cuda" if torch.cuda.is_available() else "cpu"
    is_half = (device == "cuda")
    print(f"Using device: {device}, FP16: {is_half}")

    print("Loading HuBERT...")
    hubert = HubertModel.from_pretrained("facebook/hubert-base-ls960").to(device)
    if is_half:
        hubert = hubert.half()
    hubert.eval()

    print("Loading RMVPE...")
    rmvpe = RMVPE("models/rvc/rmvpe.pt", is_half=is_half, device=device)

    print("Loading miku.pth...")
    cpt = torch.load("models/rvc/miku.pth", map_location="cpu")
    config = cpt["config"]
    target_sr = int(config[-1]) if isinstance(config[-1], (int, float)) else 40000
    net_g = SynthesizerTrnMs768NSFsid(*config, is_half=is_half)
    net_g.load_state_dict(cpt["weight"], strict=False)
    net_g.eval().to(device)
    if is_half:
        net_g = net_g.half()

    print("Loading FAISS index...")
    index = faiss.read_index("models/rvc/miku.index")
    if hasattr(index, "make_direct_map"):
        index.make_direct_map()

    # Warmup
    print("Warming up GPU...")
    t_dtype = torch.half if is_half else torch.float32
    with torch.no_grad():
        _ = hubert(torch.zeros(1, 16000, dtype=t_dtype, device=device))
        phone = torch.zeros(1, 10, 768, dtype=t_dtype, device=device)
        phone_len = torch.tensor([10], dtype=torch.long, device=device)
        pitch = torch.zeros(1, 10, dtype=torch.long, device=device)
        pitchf = torch.full((1, 10), 440.0, dtype=torch.float32, device=device)
        sid = torch.tensor([0], dtype=torch.long, device=device)
        _ = net_g.infer(phone, phone_len, pitch, pitchf, sid)
    if device == "cuda":
        torch.cuda.synchronize()

    print("--- Starting RVC conversion ---")
    t0 = time.perf_counter()
    audio_16k = decode_audio_bytes(bytes(mp3_bytes), target_sr=16000)
    dur_s = len(audio_16k) / 16000.0

    wav_tensor = torch.from_numpy(audio_16k).unsqueeze(0).to(dtype=t_dtype, device=device)
    with torch.no_grad():
        out = hubert(wav_tensor)
        feats_50hz = out.last_hidden_state[0].float().cpu().numpy()
    feats = np.repeat(feats_50hz, 2, axis=0)

    f0 = rmvpe.infer_from_audio(audio_16k, thred=0.03)

    min_len = min(len(feats), len(f0))
    feats = feats[:min_len]
    f0 = f0[:min_len]

    # Index retrieval
    index_rate = 0.5
    if index is not None and index_rate > 0.0:
        feats_query = feats.astype(np.float32)
        score, idx = index.search(feats_query, k=8)
        print(f"Index search returned: idx shape={idx.shape}, min={idx.min()}, max={idx.max()}, ntotal={index.ntotal}")
        weight = np.square(1.0 / (score + 1e-4))
        weight /= np.sum(weight, axis=1, keepdims=True)
        reconstructed = np.zeros_like(feats_query)
        for i in range(len(feats_query)):
            for j in range(8):
                k = int(idx[i, j])
                if 0 <= k < index.ntotal:
                    reconstructed[i] += weight[i, j] * index.reconstruct(k)
        feats = (1.0 - index_rate) * feats + index_rate * reconstructed

    # f0 shift (+6 semitones)
    f0_up_key = 6
    if f0_up_key != 0:
        f0 = f0 * (2.0 ** (f0_up_key / 12.0))

    f0_mel_min = 1127.0 * np.log(1.0 + 50.0 / 700.0)
    f0_mel_max = 1127.0 * np.log(1.0 + 1100.0 / 700.0)
    f0_mel = 1127.0 * np.log(1.0 + f0 / 700.0)
    f0_coarse = np.zeros_like(f0, dtype=np.int64)
    voiced = f0 > 0
    f0_coarse[voiced] = np.clip(
        (f0_mel[voiced] - f0_mel_min) * 254.0 / (f0_mel_max - f0_mel_min) + 1.0,
        1,
        255,
    ).astype(np.int64)

    phone = torch.from_numpy(feats.astype(np.float32)).to(dtype=t_dtype, device=device).unsqueeze(0)
    phone_lengths = torch.tensor([phone.shape[1]], dtype=torch.long, device=device)
    pitch = torch.from_numpy(f0_coarse).to(dtype=torch.long, device=device).unsqueeze(0)
    pitchf = torch.from_numpy(f0.astype(np.float32)).to(dtype=torch.float32, device=device).unsqueeze(0)
    sid = torch.tensor([0], dtype=torch.long, device=device)

    with torch.no_grad():
        audio_out, _, _ = net_g.infer(phone, phone_lengths, pitch, pitchf, sid)
        if device == "cuda":
            torch.cuda.synchronize()
        audio_arr = audio_out[0, 0].cpu().float().numpy()

    dt = (time.perf_counter() - t0) * 1000.0
    print(f"Conversion took: {dt:.1f}ms for {dur_s:.2f}s of audio ({dur_s*1000/dt:.1f}x real-time)!")
    sf.write("scratch/miku_rvc_test.wav", audio_arr, target_sr)
    print("Saved scratch/miku_rvc_test.wav successfully!")

if __name__ == "__main__":
    asyncio.run(main())
