"""H-006, H-007, H-008: open_app/close_app must not run commands or kill unrelated processes.

Nothing is really launched or killed: _launch_target and psutil are replaced by fakes.
Run: core\\.venv\\Scripts\\python.exe -m tests.test_apps_tools  (or with pytest)
"""

import core.tools.apps as apps


class FakeProc:
    def __init__(self, pid, name):
        self.info = {"pid": pid, "name": name}
        self.pid = pid
        self.terminated = False

    def terminate(self):
        self.terminated = True

    def kill(self):
        self.terminated = True


def _with_fakes(procs, launched):
    apps._launch_target = lambda t: launched.append(t) or False
    apps._attach_user_desktop = lambda: None
    apps._index_start_menu_shortcuts = lambda: None
    apps._SHORTCUTS_CACHE.clear()
    apps._SHORTCUTS_CACHE["windows powershell"] = r"C:\fake\Windows PowerShell.lnk"
    apps.psutil.process_iter = lambda attrs: iter(procs)
    apps.psutil.wait_procs = lambda ps, timeout: (ps, [])


def test_open_app_never_passes_arguments_or_shells():
    launched = []
    _with_fakes([], launched)
    for name in ("powershell -c start-process calc", 'notepad" & calc', "cmd", "terminal",
                 "powershell", "C:\\Windows\\System32\\calc.exe"):
        apps.open_app(name)
    assert launched == [], f"nothing unsafe may be launched, got {launched}"

    apps.open_app("spotify")  # alias still works (retried once because the fake launch "fails")
    assert set(launched) == {"spotify.exe"}, launched


def test_close_app_exact_match_only():
    procs = [FakeProc(9001, "notepad.exe"), FakeProc(9002, "notepad++.exe"),
             FakeProc(9003, "explorer.exe"), FakeProc(9004, "Code.exe")]
    _with_fakes(procs, [])

    apps.close_app("e")
    assert not any(p.terminated for p in procs), "a single letter must not kill anything"

    apps.close_app("explorer")
    assert not procs[2].terminated, "protected processes are never closed"

    res = apps.close_app("bloc de notas")
    assert res["ok"] and procs[0].terminated and not procs[1].terminated, res


def test_open_app_partial_match_needs_a_real_word():
    # On the user's real Start Menu, "abre mi" opened Microsoft Edge and "abre la" a random app
    launched = []
    _with_fakes([], launched)
    apps._launch_target = lambda t: launched.append(t) or t.endswith(".lnk")
    apps._SHORTCUTS_CACHE.update({
        "microsoft edge": r"C:\fake\Microsoft Edge.lnk",
        "administrative tools": r"C:\fake\Administrative Tools.lnk",
        "visual studio installer": r"C:\a\Visual Studio Installer.lnk",
        "visual studio code": r"C:\a\very\long\install\path\Visual Studio Code.lnk",
    })
    for name in ("mi", "la", "e", "ra"):
        assert not apps.open_app(name)["ok"] and not any(t.endswith(".lnk") for t in launched), (name, launched)
    launched.clear()
    assert apps.open_app("visual")["ok"] and launched[-1].endswith("Visual Studio Code.lnk"), launched
    launched.clear()
    assert apps.open_app("admin")["ok"] and launched == [r"C:\fake\Administrative Tools.lnk"], launched




def test_open_opera_when_running_brings_it_up_instead_of_a_new_window():
    launched = []
    _with_fakes([], launched)
    apps._find_window = lambda name, exe=None: 99 if exe == "opera" else None
    apps._bring_to_front = lambda hwnd: hwnd == 99
    res = apps.open_app("opera")
    assert res["ok"] and "ya estaba abierto" in res["result"] and launched == [], (res, launched)

if __name__ == "__main__":
    test_open_app_never_passes_arguments_or_shells()
    test_close_app_exact_match_only()
    test_open_app_partial_match_needs_a_real_word()
    test_open_opera_when_running_brings_it_up_instead_of_a_new_window()
    print("ok")
