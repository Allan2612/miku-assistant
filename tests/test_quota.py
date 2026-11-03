"""Gemini requests used today: Google's day (Pacific time), counting, the once-a-day 90% warning.

Uses a temp quota file; nothing touches cache/quota.json.
Run: core\\.venv\\Scripts\\python.exe -m tests.test_quota  (or with pytest)
"""

import datetime
import json
import tempfile
from pathlib import Path

import core.quota as quota

quota.QUOTA_FILE = Path(tempfile.mkdtemp()) / "quota.json"
UTC = datetime.datetime


def test_pacific_day():
    # 2026: daylight time from Sunday 8 March 10:00 UTC to Sunday 1 November 9:00 UTC
    assert quota.pacific_now(UTC(2026, 3, 8, 9, 59)) == UTC(2026, 3, 8, 1, 59)  # still -8
    assert quota.pacific_now(UTC(2026, 3, 8, 10, 0)) == UTC(2026, 3, 8, 3, 0)  # -7
    assert quota.pacific_now(UTC(2026, 11, 1, 8, 59)) == UTC(2026, 11, 1, 1, 59)  # still -7
    assert quota.pacific_now(UTC(2026, 11, 1, 9, 0)) == UTC(2026, 11, 1, 1, 0)  # -8 again
    # 07:30 UTC on 4 Nov is still the 3rd in California: Google's day has not changed yet
    assert quota.pacific_now(UTC(2026, 11, 4, 7, 30)).date() == datetime.date(2026, 11, 3)


def test_count_and_warning():
    quota.QUOTA_FILE.unlink(missing_ok=True)
    primary = "gemini-3.5-flash-lite"
    for _ in range(449):
        assert quota.count(primary, primary) is None
    warning = quota.count(primary, primary)  # 450 of 500
    assert warning and "450 de las 500" in warning, warning
    assert quota.count(primary, primary) is None, "the warning comes once a day"
    assert quota.count("gemini-3-flash-preview", primary) is None, "fallbacks are counted, not warned about"
    text = quota.describe(primary)
    assert "451 de 500" in text and "me quedan 49" in text and "1 en los modelos de respaldo" in text, text

    # Another day (Pacific): a fresh count
    data = json.loads(quota.QUOTA_FILE.read_text(encoding="utf-8"))
    data["day"] = "2000-01-01"
    quota.QUOTA_FILE.write_text(json.dumps(data), encoding="utf-8")
    assert "0 de 500" in quota.describe(primary)


if __name__ == "__main__":
    test_pacific_day()
    test_count_and_warning()
    print("ok")
