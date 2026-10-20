import asyncio
import sys
import time
sys.path.insert(0, ".")
from core.config import WakewordConfig
from core.wakeword import WakeWordListener

async def mock_on_wake():
    print("[MOCK CALLBACK] Wake word triggered successfully!")

async def test_wakeword():
    print("=== Test 1: Disabled Wakeword ===")
    cfg_disabled = WakewordConfig(enabled=False, model="models/wakeword/hey_miku.onnx", threshold=0.5)
    ww_disabled = WakeWordListener(cfg_disabled, mock_on_wake)
    ok = ww_disabled.start()
    print("Start result when disabled:", ok)
    print("Is listening:", ww_disabled.is_listening)
    assert not ww_disabled.is_listening, "Should not be listening when disabled"
    ww_disabled.stop()
    print("Test 1 Passed!\n")

    print("=== Test 2: Enabled Wakeword with Fallback Model ===")
    cfg_enabled = WakewordConfig(enabled=True, model="models/wakeword/hey_miku.onnx", threshold=0.5)
    ww_enabled = WakeWordListener(cfg_enabled, mock_on_wake)
    ok = ww_enabled.start()
    print("Start result when enabled:", ok)
    print("Is listening:", ww_enabled.is_listening)
    assert ww_enabled.is_listening, "Should be listening when enabled"

    print("Listening for 2 seconds (measuring CPU / stability)...")
    await asyncio.sleep(2.0)

    print("Testing pause()...")
    ww_enabled.pause()
    print("Is listening after pause:", ww_enabled.is_listening)
    assert not ww_enabled.is_listening, "Should not be listening after pause"
    await asyncio.sleep(1.0)

    print("Testing resume()...")
    ww_enabled.resume()
    print("Is listening after resume:", ww_enabled.is_listening)
    assert ww_enabled.is_listening, "Should be listening after resume"
    await asyncio.sleep(1.0)

    print("Testing clean stop()...")
    ww_enabled.stop()
    print("Is listening after stop:", ww_enabled.is_listening)
    assert not ww_enabled.is_listening, "Should be stopped"
    print("Test 2 Passed!\n")

if __name__ == "__main__":
    asyncio.run(test_wakeword())
