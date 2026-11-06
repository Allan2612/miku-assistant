"""core/dns_warm.py: the lookups run in the background, keep going after a failure, and one hang holds up no other.

Run: python -m tests.test_dns_warm (from the project folder, with core/.venv), or with pytest
"""

import socket
import threading
import time

from core import dns_warm


def test_lookups_keep_going_and_a_hang_holds_up_no_other():
    seen = {"bad": 0, "good": 0, "hung": 0}
    release = threading.Event()
    real = socket.getaddrinfo

    def fake(host, *_, **__):
        seen[host] += 1
        if host == "hung":
            release.wait(5)
        if host == "bad":
            raise socket.gaierror("offline")
        return []

    socket.getaddrinfo = fake
    try:
        started = time.monotonic()
        dns_warm.start(("hung", "bad", "good"), interval_s=0.01)
        assert time.monotonic() - started < 0.5, "starting must not wait for a lookup"
        time.sleep(0.2)
        assert seen["bad"] >= 3, seen
        assert seen["good"] >= 3, seen
        assert seen["hung"] == 1, seen
    finally:
        release.set()
        time.sleep(0.05)
        socket.getaddrinfo = real


if __name__ == "__main__":
    test_lookups_keep_going_and_a_hang_holds_up_no_other()
    print("ok")
