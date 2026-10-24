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
        self.configs = getattr(self, "configs", []) + [config]
        nxt = self.replies.pop(0)
        if isinstance(nxt, Exception):
            raise nxt
        return nxt


def brain(*replies):
    b = MikuBrain(model_name="m", models_fallback=["m"])
    models = FakeModels(replies)
    b.client = type("C", (), {"aio": type("A", (), {"models": models})()})()
    return b, models


AUDIO = np.zeros(16000, dtype=np.float32)


def test_actions_take_one_request():
    ran.clear()
    b, models = brain(reply("[happy] ¡Listo!",
                            ("open_app", {"app_name": "spotify"}), ("set_volume", {"level": 30})))
    emotion, text, _ = asyncio.run(b.chat("abre es poti y pon el volumen al 30", audio=AUDIO))
    assert len(models.requests) == 1
    assert models.requests[0][-1].parts[0].inline_data.mime_type == "audio/wav", "Gemini must hear the audio"
    assert ran == [("open_app", {"app_name": "spotify"}), ("set_volume", {"level": 30})], ran
    assert (emotion, text) == ("happy", "¡Listo!")


def test_data_tool_result_is_read_out():
    b, models = brain(reply("[happy] ¡Aquí tienes tus notas!", ("read_notes", {})))
    _, text, _ = asyncio.run(b.chat("lee lo que apunté"))
    assert len(models.requests) == 1 and text == "Tienes una nota: comprar leche.", text


def test_shutdown_asks_then_yes_runs_locally():
    ran.clear()
    b, models = brain(reply("[happy] ¡Apagando!", ("shutdown_pc", {"mode": "shutdown"})))
    _, question, _ = asyncio.run(b.chat("oye, ¿me apagas el ordenador porfa?", audio=AUDIO))
    assert "confirma" in question.lower() and not ran, (question, ran)
    _, text, _ = asyncio.run(b.chat("sí", audio=AUDIO))
    assert len(models.requests) == 1, "the user's 'sí' must not cost a request"
    assert ran and ran[0][1] == "/s" and "30 segundos" in text, (ran, text)


def test_claimed_action_without_tool_is_not_a_lie():
    b, models = brain(reply("[happy] ¡Anotado! Ya lo guardé en tus notas."))
    emotion, text, _ = asyncio.run(b.chat("guarda que me gusta el té", audio=AUDIO))
    assert len(models.requests) == 1 and emotion == "sad" and "no llegué a hacerlo" in text, text
    b, _ = brain(reply("[happy] ¡Hola! ¿Qué tal tu día?"))
    assert asyncio.run(b.chat("hola miku que tal"))[1] == "¡Hola! ¿Qué tal tu día?", "plain chat is untouched"


def test_claimed_action_is_done_locally_when_recognizable():
    # Live, log 05:13: Whisper heard "¡Suscríbete!", Gemini heard the audio and answered "¡Listo, volumen al
    # máximo!" without calling set_volume. The fast path knows that phrase: do it instead of apologizing
    import core.tools.media as media
    levels = []
    media.set_volume = lambda level: levels.append(level) or {"ok": True, "result": ""}
    b, models = brain(reply("[happy] ¡Listo, volumen al máximo!"))
    emotion, text, _ = asyncio.run(b.chat("¡Suscríbete!", audio=AUDIO))
    assert levels == [100] and emotion == "happy" and "100" in text, (levels, text)


def test_jot_down_goes_through_fast_path():
    import core.tools.notes as notes
    saved = []
    notes.take_note = lambda text: saved.append(text) or {"ok": True, "result": ""}
    b, models = brain()
    _, text, _ = asyncio.run(b.chat("¡Apunta que tengo pendiente subir el PR!", audio=AUDIO))
    assert saved == ["tengo pendiente subir el PR"] and not models.requests and "Apuntado" in text, saved


def test_screenshot_only_when_asked_and_in_the_same_request():
    import core.llm as llm
    shots = []
    llm.capture_screen_png = lambda: shots.append(1) or b"\x89PNG fake"
    b, models = brain(reply("[thinking] Veo un error de Python."), reply("[happy] ¡Hola!"))
    asyncio.run(b.chat("qué ves en mi pantalla", audio=AUDIO))
    parts = models.requests[0][-1].parts
    assert len(models.requests) == 1 and [p.inline_data.mime_type for p in parts] == ["audio/wav", "image/png"]
    asyncio.run(b.chat("cuéntame un chiste"))
    assert len(shots) == 1 and len(models.requests[1][-1].parts) == 1, "no screenshot unless asked"


def _builtins(config):
    return [n for t in config.tools for n in ("google_search", "url_context") if getattr(t, n, None)]


