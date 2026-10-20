import ctypes
from ctypes import wintypes
import psutil

kernel32 = ctypes.windll.kernel32
advapi32 = ctypes.windll.advapi32

explorer_pid = None
for p in psutil.process_iter(['pid', 'name']):
    if p.info['name'] and p.info['name'].lower() == 'explorer.exe':
        explorer_pid = p.info['pid']
        break

print("Explorer PID:", explorer_pid)

PROCESS_QUERY_INFORMATION = 0x0400
h_proc = kernel32.OpenProcess(PROCESS_QUERY_INFORMATION, False, explorer_pid)
print("OpenProcess h_proc:", h_proc)

if h_proc:
    h_token = wintypes.HANDLE()
    TOKEN_DUPLICATE = 0x0002
    TOKEN_QUERY = 0x0008
    TOKEN_ASSIGN_PRIMARY = 0x0001
    ret = advapi32.OpenProcessToken(h_proc, TOKEN_DUPLICATE | TOKEN_QUERY | TOKEN_ASSIGN_PRIMARY, ctypes.byref(h_token))
    print("OpenProcessToken ret:", ret, "token:", h_token.value)
