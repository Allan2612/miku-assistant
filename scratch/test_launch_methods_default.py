import ctypes
from ctypes import wintypes
import time
import subprocess
import os

user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32
GENERIC_ALL = 0x10000000

h_winsta = user32.OpenWindowStationW("WinSta0", False, GENERIC_ALL)
if h_winsta:
    user32.SetProcessWindowStation(h_winsta)

h_desk = user32.OpenDesktopW("Default", 0, False, GENERIC_ALL)
if h_desk:
    user32.SetThreadDesktop(h_desk)

def get_default_windows():
    wins = []
    def cb(hwnd, extra):
        length = user32.GetWindowTextLengthW(hwnd)
        if length > 0 and user32.IsWindowVisible(hwnd):
            buff = ctypes.create_unicode_buffer(length + 1)
            user32.GetWindowTextW(hwnd, buff, length + 1)
            wins.append((hwnd, buff.value))
        return True
    cb_func = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)(cb)
    user32.EnumWindows(cb_func, 0)
    return wins

# Method 1: powershell Start-Process
print("Method 1: powershell -Command Start-Process notepad...")
subprocess.run(["powershell", "-NoProfile", "-Command", "Start-Process notepad"], check=False)
time.sleep(2)
for h, t in get_default_windows():
    if "notas" in t.lower() or "notepad" in t.lower():
        print(f"  Method 1 SUCCESS: [{h}] {t}")

# Method 2: C:\Windows\notepad.exe directly
print("Method 2: C:\\Windows\\notepad.exe...")
os.startfile("C:\\Windows\\notepad.exe")
time.sleep(2)
for h, t in get_default_windows():
    if "notas" in t.lower() or "notepad" in t.lower():
        print(f"  Method 2 SUCCESS: [{h}] {t}")
