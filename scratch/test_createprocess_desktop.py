import ctypes
from ctypes import wintypes
import time

kernel32 = ctypes.windll.kernel32
user32 = ctypes.windll.user32

class STARTUPINFOW(ctypes.Structure):
    _fields_ = [
        ('cb', wintypes.DWORD),
        ('lpReserved', wintypes.LPWSTR),
        ('lpDesktop', wintypes.LPWSTR),
        ('lpTitle', wintypes.LPWSTR),
        ('dwX', wintypes.DWORD),
        ('dwY', wintypes.DWORD),
        ('dwXSize', wintypes.DWORD),
        ('dwYSize', wintypes.DWORD),
        ('dwXCountChars', wintypes.DWORD),
        ('dwYCountChars', wintypes.DWORD),
        ('dwFillAttribute', wintypes.DWORD),
        ('dwFlags', wintypes.DWORD),
        ('wShowWindow', wintypes.WORD),
        ('cbReserved2', wintypes.WORD),
        ('lpReserved2', ctypes.c_char_p),
        ('hStdInput', wintypes.HANDLE),
        ('hStdOutput', wintypes.HANDLE),
        ('hStdError', wintypes.HANDLE),
    ]

class PROCESS_INFORMATION(ctypes.Structure):
    _fields_ = [
        ('hProcess', wintypes.HANDLE),
        ('hThread', wintypes.HANDLE),
        ('dwProcessId', wintypes.DWORD),
        ('dwThreadId', wintypes.DWORD),
    ]

si = STARTUPINFOW()
si.cb = ctypes.sizeof(STARTUPINFOW)
desktop_str = ctypes.create_unicode_buffer("WinSta0\\Default")
si.lpDesktop = ctypes.cast(desktop_str, wintypes.LPWSTR)
si.dwFlags = 1 # STARTF_USESHOWWINDOW
si.wShowWindow = 1 # SW_SHOWNORMAL

pi = PROCESS_INFORMATION()

# Try launching calc.exe or notepad.exe
cmd = ctypes.create_unicode_buffer("calc.exe")
ret = kernel32.CreateProcessW(
    None,
    cmd,
    None,
    None,
    False,
    0,
    None,
    None,
    ctypes.byref(si),
    ctypes.byref(pi)
)
print("CreateProcessW ret:", ret, "PID:", pi.dwProcessId, "err:", kernel32.GetLastError())

time.sleep(2)

GENERIC_ALL = 0x10000000
h_desk = user32.OpenDesktopW('Default', 0, False, GENERIC_ALL)
user32.SetThreadDesktop(h_desk)

def cb(hwnd, extra):
    length = user32.GetWindowTextLengthW(hwnd)
    if length > 0 and user32.IsWindowVisible(hwnd):
        buff = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(hwnd, buff, length + 1)
        if any(w in buff.value.lower() for w in ['calc', 'calculadora']):
            print(f"FOUND ON DEFAULT DESKTOP: [{hwnd}] {buff.value}")
    return True

user32.EnumWindows(ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)(cb), 0)
