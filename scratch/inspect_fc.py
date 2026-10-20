import asyncio
import os
import sys
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv
from google import genai
from google.genai import types
from core.tools import get_registered_tools

load_dotenv()

SYSTEM_PROMPT = """Eres Miku, una asistente de escritorio.
REGLA FUNDAMENTAL: Tienes herramientas para controlar el PC.
Cuando el usuario te pida una acción (abrir/cerrar apps, subir/bajar volumen, reproducir música, buscar en web, hora, estado, notas, etc.), ES OBLIGATORIO LLAMAR A LA HERRAMIENTA.
NUNCA inventes ni finjas que hiciste una acción en texto sin haber llamado primero a la herramienta.
Cuando la herramienta termine, responde brevemente empezando con [happy] confirmando el resultado.
"""

async def test_prompt():
    api_key = os.getenv("GEMINI_API_KEY")
    client = genai.Client(api_key=api_key)
    tools = get_registered_tools()
    
    config = types.GenerateContentConfig(
        system_instruction=SYSTEM_PROMPT,
        tools=tools,
        temperature=0.3,
    )
    
    chat = client.aio.chats.create(
        model="gemini-3.5-flash-lite",
        config=config,
    )
    
    test_queries = [
        "Abre el bloc de notas",
        "Pon el volumen al 30",
        "Pausa la música",
    ]
    
    for q in test_queries:
        print(f"\n==========================================")
        print(f"QUERY: '{q}'")
        res = await chat.send_message(q)
        print("Miku Text:", res.text)

if __name__ == "__main__":
    asyncio.run(test_prompt())
