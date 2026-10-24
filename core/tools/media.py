"""
Miku Assistant - Media and Audio Tools (tools/media.py)
"""

import ctypes
import logging
import re
from typing import Dict, List, Any, Optional
from pycaw.pycaw import AudioUtilities
from pycaw.constants import AudioDeviceState

from core.tools import tool
from core.tools._win import attach_user_desktop as _attach_user_desktop

logger = logging.getLogger("miku.tools.media")

# Windows Virtual Keys for Media
VK_MEDIA_NEXT_TRACK = 0xB0
VK_MEDIA_PREV_TRACK = 0xB1
VK_MEDIA_STOP = 0xB2
VK_MEDIA_PLAY_PAUSE = 0xB3


def _press_key(vk_code: int) -> None:
    """Sends extended keyboard event for Windows media control keys on user desktop."""
    _attach_user_desktop()
    user32 = ctypes.windll.user32
    KEYEVENTF_EXTENDEDKEY = 0x0001
    KEYEVENTF_KEYUP = 0x0002
    user32.keybd_event(vk_code, 0, KEYEVENTF_EXTENDEDKEY, 0)
    user32.keybd_event(vk_code, 0, KEYEVENTF_EXTENDEDKEY | KEYEVENTF_KEYUP, 0)


def _get_active_output_endpoints() -> List[Any]:
    """Retrieves all active audio output endpoints (headsets, monitors, speakers)."""
    try:
        import comtypes
        comtypes.CoInitialize()
    except Exception:
        pass

    endpoints = []
    try:
        speakers = AudioUtilities.GetSpeakers()
        if speakers and hasattr(speakers, "EndpointVolume"):
            endpoints.append(speakers.EndpointVolume)
    except Exception:
        pass

    try:
        for d in AudioUtilities.GetAllDevices():
            if d.state == AudioDeviceState.Active and getattr(d, "id", "").startswith("{0.0.0."):
                try:
                    ep = d.EndpointVolume
                    if ep and ep not in endpoints:
                        endpoints.append(ep)
                except Exception:
                    pass
    except Exception:
        pass

    return endpoints


@tool(
    name="media_control",
    description="Controla la reproducción multimedia de Windows (play_pause, next, previous, stop)."
)
def media_control(action: str) -> Dict[str, Any]:
    """Envía comandos multimedia virtuales."""
    act = action.strip().lower()

    # next/prev/stop first: "siguiente canción" also contains play/pause words (H-013)
    if any(k in act for k in ("next", "siguient", "pasar", "adelant")):
        _press_key(VK_MEDIA_NEXT_TRACK)
        return {"ok": True, "result": "Pasando a la siguiente canción."}
    elif any(k in act for k in ("prev", "anterior", "retroced", "atras", "atrás")):
        _press_key(VK_MEDIA_PREV_TRACK)
        return {"ok": True, "result": "Volviendo a la canción anterior."}
    elif any(k in act for k in ("stop", "deten", "parar", "frenar")):
        _press_key(VK_MEDIA_STOP)
        return {"ok": True, "result": "Reproducción detenida."}
    elif any(k in act for k in ("play", "pause", "reproduc", "paus", "alternar", "continuar", "cancion", "canción", "musica", "música")):
        _press_key(VK_MEDIA_PLAY_PAUSE)
        # Read aloud when the model adds no text: "Reproducción alternada (play/pause)" sounded like a manual
        return {"ok": True, "result": "¡Listo!"}
    return {"ok": False, "result": f"No reconozco la acción '{action}' (usa play_pause, next, previous o stop)."}


@tool(
    name="set_volume",
    description="Ajusta el volumen maestro del sistema a un nivel exacto de 0 a 100."
)
def set_volume(level: int) -> Dict[str, Any]:
    """Establece el volumen en todos los dispositivos de audio de salida activos."""
    clamped = max(0, min(100, int(level)))
    scalar = clamped / 100.0

    applied = 0
    for endpoint in _get_active_output_endpoints():
        try:
            endpoint.SetMasterVolumeLevelScalar(scalar, None)
            if clamped > 0 and endpoint.GetMute():
                endpoint.SetMute(False, None)
            applied += 1
        except Exception:
            pass

    if not applied:
        return {"ok": False, "result": "No pude cambiar el volumen: no hay dispositivos de salida activos."}
    return {"ok": True, "result": f"Volumen ajustado al {clamped}%."}


@tool(
    name="change_volume",
    description="Modifica el volumen maestro del sistema sumando o restando una cantidad (ej: delta: 10 o delta: -15)."
)
def change_volume(delta: int) -> Dict[str, Any]:
    """Modifica el volumen sumando un delta porcentual en todos los dispositivos de salida."""
    endpoints = _get_active_output_endpoints()
    if not endpoints:
        return {"ok": False, "result": "No se encontraron dispositivos de audio de salida activos."}

    current_scalar = endpoints[0].GetMasterVolumeLevelScalar()
    current_level = int(round(current_scalar * 100))
    new_level = max(0, min(100, current_level + int(delta)))
    new_scalar = new_level / 100.0

    for endpoint in endpoints:
        try:
            endpoint.SetMasterVolumeLevelScalar(new_scalar, None)
            if new_level > 0 and endpoint.GetMute():
                endpoint.SetMute(False, None)
        except Exception:
            pass

    return {"ok": True, "result": f"Volumen cambiado de {current_level}% a {new_level}%."}


@tool(
    name="mute",
    description="Silencia o activa el sonido maestro del sistema (on: true para silenciar, on: false para activar sonido)."
)
def mute(on: Optional[bool] = None, action: str = "", state: str = "") -> Dict[str, Any]:
    """Silencia o reactiva el volumen maestro en todos los dispositivos de salida."""
    if on is None:
        # Whole words, in priority order: substrings turned "activar el silencio" into unmute (H-013)
        words = set(re.findall(r"\w+", (action or state).lower()))
        if words & {"unmute", "desilenciar", "desmutear", "reactivar", "quita", "quitar", "false", "off", "no"}:
            target_on = False
        elif words & {"silencio", "silencia", "silenciar", "mute", "mutea", "mutear", "true", "on"}:
            target_on = True
        else:
            target_on = not (words & {"activa", "activar", "sonido", "enciende"})
    else:
        target_on = bool(on)

    applied = 0
    for endpoint in _get_active_output_endpoints():
        try:
            endpoint.SetMute(target_on, None)
            applied += 1
        except Exception:
            pass
    if not applied:
        return {"ok": False, "result": "No pude cambiar el silencio: no hay dispositivos de salida activos."}
    state_str = "silenciado" if target_on else "reactivado"
    return {"ok": True, "result": f"Sonido {state_str}."}

