"""
Miku Assistant - OBS by voice (tools/obs.py)

Clips from the replay buffer, recording and scenes, through the WebSocket server built into OBS 28+ (protocol v5).
One short connection per order: tools run in worker threads, so the sync client of `websockets` is enough.
Password in .env as OBS_PASSWORD (Tools -> WebSocket Server Settings in OBS); OBS_URL to change the address.
Streaming is left out on purpose: a misheard phrase must never go live.
"""

import base64
import difflib
import hashlib
import json
import logging
import os
from pathlib import Path
from typing import Any, Dict, Optional

from core.tools import tool

logger = logging.getLogger("miku.tools.obs")

TIMEOUT_S = 3.0
ENV_FILE = Path(__file__).resolve().parents[2] / ".env"
NOT_RUNNING = ("OBS no está abierto o su servidor WebSocket está apagado. Actívalo en OBS: Herramientas, "
               "Ajustes del servidor WebSocket.")
# requestStatus codes of obs-websocket 5
OUTPUT_RUNNING, OUTPUT_NOT_RUNNING = 500, 501


class ObsError(Exception):
    def __init__(self, message: str, code: int = 0) -> None:
        super().__init__(message)
        self.code = code


def _password() -> str:
    """Read from .env on every order: fixing a wrong password needs no restart."""
    from dotenv import dotenv_values
    return dotenv_values(ENV_FILE).get("OBS_PASSWORD") or os.getenv("OBS_PASSWORD", "")


def _auth(password: str, salt: str, challenge: str) -> str:
    secret = base64.b64encode(hashlib.sha256((password + salt).encode()).digest()).decode()
    return base64.b64encode(hashlib.sha256((secret + challenge).encode()).digest()).decode()


def _request(request_type: str, data: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Connects, identifies, sends one request and returns its responseData. Raises ObsError."""
    from websockets.exceptions import ConnectionClosed, WebSocketException
    from websockets.sync.client import connect

    url = os.getenv("OBS_URL", "ws://127.0.0.1:4455")
    try:
        with connect(url, open_timeout=TIMEOUT_S, subprotocols=["obswebsocket.json"]) as ws:
            hello = json.loads(ws.recv(timeout=TIMEOUT_S))["d"]
            identify: Dict[str, Any] = {"rpcVersion": 1, "eventSubscriptions": 0}  # no events: just the answer
            if challenge := hello.get("authentication"):
                password = _password()
                if not password:
                    raise ObsError("OBS pide contraseña: ponla en el archivo .env como OBS_PASSWORD.")
                identify["authentication"] = _auth(password, challenge["salt"], challenge["challenge"])
            ws.send(json.dumps({"op": 1, "d": identify}))
            ws.recv(timeout=TIMEOUT_S)  # Identified (op 2); a wrong password closes the connection instead
            ws.send(json.dumps({"op": 6, "d": {"requestType": request_type, "requestId": "miku",
                                               "requestData": data or {}}}))
            while True:
                msg = json.loads(ws.recv(timeout=TIMEOUT_S))
                if msg.get("op") == 7:
                    break
    except ConnectionClosed as e:
        if e.rcvd and e.rcvd.code == 4009:
            raise ObsError("OBS rechazó la contraseña: revisa OBS_PASSWORD en el archivo .env.") from e
        raise ObsError(f"OBS cerró la conexión ({e}).") from e
    except (OSError, TimeoutError, WebSocketException) as e:  # refused, no answer, not an OBS server
        raise ObsError(NOT_RUNNING) from e
    status = msg["d"]["requestStatus"]
    if not status.get("result"):
        raise ObsError(status.get("comment") or f"error {status.get('code')}", status.get("code", 0))
    return msg["d"].get("responseData") or {}


def obs_open() -> bool:
    """OBS is running: only then do loose phrases like "guarda eso" mean a clip."""
    import psutil
    return any((p.info.get("name") or "").lower() in ("obs64.exe", "obs32.exe", "obs.exe")
               for p in psutil.process_iter(["name"]))


def _clip() -> Dict[str, Any]:
    if not _request("GetReplayBufferStatus").get("outputActive"):
        try:
            _request("StartReplayBuffer")
        except ObsError as e:
            return {"ok": False, "result": f"No pude encender el búfer de repetición ({e}). Actívalo en OBS: "
                                           "Ajustes, Salida, Búfer de repetición."}
        # What happened before this moment is not in the buffer: say so instead of saving an empty clip
        return {"ok": False, "result": "El búfer de repetición estaba apagado: ya lo encendí. Desde ahora sí puedo "
                                       "guardar clips."}
    _request("SaveReplayBuffer")
    return {"ok": True, "result": "¡Clip guardado!"}


def _scene(name: str) -> Dict[str, Any]:
    scenes = [s.get("sceneName", "") for s in _request("GetSceneList").get("scenes", [])]
    lowered = {s.lower(): s for s in scenes}
    want = name.strip().lower()
    match = lowered.get(want) or next((s for low, s in lowered.items() if want and want in low), None)
    if match is None:
        close = difflib.get_close_matches(want, list(lowered), n=1, cutoff=0.6)
        match = lowered[close[0]] if close else None
    if match is None:
        return {"ok": False, "result": f"No encontré la escena '{name}'. Tienes: {', '.join(scenes) or 'ninguna'}."}
    _request("SetCurrentProgramScene", {"sceneName": match})
    return {"ok": True, "result": f"Cambié a la escena {match}."}


@tool(
    name="obs",
    description=(
        "Controla OBS Studio. action = clip (guarda los últimos segundos del búfer de repetición: 'guarda eso') | "
        "record_start | record_stop | scene (cambia a la escena 'scene', por su nombre)."
    ),
)
def obs(action: str, scene: str = "") -> Dict[str, Any]:
    """Clips, grabación y escenas de OBS."""
    act = action.strip().lower()
    try:
        if act == "clip":
            return _clip()
        if act == "record_start":
            try:
                _request("StartRecord")
            except ObsError as e:
                if e.code == OUTPUT_RUNNING:
                    return {"ok": True, "result": "Ya estaba grabando."}
                raise
            return {"ok": True, "result": "¡Empecé a grabar!"}
        if act == "record_stop":
            try:
                _request("StopRecord")
            except ObsError as e:
                if e.code == OUTPUT_NOT_RUNNING:
                    return {"ok": True, "result": "No estaba grabando."}
                raise
            return {"ok": True, "result": "Paré la grabación."}
        if act == "scene":
            return _scene(scene) if scene.strip() else {"ok": False, "result": "¿A qué escena cambio?"}
    except ObsError as e:
        logger.info("OBS %s failed: %s", act, e)
        return {"ok": False, "result": str(e) if str(e).startswith("OBS") else f"OBS no pudo: {e}"}
    return {"ok": False, "result": f"No sé hacer '{action}' en OBS (clip, record_start, record_stop, scene)."}
