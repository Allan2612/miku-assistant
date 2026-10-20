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

for h in enum_windows():
    if user32.IsWindowVisible(h):
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
            print(f"HWND {h} | {p_name} ({p.value}): '{buff.value}'")
