"""
Miku Assistant - Isolated GPU RVC Worker Subprocess
Strict adherence to GEMINI.md:
- Runs in an isolated subprocess so PyTorch and CUDA reside entirely here.
- When killed by resources.py, Windows reclaims 100% of GPU VRAM (0 MB idle).
- Fast FP16 inference on RTX 3050 with Transformers HuBERT, RMVPE, FAISS, and VITS.
"""

from __future__ import annotations

import base64
import io
import json
import logging
import os
import sys
import time
from pathlib import Path
from typing import Optional

# Add project root to sys.path so infer_pack and core can be imported
ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))
if str(ROOT_DIR / "core") not in sys.path:
    sys.path.insert(0, str(ROOT_DIR / "core"))

import av
import faiss
import numpy as np
import scipy.signal
import soundfile as sf
import torch
from transformers import HubertModel

from infer_pack.models import SynthesizerTrnMs768NSFsid
from rmvpe import RMVPE

# Logging to stderr so stdin/stdout remain clean for IPC
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [rvc_worker] [%(levelname)s] %(message)s",
    stream=sys.stderr,
)
logger = logging.getLogger("miku.rvc_worker")


def decode_audio_bytes(raw_bytes: bytes, target_sr: int = 16000) -> np.ndarray:
    """Decodes arbitrary audio bytes (mp3/wav) in-memory directly to float32 mono at target_sr."""
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


