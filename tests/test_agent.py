"""The brain as an agent: tool calls run locally, their results go back to Gemini, and it answers from them.

One request for plain chat; tools add a follow-up per round (at most MAX_TOOL_ROUNDS). A claimed action without a
tool call gets one nudge. Local paths (fast path, the "sí" to a shutdown, goodbyes) cost no request.
Fake client: no network, no quota. shutdown is faked: nothing is really shut down.
Run: core\\.venv\\Scripts\\python.exe -m tests.test_agent  (or with pytest)
"""

import asyncio
import os
import time

import numpy as np
from google.genai import types

os.environ.setdefault("GEMINI_API_KEY", "test")

import core.tools as tools
import core.llm as llm
import core.tools.system as system
from core.llm import MAX_TOOL_ROUNDS, MikuBrain

ran = []
system.subprocess.run = lambda args, check: ran.append(args)


def fake_tool(name, result, ok=True):
    def run(*args, **kwargs):
        ran.append((name, kwargs or args))
        return {"ok": ok, "result": result}
    tools._TOOL_METADATA[name]["function"] = run


fake_tool("open_app", "He abierto Spotify.")
fake_tool("set_volume", "Volumen ajustado al 30%.")
fake_tool("read_notes", "Tu última nota: comprar leche.")
fake_tool("take_note", "Nota guardada.")


def reply(text, *calls):
    parts = ([types.Part(text=text)] if text else []) + [
        types.Part(function_call=types.FunctionCall(id=f"c{i}", name=n, args=a)) for i, (n, a) in enumerate(calls)
    ]
    return types.GenerateContentResponse(candidates=[types.Candidate(content=types.Content(role="model", parts=parts))])


class FakeModels:
    def __init__(self, replies):
        self.replies, self.requests, self.configs, self.models = list(replies), [], [], []

    async def generate_content(self, model, contents, config):
        assert config.automatic_function_calling.disable, "the agent loop is ours: the SDK must not run tools"
        self.models.append(model)
        self.requests.append(list(contents))
        self.configs.append(config)
        nxt = self.replies.pop(0)
        if isinstance(nxt, Exception):
            raise nxt
        return nxt


def brain(*replies):
    b = MikuBrain(model_name="m", models_fallback=["m"])
    llm.describe_pc = lambda: ""  # the real PC state is not part of these tests
    models = FakeModels(replies)
    b.client = type("C", (), {"aio": type("A", (), {"models": models})()})()
    return b, models


def responses_sent(request):
    """The function_response parts of the last user content of a request."""
    return [p.function_response for p in request[-1].parts if p.function_response]


AUDIO = np.zeros(16000, dtype=np.float32)


def test_timeout_is_one_the_api_accepts():
    # 3-nov: 8 s made every request fail with 400 "Minimum allowed deadline is 10s"
    assert llm.GEMINI_TIMEOUT_MS >= 10_000


def test_action_results_go_back_and_the_answer_comes_from_them():
    ran.clear()
    b, models = brain(reply("", ("open_app", {"app_name": "spotify"}), ("set_volume", {"level": 30})),
                      reply("[happy] ¡Listo! Spotify abierto y volumen al 30."))
    emotion, text, _ = asyncio.run(b.chat("abre es poti y pon el volumen al 30", audio=AUDIO))
    assert models.requests[0][-1].parts[0].inline_data.mime_type == "audio/wav", "Gemini must hear the audio"
    # ...with Whisper's text beside it: audio alone, flash-lite replayed the previous order (log 27-oct)
    assert "abre es poti" in models.requests[0][-1].parts[1].text
    assert ran == [("open_app", {"app_name": "spotify"}), ("set_volume", {"level": 30})], ran
    sent = responses_sent(models.requests[1])
    assert [(r.id, r.name, r.response["result"]) for r in sent] == [
        ("c0", "open_app", "He abierto Spotify."), ("c1", "set_volume", "Volumen ajustado al 30%.")]
    # Its own function-call content goes back too (Gemini 3 needs the thought signatures in it)
    assert models.requests[1][-2].role == "model" and models.requests[1][-2].parts[0].function_call.name == "open_app"
    assert (emotion, text) == ("happy", "¡Listo! Spotify abierto y volumen al 30.") and len(models.requests) == 2
    assert b.last_outcome == "ok", "her body language: a happy bounce"