def test_web_tools_rejected_are_dropped_and_retried_once():
    # Seen live on the free tier: any request carrying google_search gets 429 RESOURCE_EXHAUSTED
    for error in ("429 RESOURCE_EXHAUSTED", "400 INVALID_ARGUMENT: tool combination not supported"):
        b, models = brain(RuntimeError(error), reply("[happy] ¡Hola!"))
        b.web_search = True
        assert _builtins(b._build_config()) == ["url_context", "google_search"]
        _, text, _ = asyncio.run(b.chat("hola miku que tal"))
        assert text == "¡Hola!" and not b.builtin_tools, (error, text)
        assert _builtins(models.configs[-1]) == [], "retry is without built-in tools"


def test_model_quota_does_not_disable_web_tools():
    # Fails with and without the built-in tools: the model's own quota, so keep them and fall back
    b, models = brain(RuntimeError("429 RESOURCE_EXHAUSTED"), RuntimeError("429 RESOURCE_EXHAUSTED"))
    b.all_models = ["m"]
    emotion, _, _ = asyncio.run(b.chat("hola miku que tal"))
    assert b.builtin_tools and len(models.requests) == 2, models.requests
    assert _builtins(b._build_config()) == ["url_context"], "google_search stays off unless configured"


def test_grounded_search_answer_is_not_called_a_lie():
    r = reply("[happy] Busqué y ganó T1 el mundial.")
    r.candidates[0].grounding_metadata = types.GroundingMetadata(web_search_queries=["ganador mundial lol"])
    b, _ = brain(r)
    assert asyncio.run(b.chat("quién ganó el mundial de lol"))[1] == "Busqué y ganó T1 el mundial."


def test_spoken_shutdown_asks_then_runs_with_no_request():
    ran.clear()
    b, models = brain()
    _, question, _ = asyncio.run(b.chat("¡Apaga la computadora!"))
    assert "confirma" in question.lower() and not ran, (question, ran)
    asyncio.run(b.chat("sí"))
    assert ran and ran[0][:2] == ["shutdown", "/s"] and not models.requests, (ran, models.requests)


def test_fallback_chain_tells_the_user_once():
    # Free tier: per-minute limits run out fast, so each failing model hands over to the next one
    b, models = brain(RuntimeError("429 RESOURCE_EXHAUSTED"), RuntimeError("503 UNAVAILABLE"), reply("[happy] ¡Aquí!"))
    b.all_models = ["m1", "m2", "m3", "m4"]
    cues = []

    async def cue():
        cues.append(1)

    b.on_model_switch = cue
    _, text, _ = asyncio.run(b.chat("cuéntame algo bonito", audio=AUDIO))
    assert text == "¡Aquí!" and len(models.requests) == 3 and cues == [1], (text, len(models.requests), cues)
    assert set(b._model_cooldown) == {"m1", "m2"}, "failed models wait before being tried again"

    # Healthy first model: no cue
    b, _ = brain(reply("[happy] ¡Hola!"))
    b.on_model_switch = cue
    cues.clear()
    asyncio.run(b.chat("cuéntame algo bonito"))
    assert cues == []


def test_requests_adapted_per_model():
    b, _ = brain()
    contents, config = b._build_request("abre spotify", AUDIO)
    # Gemma: no audio (gets Whisper's text), no thinking config, no built-in tools
    c, cfg = MikuBrain._for_model("gemma-4-26b-a4b-it", contents, config, "abre spotify")
    assert [p.text for p in c[-1].parts] == ["abre spotify"] and cfg.thinking_config is None
    assert not any(isinstance(t, types.Tool) for t in cfg.tools) and len(cfg.tools) == len(b.tools)
    # 3.8-flash rejects MINIMAL thinking
    _, cfg = MikuBrain._for_model("gemini-3.8-flash", contents, config, "abre spotify")
    assert cfg.thinking_config.thinking_level == "LOW" and cfg.max_output_tokens == 800
    # Everyone else: untouched (and the original config is not modified)
    assert MikuBrain._for_model("gemini-3.1-flash-lite", contents, config, "x") == (contents, config)
    assert config.thinking_config.thinking_level == "MINIMAL"


def test_fast_path_takes_no_request():
    b, models = brain()
    b._try_fast_path_tool = lambda text: ("happy", "Son las 12:00.", False)
    asyncio.run(b.chat("qué hora es", audio=AUDIO))
    assert not models.requests


if __name__ == "__main__":
    test_actions_take_one_request()
    test_data_tool_result_is_read_out()
    test_shutdown_asks_then_yes_runs_locally()
    test_claimed_action_without_tool_is_not_a_lie()
    test_claimed_action_is_done_locally_when_recognizable()
    test_jot_down_goes_through_fast_path()
    test_screenshot_only_when_asked_and_in_the_same_request()
    test_web_tools_rejected_are_dropped_and_retried_once()
    test_model_quota_does_not_disable_web_tools()
    test_grounded_search_answer_is_not_called_a_lie()
    test_spoken_shutdown_asks_then_runs_with_no_request()
    test_fallback_chain_tells_the_user_once()
    test_requests_adapted_per_model()
    test_fast_path_takes_no_request()
    print("ok")
