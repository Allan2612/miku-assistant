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

for p in psutil.process_iter(['pid', 'name']):
    if p.info['name'] and 'notepad' in p.info['name'].lower():
        pid_target = p.info['pid']
        print(f"Checking Notepad PID: {pid_target}")
        for h in enum_windows():
            pid = wintypes.DWORD()
            user32.GetWindowThreadProcessId(h, ctypes.byref(pid))
            if pid.value == pid_target:
                length = user32.GetWindowTextLengthW(h)
                buff = ctypes.create_unicode_buffer(length + 1)
                user32.GetWindowTextW(h, buff, length + 1)
                visible = user32.IsWindowVisible(h)
                iconic = user32.IsIconic(h)
                print(f"HWND {h}: title='{buff.value}', visible={visible}, iconic(minimized)={iconic}")
