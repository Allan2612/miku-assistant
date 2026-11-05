"""
Miku Assistant - Windows by number (tools/windows.py)

Like Opera's tabs: the PC state lists every window the user sees with its number (its handle), and `windows`
acts on those numbers. Finding a window by a piece of its title (the old focus_app / window_action) took the
first one that matched, which often was not the one meant.
"""

import contextlib
import ctypes
import logging
from ctypes import wintypes
from pathlib import Path
from typing import Any, Dict, Iterator, List

import psutil

from core.tools import tool
from core.tools.apps import _FRIENDLY_NAMES, _NOT_APPS, _attach_user_desktop, _bring_to_front

logger = logging.getLogger("miku.tools.windows")

GW_OWNER, GWL_EXSTYLE, WS_EX_TOOLWINDOW, DWMWA_CLOAKED = 4, -20, 0x00000080, 14
SW_MAXIMIZE, SW_RESTORE = 3, 9
# The NOACTIVATE variants leave the focus where it is: SW_MINIMIZE (6) activates the next window, which could
# take it from a game the user is playing
SW_SHOWMINNOACTIVE, SW_SHOWNOACTIVATE = 7, 4
WM_CLOSE = 0x0010
MONITOR_DEFAULTTONEAREST = 2
SWP_NOZORDER, SWP_NOACTIVATE = 0x0004, 0x0010
_DPI_AWARE_PER_MONITOR_V2 = -4
MAX_WINDOWS_IN_STATE = 25  # every window rides in every request: keep the prompt bounded


class _MONITORINFO(ctypes.Structure):
    _fields_ = [("cbSize", wintypes.DWORD), ("rcMonitor", wintypes.RECT), ("rcWork", wintypes.RECT),
                ("dwFlags", wintypes.DWORD), ("szDevice", ctypes.c_wchar * 32)]


def _user32() -> Any:
    u = ctypes.windll.user32
    # 64-bit handles: without explicit types ctypes truncates them
    u.MonitorFromWindow.restype = wintypes.HMONITOR
    u.MonitorFromWindow.argtypes = [wintypes.HWND, wintypes.DWORD]
    u.GetMonitorInfoW.argtypes = [wintypes.HMONITOR, ctypes.POINTER(_MONITORINFO)]
    u.SetThreadDpiAwarenessContext.restype = ctypes.c_void_p
    u.SetThreadDpiAwarenessContext.argtypes = [ctypes.c_void_p]
    return u


@contextlib.contextmanager
def _physical_pixels(u: Any) -> Iterator[None]:
    """Real pixels for this thread: with display scaling, positions would otherwise be scaled guesses."""
    old = u.SetThreadDpiAwarenessContext(_DPI_AWARE_PER_MONITOR_V2)
    try:
        yield
    finally:
        if old:
            u.SetThreadDpiAwarenessContext(old)


def _monitor_info(u: Any, hmon: Any) -> _MONITORINFO:
    info = _MONITORINFO(cbSize=ctypes.sizeof(_MONITORINFO))
    u.GetMonitorInfoW(hmon, ctypes.byref(info))
    return info


def _work_area(u: Any, hmon: Any) -> wintypes.RECT:
    return _monitor_info(u, hmon).rcWork


def _display_order(info: Any) -> tuple:
    return len(info.szDevice), info.szDevice  # DISPLAY10 goes after DISPLAY2


def _monitor_infos(u: Any) -> List[_MONITORINFO]:
    """In Windows' own order, so monitor 2 is what the user calls "la pantalla 2". Left to right, that one was
    monitor 1: "A la pantalla izquierda, o sea, a la pantalla 2" (log 4-nov)."""
    handles: List[Any] = []
    proc = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HMONITOR, wintypes.HDC, ctypes.POINTER(wintypes.RECT),
                              wintypes.LPARAM)
    u.EnumDisplayMonitors(None, None, proc(lambda hmon, hdc, rect, data: handles.append(hmon) or True), 0)
    return sorted((_monitor_info(u, h) for h in handles), key=_display_order)


def _monitors(u: Any) -> List[wintypes.RECT]:
    """Work areas (screen minus taskbar), by monitor number."""
    return [info.rcWork for info in _monitor_infos(u)]


