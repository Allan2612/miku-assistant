import os
import sys
from pathlib import Path
from google import genai
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")
client = genai.Client(api_key=os.environ.get("GEMINI_API_KEY"))

models = ["gemini-3.8-flash", "gemini-3.5-flash-lite", "gemini-3.1-flash-lite", "gemini-flash-latest"]

for m in models:
    try:
        resp = client.models.generate_content(model=m, contents="Hola, responde 'OK'")
        print(f"{m}: SUCCESS -> {resp.text.strip()}")
    except Exception as e:
        print(f"{m}: ERROR -> {e}")
sys.stdout.flush()
