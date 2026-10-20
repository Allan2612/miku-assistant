import ctypes
from ctypes import wintypes
import psutil
import time

kernel32 = ctypes.windll.kernel32
advapi32 = ctypes.windll.advapi32
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

explorer_pid = None
for p in psutil.process_iter(['pid', 'name']):
    if p.info['name'] and p.info['name'].lower() == 'explorer.exe':
        explorer_pid = p.info['pid']
        break

h_proc = kernel32.OpenProcess(0x0400, False, explorer_pid)
h_token = wintypes.HANDLE()
advapi32.OpenProcessToken(h_proc, 0x0002 | 0x0008 | 0x0001, ctypes.byref(h_token))

h_dup_token = wintypes.HANDLE()
SecurityImpersonation = 2
TokenPrimary = 1
advapi32.DuplicateTokenEx(
    h_token,
    0x10000000,
    None,
    SecurityImpersonation,
    TokenPrimary,
    ctypes.byref(h_dup_token)
)
print("DuplicateTokenEx h_dup_token:", h_dup_token.value)

si = STARTUPINFOW()
si.cb = ctypes.sizeof(STARTUPINFOW)
desktop_str = ctypes.create_unicode_buffer("WinSta0\\Default")
si.lpDesktop = ctypes.cast(desktop_str, wintypes.LPWSTR)
si.dwFlags = 1 # STARTF_USESHOWWINDOW
si.wShowWindow = 1 # SW_SHOWNORMAL

pi = PROCESS_INFORMATION()

cmd = "notepad.exe"
ret = advapi32.CreateProcessWithTokenW(
    h_dup_token,
    0,
    None,
    cmd,
    0,
    None,
    None,
    ctypes.byref(si),
    ctypes.byref(pi)
)
print("CreateProcessWithTokenW ret:", ret, "PID:", pi.dwProcessId)

time.sleep(2)

GENERIC_ALL = 0x10000000
h_desk = user32.OpenDesktopW('Default', 0, False, GENERIC_ALL)
user32.SetThreadDesktop(h_desk)

found = []
def cb(hwnd, extra):
    length = user32.GetWindowTextLengthW(hwnd)
    if length > 0 and user32.IsWindowVisible(hwnd):
        buff = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(hwnd, buff, length + 1)
        if any(w in buff.value.lower() for w in ['notas', 'notepad']):
            found.append((hwnd, buff.value))
    return True

user32.EnumWindows(ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)(cb), 0)
print("Notepad windows found on Default desktop:", found)