class RVCInferenceEngine:
    def __init__(self) -> None:
        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        self.is_half = (self.device == "cuda")
        logger.info("Initializing RVC Engine on %s (FP16: %s)", self.device, self.is_half)

        self.net_g: Optional[SynthesizerTrnMs768NSFsid] = None
        self.rmvpe: Optional[RMVPE] = None
        self.hubert: Optional[HubertModel] = None
        self.index: Optional[faiss.Index] = None
        self.current_model_path: str = ""
        self.current_index_path: str = ""
        self.target_sr: int = 40000

    def load_models(
        self,
        model_path: str,
        index_path: str = "",
        rmvpe_path: str = "models/rvc/rmvpe.pt",
    ) -> bool:
        """Loads and warms up all RVC components."""
        try:
            # 1. ContentVec model (standard RVC v2 content encoder)
            if self.hubert is None:
                logger.info("Loading ContentVec model (lengyue233/content-vec-best)...")
                hubert = HubertModel.from_pretrained("lengyue233/content-vec-best")
                if self.device == "cuda":
                    hubert = hubert.to(self.device)
                    if self.is_half:
                        hubert = hubert.half()
                hubert.eval()
                self.hubert = hubert
                logger.info("ContentVec model loaded on %s", self.device)

            # 2. RMVPE pitch estimator
            if self.rmvpe is None:
                r_path = ROOT_DIR / rmvpe_path
                if not r_path.exists():
                    logger.error("RMVPE model not found at %s", r_path)
                    return False
                logger.info("Loading RMVPE model: %s", r_path.name)
                self.rmvpe = RMVPE(str(r_path), is_half=self.is_half, device=self.device)

            # 3. Synthesizer model (miku.pth)
            m_path = ROOT_DIR / model_path
            if not m_path.exists():
                logger.error("Voice checkpoint not found at %s", m_path)
                return False

            if self.net_g is None or self.current_model_path != str(m_path):
                logger.info("Loading VITS generator: %s", m_path.name)
                cpt = torch.load(str(m_path), map_location="cpu", weights_only=True)
                config = cpt["config"]
                self.target_sr = int(config[-1]) if isinstance(config[-1], (int, float)) else 40000

                net_g = SynthesizerTrnMs768NSFsid(*config, is_half=self.is_half)
                # strict=False is the RVC convention (training-only enc_q weights), but report real gaps (H-041)
                missing = [k for k in net_g.load_state_dict(cpt["weight"], strict=False).missing_keys
                           if not k.startswith("enc_q.")]
                if missing:
                    logger.warning("Voice checkpoint is missing %d weights (e.g. %s): voice may sound wrong",
                                   len(missing), missing[:3])
                net_g.eval()

                if self.device == "cuda":
                    net_g = net_g.cuda()
                    if self.is_half:
                        net_g = net_g.half()

                self.net_g = net_g
                self.current_model_path = str(m_path)
                logger.info("VITS generator loaded successfully (target SR: %d)", self.target_sr)

            # 4. FAISS index
            if index_path:
                idx_path = ROOT_DIR / index_path
                if idx_path.exists() and (self.index is None or self.current_index_path != str(idx_path)):
                    logger.info("Loading FAISS feature index: %s", idx_path.name)
                    idx = faiss.read_index(str(idx_path))
                    if hasattr(idx, "make_direct_map"):
                        idx.make_direct_map()
                    self.index = idx
                    self.current_index_path = str(idx_path)
                    logger.info("FAISS index loaded (total vectors: %d)", self.index.ntotal)

            # 5. Quick GPU warm-up pass
            self._warmup_pass()
            return True

        except Exception as e:
            logger.exception("Failed loading RVC models: %s", e)
            return False

    def _warmup_pass(self) -> None:
        """Executes a tiny dummy forward pass to compile CUDA kernels and eliminate first-inference lag."""
        try:
            logger.debug("Executing warm-up pass on GPU...")
            t_dtype = torch.half if self.is_half else torch.float32

            if self.hubert is not None:
                dummy_wav = torch.zeros(1, 16000, dtype=t_dtype, device=self.device)
                with torch.no_grad():
                    _ = self.hubert(dummy_wav, output_hidden_states=True)

            if self.net_g is not None:
                phone = torch.zeros(1, 10, 768, dtype=t_dtype, device=self.device)
                phone_len = torch.tensor([10], dtype=torch.long, device=self.device)
                pitch = torch.zeros(1, 10, dtype=torch.long, device=self.device)
                pitchf = torch.full((1, 10), 440.0, dtype=torch.float32, device=self.device)
                sid = torch.tensor([0], dtype=torch.long, device=self.device)
                with torch.no_grad():
                    _ = self.net_g.infer(phone, phone_len, pitch, pitchf, sid)

            if self.device == "cuda":
                torch.cuda.synchronize()
            logger.info("RVC warm-up pass completed. Ready for real-time conversion.")
        except Exception as e:
            logger.warning("Warm-up pass encountered non-fatal error: %s", e)

    def convert(
        self,
        audio_bytes: bytes,
        f0_up_key: int = 0,
        index_rate: float = 0.25,
        protect: float = 0.33,
    ) -> Optional[bytes]:
        """Converts input voice audio to target character voice (Miku) with anti-artifact DSP."""
        if self.net_g is None or self.rmvpe is None or self.hubert is None:
            logger.error("Engine not ready for conversion. Call load_models first.")
            return None

        t_start = time.perf_counter()

        # 1. Decode in-memory to 16kHz float32
        raw_audio_16k = decode_audio_bytes(audio_bytes, target_sr=16000)
        if len(raw_audio_16k) == 0:
            logger.warning("Decoded audio is empty.")
            return None

        dur_s = len(raw_audio_16k) / 16000.0

        # 2. Boundary reflection padding (0.15s) to eliminate edge convolution clicks/pops
        pad_len_16k = int(0.15 * 16000)
        audio_16k = np.pad(raw_audio_16k, (pad_len_16k, pad_len_16k), mode="reflect")

        # 3. Extract ContentVec features at 50 Hz, repeat to 100 Hz
        t_dtype = torch.half if self.is_half else torch.float32
        wav_tensor = torch.from_numpy(audio_16k).unsqueeze(0).to(dtype=t_dtype, device=self.device)
        with torch.no_grad():
            out = self.hubert(wav_tensor, output_hidden_states=True)
            feats_50hz = out.hidden_states[12][0].float().cpu().numpy()  # [T_50hz, 768]
        feats = np.repeat(feats_50hz, 2, axis=0)  # [T_100hz, 768]

        # 4. Extract Pitch (f0) using RMVPE and smooth with median filter (radius=3)
        # Median filter removes 1-frame micro-spikes that cause vocoder "petardeos"
        f0 = self.rmvpe.infer_from_audio(audio_16k, thred=0.03)
        f0 = scipy.signal.medfilt(f0, 3)

        # Align time frames
        min_len = min(len(feats), len(f0))
        feats_orig = feats[:min_len]
        feats = np.copy(feats_orig)
        f0 = f0[:min_len]

        # 5. Optional Index Retrieval via FAISS
        if self.index is not None and index_rate > 0.0:
            try:
                feats_query = feats_orig.astype(np.float32)
                score, idx = self.index.search(feats_query, k=8)
                weight = np.square(1.0 / (score + 1e-4))
                weight /= np.sum(weight, axis=1, keepdims=True)
                # One batched lookup of only the neighbors needed (H-041); preloading every vector
                # would cost ~380 MB of RAM. FAISS returns -1 for missing neighbors.
                valid = (idx >= 0) & (idx < self.index.ntotal)
                neighbors = self.index.reconstruct_batch(np.where(valid, idx, 0).ravel().astype("int64"))
                neighbors = neighbors.reshape(*idx.shape, self.index.d)
                reconstructed = np.einsum("tk,tkd->td", weight * valid, neighbors)
                feats = (1.0 - index_rate) * feats_orig + index_rate * reconstructed
            except Exception as e:
                logger.warning("FAISS index retrieval skipped due to error: %s", e)

        # 6. Protect voiceless consonants and breath sounds from vocoder distortion/clicks
        if protect < 0.5:
            pitchff = np.copy(f0)
            pitchff[f0 > 0] = 1.0
            pitchff[f0 < 1] = protect
            feats = feats * pitchff[:, None] + feats_orig * (1.0 - pitchff[:, None])

        # 7. Pitch shifting for character timbre
        if f0_up_key != 0:
            f0 = f0 * (2.0 ** (f0_up_key / 12.0))

        # Pitch coarse quantization
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

        # 8. Synthesizer Inference
        phone = torch.from_numpy(feats.astype(np.float32)).to(dtype=t_dtype, device=self.device).unsqueeze(0)
        phone_lengths = torch.tensor([phone.shape[1]], dtype=torch.long, device=self.device)
        pitch = torch.from_numpy(f0_coarse).to(dtype=torch.long, device=self.device).unsqueeze(0)
        pitchf = torch.from_numpy(f0.astype(np.float32)).to(dtype=torch.float32, device=self.device).unsqueeze(0)
        sid = torch.tensor([0], dtype=torch.long, device=self.device)

        with torch.no_grad():
            audio_out, _, _ = self.net_g.infer(phone, phone_lengths, pitch, pitchf, sid)
            if self.device == "cuda":
                torch.cuda.synchronize()
            audio_arr = audio_out[0, 0].cpu().float().numpy()

        # 9. Crop padded edge frames at target_sr
        pad_target = int(pad_len_16k * (self.target_sr / 16000))
        if len(audio_arr) > 2 * pad_target:
            audio_arr = audio_arr[pad_target:-pad_target]

        # 10. DC offset removal + smooth peak normalization (prevents DAC/driver clipping)
        audio_arr = audio_arr - np.mean(audio_arr)
        max_val = np.max(np.abs(audio_arr))
        if max_val > 0.01:
            audio_arr = (audio_arr / max_val) * 0.90

        # 11. Encode output audio to 16-bit PCM WAV in memory
        out_buf = io.BytesIO()
        sf.write(out_buf, audio_arr, self.target_sr, format="WAV", subtype="PCM_16")
        wav_bytes = out_buf.getvalue()

        dt = (time.perf_counter() - t_start) * 1000.0
        logger.info(
            "RVC converted %.2fs input -> %.2fs Miku voice (%.1f ms total, %.1fx real-time)",
            dur_s,
            len(audio_arr) / float(self.target_sr),
            dt,
            (dur_s * 1000.0) / max(1.0, dt),
        )
        return wav_bytes


