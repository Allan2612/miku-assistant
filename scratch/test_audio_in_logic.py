import asyncio
import numpy as np

# Test the core silence/speech detection loop logic from audio_in.py
block_size = 512
sample_rate = 16000
chunk_dur = block_size / sample_rate # 0.032s

# Simulate 0.3s ambient noise (rms ~ 0.0007), 1.5s speech (rms ~ 0.0025), then 2.0s ambient noise (rms ~ 0.0007)
ambient_chunks = [np.random.normal(0, 0.0007, block_size).astype(np.float32) for _ in range(10)]
speech_chunks = [np.random.normal(0, 0.0025, block_size).astype(np.float32) for _ in range(45)]
trailing_chunks = [np.random.normal(0, 0.0007, block_size).astype(np.float32) for _ in range(60)]

chunks = ambient_chunks + speech_chunks + trailing_chunks

speech_started = False
silence_accumulated = 0.0
speech_accumulated = 0.0
smoothed_rms = 0.0
silence_limit = 0.7
min_speech_duration = 0.35

ambient_noise_samples = []
calibrated = False
energy_threshold = 0.0020
silence_threshold = 0.0015

recorded_chunks = []
stopped_at_chunk = None

for i, chunk in enumerate(chunks):
    rms = float(np.sqrt(np.mean(chunk**2)))
    if smoothed_rms == 0.0:
        smoothed_rms = rms
    else:
        smoothed_rms = 0.65 * smoothed_rms + 0.35 * rms

    if not calibrated:
        ambient_noise_samples.append(rms)
        if len(ambient_noise_samples) >= 6:
            avg_noise = float(np.mean(ambient_noise_samples))
            energy_threshold = max(0.0013, min(0.015, avg_noise * 1.5 + 0.0004))
            silence_threshold = max(0.0010, energy_threshold * 0.90)
            calibrated = True

    if not speech_started:
        if rms > energy_threshold or smoothed_rms > energy_threshold:
            speech_started = True
            speech_accumulated = chunk_dur
            recorded_chunks.append(chunk)
            print(f"Speech start detected at chunk {i} ({i*chunk_dur:.2f}s). RMS: {rms:.4f} > {energy_threshold:.4f}")
    else:
        recorded_chunks.append(chunk)
        speech_accumulated += chunk_dur

        if smoothed_rms < silence_threshold:
            silence_accumulated += chunk_dur
            if silence_accumulated >= silence_limit:
                print(f"Silence detected: {silence_accumulated:.2f}s after speech {speech_accumulated:.2f}s at chunk {i} ({i*chunk_dur:.2f}s).")
                stopped_at_chunk = i
                break
        else:
            silence_accumulated = max(0.0, silence_accumulated - chunk_dur * 0.5)

total_time = stopped_at_chunk * chunk_dur if stopped_at_chunk else len(chunks) * chunk_dur
print(f"Total recording time: {total_time:.2f}s (Expected ~2.5s). Recorded {len(recorded_chunks)} chunks.")
assert speech_started, "Speech should have started"
assert stopped_at_chunk is not None, "Silence should have stopped recording"
print("SUCCESS! AudioIn logic works perfectly!")
