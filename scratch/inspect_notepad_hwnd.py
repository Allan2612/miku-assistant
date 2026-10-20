import ctypes
from ctypes import wintypes
user32 = ctypes.windll.user32

for hwnd in [7931950, 854704]:
    if user32.IsWindow(hwnd):
        pid = wintypes.DWORD()
        tid = user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        length = user32.GetWindowTextLengthW(hwnd)
        buff = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(hwnd, buff, length + 1)
        print(f"HWND {hwnd}: PID={pid.value}, TID={tid}, title='{buff.value}', visible={user32.IsWindowVisible(hwnd)}")
    else:
        print(f"HWND {hwnd} is no longer a valid window.")
