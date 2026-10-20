import ctypes
from ctypes import wintypes
import subprocess
import time

user32 = ctypes.windll.user32
GENERIC_ALL = 0x10000000

h_winsta = user32.OpenWindowStationW("WinSta0", False, GENERIC_ALL)
if h_winsta:
    user32.SetProcessWindowStation(h_winsta)

h_desk = user32.OpenDesktopW("Default", 0, False, GENERIC_ALL)
if h_desk:
    user32.SetThreadDesktop(h_desk)
    print("Attached to Default desktop successfully!")

si = subprocess.STARTUPINFO()
si.lpDesktop = "WinSta0\\Default"

print("Launching notepad with lpDesktop='WinSta0\\Default'...")
p = subprocess.Popen('cmd.exe /c start "" "notepad.exe"', shell=True, startupinfo=si)
time.sleep(2)

print("Checking windows on Default desktop:")
def cb(hwnd, extra):
    length = user32.GetWindowTextLengthW(hwnd)
    if length > 0 and user32.IsWindowVisible(hwnd):
        buff = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(hwnd, buff, length + 1)
        if any(w in buff.value.lower() for w in ["notas", "notepad"]):
            print(f"FOUND ON DEFAULT DESKTOP: HWND {hwnd} | title='{buff.value}'")
    return True

cb_func = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)(cb)
user32.EnumWindows(cb_func, 0)
