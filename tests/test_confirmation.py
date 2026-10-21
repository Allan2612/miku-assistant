"""H-001: destructive tools run only after the user's own "sí", never on the LLM's confirmed=True.

shutdown is faked: nothing is really shut down.
Run: core\\.venv\\Scripts\\python.exe -m tests.test_confirmation  (or with pytest)
"""

import core.tools as tools
import core.tools.system as system

ran = []
system.subprocess.run = lambda args, check: ran.append(args)
shutdown = tools._TOOL_REGISTRY["shutdown_pc"]


def test_llm_cannot_self_confirm():
    ran.clear()
    tools.note_user_reply("apaga el equipo")
    res = shutdown(mode="shutdown", confirmed=True)
    assert res.get("requires_confirmation") and not ran, res


def test_user_yes_runs_the_approved_action():
    ran.clear()
    tools.note_user_reply("reinicia el pc")
    shutdown(mode="restart", confirmed=True)
    tools.note_user_reply("sí, hazlo")
    shutdown(mode="shutdown", confirmed=True)  # LLM changes the mode: the approved one must run
    assert ran and ran[0][1] == "/r", ran
    shutdown(mode="restart", confirmed=True)  # confirmation is single-use
    assert len(ran) == 1, ran


def test_other_reply_cancels():
    ran.clear()
    tools.note_user_reply("apaga el equipo")
    shutdown(mode="shutdown")
    tools.note_user_reply("no, mejor no")
    shutdown(mode="shutdown", confirmed=True)
    assert not ran, ran


if __name__ == "__main__":
    test_llm_cannot_self_confirm()
    test_user_yes_runs_the_approved_action()
    test_other_reply_cancels()
    print("ok")
