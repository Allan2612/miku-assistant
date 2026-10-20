import asyncio
import edge_tts

async def list_voices():
    voices = await edge_tts.list_voices()
    for v in voices:
        if v['Locale'].startswith('es-') and v['Gender'] == 'Female':
            print(f"{v['ShortName']:28} {v['Locale']}")

if __name__ == "__main__":
    asyncio.run(list_voices())
