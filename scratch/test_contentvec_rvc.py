import asyncio
import io
import time
import edge_tts
import torch
import numpy as np
import soundfile as sf
import av
import faiss
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

async def test():
    device = "cuda" if torch.cuda.is_available() else "cpu"
    is_half = (device == "cuda")
    t_dtype = torch.half if is_half else torch.float32
    print(f"Device: {device}, FP16: {is_half}")

    print("Generating edge-tts sample with es-ES-XimenaNeural...")
    tts = edge_tts.Communicate("¡Hola, maestro! Soy Hatsune Miku, tu asistente de escritorio.", "es-ES-XimenaNeural")
    mp3_bytes = bytearray()
    async for chunk in tts.stream():
        if chunk["type"] == "audio":
            mp3_bytes.extend(chunk["data"])
    audio_16k = decode_audio_bytes(bytes(mp3_bytes), target_sr=16000)
    dur_s = len(audio_16k) / 16000.0
    print(f"Input audio: {dur_s:.2f}s")

    print("Loading ContentVec (lengyue233/content-vec-best)...")
    contentvec = HubertModel.from_pretrained("lengyue233/content-vec-best").to(device)
    if is_half:
        contentvec = contentvec.half()
    contentvec.eval()

    print("Loading RMVPE...")
    rmvpe = RMVPE("models/rvc/rmvpe.pt", is_half=is_half, device=device)

    print("Loading miku.pth...")
    cpt = torch.load("models/rvc/miku.pth", map_location="cpu")
    config = cpt["config"]
    target_sr = int(config[-1]) if isinstance(config[-1], (int, float)) else 40000
    net_g = SynthesizerTrnMs768NSFsid(*config, is_half=is_half).to(device)
    net_g.load_state_dict(cpt["weight"], strict=False)
    if is_half:
        net_g = net_g.half()
    net_g.eval()

    print("Loading FAISS index...")
    index = faiss.read_index("models/rvc/miku.index")
    if hasattr(index, "make_direct_map"):
        index.make_direct_map()

    # Test two key settings: f0_up_key = 0 and f0_up_key = 2
    for f0_up in [0, 2]:
        for idx_rate in [0.0, 0.4]:
            t0 = time.perf_counter()
            # 1. Extract ContentVec features
            wav_tensor = torch.from_numpy(audio_16k).unsqueeze(0).to(dtype=t_dtype, device=device)
            with torch.no_grad():
                out = contentvec(wav_tensor, output_hidden_states=True)
                # In RVC v2, layer 12 features (768-dim) are extracted
                feats_50hz = out.hidden_states[12][0].float().cpu().numpy()
            feats = np.repeat(feats_50hz, 2, axis=0) # [T_100hz, 768]

            # 2. RMVPE pitch
            f0 = rmvpe.infer_from_audio(audio_16k, thred=0.03)

            min_len = min(len(feats), len(f0))
            feats = feats[:min_len]
            f0 = f0[:min_len]

            # 3. FAISS index
            if idx_rate > 0.0 and index is not None:
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

            # 4. Pitch shift
            if f0_up != 0:
                f0 = f0 * (2.0 ** (f0_up / 12.0))

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

            # 5. Synthesize
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

            out_fn = f"scratch/miku_cvec_f0_{f0_up}_idx_{idx_rate}.wav"
            sf.write(out_fn, audio_arr, target_sr)
            dt = (time.perf_counter() - t0) * 1000.0
            print(f"Generated {out_fn} in {dt:.1f}ms (f0={f0_up}, idx={idx_rate})")

if __name__ == "__main__":
    asyncio.run(test())
