import asyncio
import json
import base64
import soundfile as sf
import io
import websockets

async def test_e2e():
    uri = "ws://127.0.0.1:8765"
    print(f"Connecting to {uri}...")
    async with websockets.connect(uri, max_size=20*1024*1024) as ws:
        await ws.send(json.dumps({"type": "ready"}))
        print("Sent ready.")

        # Send text prompt
        prompt = "Hola Miku, dime qué día es hoy en una frase corta."
        print(f"Sending prompt: {prompt}")
        await ws.send(json.dumps({"type": "text_input", "text": prompt}))

        speak_received = False
        while not speak_received:
            msg_str = await ws.recv()
            msg = json.loads(msg_str)
            mtype = msg.get("type")
            print(f"Received msg type: {mtype}")
            if mtype == "subtitle":
                print(f"  Subtitle [{msg.get('who')}]: {msg.get('text')}")
            elif mtype == "expression":
                print(f"  Expression: {msg.get('name')}")
            elif mtype == "state":
                print(f"  State: {msg.get('value')}")
            elif mtype == "speak":
                speak_received = True
                audio_b64 = msg.get("audio_b64", "")
                mime = msg.get("mime", "")
                print(f"  SPEAK! mime: {mime}, audio_b64 len: {len(audio_b64)}")
                raw_audio = base64.b64decode(audio_b64)
                data, sr = sf.read(io.BytesIO(raw_audio))
                dur = len(data) / sr
                print(f"  Audio decoded: {len(data)} samples, {sr} Hz, {dur:.2f}s, max_amp: {abs(data).max():.4f}")
                sf.write("scratch/received_miku.wav", data, sr)
                print("  Saved to scratch/received_miku.wav!")

                # Report speak_done
                await ws.send(json.dumps({"type": "speak_done"}))
                print("Sent speak_done.")

        print("End-to-end RVC test successful!")

if __name__ == "__main__":
    asyncio.run(test_e2e())
