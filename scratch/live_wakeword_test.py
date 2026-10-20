import time
import numpy as np
import sounddevice as sd
from openwakeword.model import Model

model = Model(wakeword_models=["models/wakeword/hey_miku.onnx"], vad_threshold=0.5)

print("Starting live test for 6 seconds. Please speak or say 'Hey Miku'...")
def callback(indata, frames, time_info, status):
    audio_data = indata[:, 0]
    rms = float(np.sqrt(np.mean(audio_data.astype(np.float32) ** 2)))
    pred = model.predict(audio_data)
    score = pred.get("hey_miku", 0.0)
    if rms > 15.0 or score > 0.05:
        print(f"RMS: {rms:6.1f} | Score: {score:6.3f}")

with sd.InputStream(samplerate=16000, channels=1, dtype="int16", blocksize=1280, callback=callback):
    time.sleep(6)
print("Finished.")