def test_failed_tool_is_seen_by_the_model():
    fake_tool("close_app", "No encontré Discord abierto.", ok=False)
    b, models = brain(reply("", ("close_app", {"name": "discord"})), reply("[sad] Discord no estaba abierto."))
    _, text, _ = asyncio.run(b.chat("cierra discord porfa amiga"))
    assert responses_sent(models.requests[1])[0].response["ok"] is False and text == "Discord no estaba abierto."
    assert b.last_outcome == "fail", "her body language: a shrug"
    # The new emotions are kept, not turned into "happy"
    assert b._parse_emotion("[shy] Ay, gracias.") == ("shy", "Ay, gracias.")
    # Tags mid-answer are never read out (log 27-oct: "un [yatta] café"); the goodbye tag survives for chat()
    assert b._parse_emotion("[happy] ¿Qué necesitas, un [yatta] café?") == ("happy", "¿Qué necesitas, un café?")
    assert b._parse_emotion("[happy] ¡Nos vemos! [adios]")[1].endswith("[adios]")


def test_multi_step_task_and_the_round_limit():
    b, models = brain(reply("", ("read_notes", {})), reply("", ("take_note", {"text": "x"})), reply("[happy] Hecho."))
    assert asyncio.run(b.chat("revisa mis notas y apunta lo que falte"))[1] == "Hecho." and len(models.requests) == 3
    # A model that keeps calling tools stops after MAX_TOOL_ROUNDS follow-ups; the last results are read out
    loops = [reply("", ("read_notes", {}))] * (MAX_TOOL_ROUNDS + 1)
    b, models = brain(*loops)
    _, text, _ = asyncio.run(b.chat("haz algo raro con mis notas una y otra vez"))
    assert len(models.requests) == MAX_TOOL_ROUNDS + 1 and text == "Tu última nota: comprar leche.", text


def test_follow_up_failure_reads_the_results():
    b, _ = brain(reply("", ("set_volume", {"level": 30})), RuntimeError("429 RESOURCE_EXHAUSTED"))
    emotion, text, _ = asyncio.run(b.chat("pon el sonido como a treinta porfa"))
    assert (emotion, text) == ("happy", "Volumen ajustado al 30%."), "the action is done: say what happened"


def test_claimed_action_without_tool_gets_one_nudge():
    ran.clear()
    b, models = brain(reply("[happy] ¡Anotado! Ya lo guardé en tus notas."),
                      reply("", ("take_note", {"text": "me gusta el té"})), reply("[happy] Ahora sí, guardado."))
    _, text, _ = asyncio.run(b.chat("guarda que me gusta el té", audio=AUDIO))
    assert "no llamaste ninguna herramienta" in models.requests[1][-1].parts[0].text
    assert ran == [("take_note", {"text": "me gusta el té"})] and text == "Ahora sí, guardado.", (ran, text)
    # Only one nudge: a model that insists is answered as it is
    b, models = brain(reply("[happy] ¡Anotado!"), reply("[happy] ¡Anotado, de verdad!"))
    assert asyncio.run(b.chat("guarda lo del té por favor"))[1] == "¡Anotado, de verdad!" and len(models.requests) == 2


