import ctypes
from ctypes import wintypes
import psutil

user32 = ctypes.windll.user32

def enum_windows():
    hwnds = []
    def cb(hwnd, extra):
        hwnds.append(hwnd)
        return True
    cb_func = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)(cb)
    user32.EnumWindows(cb_func, 0)
    return hwnds

print("Scanning all top-level windows with title...")
for h in enum_windows():
    length = user32.GetWindowTextLengthW(h)
    if length > 0:
        buff = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(h, buff, length + 1)
        p = wintypes.DWORD()
        user32.GetWindowThreadProcessId(h, ctypes.byref(p))
        try:
            p_name = psutil.Process(p.value).name()
        except Exception:
            p_name = "unknown"
        if any(w in buff.value.lower() for w in ["notas", "notepad", "bloc"]):
            vis = user32.IsWindowVisible(h)
            print(f"HWND {h} | PID {p.value} ({p_name}) | visible={vis} | title='{buff.value}'")
