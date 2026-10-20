import ctypes
from ctypes import wintypes
import psutil

user32 = ctypes.windll.user32
GENERIC_ALL = 0x10000000
h_desk = user32.OpenDesktopW('Default', 0, False, GENERIC_ALL)
user32.SetThreadDesktop(h_desk)

for hwnd in [131214, 4982584, 1836600]:
    p = wintypes.DWORD()
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(p))
    try:
        proc = psutil.Process(p.value)
        print(f"HWND {hwnd}: PID {p.value} ({proc.name()})")
    except Exception as e:
        print(f"HWND {hwnd}: {e}")