def test_no_nudge_for_plain_chat_or_about_the_last_action():
    b, models = brain(reply("[happy] ¡Hola! ¿Qué tal tu día?"))
    assert asyncio.run(b.chat("hola miku que tal"))[1] == "¡Hola! ¿Qué tal tu día?" and len(models.requests) == 1
    # Log 06:16: "¿Estás segura que la guardaste?" right after saving it: "lo apunté" is true
    b, models = brain(reply("", ("take_note", {"text": "abrir un PR"})), reply("[happy] ¡Anotado!"),
                      reply("[happy] ¡Claro que sí! Lo apunté en tus notas."))
    asyncio.run(b.chat("oye amiga guarda en mis notas lo del PR de mañana"))
    _, text, _ = asyncio.run(b.chat("¿Estás segura que la guardaste?"))
    assert text == "¡Claro que sí! Lo apunté en tus notas." and len(models.requests) == 3


def test_grounded_search_answer_is_not_nudged():
    r = reply("[happy] Busqué y ganó T1 el mundial.")
    r.candidates[0].grounding_metadata = types.GroundingMetadata(web_search_queries=["ganador mundial lol"])
    b, models = brain(r)
    assert asyncio.run(b.chat("quién ganó el mundial de lol"))[1] == "Busqué y ganó T1 el mundial."
    assert len(models.requests) == 1


def test_shutdown_question_comes_from_the_model_and_the_yes_is_local():
    ran.clear()
    b, models = brain(reply("", ("shutdown_pc", {"mode": "shutdown"})), reply("[neutral] ¿Seguro que la apago?"))
    _, question, _ = asyncio.run(b.chat("oye, ¿me apagas el ordenador porfa?", audio=AUDIO))
    assert responses_sent(models.requests[1])[0].response.get("requires_confirmation") and not ran
    assert question == "¿Seguro que la apago?"
    _, text, _ = asyncio.run(b.chat("sí", audio=AUDIO))
    assert len(models.requests) == 2, "the user's 'sí' must not cost a request"
    assert ran and ran[0][1] == "/s" and "30 segundos" in text, (ran, text)


def test_spoken_shutdown_asks_then_runs_with_no_request():
    ran.clear()
    b, models = brain()
    _, question, _ = asyncio.run(b.chat("¡Apaga la computadora!"))
    assert "confirma" in question.lower() and not ran, (question, ran)
    asyncio.run(b.chat("sí"))
    assert ran and ran[0][:2] == ["shutdown", "/s"] and not models.requests, (ran, models.requests)


def test_gemini_can_mark_a_goodbye_the_lists_missed():
    # A goodbye in words no list catches: Gemini ends with [adios], she says the rest and hides
    b, _ = brain(reply("[happy] ¡De nada! Aquí estaré. [adios]"), reply("[adios] ¡Nos vemos!"), reply("[happy] Claro."))
    assert asyncio.run(b.chat("me retiro por hoy, mil gracias por todo lo de hoy")) == ("happy", "¡De nada! Aquí estaré.", True)
    assert asyncio.run(b.chat("bueno, me voy a dormir que mañana madrugo")) == ("happy", "¡Nos vemos!", True)
    assert asyncio.run(b.chat("cuéntame un chiste corto")) == ("happy", "Claro.", False)
    assert "[adios]" not in str(b._history_turns), "the tag never reaches the voice or the history"


def test_goodbye_answer_fits_what_was_said():
    from core.llm import GOODBYE_ANSWERS, THANKS_ANSWERS
    b, _ = brain()
    for _ in range(5):
        assert asyncio.run(b.chat("Adiós."))[1] in GOODBYE_ANSWERS
        b._last_query_text = ""
        assert asyncio.run(b.chat("Gracias."))[1] in THANKS_ANSWERS
        b._last_query_text = ""


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
    assert len(models.requests) == 1 and [p.inline_data.mime_type for p in parts if p.inline_data] == ["audio/wav", "image/png"]
    asyncio.run(b.chat("cuéntame un chiste"))
    assert len(shots) == 1 and not any(p.inline_data for p in models.requests[1][-1].parts), "no screenshot unless asked"


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
    asyncio.run(b.chat("hola miku que tal"))
    assert b.builtin_tools and len(models.requests) == 2, models.requests
    assert _builtins(b._build_config()) == ["url_context"], "google_search stays off unless configured"


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


