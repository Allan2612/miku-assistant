"""
Miku Assistant - Keeps the DNS answers of the hosts she needs in Windows' cache, from background threads.

On some PCs a lookup with no cached answer hangs about 11 s (measured 5-nov, a host-only VirtualBox adapter with a dead
DNS server is the likely cause). That is past the 10 s limit of a Gemini request and of a tool, so 8 of 16 first requests
of a session failed, against 3 of 86 of the rest, whatever the model. Here the wait falls on a thread nobody waits for.
"""

import logging
import socket
import threading
import time

logger = logging.getLogger("miku.dns")

HOSTS = (
    "generativelanguage.googleapis.com",  # Gemini
    "speech.platform.bing.com",  # edge-tts
    "geocoding-api.open-meteo.com",  # weather
    "api.open-meteo.com",
    "www.youtube.com",  # youtube_play
)
INTERVAL_S = 5.0  # a lookup still in the cache sends nothing out; an expired one (TTLs of 53-300 s) hangs up to 12 s again
SLOW_S = 2.0


def _keep_warm(host: str, interval_s: float) -> None:
    while True:
        started = time.monotonic()
        try:
            socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)
        except OSError as e:  # offline: the real request will say so
            logger.debug("DNS lookup of %s failed: %s", host, e)
        took = time.monotonic() - started
        if took > SLOW_S:
            logger.info("Slow DNS lookup of %s (%.1fs): no request waited for it.", host, took)
        time.sleep(interval_s)


def start(hosts: tuple = HOSTS, interval_s: float = INTERVAL_S) -> None:
    """One daemon thread per host, so a hung lookup holds up no other."""
    for host in hosts:
        threading.Thread(target=_keep_warm, args=(host, interval_s), daemon=True, name=f"miku-dns-{host}").start()
