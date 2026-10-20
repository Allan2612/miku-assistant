import asyncio
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.llm import MikuBrain

async def test_all():
    brain = MikuBrain()
    
    queries = [
        "Abre el navegador",
        "Abre el bloc de notas",
        "Abre las notas",
        "Abre Google",
        "Abre YouTube",
        "Busca en Google noticias de hoy",
        "Busca en YouTube música de Miku",
        "Sube el volumen",
        "Baja el volumen",
        "Mutea el volumen",
        "Pausa la música",
        "Reanuda la música",
        "Muestra el escritorio",
        "¿Qué hora es?",
        "¿Cómo está la computadora?",
        "Cierra el bloc de notas",
        "Guarda una nota que diga comprar puerros",
        "Lee mis notas",
        "Pon un temporizador de 10 segundos",
        "Lista los temporizadores",
        "Bloquea la PC"
    ]
    
    for q in queries:
        print(f"\n>>> USER QUERY: {q}")
        emotion, answer, is_farewell = await brain.chat(q)
        print(f"MIKU RESPONSE [{emotion}]: {answer}")

if __name__ == "__main__":
    asyncio.run(test_all())
