"""
Miku Assistant - Streaming voice activity detection (silero-vad, CPU, ONNX).
Reuses the silero model bundled with faster-whisper (no extra dependency). Unlike
faster_whisper.vad.SileroVADModel.__call__, it keeps the LSTM state between 32 ms
chunks so it can run live while recording (H-034).
"""

from __future__ import annotations

import numpy as np

CHUNK = 512    # samples at 16 kHz (32 ms), the size silero expects
CONTEXT = 64   # samples of the previous chunk prepended to each input


class StreamingVAD:
    def __init__(self) -> None:
        from faster_whisper.vad import get_vad_model

        self._session = get_vad_model().session
        self.reset()

    def reset(self) -> None:
        self._h = np.zeros((1, 1, 128), dtype=np.float32)
        self._c = np.zeros((1, 1, 128), dtype=np.float32)
        self._context = np.zeros(CONTEXT, dtype=np.float32)

    def __call__(self, chunk: np.ndarray) -> float:
        """Speech probability (0-1) of one 512-sample float32 chunk."""
        chunk = np.asarray(chunk, dtype=np.float32).reshape(-1)
        x = np.concatenate([self._context, chunk])[None, :]
        out, self._h, self._c = self._session.run(None, {"input": x, "h": self._h, "c": self._c})
        self._context = chunk[-CONTEXT:]
        return float(np.ravel(out)[-1])
