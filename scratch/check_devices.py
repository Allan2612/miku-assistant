import sounddevice as sd
print("Default device:", sd.default.device)
for i, d in enumerate(sd.query_devices()):
    if d['max_input_channels'] > 0:
        print(f"{i}: {d['name']} (inputs: {d['max_input_channels']}, hostapi: {d['hostapi']}, sr: {d['default_samplerate']})")
