"""Started by miku.exe, the backend shuts down when miku.exe is gone (closed, crashed or killed), so a lost app never
leaves the mic open. A throwaway process plays miku.exe.

Run: core\\.venv\\Scripts\\python.exe -m tests.test_parent_watch  (or with pytest)
"""

import asyncio
import os
import subprocess
import time
import types

import core.__main__ as main_mod


def test_backend_stops_when_miku_exe_is_gone():
    # A plain exe: in the venv, sys.executable is a launcher whose child would outlive the kill
    parent = subprocess.Popen(["ping", "-n", "60", "127.0.0.1"], stdout=subprocess.DEVNULL, creationflags=0x08000000)
    exited = []
    main_mod.os = types.SimpleNamespace(environ={"MIKU_PARENT_PID": str(parent.pid)}, _exit=exited.append)
    main_mod.PARENT_CHECK_S, main_mod.PARENT_GRACE_S = 0.1, 0.3

    async def run():
        stop = asyncio.Event()
        main_mod.watch_parent(asyncio.get_running_loop(), stop)
        await asyncio.sleep(0.5)
        assert not stop.is_set(), "alive parent: keep running"
        parent.kill()
        await asyncio.wait_for(stop.wait(), 3)

    try:
        asyncio.run(run())
        time.sleep(0.6)  # past PARENT_GRACE_S: the thread calls _exit, which must still be the fake one
        assert exited == [0], "a stuck shutdown still ends the process"
    finally:
        parent.kill()
        main_mod.os = os

    # Started by hand (no MIKU_PARENT_PID): nothing to watch
    main_mod.os = types.SimpleNamespace(environ={}, _exit=exited.append)
    try:
        assert main_mod.watch_parent(None, None) is None
    finally:
        main_mod.os = os


if __name__ == "__main__":
    test_backend_stops_when_miku_exe_is_gone()
    print("ok")
