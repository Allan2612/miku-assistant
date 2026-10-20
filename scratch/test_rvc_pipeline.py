"""
Test end-to-end RVC conversion on RTX 3050.
"""

import sys
import os
import time
from pathlib import Path
import numpy as np
import soundfile as sf
import onnxruntime as ort
import torch

sys.path.insert(0, os.path.abspath("core"))
from infer_pack.models import SynthesizerTrnMs768NSFsid
from rmvpe import RMVPE

def run_test():
    print("=== Starting RVC End-to-End Test ===")
    device = "cuda" if torch.cuda.is_available() else "cpu"
    print(f"Device: {device}")

    # 1. Load TTS sample audio or generate a simple edge-tts clip
    audio_path = Path("cache/voice")
    wav_files = list(audio_path.glob("*.mp3"))
    if not wav_files:
        print("No cached voice found in cache/voice, synthesizing a short test...")
        import edge_tts
        import asyncio
        async def make_sample():
            c = edge_tts.Communicate("¡Hola, soy Hatsune Miku! ¿En qué puedo ayudarte hoy?", "es-MX-DaliaNeural")
            await c.save("scratch/test_input.mp3")
        asyncio.run(make_sample())
        input_audio_path = "scratch/test_input.mp3"
    else:
        input_audio_path = str(wav_files[0])

    print(f"Input audio: {input_audio_path}")
    import librosa
    audio_16k, _ = librosa.load(input_audio_path, sr=16000, mono=True)
    print(f"Audio 16k loaded: {len(audio_16k)} samples ({len(audio_16k)/16000:.2f}s)")

    # 2. Extract HuBERT features via ONNX
    t0 = time.perf_counter()
    hubert_sess = ort.InferenceSession("models/rvc/hubert_base.onnx", providers=["CPUExecutionProvider"])
    
    waveform = np.expand_dims(audio_16k, axis=0).astype(np.float32)
    padding_mask = np.zeros(waveform.shape, dtype=bool)
    
    inputs = {
        hubert_sess.get_inputs()[0].name: waveform,
        hubert_sess.get_inputs()[1].name: padding_mask,
    }
    feats_50hz = hubert_sess.run(None, inputs)[0][0] # [T_50hz, 768]
    feats = np.repeat(feats_50hz, 2, axis=0) # [T_100hz, 768]
    t1 = time.perf_counter()
    print(f"HuBERT features extracted: shape {feats.shape} in {(t1 - t0)*1000:.1f}ms")

    # 3. Extract Pitch (f0) via RMVPE
    t0_pitch = time.perf_counter()
    rmvpe = RMVPE("models/rvc/rmvpe.pt", is_half=False, device=device)
    f0 = rmvpe.infer_from_audio(audio_16k, thred=0.03)
    t1_pitch = time.perf_counter()
    print(f"RMVPE f0 extracted: shape {f0.shape} in {(t1_pitch - t0_pitch)*1000:.1f}ms")

    # Align lengths
    min_len = min(len(feats), len(f0))
    feats = feats[:min_len]
    f0 = f0[:min_len]

    # Apply pitch shift (f0_up_key = +6 semitones for Miku)
    f0_up_key = 6
    f0 = f0 * (2.0 ** (f0_up_key / 12.0))

    # Compute coarse pitch (pitch bin 1..255)
    f0_mel_min = 1127 * np.log(1 + 50.0 / 700)
    f0_mel_max = 1127 * np.log(1 + 1100.0 / 700)
    f0_mel = 1127 * np.log(1 + f0 / 700)
    f0_coarse = np.zeros_like(f0, dtype=np.int64)
    voiced = f0 > 0
    f0_coarse[voiced] = np.clip(
        (f0_mel[voiced] - f0_mel_min) * 254 / (f0_mel_max - f0_mel_min) + 1,
        1,
        255
    ).astype(np.int64)

    # 4. Synthesizer Inference (miku.pth)
    t0_vits = time.perf_counter()
    c = torch.load("models/rvc/miku.pth", map_location="cpu")
    net_g = SynthesizerTrnMs768NSFsid(*c["config"], is_half=False)
    net_g.load_state_dict(c["weight"], strict=False)
    net_g.eval()
    if device == "cuda":
        net_g = net_g.cuda()

    phone = torch.from_numpy(feats.astype(np.float32)).unsqueeze(0).to(device)
    phone_lengths = torch.tensor([phone.shape[1]], dtype=torch.long, device=device)
    pitch = torch.from_numpy(f0_coarse.astype(np.int64)).unsqueeze(0).to(device)
    pitchf = torch.from_numpy(f0.astype(np.float32)).unsqueeze(0).to(device)
    sid = torch.tensor([0], dtype=torch.long, device=device)

    with torch.no_grad():
        audio_out, _, _ = net_g.infer(phone, phone_lengths, pitch, pitchf, sid)
        audio_out = audio_out[0, 0].cpu().numpy()

    t1_vits = time.perf_counter()
    print(f"VITS Synthesizer completed in {(t1_vits - t0_vits)*1000:.1f}ms! Output shape: {audio_out.shape} at 40kHz ({len(audio_out)/40000:.2f}s)")

    # Save output
    out_file = "scratch/miku_rvc_test.wav"
    sf.write(out_file, audio_out, 40000)
    print(f"Wrote output to {out_file} (size: {os.path.getsize(out_file)} bytes)")

if __name__ == "__main__":
    run_test()
