"""
Miku Assistant - Apps and Windows Tools (tools/apps.py)
"""

import ctypes
from ctypes import wintypes
import logging
import os
from pathlib import Path
import re
import subprocess
import time
from typing import Dict, List, Optional, Any
import psutil

from core.tools import tool

logger = logging.getLogger("miku.tools.apps")

# Cache for Start Menu shortcuts
_SHORTCUTS_CACHE: Dict[str, str] = {}
_CACHE_INITIALIZED: bool = False

def _find_opera_gx_path() -> Optional[str]:
    """Finds the Opera GX executable path on the system."""
    candidates = [
        Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "Opera GX" / "opera.exe",
        Path(os.environ.get("PROGRAMFILES", "")) / "Opera GX" / "opera.exe",
        Path(os.environ.get("PROGRAMFILES(X86)", "")) / "Opera GX" / "opera.exe",
        Path(os.environ.get("APPDATA", "")) / "Local" / "Programs" / "Opera GX" / "opera.exe",
    ]
    for c in candidates:
        if c.is_file():
            return str(c)
    return None


# App aliases loaded from config or default fallback
DEFAULT_APP_ALIASES = {
    "opera": "opera.exe",
    "opera gx": "opera.exe",
    "operagx": "opera.exe",
    "navegador": "opera.exe",
    "browser": "opera.exe",
    "internet": "opera.exe",
    "chrome": "chrome.exe",
    "google chrome": "chrome.exe",
    "google": "opera.exe",
    "youtube": "https://www.youtube.com",
    "spotify": "spotify.exe",
    "discord": "Discord.exe",
    "steam": "steam.exe",
    "bloc de notas": "notepad.exe",
    "control de notas": "notepad.exe",
    "bloc": "notepad.exe",
    "notas": "notepad.exe",
    "notepad": "notepad.exe",
    "calculadora": "calc.exe",
    "calc": "calc.exe",
    "explorador": "explorer.exe",
    "explorador de archivos": "explorer.exe",
    "archivos": "explorer.exe",
    "terminal": "wt.exe",
    "cmd": "cmd.exe",
    "powershell": "powershell.exe",
    "vscode": "Code.exe",
    "code": "Code.exe",
    "edge": "msedge.exe",
}


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


def _attach_user_desktop() -> None:
    """Ensures current thread is attached to the interactive user desktop (WinSta0\\Default)."""
    try:
        user32 = ctypes.windll.user32
        GENERIC_ALL = 0x10000000
        h_winsta = user32.OpenWindowStationW("WinSta0", False, GENERIC_ALL)
        if h_winsta:
            user32.SetProcessWindowStation(h_winsta)
        h_desk = user32.OpenDesktopW("Default", 0, False, GENERIC_ALL)
        if h_desk:
            user32.SetThreadDesktop(h_desk)
    except Exception as e:
        logger.debug("Desktop attach failed: %s", e)


def _clean_query(name: str) -> str:
    """Strips leading Spanish articles and punctuation for robust matching."""
    q = name.strip().lower().rstrip(".!?,;")
    q = re.sub(r"^(el|la|los|las|un|una|al)\s+", "", q, flags=re.IGNORECASE).strip()
    return q


def _launch_target(target: str) -> bool:
    """Launches an application or shortcut directly onto the user's interactive desktop."""
    _attach_user_desktop()

    # 1. Primary: CreateProcessW specifying explicit lpDesktop = "WinSta0\\Default"
    # This guarantees the window appears on the user's physical screen even if called from a daemon
    try:
        si = STARTUPINFOW()
        si.cb = ctypes.sizeof(STARTUPINFOW)
        desktop_str = ctypes.create_unicode_buffer("WinSta0\\Default")
        si.lpDesktop = ctypes.cast(desktop_str, wintypes.LPWSTR)
        si.dwFlags = 1  # STARTF_USESHOWWINDOW
        si.wShowWindow = 1  # SW_SHOWNORMAL

        pi = PROCESS_INFORMATION()
        cmd = ctypes.create_unicode_buffer(str(target))
        ret = ctypes.windll.kernel32.CreateProcessW(
            None, cmd, None, None, False, 0, None, None, ctypes.byref(si), ctypes.byref(pi)
        )
        if ret:
            ctypes.windll.kernel32.CloseHandle(pi.hProcess)
            ctypes.windll.kernel32.CloseHandle(pi.hThread)
            return True
    except Exception as e:
        logger.debug("CreateProcessW failed for %s: %s", target, e)

    # 2. Secondary: ShellExecuteW for shortcuts (.lnk), protocols, URLs
    try:
        ret = ctypes.windll.shell32.ShellExecuteW(None, "open", str(target), None, None, 1)
        if ret > 32:
            return True
    except Exception:
        pass

    # 3. Tertiary: os.startfile
    try:
        os.startfile(target)
        return True
    except Exception:
        pass

    # 4. Quaternary: subprocess start
    try:
        si_sub = subprocess.STARTUPINFO()
        si_sub.lpDesktop = "WinSta0\\Default"
        subprocess.Popen(f'cmd.exe /c start "" "{target}"', shell=True, startupinfo=si_sub)
        return True
    except Exception:
        pass

    return False


