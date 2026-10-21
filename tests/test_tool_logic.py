"""H-011, H-013, H-015: tool argument handling. Keys, audio, shutdown and file opening are faked.

Run: core\\.venv\\Scripts\\python.exe -m tests.test_tool_logic  (or with pytest)
"""

from core.tools import note_user_reply
import core.tools.files as files
import core.tools.media as media
import core.tools.system as system


def test_media_control_picks_the_right_key():
    pressed = []
    media._press_key = pressed.append
    media.media_control("siguiente canción")
    media.media_control("canción anterior")
    assert pressed == [media.VK_MEDIA_NEXT_TRACK, media.VK_MEDIA_PREV_TRACK], pressed
    assert not media.media_control("bailar")["ok"]


def test_mute_understands_the_phrase():
    class Ep:
        state = None
        def SetMute(self, on, _):
            Ep.state = on
    media._get_active_output_endpoints = lambda: [Ep()]
    cases = {"activar el silencio": True, "silencia el teléfono": True,
             "quita el silencio": False, "activa el sonido": False}
    for phrase, expected in cases.items():
        media.mute(action=phrase)
        assert Ep.state is expected, (phrase, Ep.state)
    media._get_active_output_endpoints = lambda: []
    assert not media.mute(True)["ok"], "no devices must not report success"


def test_shutdown_question_matches_action():
    ran = []
    system.subprocess.run = lambda args, check: ran.append(args)
    res = system.shutdown_pc(mode="apagar")
    assert "apagar" in res["result"] and not ran, res
    note_user_reply("sí")  # the user, not the LLM, confirms (H-001)
    system.shutdown_pc(mode="apagar", confirmed=True)
    assert ran and ran[0][1] == "/s", ran


def test_open_file_refuses_executables():
    opened = []
    files.os.startfile = opened.append
    files.os.path.exists = lambda p: True
    files._SESSION_FOUND_FILES.update({r"C:\x\setup.exe", r"C:\x\informe.pdf"})
    assert not files.open_file("setup.exe")["ok"]
    assert files.open_file("informe.pdf")["ok"] and opened == [r"C:\x\informe.pdf"], opened


if __name__ == "__main__":
    test_media_control_picks_the_right_key()
    test_mute_understands_the_phrase()
    test_shutdown_question_matches_action()
    test_open_file_refuses_executables()
    print("ok")
