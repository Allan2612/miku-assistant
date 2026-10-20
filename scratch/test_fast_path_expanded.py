import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.llm import MikuBrain

brain = MikuBrain(model_name="gemini-3.5-flash-lite", models_fallback=["gemini-flash-lite-latest"])

test_queries = [
    "abre el navegador",
    "abre el bloc de notas",
    "notas",
    "youtube",
    "qué hora",
    "toma una nota: comprar leche",
    "sube el volumen",
    "silencio",
    "muestra el escritorio"
]

all_ok = True
for q in test_queries:
    res = brain._try_fast_path_tool(q)
    print(f"Query '{q}' -> {res}")
    if res is None:
        all_ok = False
        print(f"FAILED on query: {q}")

if all_ok:
    print("\nALL FAST-PATH QUERIES PASSED!")