def _index_start_menu_shortcuts() -> None:
    """Indexes .lnk files from system and user Start Menu folders."""
    global _SHORTCUTS_CACHE, _CACHE_INITIALIZED
    if _CACHE_INITIALIZED:
        return

    shortcut_dirs = [
        Path(os.environ.get("ProgramData", "C:\\ProgramData")) / "Microsoft" / "Windows" / "Start Menu" / "Programs",
        Path(os.environ.get("APPDATA", "")) / "Microsoft" / "Windows" / "Start Menu" / "Programs",
    ]

    for s_dir in shortcut_dirs:
        if not s_dir.exists():
            continue
        try:
            for path in s_dir.rglob("*.lnk"):
                clean_name = path.stem.lower()
                if clean_name not in _SHORTCUTS_CACHE:
                    _SHORTCUTS_CACHE[clean_name] = str(path)
        except Exception as e:
            logger.warning("Error indexing start menu directory %s: %s", s_dir, e)

    _CACHE_INITIALIZED = True
    logger.debug("Indexed %d Start Menu shortcuts.", len(_SHORTCUTS_CACHE))


@tool(
    name="open_app",
    description="Abre una aplicación instalada en la PC por su nombre (ej: Spotify, Chrome, Discord, Bloc de notas)."
)
def open_app(name: str = "", app_name: str = "") -> Dict[str, Any]:
    """Abre una aplicación instalada."""
    target_name = name or app_name
    if not target_name:
        return {"ok": False, "result": "Debes especificar el nombre de la aplicación."}
    _index_start_menu_shortcuts()
    query = _clean_query(target_name)

    # 0. Check Opera GX specifically
    if query in ("opera", "opera gx", "operagx", "navegador", "browser", "internet"):
        opera_path = _find_opera_gx_path()
        if opera_path and _launch_target(opera_path):
            time.sleep(0.3)
            _attach_user_desktop()
            ctypes.windll.user32.AllowSetForegroundWindow(0xFFFFFFFF)
            return {"ok": True, "result": "He abierto Opera GX."}

    # 1. Check known aliases
    if query in DEFAULT_APP_ALIASES:
        target = DEFAULT_APP_ALIASES[query]
        if _launch_target(target):
            time.sleep(0.3)
            _attach_user_desktop()
            ctypes.windll.user32.AllowSetForegroundWindow(0xFFFFFFFF)
            return {"ok": True, "result": f"He abierto {target_name}."}

    # 2. Check exact or substring shortcut match
    matches: List[str] = []
    for sc_name, sc_path in _SHORTCUTS_CACHE.items():
        if query == sc_name:
            matches = [sc_path]
            break
        elif query in sc_name:
            matches.append(sc_path)

    if len(matches) == 1:
        if _launch_target(matches[0]):
            time.sleep(0.3)
            _attach_user_desktop()
            ctypes.windll.user32.AllowSetForegroundWindow(0xFFFFFFFF)
            return {"ok": True, "result": f"He abierto {target_name}."}
    elif len(matches) > 1:
        best_match = min(matches, key=len)
        if _launch_target(best_match):
            time.sleep(0.3)
            _attach_user_desktop()
            ctypes.windll.user32.AllowSetForegroundWindow(0xFFFFFFFF)
            match_names = [Path(m).stem for m in matches[:3]]
            return {"ok": True, "result": f"Encontré varias opciones ({', '.join(match_names)}). Abrí {Path(best_match).stem}."}

    # 3. Direct executable attempt
    for candidate in [f"{query}.exe", query]:
        if _launch_target(candidate):
            time.sleep(0.3)
            _attach_user_desktop()
            ctypes.windll.user32.AllowSetForegroundWindow(0xFFFFFFFF)
            return {"ok": True, "result": f"He abierto {target_name}."}

    return {"ok": False, "result": f"No pude encontrar ni abrir la aplicación '{target_name}'. Verifiqué el menú inicio y los alias conocidos."}


