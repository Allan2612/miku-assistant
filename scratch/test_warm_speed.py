import asyncio
import json
import base64
import time
import soundfile as sf
import io
import websockets

async def test_warm_speed():
    uri = "ws://127.0.0.1:8765"
    async with websockets.connect(uri, max_size=20*1024*1024) as ws:
        await ws.send(json.dumps({"type": "ready"}))
        await asyncio.sleep(0.5)

        for phrase in ["Cuenta hasta 3", "¿Cuál es tu color favorito?"]:
            print(f"\n--- Turn: '{phrase}' ---")
            t_start = time.perf_counter()
            await ws.send(json.dumps({"type": "text_input", "text": phrase}))

            while True:
                msg = json.loads(await ws.recv())
                mtype = msg.get("type")
                if mtype == "subtitle" and msg.get("who") == "miku":
                    print(f"  Miku: {msg.get('text')}")
                elif mtype == "speak":
                    t_speak = time.perf_counter() - t_start
                    mime = msg.get("mime")
                    raw = base64.b64decode(msg.get("audio_b64"))
                    data, sr = sf.read(io.BytesIO(raw))
                    print(f"  => Time to speak: {t_speak:.2f}s | Audio: {len(data)/sr:.2f}s | Mime: {mime}")
                    await ws.send(json.dumps({"type": "speak_done"}))
                    break

if __name__ == "__main__":
    asyncio.run(test_warm_speed())
