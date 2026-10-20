import asyncio
import io
import time
import edge_tts
import torch
import numpy as np
import soundfile as sf
import av
import faiss
import scipy.signal
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "core"))

from transformers import HubertModel
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

async def test_clean():
    device = "cuda" if torch.cuda.is_available() else "cpu"
    is_half = (device == "cuda")
    t_dtype = torch.half if is_half else torch.float32

    phrase = "¡Hola, maestro! Soy Hatsune Miku, tu asistente virtual. ¿Qué vamos a hacer hoy?"
    print(f"Generating TTS for: '{phrase}'...")
    tts = edge_tts.Communicate(phrase, "es-MX-DaliaNeural", rate="+5%", pitch="+10Hz")
    mp3_bytes = bytearray()
    async for chunk in tts.stream():
        if chunk["type"] == "audio":
            mp3_bytes.extend(chunk["data"])
    raw_audio_16k = decode_audio_bytes(bytes(mp3_bytes), target_sr=16000)

    # 1. Pad 0.15s of silence at edges to prevent convolution boundary clicks
    pad_samples_16k = int(0.15 * 16000)
    audio_16k = np.pad(raw_audio_16k, (pad_samples_16k, pad_samples_16k), mode="reflect")

    contentvec = HubertModel.from_pretrained("lengyue233/content-vec-best").to(device)
    if is_half:
        contentvec = contentvec.half()
    contentvec.eval()

    rmvpe = RMVPE("models/rvc/rmvpe.pt", is_half=is_half, device=device)

    # 2. Extract ContentVec
    wav_tensor = torch.from_numpy(audio_16k).unsqueeze(0).to(dtype=t_dtype, device=device)
    with torch.no_grad():
        out = contentvec(wav_tensor, output_hidden_states=True)
        feats_50hz = out.hidden_states[12][0].float().cpu().numpy()
    feats = np.repeat(feats_50hz, 2, axis=0)

    # 3. Extract RMVPE pitch and apply MEDIAN FILTER (radius=3) to remove single-frame glitch spikes
    f0 = rmvpe.infer_from_audio(audio_16k, thred=0.03)
    f0 = scipy.signal.medfilt(f0, 3)

    min_len = min(len(feats), len(f0))
    feats = feats[:min_len]
    f0 = f0[:min_len]

    # 4. Load Mellow model & FAISS
    cpt = torch.load("models/rvc/miku_mellow.pth", map_location="cpu")
    config = cpt["config"]
    target_sr = int(config[-1]) if isinstance(config[-1], (int, float)) else 40000
    net_g = SynthesizerTrnMs768NSFsid(*config, is_half=is_half).to(device)
    net_g.load_state_dict(cpt["weight"], strict=False)
    if is_half:
        net_g = net_g.half()
    net_g.eval()

    # FAISS retrieval with moderate rate
    index = faiss.read_index("models/rvc/miku_mellow.index")
    if hasattr(index, "make_direct_map"):
        index.make_direct_map()
    idx_rate = 0.25
    feats_query = feats.astype(np.float32)
    score, idx = index.search(feats_query, k=8)
    weight = np.square(1.0 / (score + 1e-4))
    weight /= np.sum(weight, axis=1, keepdims=True)
    reconstructed = np.zeros_like(feats_query)
    for i in range(len(feats_query)):
        for j in range(8):
            k = int(idx[i, j])
            if 0 <= k < index.ntotal:
                reconstructed[i] += weight[i, j] * index.reconstruct(k)
    feats = (1.0 - idx_rate) * feats + idx_rate * reconstructed

    # Coarse pitch
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

    # 5. Crop padded edge frames at target_sr
    pad_samples_target = int(pad_samples_16k * (target_sr / 16000))
    if len(audio_arr) > 2 * pad_samples_target:
        audio_arr = audio_arr[pad_samples_target:-pad_samples_target]

    # 6. Post-processing: DC offset removal + smooth peak normalization
    audio_arr = audio_arr - np.mean(audio_arr)
    max_val = np.max(np.abs(audio_arr))
    if max_val > 0.01:
        audio_arr = (audio_arr / max_val) * 0.92

    out_clean = "app/public/samples/miku_mellow_latina_clean.wav"
    sf.write(out_clean, audio_arr, target_sr)
    print(f"Saved clean audio to {out_clean}!")

    # Check jumps
    diffs = np.abs(np.diff(audio_arr))
    clicks = np.where(diffs > 0.3)[0]
    print(f"Analysis: Max jump: {np.max(diffs):.4f}, Jumps > 0.3: {len(clicks)} (was 1499 before!)")

if __name__ == "__main__":
    asyncio.run(test_clean())
