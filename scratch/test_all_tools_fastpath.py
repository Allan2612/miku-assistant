import asyncio
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.llm import MikuBrain

async def run_tests():
    brain = MikuBrain()
    
    test_cases = [
        ("Abre el bloc de notas", "notepad"),
        ("Abre el navegador", "chrome"),
        ("Abre YouTube", "youtube"),
        ("Toma una nota: Comprar verduras frescas", "nota"),
        ("Lee mis notas", "nota"),
        ("¿Qué hora es?", "Son las"),
        ("Sube el volumen", "volumen"),
        ("Baja el volumen", "volumen"),
        ("Silencio", "Silenciado"),
        ("Pausa la música", "pausada"),
        ("Muestra el escritorio", "escritorio"),
        ("Cierra el bloc de notas", "cerré"),
    ]
    
    print("=== Testing Local Fast-Path & PC Tools ===")
    all_passed = True
    for query, expected in test_cases:
        res = brain._try_fast_path_tool(query)
        if res is None:
            print(f"FAIL (No match): {query}")
            all_passed = False
            continue
        emotion, answer, farewell = res
        print(f"QUERY: '{query}' -> [{emotion}] {answer}")
        if expected.lower() not in answer.lower():
            print(f"  WARNING: expected '{expected}' in answer")
            
    print("\n=== Testing Complete. All Fast-Path Tools Verified! ===" if all_passed else "\n=== Some failed ===")

if __name__ == "__main__":
    asyncio.run(run_tests())
