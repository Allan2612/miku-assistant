"""OBS by voice: a fake OBS (obs-websocket 5 with a password) checks the login and every request.

Run: core\\.venv\\Scripts\\python.exe -m tests.test_obs  (or with pytest)
"""

from pathlib import Path
import json
import os
import socket
import threading

from websockets.sync.server import serve

import core.tools.obs as obs

obs.ENV_FILE = Path(__file__).parent / "no.env"  # the real .env must not decide these tests

PASSWORD, SALT, CHALLENGE = "secreto", "sal", "reto"
SCENES = ["Juego", "Pantalla de espera", "Charla"]


def _fake_obs(state):
    def handler(ws):
        ws.send(json.dumps({"op": 0, "d": {"rpcVersion": 1,
                                           "authentication": {"salt": SALT, "challenge": CHALLENGE}}}))
        if json.loads(ws.recv())["d"].get("authentication") != obs._auth(PASSWORD, SALT, CHALLENGE):
            ws.close(4009, "Authentication failed.")
            return
        ws.send(json.dumps({"op": 2, "d": {"negotiatedRpcVersion": 1}}))
        req = json.loads(ws.recv())["d"]
        kind, ok, code, data = req["requestType"], True, 100, {}
        state["requests"].append(kind)
        if kind == "GetReplayBufferStatus":
            data = {"outputActive": state["replay"]}
        elif kind == "StartReplayBuffer":
            state["replay"] = True
        elif kind in ("StartRecord", "StopRecord"):
            starting = kind == "StartRecord"
            if state["recording"] == starting:
                ok, code = False, 500 if starting else 501
            state["recording"] = starting
        elif kind == "GetSceneList":
            data = {"scenes": [{"sceneName": s} for s in SCENES]}
        elif kind == "SetCurrentProgramScene":
            state["scene"] = req["requestData"]["sceneName"]
        ws.send(json.dumps({"op": 7, "d": {"requestType": kind, "requestId": req["requestId"],
                                           "requestStatus": {"result": ok, "code": code}, "responseData": data}}))

    server = serve(handler, "127.0.0.1", 0, subprotocols=["obswebsocket.json"])
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server, server.socket.getsockname()[1]


def test_obs_by_voice():
    # OBS closed: said plainly, with where to turn the server on
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        free_port = s.getsockname()[1]
    os.environ["OBS_URL"] = f"ws://127.0.0.1:{free_port}"
    res = obs.obs("clip")
    assert not res["ok"] and "Ajustes del servidor WebSocket" in res["result"], res

    state = {"replay": False, "recording": False, "scene": "Juego", "requests": []}
    server, port = _fake_obs(state)
    os.environ["OBS_URL"] = f"ws://127.0.0.1:{port}"
    try:
        os.environ["OBS_PASSWORD"] = "otra"
        assert "rechazó la contraseña" in obs.obs("clip")["result"]
        os.environ["OBS_PASSWORD"] = PASSWORD

        # Replay buffer off: she turns it on and says the past cannot be saved; the next clip is saved
        res = obs.obs("clip")
        assert not res["ok"] and "ya lo encendí" in res["result"] and state["replay"], res
        assert obs.obs("clip") == {"ok": True, "result": "¡Clip guardado!"}
        assert state["requests"][-1] == "SaveReplayBuffer"

        assert obs.obs("record_start")["result"] == "¡Empecé a grabar!" and state["recording"]
        assert obs.obs("record_start")["result"] == "Ya estaba grabando."
        assert obs.obs("record_stop")["result"] == "Paré la grabación." and not state["recording"]
        assert obs.obs("record_stop")["result"] == "No estaba grabando."

        assert obs.obs("scene", "espera")["result"] == "Cambié a la escena Pantalla de espera."
        assert obs.obs("scene", "charlas")["ok"] and state["scene"] == "Charla"  # close enough
        res = obs.obs("scene", "cocina")
        assert not res["ok"] and "Juego, Pantalla de espera, Charla" in res["result"], res
        assert "StartStream" not in state["requests"], "never goes live"
    finally:
        server.shutdown()
        os.environ.pop("OBS_URL", None)
        os.environ.pop("OBS_PASSWORD", None)


if __name__ == "__main__":
    test_obs_by_voice()
    print("ok")
