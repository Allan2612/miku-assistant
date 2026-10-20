import asyncio
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.llm import MikuBrain

async def test_brain():
    brain = MikuBrain()
    
    test_queries = [
        "Abre el bloc de notas",
        "Abre YouTube en el navegador",
        "Toma una nota que diga: reunión mañana a las 10",
        "¿Qué hora es?",
        "Pon el volumen al 40%"
    ]
    
    for q in test_queries:
        print(f"\n==========================================")
        print(f"USER: {q}")
        print(f"==========================================")
        emotion, answer, is_farewell = await brain.chat(q)
        print(f"MIKU [{emotion}]: {answer} (farewell={is_farewell})")

if __name__ == "__main__":
    asyncio.run(test_brain())
