import ctypes
from ctypes import wintypes
import psutil

user32 = ctypes.windll.user32

pids = [p.info['pid'] for p in psutil.process_iter(['pid', 'name']) if p.info['name'] and 'notepad' in p.info['name'].lower()]
print('PIDs:', pids)

def enum_windows():
    hwnds = []
    def cb(hwnd, extra):
        hwnds.append(hwnd)
        return True
    cb_func = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)(cb)
    user32.EnumWindows(cb_func, 0)
    return hwnds

for h in enum_windows():
    p = wintypes.DWORD()
    user32.GetWindowThreadProcessId(h, ctypes.byref(p))
    if p.value in pids:
        length = user32.GetWindowTextLengthW(h)
        buff = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(h, buff, length + 1)
        visible = user32.IsWindowVisible(h)
        print(f"PID {p.value} HWND {h}: title='{buff.value}', visible={visible}")
