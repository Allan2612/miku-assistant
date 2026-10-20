import sys
import logging
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

logging.basicConfig(level=logging.INFO)

from core.config import load_config
from core.tools.web import _find_opera_gx, open_url
from core.tools.apps import open_app, _find_opera_gx_path
from core.wakeword import WakeWordListener

print("1. Testing Opera GX resolution...")
path_web = _find_opera_gx()
path_apps = _find_opera_gx_path()
print(f"  _find_opera_gx: {path_web}")
print(f"  _find_opera_gx_path: {path_apps}")
assert path_web is not None and Path(path_web).is_file(), "Opera GX not found"

print("\n2. Testing open_app('navegador') logic...")
res_nav = open_app("navegador")
print(f"  open_app('navegador') result: {res_nav}")
assert res_nav.get("ok") is True, f"Failed to open navegador: {res_nav}"

print("\n3. Testing open_app('opera gx') logic...")
res_opera = open_app("opera gx")
print(f"  open_app('opera gx') result: {res_opera}")
assert res_opera.get("ok") is True, f"Failed to open opera gx: {res_opera}"

print("\n4. Testing WakeWord config and initialization...")
cfg = load_config()
print(f"  Wakeword config: enabled={cfg.wakeword.enabled}, threshold={cfg.wakeword.threshold}, patience={cfg.wakeword.patience}, vad_threshold={cfg.wakeword.vad_threshold}")

async def dummy_cb():
    pass

ww = WakeWordListener(config=cfg.wakeword, on_wake=dummy_cb)
started = ww.start()
print(f"  WakeWordListener started: {started}")
assert started is True, "Failed to start WakeWordListener"

# Test stopping cleanly
ww.stop()
print("  WakeWordListener stopped cleanly.")

print("\nALL OPERA GX AND WAKEWORD VERIFICATIONS PASSED!")
