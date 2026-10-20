import asyncio
import io
import time
import av
import edge_tts
import numpy as np
from faster_whisper import WhisperModel

async def synth():
    tts = edge_tts.Communicate("Hola Miku, abre el bloc de notas por favor.", "es-MX-DaliaNeural")
    data = bytearray()
    async for chunk in tts.stream():
        if chunk["type"] == "audio":
            data.extend(chunk["data"])
    container = av.open(io.BytesIO(bytes(data)))
    resampler = av.AudioResampler(format="fltp", layout="mono", rate=16000)
    chunks = []
    for f in container.decode(audio=0):
        for rf in resampler.resample(f):
            chunks.append(rf.to_ndarray())
    return np.concatenate(chunks, axis=1).squeeze(0)

async def main():
    audio = await synth()
    print("Audio length:", len(audio) / 16000, "seconds")
    
    # Test small
    print("Testing faster-whisper 'small' (6 threads)...")
    m_small = WhisperModel("small", device="cpu", compute_type="int8", cpu_threads=6)
    list(m_small.transcribe(audio, language="es", beam_size=1)[0])
    t0 = time.time()
    segs, info = m_small.transcribe(
        audio,
        language="es",
        beam_size=1,
        best_of=1,
        temperature=0.0,
        initial_prompt="Miku, Hey Miku, Oye Miku, abre el bloc de notas.",
        vad_filter=False,
        condition_on_previous_text=False,
    )
    text = " ".join(s.text.strip() for s in segs)
    print(f"Small: {time.time()-t0:.2f}s -> '{text}'")

    # Test base
    print("Testing faster-whisper 'base' (6 threads)...")
    m_base = WhisperModel("base", device="cpu", compute_type="int8", cpu_threads=6)
    list(m_base.transcribe(audio, language="es", beam_size=1)[0])
    t0 = time.time()
    segs, info = m_base.transcribe(
        audio,
        language="es",
        beam_size=1,
        best_of=1,
        temperature=0.0,
        initial_prompt="Miku, Hey Miku, Oye Miku, abre el bloc de notas.",
        vad_filter=False,
        condition_on_previous_text=False,
    )
    text = " ".join(s.text.strip() for s in segs)
    print(f"Base: {time.time()-t0:.2f}s -> '{text}'")

if __name__ == "__main__":
    asyncio.run(main())