def _layout_text(infos: List[Any]) -> str:
    """Which number is where, for the state: "Monitores: 2 = izquierda; 1 = derecha, principal."
    shortcut: side by side only; screens stacked one above the other get left/right names, fix if someone has them."""
    numbered = sorted(enumerate(infos, 1), key=lambda pair: pair[1].rcMonitor.left)
    parts = []
    for rank, (n, info) in enumerate(numbered):
        place = "izquierda" if rank == 0 else "derecha" if rank == len(numbered) - 1 else "centro"
        parts.append(f"{n} = {place}{', principal' if info.dwFlags & 1 else ''}")
    return f"Monitores: {'; '.join(parts)}."


def _monitor_number(u: Any, hwnd: int, monitors: List[wintypes.RECT]) -> int:
    area = _work_area(u, u.MonitorFromWindow(hwnd, MONITOR_DEFAULTTONEAREST))
    return next((n for n, r in enumerate(monitors, 1) if (r.left, r.top) == (area.left, area.top)), 1)


def visible_windows() -> List[Dict[str, Any]]:
    """The top-level windows the user sees, front to back (taskbar-like: titled, unowned, not cloaked or tool)."""
    _attach_user_desktop()
    u, dwm = _user32(), ctypes.windll.dwmapi
    foreground = u.GetForegroundWindow()
    found: List[Dict[str, Any]] = []
    with _physical_pixels(u):
        monitors = _monitors(u)

        def callback(hwnd, _):
            if not u.IsWindowVisible(hwnd) or u.GetWindowTextLengthW(hwnd) == 0:
                return True
            if u.GetWindow(hwnd, GW_OWNER) or u.GetWindowLongW(hwnd, GWL_EXSTYLE) & WS_EX_TOOLWINDOW:
                return True
            cloaked = wintypes.DWORD(0)  # suspended UWP apps and windows on other virtual desktops
            dwm.DwmGetWindowAttribute(hwnd, DWMWA_CLOAKED, ctypes.byref(cloaked), ctypes.sizeof(cloaked))
            if cloaked.value:
                return True
            pid = wintypes.DWORD(0)
            u.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
            try:
                exe = Path(psutil.Process(pid.value).name()).stem
            except (psutil.Error, OSError):
                return True
            size = u.GetWindowTextLengthW(hwnd)
            title = ctypes.create_unicode_buffer(size + 1)
            u.GetWindowTextW(hwnd, title, size + 1)
            found.append({
                "id": int(hwnd), "exe": exe, "title": title.value, "active": hwnd == foreground,
                "minimized": bool(u.IsIconic(hwnd)), "maximized": bool(u.IsZoomed(hwnd)),
                "monitor": _monitor_number(u, hwnd, monitors), "monitors": len(monitors),
            })
            return True

        u.EnumWindows(ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)(callback), 0)
    return found


# SHQueryUserNotificationState: busy (a full-screen app), a Direct3D game at full screen, presentation mode.
# The same check Windows' own "Do not disturb when playing a game / using an app in full screen" uses
_QUNS_FULLSCREEN = {2, 3, 4}


def fullscreen_app_in_front() -> bool:
    """A game or a video at full screen is in front. Microseconds; False if Windows cannot tell."""
    state = ctypes.c_int(0)
    try:
        if ctypes.windll.shell32.SHQueryUserNotificationState(ctypes.byref(state)) != 0:
            return False
    except (AttributeError, OSError):
        return False
    return state.value in _QUNS_FULLSCREEN


def _app_name(w: Dict[str, Any]) -> str:
    exe = w["exe"]
    return _FRIENDLY_NAMES.get(exe.lower(), exe[:1].upper() + exe[1:])


def describe_windows() -> str:
    """The windows as lines for the model's state block."""
    wins = [w for w in visible_windows() if w["exe"].lower() not in _NOT_APPS]
    if not wins:
        return "Ventanas abiertas: ninguna."
    several_monitors = wins[0]["monitors"] > 1
    lines = ["Ventanas abiertas, de la de delante a la de atrás (usa el número como window_id):"]
    if several_monitors:
        lines.insert(0, _layout_text(_monitor_infos(_user32())))
    for w in wins[:MAX_WINDOWS_IN_STATE]:
        name, title = _app_name(w), w["title"][:60]
        marks = [m for m, on in (("activa", w["active"]), ("minimizada", w["minimized"]),
                                 ("maximizada", w["maximized"])) if on]
        if several_monitors:
            marks.append(f"monitor {w['monitor']}")
        shown = name if title.lower() in (name.lower(), w["exe"].lower()) else f"{name} — {title}"
        lines.append(f"  [{w['id']}] {shown}{' — ' + ', '.join(marks) if marks else ''}")
    if len(wins) > MAX_WINDOWS_IN_STATE:
        lines.append(f"  ... y {len(wins) - MAX_WINDOWS_IN_STATE} ventanas más")
    return "\n".join(lines)


