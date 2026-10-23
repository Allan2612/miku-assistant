"""At most ONE Gemini request per user turn: tools run locally and their results never go back to Gemini.

Fake client: no network, no quota. shutdown is faked: nothing is really shut down.
Run: core\\.venv\\Scripts\\python.exe -m tests.test_one_request  (or with pytest)
"""

import asyncio
import os

import numpy as np
from google.genai import types

os.environ.setdefault("GEMINI_API_KEY", "test")

import core.tools as tools
import core.tools.system as system
from core.llm import MikuBrain

ran = []
system.subprocess.run = lambda args, check: ran.append(args)


def fake_tool(name, result):
    def run(**kwargs):
        ran.append((name, kwargs))
        return {"ok": True, "result": result}
    tools._TOOL_METADATA[name]["function"] = run


fake_tool("open_app", "He abierto Spotify.")
fake_tool("set_volume", "Volumen al 30%.")
fake_tool("read_notes", "Tienes una nota: comprar leche.")


def reply(text, *calls):
    parts = ([types.Part(text=text)] if text else []) + [
        types.Part(function_call=types.FunctionCall(name=n, args=a)) for n, a in calls
    ]
    return types.GenerateContentResponse(candidates=[types.Candidate(content=types.Content(role="model", parts=parts))])


class FakeModels:
    def __init__(self, replies):
        self.replies, self.requests = list(replies), []

    async def generate_content(self, model, contents, config):
        assert config.automatic_function_calling.disable, "AFC would send tool results back: a 2nd request"
        self.requests.append(contents)
        return self.replies.pop(0)


def brain(*replies):
    b = MikuBrain(model_name="m", models_fallback=["m"])
    models = FakeModels(replies)
    b.client = type("C", (), {"aio": type("A", (), {"models": models})()})()
    return b, models


AUDIO = np.zeros(16000, dtype=np.float32)


def test_actions_take_one_request():
    ran.clear()
    b, models = brain(reply("{abre spotify y pon el volumen al 30} [happy] ¡Listo!",
                            ("open_app", {"app_name": "spotify"}), ("set_volume", {"level": 30})))
    emotion, text, _ = asyncio.run(b.chat("abre es poti y pon el volumen al 30", audio=AUDIO))
    assert len(models.requests) == 1
    assert models.requests[0][-1].parts[0].inline_data.mime_type == "audio/wav", "Gemini must hear the audio"
    assert ran == [("open_app", {"app_name": "spotify"}), ("set_volume", {"level": 30})], ran
    assert (emotion, text) == ("happy", "¡Listo!") and b.last_heard == "abre spotify y pon el volumen al 30"


def test_data_tool_result_is_read_out():
    b, models = brain(reply("[happy] ¡Aquí tienes tus notas!", ("read_notes", {})))
    _, text, _ = asyncio.run(b.chat("lee lo que apunté"))
    assert len(models.requests) == 1 and text == "Tienes una nota: comprar leche.", text


def test_shutdown_asks_then_yes_runs_locally():
    ran.clear()
    b, models = brain(reply("[happy] ¡Apagando!", ("shutdown_pc", {"mode": "shutdown"})))
    _, question, _ = asyncio.run(b.chat("apaga el ordenador", audio=AUDIO))
    assert "confirma" in question.lower() and not ran, (question, ran)
    _, text, _ = asyncio.run(b.chat("sí", audio=AUDIO))
    assert len(models.requests) == 1, "the user's 'sí' must not cost a request"
    assert ran and ran[0][1] == "/s" and "30 segundos" in text, (ran, text)


def test_fast_path_takes_no_request():
    b, models = brain()
    b._try_fast_path_tool = lambda text: ("happy", "Son las 12:00.", False)
    asyncio.run(b.chat("qué hora es", audio=AUDIO))
    assert not models.requests


if __name__ == "__main__":
    test_actions_take_one_request()
    test_data_tool_result_is_read_out()
    test_shutdown_asks_then_yes_runs_locally()
    test_fast_path_takes_no_request()
    print("ok")