def test_back_to_the_primary_after_a_failure():
    # One 504 on the primary: this turn goes to the fallback, the next one (cooldown over) to the primary again
    # (log 2-nov: 12 turns stuck on the fallback)
    b, models = brain(RuntimeError("504 DEADLINE_EXCEEDED"), reply("[happy] ¡Uno!"), reply("[happy] ¡Dos!"))
    b.all_models = ["m1", "m2"]
    asyncio.run(b.chat("cuéntame algo bonito", audio=AUDIO))
    b._model_cooldown.clear()
    asyncio.run(b.chat("y otra cosa distinta", audio=AUDIO))
    assert models.models == ["m1", "m2", "m1"], models.models

    # Failing turn after turn (log 3-nov: 504 on every request): the cooldown grows, so the turns stop
    # losing 10 s on it; one answer resets it
    b, models = brain(*[RuntimeError("504 DEADLINE_EXCEEDED"), reply("[happy] ¡Ok!")] * 3, reply("[happy] ¡Ok!"))
    b.all_models = ["m1", "m2"]
    waits = []
    for i in range(3):
        b._model_cooldown.pop("m1", None)  # cooldown over: m1 is tried again
        asyncio.run(b.chat(f"pregunta {i}", audio=AUDIO))
        waits.append(round(b._model_cooldown["m1"] - llm.time.monotonic()))
    assert waits[0] <= 15 and 110 < waits[1] <= 120 and 590 < waits[2] <= 600, waits
    b._model_cooldown.clear()
    b.all_models = ["m1"]
    asyncio.run(b.chat("otra", audio=AUDIO))
    assert "m1" not in b._fail_streak, "an answer resets the streak"

    # A failed Gemma first must not leave the next model with Whisper's text instead of the audio
    b, models = brain(RuntimeError("503 UNAVAILABLE"), reply("[happy] ¡Hola!"))
    b.all_models = ["gemma-4-26b-a4b-it", "m2"]
    asyncio.run(b.chat("cuéntame algo bonito", audio=AUDIO))
    assert any(p.inline_data for p in models.requests[1][-1].parts), "the audio reaches the next model"


def test_small_talk_is_marked_so_the_last_order_is_not_replayed():
    # Log 3-nov: "¿Cómo estás, oye?" after some clips saved another clip (4 of 6 live retries without the mark, 0 of 6
    # with it). Orders the local rules miss ("Déjalo al 20") get no mark: Gemini still runs them
    b, _ = brain()
    marked = lambda text: any(p.text == llm.CHAT_HINT for p in b._build_request(text, AUDIO)[0][-1].parts)
    assert marked("¿Cómo estás, oye?") and marked("Gracias mi amor, te amo.")
    assert not marked("Déjalo al 20.") and not marked("Mueve Opera a la pantalla de la derecha.") and not marked("Sí.")


def test_requests_adapted_per_model():
    b, _ = brain()
    contents, config = b._build_request("abre spotify", AUDIO)
    # Gemma: no audio (gets Whisper's text), no thinking config, no built-in tools
    c, cfg = MikuBrain._for_model("gemma-4-26b-a4b-it", contents, config, "abre spotify")
    assert [p.text for p in c[-1].parts if p.text][-1] == "abre spotify" and cfg.thinking_config is None
    assert not any(p.inline_data for p in c[-1].parts)
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


