"""
Miku Assistant - Apps and Windows Tools (tools/apps.py)
"""

import ctypes
from ctypes import wintypes
import logging
import os
from pathlib import Path
import re
import time
from typing import Dict, List, Optional, Any
import psutil

from core.config import load_config
from core.tools import tool
from core.tools._win import attach_user_desktop as _attach_user_desktop, find_opera_gx as _find_opera_gx_path

logger = logging.getLogger("miku.tools.apps")

# Cache for Start Menu shortcuts
_SHORTCUTS_CACHE: Dict[str, str] = {}
_CACHE_INITIALIZED: bool = False

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
    "vscode": "Code.exe",
    "code": "Code.exe",
    "edge": "msedge.exe",
}
# config.yaml -> apps adds or overrides aliases (H-009)
DEFAULT_APP_ALIASES.update({k.lower(): v for k, v in load_config().apps.items()})


# Shells and script hosts: opening them lets the LLM chain type_text into a command line (H-007)
_BLOCKED_LAUNCH = {
    "cmd", "powershell", "pwsh", "wt", "windowsterminal", "bash", "wsl",
    "wscript", "cscript", "mshta", "rundll32", "regsvr32", "reg", "regedit",
}

# Never killed by close_app (H-008)
_PROTECTED_PROCESSES = {
    "explorer", "dwm", "csrss", "winlogon", "wininit", "lsass", "services",
    "svchost", "smss", "system", "fontdrvhost", "sihost", "taskmgr",
}

# Bare executable name only: no spaces, paths, quotes or arguments (H-006)
_SIMPLE_EXE = re.compile(r"^[\w.-]+$")

# Start Menu shortcut names that open a shell
_BLOCKED_SHORTCUT_WORDS = ("powershell", "terminal", "command prompt", "símbolo del sistema", "simbolo del sistema", "cmd")


def _is_shell(name: str) -> bool:
    n = name.lower().removesuffix(".exe")
    return n in _BLOCKED_LAUNCH or any(w in n for w in _BLOCKED_SHORTCUT_WORDS)

_CONSOLE_CLASSES = {"ConsoleWindowClass", "CASCADIA_HOSTING_WINDOW_CLASS"}


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
        # Quoted: the whole target is the executable, never "exe + arguments" (H-006)
        cmd = ctypes.create_unicode_buffer(f'"{target}"')
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
    if _is_shell(query):
        return {"ok": False, "result": "Por seguridad no abro consolas ni intérpretes de comandos."}

    # 0. Check Opera GX specifically
    if query in ("opera", "opera gx", "operagx", "navegador", "browser", "internet"):
        # Already open: launching it again opened a SECOND window (user, 24-oct); bring the one there is
        running = _find_window("", exe="opera")
        if running and _bring_to_front(running):
            return {"ok": True, "result": "Opera ya estaba abierto; te lo traje al frente."}
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

    # 2. Check exact or partial shortcut match. Partial: 3+ letters at the start of a word, or "abre mi"
    # opened Microsoft Edge and "abre la" a random app (seen on the real Start Menu)
    partial = re.compile(rf"\b{re.escape(query)}") if len(query) >= 3 else None
    matches: List[str] = []
    for sc_name, sc_path in _SHORTCUTS_CACHE.items():
        if _is_shell(sc_name):
            continue
        if query == sc_name:
            matches = [sc_path]
            break
        elif partial and partial.search(sc_name):
            matches.append(sc_path)

    if len(matches) == 1:
        if _launch_target(matches[0]):
            time.sleep(0.3)
            _attach_user_desktop()
            ctypes.windll.user32.AllowSetForegroundWindow(0xFFFFFFFF)
            return {"ok": True, "result": f"He abierto {target_name}."}
    elif len(matches) > 1:
        # Shortest shortcut name, not path: the path length depends on the install folder
        best_match = min(matches, key=lambda p: len(Path(p).stem))
        if _launch_target(best_match):
            time.sleep(0.3)
            _attach_user_desktop()
            ctypes.windll.user32.AllowSetForegroundWindow(0xFFFFFFFF)
            match_names = [Path(m).stem for m in matches[:3]]
            return {"ok": True, "result": f"Encontré varias opciones ({', '.join(match_names)}). Abrí {Path(best_match).stem}."}

    # 3. Direct executable attempt: bare names only, never shells (H-006, H-007)
    exe_stem = query.removesuffix(".exe")
    if not _SIMPLE_EXE.match(query):
        return {"ok": False, "result": f"No pude encontrar la aplicación '{target_name}' en el menú Inicio ni en los alias conocidos."}
    for candidate in [f"{exe_stem}.exe"]:
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

    if query in _PROTECTED_PROCESSES or alias in _PROTECTED_PROCESSES:
        return {"ok": False, "result": f"Por seguridad no cierro '{target_name}'."}

    # Never kill Miku's own backend or the process that launched it
    me = psutil.Process()
    own_pids = {me.pid} | {p.pid for p in me.parents()}

    # Exact name match only: substrings killed unrelated processes (H-008)
    targets: List[psutil.Process] = []
    for proc in psutil.process_iter(["pid", "name"]):
        name = (proc.info["name"] or "").lower().removesuffix(".exe")
        if name and name in (query, alias) and proc.info["pid"] not in own_pids:
            targets.append(proc)

    terminated_names = set()
    for proc in targets:
        try:
            proc.terminate()  # lets the app close cleanly; kill() only as fallback
            terminated_names.add(proc.info["name"])
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    _, alive = psutil.wait_procs(targets, timeout=3)
    for proc in alive:
        try:
            proc.kill()
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass

    if terminated_names:
        return {"ok": True, "result": f"He cerrado {target_name} ({', '.join(sorted(terminated_names))})."}
    return {"ok": False, "result": f"No encontré ninguna aplicación activa llamada '{target_name}'."}


