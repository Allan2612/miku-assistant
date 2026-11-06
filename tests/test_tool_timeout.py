"""H-003: a hung tool returns an error after TOOL_TIMEOUT_S instead of hanging the turn.

Run: core\\.venv\\Scripts\\python.exe -m tests.test_tool_timeout  (or with pytest)
"""

import time

import core.tools as tools


def test_hung_tool_times_out():
    tools.TOOL_TIMEOUT_S = 0.5

    @tools.tool(name="_test_sleeper")
    def sleeper() -> str:
        time.sleep(5)
        return "never"

    start = time.monotonic()
    res = sleeper()
    assert not res["ok"] and time.monotonic() - start < 2, res


def test_timeout_is_marked_and_does_not_sound_like_success():
    tools.TOOL_TIMEOUT_S = 0.2

    @tools.tool(name="_test_sleeper2")
    def sleeper() -> str:
        time.sleep(2)
        return "never"

    res = sleeper()
    assert res["timed_out"] and not res["ok"] and "no sé si se hizo" in res["result"], res


if __name__ == "__main__":
    test_hung_tool_times_out()
    test_timeout_is_marked_and_does_not_sound_like_success()
    print("ok")
