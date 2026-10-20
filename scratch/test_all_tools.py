import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.tools import get_registered_tools

def test_direct_tools():
    print("=== Testing Direct Tool Execution ===")
    from core.tools.apps import open_app, close_app, show_desktop
    from core.tools.media import set_volume, change_volume, mute, media_control
    from core.tools.web import open_url, web_search, youtube_search
    from core.tools.system import get_datetime, get_system_status, lock_pc
    from core.tools.files import find_file
    from core.tools.timers import set_timer, list_timers, cancel_timer
    from core.tools.notes import take_note, read_notes
    
    # 1. Notes
    res_note = take_note("Nota de prueba de Miku")
    print("take_note:", res_note)
    res_read = read_notes()
    print("read_notes:", res_read)
    
    # 2. System
    print("get_datetime:", get_datetime())
    print("get_system_status:", get_system_status())
    
    # 3. Web
    # We won't actually pop 10 browser tabs, but let's test open_url
    print("Testing web tools function signature...")
    
    # 4. Apps: open notepad
    print("Testing open_app('notepad')...")
    res_app = open_app("notepad")
    print("open_app('notepad'):", res_app)
    
    # 5. Close notepad
    import time
    time.sleep(1)
    res_close = close_app("notepad")
    print("close_app('notepad'):", res_close)
    
    # 6. Volume
    print("get/set volume...")
    res_vol = set_volume(30)
    print("set_volume(30):", res_vol)
    
    # 7. Timers
    t_res = set_timer(60, "Prueba")
    print("set_timer:", t_res)
    l_res = list_timers()
    print("list_timers:", l_res)
    
    print("All direct tool executions completed!")

if __name__ == "__main__":
    test_direct_tools()