def test_pc_state_rides_in_the_request_but_not_in_the_history():
    b, models = brain(reply("[happy] Tienes Spotify abierto."), reply("[happy] Vale."))
    llm.describe_pc = lambda: "[Estado del PC] Apps abiertas: Spotify."
    asyncio.run(b.chat("qué tengo abierto"))
    assert [p.text for p in models.requests[0][-1].parts] == ["qué tengo abierto", "[Estado del PC] Apps abiertas: Spotify."]
    llm.describe_pc = lambda: "[Estado del PC] Apps abiertas: ninguna."
    asyncio.run(b.chat("gracias por decirme, ahora cuéntame algo"))
    history_texts = [p.text for c in models.requests[1][:-1] for p in c.parts]
    assert not any("Estado del PC" in t for t in history_texts), "an old snapshot must not stay in the history"
    assert "ninguna" in models.requests[1][-1].parts[1].text


def test_history_survives_a_restart_and_keeps_reminders():
    import tempfile
    from pathlib import Path
    import core.tools.memory as memory
    path = Path(tempfile.mkdtemp()) / "history.json"
    memory.CONVERSATIONS_DIR = path.parent / "conversations"  # never the real cache/conversations
    b = MikuBrain(model_name="m", models_fallback=["m"], history_file=path)
    b._remember("me llamo Alan", "[happy] ¡Hola, Alan!")
    # A reminder she said is in the history: "recuérdamelo en 10 minutos" needs to know what "lo" is
    b.note_announcement("¡Oye, recuerda: tomar agua!")

    again = MikuBrain(model_name="m", models_fallback=["m"], history_file=path)
    texts = [t["text"] for t in again._history_turns]
    assert "me llamo Alan" in texts and "[happy] ¡Oye, recuerda: tomar agua!" in texts, texts

    # One from another day comes back too, marked as a past conversation
    old = time.time() - llm.HISTORY_MAX_AGE_S - 60
    os.utime(path, (old, old))
    turns = MikuBrain(model_name="m", models_fallback=["m"], history_file=path)._history_turns
    assert turns[0]["text"] == "me llamo Alan" and "conversación del" in turns[-2]["text"], turns
    assert [t["role"] for t in turns] == ["user", "model"] * (len(turns) // 2), "roles must alternate"

    # Every exchange is archived by day, emotion tag dropped; recall finds it by words or by day
    day = memory.recall_conversation(text="Alan")["result"]
    assert "me llamo Alan" in day and "¡Hola, Alan!" in day and "[happy]" not in day, day
    assert "No encontré" in memory.recall_conversation(text="banco")["result"]
    assert "No encontré" in memory.recall_conversation(date="2020-01-01")["result"]
    # Tests and other callers without a file keep it in memory only
    assert MikuBrain(model_name="m", models_fallback=["m"])._history_turns == []


if __name__ == "__main__":
    test_small_talk_is_marked_so_the_last_order_is_not_replayed()
    test_back_to_the_primary_after_a_failure()
    test_action_results_go_back_and_the_answer_comes_from_them()
    test_failed_tool_is_seen_by_the_model()
    test_multi_step_task_and_the_round_limit()
    test_follow_up_failure_reads_the_results()
    test_claimed_action_without_tool_gets_one_nudge()
    test_no_nudge_for_plain_chat_or_about_the_last_action()
    test_grounded_search_answer_is_not_nudged()
    test_shutdown_question_comes_from_the_model_and_the_yes_is_local()
    test_spoken_shutdown_asks_then_runs_with_no_request()
    test_goodbye_answer_fits_what_was_said()
    test_gemini_can_mark_a_goodbye_the_lists_missed()
    test_jot_down_goes_through_fast_path()
    test_screenshot_only_when_asked_and_in_the_same_request()
    test_web_tools_rejected_are_dropped_and_retried_once()
    test_model_quota_does_not_disable_web_tools()
    test_fallback_chain_tells_the_user_once()
    test_requests_adapted_per_model()
    test_fast_path_takes_no_request()
    test_pc_state_rides_in_the_request_but_not_in_the_history()
    test_history_survives_a_restart_and_keeps_reminders()
    test_timeout_is_one_the_api_accepts()
    print("ok")
