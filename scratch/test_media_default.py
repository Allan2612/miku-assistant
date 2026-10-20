import ctypes
import time

user32 = ctypes.windll.user32
GENERIC_ALL = 0x10000000

h_winsta = user32.OpenWindowStationW("WinSta0", False, GENERIC_ALL)
if h_winsta:
    user32.SetProcessWindowStation(h_winsta)

h_desk = user32.OpenDesktopW("Default", 0, False, GENERIC_ALL)
if h_desk:
    user32.SetThreadDesktop(h_desk)
    print("Attached to Default desktop!")

KEYEVENTF_EXTENDEDKEY = 0x0001
KEYEVENTF_KEYUP = 0x0002
VK_MEDIA_PLAY_PAUSE = 0xB3

print("Sending VK_MEDIA_PLAY_PAUSE on Default desktop...")
user32.keybd_event(VK_MEDIA_PLAY_PAUSE, 0, KEYEVENTF_EXTENDEDKEY, 0)
user32.keybd_event(VK_MEDIA_PLAY_PAUSE, 0, KEYEVENTF_EXTENDEDKEY | KEYEVENTF_KEYUP, 0)
print("Sent successfully!")
