import psutil
import os
import ctypes

p = psutil.Process()
print("Python PID:", p.pid, "Session:", p.environ().get('SESSIONNAME'))

for pid in [19800, 34944]:
    try:
        np = psutil.Process(pid)
        print("Notepad PID:", pid, "Session:", np.environ().get('SESSIONNAME'), "exe:", np.exe())
    except Exception as e:
        print("Error for", pid, e)
