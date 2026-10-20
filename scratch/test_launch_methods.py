import os
import time
import subprocess
import ctypes
from ctypes import wintypes
import psutil

user32 = ctypes.windll.user32

def enum_windows():
    hwnds = []
    def cb(hwnd, extra):
        hwnds.append(hwnd)
        return True
    cb_func = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)(cb)
    user32.EnumWindows(cb_func, 0)
    return hwnds

def check_notepad():
    found = False
    for p in psutil.process_iter(['pid', 'name']):
        if p.info['name'] and 'notepad' in p.info['name'].lower():
            pid = p.info['pid']
            print(f"Notepad PID: {pid}")
            for h in enum_windows():
                p_id = wintypes.DWORD()
                user32.GetWindowThreadProcessId(h, ctypes.byref(p_id))
                if p_id.value == pid:
                    length = user32.GetWindowTextLengthW(h)
                    buff = ctypes.create_unicode_buffer(length + 1)
                    user32.GetWindowTextW(h, buff, length + 1)
                    vis = user32.IsWindowVisible(h)
                    print(f"  -> Window HWND {h}: title='{buff.value}', visible={vis}")
                    found = True
    return found

print("1. Terminating any running notepads...")
for p in psutil.process_iter(['pid', 'name']):
    if p.info['name'] and 'notepad' in p.info['name'].lower():
        try: p.terminate()
        except: pass
time.sleep(1)

print("\n2. Launching with os.startfile('notepad.exe')...")
try:
    os.startfile('notepad.exe')
except Exception as e:
    print("os.startfile failed:", e)

time.sleep(2)
if not check_notepad():
    print("No window found with os.startfile!")

print("\n3. Testing cmd /c start notepad...")
subprocess.run("cmd.exe /c start notepad", shell=True)
time.sleep(2)
check_notepad()
