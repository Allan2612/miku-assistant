import asyncio
import os
import logging
from dotenv import load_dotenv
from google import genai
from google.genai import types
from core.tools import get_registered_tools

load_dotenv()
logging.basicConfig(level=logging.DEBUG)

async def debug_call():
    api_key = os.getenv("GEMINI_API_KEY")
    client = genai.Client(api_key=api_key)
    tools = get_registered_tools()
    
    config = types.GenerateContentConfig(
        system_instruction="Eres Miku. Tienes herramientas disponibles para controlar el PC. Úsalas siempre que el usuario te pida una acción.",
        tools=tools,
        temperature=0.7,
    )
    
    chat = client.aio.chats.create(
        model="gemini-3.5-flash-lite",
        config=config,
    )
    
    print("\n--- TEST: 'Vaya Miku, pon el volumen al 30.' ---")
    res = await chat.send_message("Vaya Miku, pon el volumen al 30.")
    print("RES TEXT:", res.text)
    print("FUNCTION CALLS IN RES:", res.function_calls)
    
    print("\n--- TEST: 'Abre el bloc de notas' ---")
    res2 = await chat.send_message("Abre el bloc de notas")
    print("RES TEXT 2:", res2.text)
    print("FUNCTION CALLS IN RES 2:", res2.function_calls)

if __name__ == "__main__":
    asyncio.run(debug_call())