@tool(
    name="close_app",
    description="Cierra una aplicación abierta por su nombre o ejecutable (ej: Chrome, Spotify, Discord)."
)
def close_app(name: str = "", app_name: str = "") -> Dict[str, Any]:
    """Cierra los procesos y ventanas correspondientes a una aplicación sin pedir confirmación."""
    target_name = name or app_name
    if not target_name:
        return {"ok": False, "result": "Debes especificar el nombre de la aplicación a cerrar."}
    _attach_user_desktop()
    query = _clean_query(target_name).replace(".exe", "")
    alias = DEFAULT_APP_ALIASES.get(query, query).lower().replace(".exe", "")

    closed_count = 0
    terminated_names = set()

    for proc in psutil.process_iter(["pid", "name", "exe"]):
        try:
            p_name = proc.info["name"].lower() if proc.info["name"] else ""
            clean_p = p_name.replace(".exe", "")
            if query == clean_p or alias == clean_p or query in clean_p:
                proc.kill()
                closed_count += 1
                terminated_names.add(proc.info["name"])
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue

    if closed_count > 0:
        return {"ok": True, "result": f"He cerrado {target_name} ({', '.join(terminated_names)})."}
    return {"ok": False, "result": f"No encontré ninguna aplicación activa llamada '{target_name}'."}


@tool(
    name="show_desktop",
    description="Muestra el escritorio de Windows minimizando todas las ventanas (Win+D)."
)
def show_desktop() -> Dict[str, Any]:
    """Envía la pulsación Win+D en el escritorio interactivo."""
    _attach_user_desktop()
    user32 = ctypes.windll.user32
    VK_LWIN = 0x5B
    KEY_D = 0x44
    KEYEVENTF_KEYUP = 0x0002

    user32.keybd_event(VK_LWIN, 0, 0, 0)
    user32.keybd_event(KEY_D, 0, 0, 0)
    user32.keybd_event(KEY_D, 0, KEYEVENTF_KEYUP, 0)
    user32.keybd_event(VK_LWIN, 0, KEYEVENTF_KEYUP, 0)

    return {"ok": True, "result": "Mostrando el escritorio."}


@tool(
    name="focus_app",
    description="Trae la ventana de una aplicación al primer plano por su nombre o título."
)
def focus_app(name: str = "", app_name: str = "") -> Dict[str, Any]:
    """Busca y trae una ventana visible al primer plano en el escritorio interactivo."""
    target_name = name or app_name
    if not target_name:
        return {"ok": False, "result": "Debes indicar el nombre de la ventana a enfocar."}
    _attach_user_desktop()
    query = _clean_query(target_name)
    user32 = ctypes.windll.user32
    found_hwnd = None

    def enum_windows_callback(hwnd, extra):
        nonlocal found_hwnd
        if not user32.IsWindowVisible(hwnd):
            return True
        length = user32.GetWindowTextLengthW(hwnd)
        if length > 0:
            buff = ctypes.create_unicode_buffer(length + 1)
            user32.GetWindowTextW(hwnd, buff, length + 1)
            title = buff.value.lower()
            if query in title:
                found_hwnd = hwnd
                return False
        return True

    WNDENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    user32.EnumWindows(WNDENUMPROC(enum_windows_callback), 0)

    if found_hwnd:
        SW_RESTORE = 9
        user32.AllowSetForegroundWindow(0xFFFFFFFF)
        user32.ShowWindow(found_hwnd, SW_RESTORE)
        user32.SetForegroundWindow(found_hwnd)
        return {"ok": True, "result": f"He traído {target_name} al frente."}

    return {"ok": False, "result": f"No encontré ninguna ventana abierta que coincida con '{target_name}'."}


@tool(
    name="type_text",
    description="Escribe texto en la ventana o campo actualmente activo (máx 500 caracteres)."
)
def type_text(text: str) -> Dict[str, Any]:
    """Escribe texto simulando pulsaciones de teclado en la ventana activa del usuario."""
    _attach_user_desktop()
    if len(text) > 500:
        text = text[:500]

    user32 = ctypes.windll.user32
    for char in text:
        vk = user32.VkKeyScanW(ord(char))
        if vk != -1:
            shift = (vk >> 8) & 1
            code = vk & 0xFF
            if shift:
                user32.keybd_event(0x10, 0, 0, 0)
            user32.keybd_event(code, 0, 0, 0)
            user32.keybd_event(code, 0, 2, 0)
            if shift:
                user32.keybd_event(0x10, 0, 2, 0)
        time.sleep(0.01)

    return {"ok": True, "result": f"Texto escrito ({len(text)} caracteres)."}
