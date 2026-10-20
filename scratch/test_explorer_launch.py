import subprocess
import time
import ctypes
from ctypes import wintypes

user32 = ctypes.windll.user32
GENERIC_ALL = 0x10000000

h_winsta = user32.OpenWindowStationW("WinSta0", False, GENERIC_ALL)
if h_winsta:
    user32.SetProcessWindowStation(h_winsta)

h_desk = user32.OpenDesktopW("Default", 0, False, GENERIC_ALL)
if h_desk:
    user32.SetThreadDesktop(h_desk)

print("Launching via explorer.exe notepad.exe...")
subprocess.run(["explorer.exe", "notepad.exe"])
time.sleep(2)

found = []
def cb(hwnd, extra):
    length = user32.GetWindowTextLengthW(hwnd)
    if length > 0 and user32.IsWindowVisible(hwnd):
        buff = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(hwnd, buff, length + 1)
        title = buff.value.lower()
        if "notas" in title or "notepad" in title:
            found.append((hwnd, buff.value))
    return True

cb_func = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)(cb)
user32.EnumWindows(cb_func, 0)
print("Notepad windows found on Default desktop after explorer.exe:", found)
