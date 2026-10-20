import sys
import logging
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# Silence verbose loggers during test
logging.basicConfig(level=logging.ERROR)

from core.tools import _TOOL_REGISTRY

print(f"Testing all registered tools ({len(_TOOL_REGISTRY)} tools)...")

tests = [
    # System
    ("get_datetime", {}),
    ("get_system_status", {}),

    # Notes
    ("take_note", {"text": "Nota de prueba Miku"}),
    ("read_notes", {"last_n": 2}),
    ("open_notes", {}),

    # Timers
    ("list_timers", {}),
    ("cancel_timer", {"timer_id": 9999}),

    # Media
    ("change_volume", {"delta": 0}),
    ("set_volume", {"level": 50}),
    ("mute", {"action": "unmute"}),
    ("media_control", {"action": "play_pause"}),

    # Files
    ("find_file", {"name": "notes.md"}),
    ("open_folder", {"name": "documentos"}),

    # Apps queries & safe calls
    ("focus_app", {"app_name": "notepad"}),
    ("focus_app", {"name": "notepad"}),
    ("show_desktop", {}),

    # Web URL & Searches
    ("open_url", {"url": "https://example.com"}),
    ("web_search", {"query": "Hatsune Miku"}),
    ("youtube_search", {"query": "World is Mine"}),

    # App open/close
    ("open_app", {"name": "bloc de notas"}),
    ("close_app", {"name": "bloc de notas"}),
]

passed = 0
for name, kwargs in tests:
    if name not in _TOOL_REGISTRY:
        print(f"FAILED: {name} not found in registry")
        continue
    fn = _TOOL_REGISTRY[name]
    try:
        res = fn(**kwargs)
        if isinstance(res, dict) and "ok" in res:
            passed += 1
            print(f"[OK] {name}: ok={res['ok']} -> {str(res['result'])[:60]}")
        else:
            print(f"[WARN] {name}: unexpected return format: {res}")
    except Exception as e:
        print(f"[ERR] {name} crashed: {e}")

print(f"\nAll tests completed: {passed}/{len(tests)} succeeded.")
