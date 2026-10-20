import asyncio
import os
from dotenv import load_dotenv
from google import genai
from google.genai import types
from core.tools import get_registered_tools

load_dotenv()

async def test_tracing():
    api_key = os.getenv("GEMINI_API_KEY")
    client = genai.Client(api_key=api_key)
    
    # Wrap all tools with detailed print tracing
    raw_tools = get_registered_tools()
    traced_tools = []
    for t in raw_tools:
        def make_tracer(fn):
            def traced(*args, **kwargs):
                print(f"\n==========================================")
                print(f"*** TOOL EXECUTED: {fn.__name__} ***")
                print(f"   args: {args}")
                print(f"   kwargs: {kwargs}")
                res = fn(*args, **kwargs)
                print(f"   RETURN VALUE: {res}")
                print(f"==========================================\n")
                return res
            traced.__name__ = fn.__name__
            traced.__doc__ = fn.__doc__
            return traced
        traced_tools.append(make_tracer(t))
        
    config = types.GenerateContentConfig(
        system_instruction="Eres Miku. Tienes herramientas disponibles para controlar el PC. Úsalas siempre que el usuario te pida una acción. Si una herramienta falla, di la verdad al usuario.",
        tools=traced_tools,
        temperature=0.3,
    )
    
    chat = client.aio.chats.create(
        model="gemini-3.5-flash-lite",
        config=config,
    )
    
    for prompt in ["Abre el bloc de notas", "Pon el volumen al 30", "Pausa la música"]:
        print(f"\n--- USER PROMPT: '{prompt}' ---")
        res = await chat.send_message(prompt)
        print("FINAL MODEL RESPONSE:", res.text)

if __name__ == "__main__":
    asyncio.run(test_tracing())
