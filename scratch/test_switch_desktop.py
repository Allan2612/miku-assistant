import ctypes
from ctypes import wintypes
import psutil

user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32

GENERIC_ALL = 0x10000000
h_winsta = user32.OpenWindowStationW("WinSta0", False, GENERIC_ALL)
print("OpenWindowStationW('WinSta0'):", h_winsta)
if h_winsta:
    user32.SetProcessWindowStation(h_winsta)

h_desk = user32.OpenDesktopW("Default", 0, False, GENERIC_ALL)
print("OpenDesktopW('Default'):", h_desk)

if h_desk:
    ret = user32.SetThreadDesktop(h_desk)
    print("SetThreadDesktop ret:", ret)

    count = 0
    windows_found = []
    def cb(hwnd, extra):
        global count
        count += 1
        length = user32.GetWindowTextLengthW(hwnd)
        if length > 0 and user32.IsWindowVisible(hwnd):
            buff = ctypes.create_unicode_buffer(length + 1)
            user32.GetWindowTextW(hwnd, buff, length + 1)
            windows_found.append((hwnd, buff.value))
        return True

    cb_func = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)(cb)
    user32.EnumWindows(cb_func, 0)
    print(f"Windows count on Default desktop: {count}, visible with titles: {len(windows_found)}")
    for h, title in windows_found[:10]:
        print(f"  [{h}] {title}")