def _place(hwnd: int, x: int, y: int, width: int, height: int) -> None:
    u = _user32()
    with _physical_pixels(u):
        u.ShowWindow(hwnd, SW_SHOWNOACTIVATE)  # out of maximized (it would ignore a new size), focus untouched
        u.SetWindowPos(hwnd, None, x, y, width, height, SWP_NOZORDER | SWP_NOACTIVATE)


def _apply(action: str, w: Dict[str, Any], monitor: int) -> None:
    """Does one action on one window. Never takes the focus except for "focus" itself."""
    u, hwnd = _user32(), w["id"]
    if action == "focus":
        _bring_to_front(hwnd)
    elif action in ("minimize", "maximize", "restore"):
        u.ShowWindow(hwnd, {"minimize": SW_SHOWMINNOACTIVE, "maximize": SW_MAXIMIZE, "restore": SW_RESTORE}[action])
    elif action == "close":
        # Asks the app to close, as the X button does: it can still ask to save first
        u.PostMessageW(hwnd, WM_CLOSE, 0, 0)
    else:
        with _physical_pixels(u):
            area = _monitors(u)[(monitor or w["monitor"]) - 1]
        width, height = area.right - area.left, area.bottom - area.top
        if action == "left":
            _place(hwnd, area.left, area.top, width // 2, height)
        elif action == "right":
            _place(hwnd, area.left + width // 2, area.top, width - width // 2, height)
        elif action == "move":
            _place(hwnd, area.left + width // 8, area.top + height // 8, width * 3 // 4, height * 3 // 4)
            if w["maximized"]:
                u.ShowWindow(hwnd, SW_MAXIMIZE)


_ACTIONS = {"focus": "Te puse delante", "minimize": "Minimicé", "maximize": "Maximicé", "restore": "Restauré",
            "close": "Cerré", "left": "Puse a la izquierda", "right": "Puse a la derecha", "move": "Moví"}


@tool(
    name="windows",
    description=(
        "Maneja ventanas de Windows por su número (window_id) del estado del PC. action = focus (traerla delante: "
        "'ponlo en foco', 'enfócalo', 'tráelo al frente', 'abre la ventana X'; si no dice cuál, la última de la que "
        "hablaron) | minimize | maximize | restore | close (como la X: la app puede pedir guardar) | left / right "
        "(la mitad izquierda o derecha de SU monitor, solo si pide una mitad o un lado) | move (a otro monitor: 'a la "
        "pantalla derecha', 'izquierda', 'principal', 'la otra', 'la 2'; monitor = su número en la línea Monitores "
        "del estado). window_ids: una o varias; para 'minimiza todo menos "
        "X', pasa todas las demás. Para pestañas de Opera usa browser_tabs; para cerrar un programa entero, close_app."
    ),
)
def windows(action: str, window_ids: List[int], monitor: int = 0) -> Dict[str, Any]:
    """Activa, minimiza, maximiza, restaura, cierra, coloca o mueve ventanas concretas por su número."""
    act = action.strip().lower()
    if act not in _ACTIONS:
        return {"ok": False, "result": f"No sé hacer '{action}' con ventanas ({', '.join(_ACTIONS)})."}
    known = {w["id"]: w for w in visible_windows() if w["exe"].lower() not in _NOT_APPS}
    ids = [int(i) for i in window_ids or []]
    unknown = [i for i in ids if i not in known]
    if not ids or unknown:
        return {"ok": False, "result": f"No hay ventanas con esos números ({unknown or 'ninguno'}); mira el estado."}
    monitors = next(iter(known.values()))["monitors"]
    if act == "move" and not 1 <= int(monitor) <= monitors:
        return {"ok": False, "result": f"Hay {monitors} monitor(es); dime a cuál (1 a {monitors})."}
    targets = [known[i] for i in ids][:1] if act == "focus" else [known[i] for i in ids]
    for w in targets:
        try:
            _apply(act, w, int(monitor))
        except OSError as e:
            return {"ok": False, "result": f"No pude con {_app_name(w)}: {e}"}
    what = _app_name(targets[0]) if len(targets) == 1 else f"{len(targets)} ventanas"
    where = f" al monitor {monitor}" if act == "move" else ""
    return {"ok": True, "result": f"{_ACTIONS[act]} {what}{where}."}
