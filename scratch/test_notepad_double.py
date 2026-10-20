import subprocess
import time
import psutil

print("Testing launching notepad when it is already running...")
# Launch 1
subprocess.run("start notepad", shell=True)
time.sleep(1)

# Launch 2
subprocess.run("start notepad", shell=True)
time.sleep(1)

notepads = [p.info for p in psutil.process_iter(['pid', 'name']) if p.info['name'] and 'notepad' in p.info['name'].lower()]
print("Notepad processes count:", len(notepads))
