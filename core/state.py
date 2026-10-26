"""
Miku Assistant - What the PC looks like right now, for the model.

Each request carries this snapshot (apps, volume, timers, Opera tabs and visible search results), so the model
decides from facts in the same request: "cierra todas menos la de T y T", "la segunda opción", "¿lo guardaste?"
used to be guesses. Read-only and best effort: a part that fails is left out, never the whole turn.
"""

from __future__ import annotations

import logging
from typing import List

from core.browser import bridge

logger = logging.getLogger("miku.state")


def describe_pc() -> str:
    """A short plain-text snapshot. Blocking (window list, COM for the volume): call it from a thread."""
    lines: List[str] = ["[Estado del PC ahora mismo; no lo leas en voz alta]"]
    try:
        from core.tools.apps import _spoken_app_list, _visible_window_processes
        lines.append(f"Apps abiertas: {_spoken_app_list(_visible_window_processes()) or 'ninguna'}.")
    except Exception as e:
        logger.debug("No app list for the state: %s", e)
    try:
        import comtypes
        from pycaw.pycaw import AudioUtilities
        comtypes.CoInitialize()
        # The default output only: listing every device (what the volume tools do) took ~300 ms per request
        ep = AudioUtilities.GetSpeakers().EndpointVolume
        level = round(ep.GetMasterVolumeLevelScalar() * 100)
        lines.append(f"Volumen: {level}%{' (silenciado)' if ep.GetMute() else ''}.")
    except Exception as e:
        logger.debug("No volume for the state: %s", e)
    from core.tools.timers import describe_timers
    if timers := describe_timers():
        lines.append(f"Temporizadores y recordatorios: {timers}.")
    try:
        from core.tools.notes import describe_pending
        if pending := describe_pending():
            lines.append(f"Pendientes del usuario: {pending}.")
    except OSError as e:
        logger.debug("No notes for the state: %s", e)
    lines.append(bridge.describe())
    return "\n".join(lines)
