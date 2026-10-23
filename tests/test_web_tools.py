"""open_url / web_search / youtube_search open the browser (8dbb6f8 had deleted their helper: NameError on every call).

Run: core\\.venv\\Scripts\\python.exe -m tests.test_web_tools  (or with pytest)
"""

import core.tools.web as web


def test_web_tools_open_browser():
    opened = []
    # Mock below the helper so the real _open_in_browser runs
    web._find_opera_gx = lambda: None
    web.os.startfile = opened.append
    assert web.open_url("example.com")["ok"]
    assert web.web_search("miku")["ok"]
    assert web.youtube_search("world is mine")["ok"]
    assert opened == [
        "https://example.com",
        "https://www.google.com/search?q=miku",
        "https://www.youtube.com/results?search_query=world+is+mine",
    ], opened


if __name__ == "__main__":
    test_web_tools_open_browser()
    print("ok")