@tool(
    name="show_desktop",
    description="Muestra el escritorio de Windows MINIMIZANDO todas las ventanas (Win+D). No cierra nada: para cerrar pestañas usa browser_action, para cerrar un programa close_app."
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
    found_hwnd = _find_window(target_name)
    if found_hwnd:
        _bring_to_front(found_hwnd)
        return {"ok": True, "result": f"He traído {target_name} al frente."}

    return {"ok": False, "result": f"No encontré ninguna ventana abierta que coincida con '{target_name}'."}


_SHOW_COMMANDS = {"minimize": 6, "maximize": 3, "restore": 9}
_ACTION_WORDS = {"minimiza": "minimize", "maximiza": "maximize", "restaura": "restore", "agranda": "maximize", "esconde": "minimize"}


@tool(
    name="window_action",
    description="Minimiza, maximiza o restaura la ventana de una aplicación abierta por su nombre o título (action: minimize | maximize | restore)."
)
def window_action(name: str, action: str = "minimize") -> Dict[str, Any]:
    """Cambia el estado de una ventana visible."""
    act = action.strip().lower()
    act = next((v for k, v in _ACTION_WORDS.items() if act.startswith(k)), act)
    if act not in _SHOW_COMMANDS:
        return {"ok": False, "result": f"No sé hacer '{action}' con una ventana (usa minimize, maximize o restore)."}
    # An empty name matches every title: it would act on whatever window comes first
    hwnd = _find_window(name) if _clean_query(name) else None
    if not hwnd:
        return {"ok": False, "result": f"No encontré ninguna ventana abierta que coincida con '{name}'."}
    ctypes.windll.user32.ShowWindow(hwnd, _SHOW_COMMANDS[act])
    done = {"minimize": "minimicé", "maximize": "maximicé", "restore": "restauré"}[act]
    return {"ok": True, "result": f"Listo, {done} {name}."}


def _find_window(target_name: str, exe: Optional[str] = None) -> Optional[int]:
    """First visible top-level window whose title contains the cleaned name; with exe, only that process's
    main windows (unowned, not tool windows), e.g. exe="opera" for Opera's browser windows."""
    _attach_user_desktop()
    query = _clean_query(target_name)
    user32 = ctypes.windll.user32
    GW_OWNER, GWL_EXSTYLE, WS_EX_TOOLWINDOW = 4, -20, 0x00000080
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
            if query in title and (exe is None or _is_main_window_of(hwnd, exe)):
                found_hwnd = hwnd
                return False
        return True

    def _is_main_window_of(hwnd, stem: str) -> bool:
        if user32.GetWindow(hwnd, GW_OWNER) or user32.GetWindowLongW(hwnd, GWL_EXSTYLE) & WS_EX_TOOLWINDOW:
            return False
        pid = wintypes.DWORD(0)
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        try:
            return Path(psutil.Process(pid.value).name()).stem.lower() == stem
        except (psutil.Error, OSError):
            return False

    WNDENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    user32.EnumWindows(WNDENUMPROC(enum_windows_callback), 0)
    return found_hwnd


def _bring_to_front(hwnd: int) -> bool:
    """Makes hwnd the foreground window and says whether it really is (Windows refuses background processes)."""
    _attach_user_desktop()
    user32, kernel32 = ctypes.windll.user32, ctypes.windll.kernel32
    if user32.IsIconic(hwnd):
        user32.ShowWindow(hwnd, 9)  # SW_RESTORE only when minimized: it would un-maximize a maximized window
    # Joining the input of the current foreground thread lifts the foreground lock for this call
    fg_thread = user32.GetWindowThreadProcessId(user32.GetForegroundWindow(), None)
    own_thread = kernel32.GetCurrentThreadId()
    attached = fg_thread and fg_thread != own_thread and user32.AttachThreadInput(own_thread, fg_thread, True)
    try:
        # Two tries: a browser busy loading a page sometimes ignored the first one (live test)
        for _ in range(2):
            user32.AllowSetForegroundWindow(0xFFFFFFFF)
            user32.BringWindowToTop(hwnd)
            user32.SetForegroundWindow(hwnd)
            time.sleep(0.15)
            if user32.GetForegroundWindow() == hwnd:
                return True
    finally:
        if attached:
            user32.AttachThreadInput(own_thread, fg_thread, False)
    return False


def _press(*vks: int) -> None:
    """Presses a key chord, e.g. _press(0x11, ord("L")) for Ctrl+L, into the foreground window."""
    user32 = ctypes.windll.user32
    for vk in vks:
        user32.keybd_event(vk, 0, 0, 0)
    for vk in reversed(vks):
        user32.keybd_event(vk, 0, 2, 0)


def _type_into_foreground(text: str) -> None:
    """Types text key by key into the foreground window (callers check which window that is)."""
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


@tool(
    name="type_text",
    description="Escribe texto en la ventana o campo actualmente activo (máx 500 caracteres)."
)
def type_text(text: str) -> Dict[str, Any]:
    """Escribe texto simulando pulsaciones de teclado en la ventana activa del usuario."""
    _attach_user_desktop()
    user32 = ctypes.windll.user32

    # Never type into a console: that would turn type_text into command execution (H-007)
    cls = ctypes.create_unicode_buffer(256)
    user32.GetClassNameW(user32.GetForegroundWindow(), cls, 256)
    if cls.value in _CONSOLE_CLASSES:
        return {"ok": False, "result": "Por seguridad no escribo en consolas ni terminales."}

    # No line breaks: Enter would submit forms or commands
    text = " ".join(text.splitlines())[:500]
    _type_into_foreground(text)

    return {"ok": True, "result": f"Texto escrito ({len(text)} caracteres)."}


# Spoken names for common executables; anything else is read as its exe name
_FRIENDLY_NAMES = {
    "msedge": "Edge", "chrome": "Chrome", "opera": "Opera", "firefox": "Firefox", "brave": "Brave",
    "code": "Visual Studio Code", "winword": "Word", "excel": "Excel", "powerpnt": "PowerPoint",
    "explorer": "el Explorador de archivos", "notepad": "el Bloc de notas", "spotify": "Spotify",
    "discord": "Discord", "steam": "Steam", "steamwebhelper": "Steam", "windowsterminal": "la Terminal",
    "obs64": "OBS", "vlc": "VLC", "whatsapp": "WhatsApp", "telegram": "Telegram",
}
# Hosts and shell parts that own visible windows but are not "apps" to the user
_NOT_APPS = {"applicationframehost", "textinputhost", "shellexperiencehost", "searchhost", "startmenuexperiencehost",
             "systemsettings", "lockapp", "app", "pythonw", "python"}  # app / pythonw: Miku herself


def _spoken_app_list(exe_stems: List[str]) -> str:
    """'opera', 'Spotify', 'opera' -> 'Opera y Spotify': friendly names, no duplicates, order kept."""
    names: List[str] = []
    for stem in exe_stems:
        key = stem.lower()
        if key in _NOT_APPS:
            continue
        name = _FRIENDLY_NAMES.get(key, stem[:1].upper() + stem[1:])
        if name not in names:
            names.append(name)
    if not names:
        return ""
    return names[0] if len(names) == 1 else ", ".join(names[:-1]) + " y " + names[-1]


def _visible_window_processes() -> List[str]:
    """Exe stems of the top-level windows the user sees (taskbar-like: titled, unowned, not cloaked or tool)."""
    _attach_user_desktop()
    user32, dwmapi = ctypes.windll.user32, ctypes.windll.dwmapi
    GW_OWNER, GWL_EXSTYLE, WS_EX_TOOLWINDOW, DWMWA_CLOAKED = 4, -20, 0x00000080, 14
    stems: List[str] = []

    def callback(hwnd, _):
        if not user32.IsWindowVisible(hwnd) or user32.GetWindowTextLengthW(hwnd) == 0:
            return True
        if user32.GetWindow(hwnd, GW_OWNER) or user32.GetWindowLongW(hwnd, GWL_EXSTYLE) & WS_EX_TOOLWINDOW:
            return True
        cloaked = wintypes.DWORD(0)  # suspended UWP apps and windows on other virtual desktops
        dwmapi.DwmGetWindowAttribute(hwnd, DWMWA_CLOAKED, ctypes.byref(cloaked), ctypes.sizeof(cloaked))
        if cloaked.value:
            return True
        pid = wintypes.DWORD(0)
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        try:
            stems.append(Path(psutil.Process(pid.value).name()).stem)
        except (psutil.Error, OSError):
            pass
        return True

    WNDENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    user32.EnumWindows(WNDENUMPROC(callback), 0)
    return stems


@tool(
    name="list_open_apps",
    description="Dice qué aplicaciones tiene abiertas el usuario ahora mismo (las ventanas visibles)."
)
def list_open_apps() -> Dict[str, Any]:
    """Lista las apps con ventanas visibles."""
    spoken = _spoken_app_list(_visible_window_processes())
    if not spoken:
        return {"ok": True, "result": "No veo ninguna aplicación abierta."}
    return {"ok": True, "result": f"Tienes abiertos: {spoken}."}
