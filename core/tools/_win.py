"""
Miku Assistant - Windows helpers shared by the tools (H-010, H-018).
"""

import ctypes
import logging
import os
from pathlib import Path
from typing import Optional

logger = logging.getLogger("miku.tools.win")

GENERIC_ALL = 0x10000000
_desktop_handle: Optional[int] = None


def attach_user_desktop() -> None:
    """Attaches the calling thread to the interactive desktop (WinSta0\\Default).

    The station/desktop handles are opened once per process and kept: each tool runs in
    its own thread, and SetThreadDesktop needs the handle alive while the thread uses it.
    """
    global _desktop_handle
    try:
        user32 = ctypes.windll.user32
        if _desktop_handle is None:
            h_winsta = user32.OpenWindowStationW("WinSta0", False, GENERIC_ALL)
            if h_winsta:
                user32.SetProcessWindowStation(h_winsta)
            _desktop_handle = user32.OpenDesktopW("Default", 0, False, GENERIC_ALL) or 0
        if _desktop_handle:
            user32.SetThreadDesktop(_desktop_handle)
    except Exception as e:
        logger.debug("Desktop attach failed: %s", e)


def find_opera_gx() -> Optional[str]:
    """Finds the Opera GX executable path on the system."""
    candidates = [
        Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "Opera GX" / "opera.exe",
        Path(os.environ.get("PROGRAMFILES", "")) / "Opera GX" / "opera.exe",
        Path(os.environ.get("PROGRAMFILES(X86)", "")) / "Opera GX" / "opera.exe",
    ]
    for c in candidates:
        if c.is_file():
            return str(c)
    return None
