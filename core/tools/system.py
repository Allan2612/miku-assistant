"""
Miku Assistant - System Tools (tools/system.py)
"""

import ctypes
import datetime
import logging
import os
import subprocess
from typing import Dict, Any
import psutil

from core.tools import tool

logger = logging.getLogger("miku.tools.system")

DIAS_SEMANA = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]
MESES = [
    "enero", "febrero", "marzo", "abril", "mayo", "junio",
    "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre"
]


@tool(
    name="get_datetime",
    description="Devuelve la fecha actual, día de la semana y hora exacta del sistema."
)
def get_datetime() -> Dict[str, Any]:
    """Obtiene la fecha y hora actual en español."""
    now = datetime.datetime.now()
    dia = DIAS_SEMANA[now.weekday()]
    mes = MESES[now.month - 1]
    hora_str = now.strftime("%H:%M")
    texto = f"Hoy es {dia} {now.day} de {mes} de {now.year}, y son las {hora_str}."
    return {"ok": True, "result": texto}


@tool(
    name="get_system_status",
    description="Obtiene las métricas de estado del sistema: uso de CPU %, memoria RAM usada y libre, y espacio en disco."
)
def get_system_status() -> Dict[str, Any]:
    """Devuelve el uso de recursos del PC."""
    cpu_percent = psutil.cpu_percent(interval=0.1)
    mem = psutil.virtual_memory()
    disk = psutil.disk_usage("C:")

    ram_used_gb = mem.used / (1024**3)
    ram_total_gb = mem.total / (1024**3)
    disk_free_gb = disk.free / (1024**3)

    texto = (
        f"CPU al {cpu_percent:.0f}%, RAM al {mem.percent:.0f}% "
        f"({ram_used_gb:.1f} GB de {ram_total_gb:.1f} GB usados) "
        f"y {disk_free_gb:.0f} GB libres en disco C:."
    )
    return {"ok": True, "result": texto}


@tool(
    name="lock_pc",
    description="Bloquea la sesión actual de Windows (pantalla de bloqueo)."
)
def lock_pc() -> Dict[str, Any]:
    """Bloquea la sesión de usuario."""
    ctypes.windll.user32.LockWorkStation()
    return {"ok": True, "result": "Sesión de Windows bloqueada."}


@tool(
    name="shutdown_pc",
    description="Apaga, reinicia o suspende la PC. Requiere confirmación explícita (mode: shutdown | restart | sleep).",
    destructive=True
)
def shutdown_pc(mode: str = "shutdown", confirmed: bool = False) -> Dict[str, Any]:
    """Apaga o reinicia el sistema con confirmación previa obligatoria."""
    # Normalize once so the confirmation question and the executed action always match (H-015)
    m = {"apagar": "shutdown", "reiniciar": "restart", "suspender": "sleep"}.get(mode.strip().lower(), mode.strip().lower())
    if m not in ("shutdown", "restart", "sleep"):
        return {"ok": False, "result": f"Modo desconocido '{mode}' (usa shutdown, restart o sleep)."}

    if not confirmed:
        action_name = {"shutdown": "apagar", "restart": "reiniciar", "sleep": "suspender"}[m]
        return {
            "ok": False,
            "requires_confirmation": True,
            "result": f"¿Estás seguro de que deseas {action_name} la computadora? Por favor confirma diciendo sí."
        }

    if m == "shutdown":
        subprocess.run(["shutdown", "/s", "/t", "30", "/c", "Miku Assistant: Apagando el equipo en 30 segundos."], check=False)
        return {"ok": True, "result": "El equipo se apagará en 30 segundos (puedes cancelar con 'shutdown /a')."}
    if m == "restart":
        subprocess.run(["shutdown", "/r", "/t", "30", "/c", "Miku Assistant: Reiniciando el equipo en 30 segundos."], check=False)
        return {"ok": True, "result": "El equipo se reiniciará en 30 segundos."}
    ctypes.windll.Powrprof.SetSuspendState(0, 1, 0)
    return {"ok": True, "result": "Equipo suspendido."}


def _powershell(script: str, env_text: str = "") -> subprocess.CompletedProcess:
    # Text goes through an env var, never into the command line: no quoting or injection issues
    env = dict(os.environ, MIKU_CLIP=env_text)
    return subprocess.run(
        ["powershell", "-NoProfile", "-NonInteractive", "-Command",
         "[Console]::OutputEncoding = [Text.Encoding]::UTF8; " + script],
        env=env, capture_output=True, timeout=8, creationflags=subprocess.CREATE_NO_WINDOW,
    )


@tool(
    name="copy_to_clipboard",
    description="Copia un texto al portapapeles de Windows para que el usuario lo pegue con Ctrl+V."
)
def copy_to_clipboard(text: str) -> Dict[str, Any]:
    """Pone texto en el portapapeles."""
    if not text.strip():
        return {"ok": False, "result": "No hay nada que copiar."}
    if _powershell("Set-Clipboard -Value $env:MIKU_CLIP", text).returncode != 0:
        return {"ok": False, "result": "No pude copiar al portapapeles."}
    return {"ok": True, "result": "Copiado al portapapeles."}


@tool(
    name="read_clipboard",
    description="Lee en voz alta el texto que hay en el portapapeles de Windows (lo último que copió el usuario)."
)
def read_clipboard() -> Dict[str, Any]:
    """Devuelve el texto del portapapeles (máx 400 caracteres)."""
    proc = _powershell("Get-Clipboard -Raw")
    text = proc.stdout.decode("utf-8", "replace").strip()
    if proc.returncode != 0 or not text:
        return {"ok": True, "result": "El portapapeles está vacío o no tiene texto."}
    return {"ok": True, "result": text[:400] + ("..." if len(text) > 400 else "")}


@tool(
    name="quota_status",
    description="Dice cuántas peticiones a Gemini lleva hoy Miku y cuántas le quedan ('¿cuánta cuota te queda?').",
)
def quota_status() -> Dict[str, Any]:
    """Peticiones de hoy contra el límite diario del plan gratuito."""
    from core import quota
    from core.config import load_config
    return {"ok": True, "result": quota.describe(load_config().llm.model)}