def main() -> None:
    # Protect JSON-RPC IPC pipe: save real stdout, redirect sys.stdout to sys.stderr
    ipc_out = sys.stdout
    sys.stdout = sys.stderr

    logger.info("RVC Worker process started (PID: %d)", os.getpid())
    engine = RVCInferenceEngine()

    def send_resp(data: dict) -> None:
        ipc_out.write(json.dumps(data) + "\n")
        ipc_out.flush()

    # Read commands from stdin line-by-line
    while True:
        try:
            line = sys.stdin.readline()
            if not line:
                # EOF reached: parent core process terminated or pipe closed
                logger.info("Parent pipe closed (EOF). Exiting worker.")
                break

            clean_line = line.strip()
            if not clean_line:
                continue

            req = json.loads(clean_line)
            cmd = req.get("cmd", "")

            if cmd == "ping":
                send_resp({"status": "pong"})

            elif cmd == "load" or cmd == "warmup":
                model_path = req.get("model", "models/rvc/miku.pth")
                index_path = req.get("index", "models/rvc/miku.index")
                ok = engine.load_models(model_path=model_path, index_path=index_path)
                send_resp({"status": "ok" if ok else "error"})

            elif cmd == "convert":
                audio_b64 = req.get("audio_b64", "")
                f0_up_key = int(req.get("f0_up_key", 0))
                index_rate = float(req.get("index_rate", 0.25))
                protect = float(req.get("protect", 0.33))

                if not audio_b64:
                    send_resp({"status": "error", "error": "Missing audio_b64"})
                    continue

                raw_input_bytes = base64.b64decode(audio_b64)
                converted_bytes = engine.convert(
                    audio_bytes=raw_input_bytes,
                    f0_up_key=f0_up_key,
                    index_rate=index_rate,
                    protect=protect,
                )

                if converted_bytes:
                    res_b64 = base64.b64encode(converted_bytes).decode("ascii")
                    send_resp({
                        "status": "ok",
                        "audio_b64": res_b64,
                        "mime": "audio/wav",
                    })
                else:
                    send_resp({"status": "error", "error": "Conversion produced no output"})

            elif cmd == "quit":
                logger.info("Received quit command. Shutting down gracefully.")
                send_resp({"status": "ok"})
                break

            else:
                send_resp({"status": "error", "error": f"Unknown command '{cmd}'"})

        except KeyboardInterrupt:
            logger.info("Interrupted. Exiting.")
            break
        except Exception as e:
            logger.exception("Error processing command: %s", e)
            try:
                send_resp({"status": "error", "error": str(e)})
            except Exception:
                pass

    logger.info("RVC Worker process exiting.")
    sys.exit(0)


if __name__ == "__main__":
    main()
