"""
Miku Assistant - Where her files live.

PROGRAM: the code and the models (the project folder in development, the install folder once installed).
DATA: config.yaml, .env and cache/ (logs, memory, reminders...). In development it is the project folder too;
once installed, miku.exe sets MIKU_HOME to %APPDATA%\\Miku Assistant, so updating or uninstalling the program never
touches the user's data.
"""

import os
from pathlib import Path

PROGRAM = Path(__file__).resolve().parents[1]
DATA = Path(os.environ.get("MIKU_HOME") or PROGRAM)
CACHE = DATA / "cache"
CONFIG = DATA / "config.yaml"
ENV = DATA / ".env"
