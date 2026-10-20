import soundfile as sf
import numpy as np
import librosa
from faster_whisper import WhisperModel

model = WhisperModel('small', device='cpu', compute_type='int8')

files = [
    'scratch/latest_test_response.wav',
]

for fn in files:
    data, sr = sf.read(fn)
    if sr != 16000:
        data = librosa.resample(data, orig_sr=sr, target_sr=16000)
    data = data.astype(np.float32)
    segments, info = model.transcribe(data, language='es')
    res = " ".join(s.text for s in segments)
    print(fn, f"[prob={info.language_probability:.2f}]:", res.strip())
