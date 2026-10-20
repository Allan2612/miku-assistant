import ctypes
from ctypes import wintypes
import time
import subprocess
import os

user32 = ctypes.windll.user32
shell32 = ctypes.windll.shell32
GENERIC_ALL = 0x10000000

h_winsta = user32.OpenWindowStationW("WinSta0", False, GENERIC_ALL)
if h_winsta:
    user32.SetProcessWindowStation(h_winsta)

h_desk = user32.OpenDesktopW("Default", 0, False, GENERIC_ALL)
if h_desk:
    user32.SetThreadDesktop(h_desk)

ret = shell32.ShellExecuteW(None, "open", "notepad.exe", None, None, 1)
print(f"ShellExecuteW returned: {ret}")
time.sleep(2)

def cb(hwnd, extra):
    length = user32.GetWindowTextLengthW(hwnd)
    if length > 0 and user32.IsWindowVisible(hwnd):
        buff = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(hwnd, buff, length + 1)
        if any(w in buff.value.lower() for w in ["notas", "notepad"]):
            print(f"SUCCESS: [{hwnd}] {buff.value}")
    return True

user32.EnumWindows(ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)(cb), 0)
