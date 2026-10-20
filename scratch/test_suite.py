"""
Miku Assistant - Comprehensive System & Diagnostic Test Suite
Tests configuration, wakeword listener, tools, audio structures, emotion parsing, and pipeline interfaces.
"""

import asyncio
from pathlib import Path
import sys
import time
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

def test_config():
    from core.config import load_config
    cfg = load_config("config.yaml")
    assert cfg.language == "es"
    assert cfg.wakeword.enabled is True
    assert "hey_miku.onnx" in cfg.wakeword.model
    assert cfg.rvc.enabled is True
    assert "miku_mellow.pth" in cfg.rvc.model
    print("PASS: test_config")

def test_tools():
    from core.tools import get_registered_tools
    tools = get_registered_tools()
    assert len(tools) == 26, f"Expected 26 tools, found {len(tools)}"
    names = {t.__name__ for t in tools}
    assert "open_app" in names
    assert "close_app" in names
    assert "open_notes" in names
    assert "shutdown_pc" in names
    assert "set_volume" in names
    assert "media_control" in names
    assert "find_file" in names
    assert "set_timer" in names
    assert "take_note" in names
    print("PASS: test_tools")

def test_llm_parsing():
    from core.llm import MikuBrain
    brain = MikuBrain()
    
    # Test emotion parsing
    e1, t1 = brain._parse_emotion("[happy] ¡Hola maestro! ¿Cómo estás?")
    assert e1 == "happy" and t1 == "¡Hola maestro! ¿Cómo estás?"
    
    e2, t2 = brain._parse_emotion("[surprised] ¡No me lo puedo creer!")
    assert e2 == "surprised" and t2 == "¡No me lo puedo creer!"
    
    e3, t3 = brain._parse_emotion("Sin emoción directa.")
    assert e3 == "happy" and t3 == "Sin emoción directa."
    
    # Test markdown sanitization
    sanitized = brain._sanitize_for_speech("Mira esto: **importante** y visita [Google](https://google.com) #titulo")
    assert "**" not in sanitized
    assert "https://" not in sanitized
    assert "#" not in sanitized
    assert "Google" in sanitized
    
    # Test farewell detection
    assert brain.is_farewell("adiós Miku") is True
    assert brain.is_farewell("hasta luego") is True
    assert brain.is_farewell("chao") is True
    assert brain.is_farewell("abre el bloc de notas") is False
    print("PASS: test_llm_parsing")

def test_wakeword_engine():
    from core.config import WakewordConfig
    from core.wakeword import WakeWordListener
    
    triggered = []
    async def fake_wake():
        triggered.append(time.time())

    cfg = WakewordConfig(enabled=True, model="models/wakeword/hey_miku.onnx", threshold=0.5)
    listener = WakeWordListener(config=cfg, on_wake=fake_wake)
    
    model_id, target_key = listener._resolve_model()
    assert "hey_miku.onnx" in model_id
    assert target_key == "hey_miku"
    
    # Test chunk shapes (1D and 2D arrays) without crashing
    chunk_2d = np.zeros((1280, 1), dtype=np.int16)
    chunk_1d = np.zeros(1280, dtype=np.int16)
    
    # Should handle both 1D and 2D cleanly
    listener._process_chunk(chunk_2d)
    listener._process_chunk(chunk_1d)
    
    # Test pause & resume state flags
    listener._running = True
    listener.pause()
    assert listener._paused is True
    listener.resume()
    assert listener._paused is False
    listener._running = False
    print("PASS: test_wakeword_engine")

def test_audio_vad_logic():
    from core.audio_in import AudioInput
    ai = AudioInput(sample_rate=16000, channels=1)
    assert ai.sample_rate == 16000
    assert ai.channels == 1
    print("PASS: test_audio_vad_logic")

if __name__ == "__main__":
    print("=== Running Miku Assistant Automated Test Suite ===")
    test_config()
    test_tools()
    test_llm_parsing()
    test_wakeword_engine()
    test_audio_vad_logic()
    print("=== ALL 5 TEST SUITES PASSED PERFECTLY ===")
