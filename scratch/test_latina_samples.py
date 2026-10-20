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

async def test_voices():
    device = "cuda" if torch.cuda.is_available() else "cpu"
    is_half = (device == "cuda")
    t_dtype = torch.half if is_half else torch.float32

    # Latin American voices to test
    tts_voices = [
        ("es-MX-DaliaNeural", "+5%", "+10Hz", "dalia"),
    ]

    phrase = "¡Hola, maestro! Soy Hatsune Miku, tu asistente virtual. ¿Qué vamos a hacer hoy?"

    contentvec = HubertModel.from_pretrained("lengyue233/content-vec-best").to(device)
    if is_half:
        contentvec = contentvec.half()
    contentvec.eval()

    rmvpe = RMVPE("models/rvc/rmvpe.pt", is_half=is_half, device=device)

    for voice_name, rate, pitch, tag in tts_voices:
        print(f"Generating base voice with {voice_name}...")
        tts = edge_tts.Communicate(phrase, voice_name, rate=rate, pitch=pitch)
        mp3_bytes = bytearray()
        async for chunk in tts.stream():
            if chunk["type"] == "audio":
                mp3_bytes.extend(chunk["data"])
        audio_16k = decode_audio_bytes(bytes(mp3_bytes), target_sr=16000)

        wav_tensor = torch.from_numpy(audio_16k).unsqueeze(0).to(dtype=t_dtype, device=device)
        with torch.no_grad():
            out = contentvec(wav_tensor, output_hidden_states=True)
            feats_50hz = out.hidden_states[12][0].float().cpu().numpy()
        feats_raw = np.repeat(feats_50hz, 2, axis=0)

        f0_raw = rmvpe.infer_from_audio(audio_16k, thred=0.03)

        min_len = min(len(feats_raw), len(f0_raw))
        feats_base = feats_raw[:min_len]
        f0_base = f0_raw[:min_len]

        for model_label, m_path, idx_path in [
            ("Power", "models/rvc/miku_power.pth", "models/rvc/miku_power.index"),
            ("Mellow", "models/rvc/miku_mellow.pth", "models/rvc/miku_mellow.index"),
        ]:
            cpt = torch.load(m_path, map_location="cpu")
            config = cpt["config"]
            target_sr = int(config[-1]) if isinstance(config[-1], (int, float)) else 40000
            net_g = SynthesizerTrnMs768NSFsid(*config, is_half=is_half).to(device)
            net_g.load_state_dict(cpt["weight"], strict=False)
            if is_half:
                net_g = net_g.half()
            net_g.eval()

            feats = np.copy(feats_base)
            f0 = np.copy(f0_base)

            try:
                index = faiss.read_index(idx_path)
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
            except Exception as e:
                print(f"Index error: {e}")

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

            out_path = f"app/public/samples/miku_{model_label.lower()}_latina.wav"
            sf.write(out_path, audio_arr, target_sr)
            print(f"Generated {out_path} with {model_label}!")

if __name__ == "__main__":
    asyncio.run(test_voices())
