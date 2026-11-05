"""
Miku Assistant - Bridge to Opera through Miku's own extension (browser-extension/).

The extension keeps sending every open tab (id, title, url) and the result links of a search page, and runs tab
commands with the tabs API. Exact tab ids replace the old keyboard simulation, which broke on pinned tabs,
"recently used" Ctrl+Tab, closing confirmations and stolen focus.
"""

from __future__ import annotations

import asyncio
import itertools
import json
import logging
import time
import urllib.parse
from typing import Any, Dict, List, Optional

logger = logging.getLogger("miku.browser")

# Origin of Miku's extension: its id is fixed by the "key" in browser-extension/manifest.json
EXTENSION_ORIGIN = "chrome-extension://gfjpfiehfhmpcfidlgjgbgjkaehkkaaf"
COMMAND_TIMEOUT_S = 6.0
MAX_TABS_IN_STATE = 40  # every tab rides in every request: keep the prompt bounded


class BrowserBridge:
    def __init__(self) -> None:
        self._ws: Any = None
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._pending: Dict[int, asyncio.Future] = {}
        self._ids = itertools.count(1)
        self.tabs: List[Dict[str, Any]] = []
        self.results: Optional[Dict[str, Any]] = None  # {"tab_id", "items": [{"title", "url"}]}
        self.last_opened_tab: Optional[int] = None
        self.last_opened_at = float("-inf")  # time.monotonic() of that

    @property
    def connected(self) -> bool:
        return self._ws is not None

    def attach(self, ws: Any) -> None:
        self._ws, self._loop = ws, asyncio.get_running_loop()
        logger.info("Opera extension connected.")

    def detach(self, ws: Any) -> None:
        if ws is self._ws:
            self._ws, self.tabs, self.results = None, [], None
            for fut in self._pending.values():
                fut.cancel()
            self._pending.clear()
            logger.info("Opera extension disconnected.")

    def update(self, data: Dict[str, Any]) -> None:
        self.tabs = [t for t in data.get("tabs") or [] if isinstance(t, dict)]
        self.results = data.get("results") if isinstance(data.get("results"), dict) else None

    def resolve(self, data: Dict[str, Any]) -> None:
        fut = self._pending.pop(data.get("id"), None)
        if fut and not fut.done():
            fut.set_result(data)

    async def _command(self, cmd: str, args: Dict[str, Any]) -> Dict[str, Any]:
        cmd_id = next(self._ids)
        fut = asyncio.get_running_loop().create_future()
        self._pending[cmd_id] = fut
        try:
            await self._ws.send(json.dumps({"type": "ext_cmd", "id": cmd_id, "cmd": cmd, "args": args}))
            return await asyncio.wait_for(fut, COMMAND_TIMEOUT_S)
        finally:
            self._pending.pop(cmd_id, None)

    def run(self, cmd: str, **args: Any) -> Dict[str, Any]:
        """Runs a command in Opera from a tool's thread; {"ok": False, "error": ...} if it cannot."""
        if not self.connected or self._loop is None:
            return {"ok": False, "error": "La extensión de Miku no está conectada en Opera."}
        try:
            reply = asyncio.run_coroutine_threadsafe(self._command(cmd, args), self._loop).result(COMMAND_TIMEOUT_S + 1)
        except Exception as e:  # timeout, closed socket, cancelled
            return {"ok": False, "error": f"Opera no respondió ({type(e).__name__})."}
        if reply.get("ok") and reply.get("tab_id"):
            self.last_opened_tab, self.last_opened_at = reply["tab_id"], time.monotonic()
        return reply

    def tab(self, tab_id: Optional[int]) -> Optional[Dict[str, Any]]:
        return next((t for t in self.tabs if t.get("id") == tab_id), None)

    def describe(self) -> str:
        """The tabs (and search results) as lines for the model's state block."""
        if not self.connected:
            return "Opera: la extensión de Miku no está conectada (no puedo ver ni manejar pestañas)."
        if not self.tabs:
            return "Opera: sin pestañas abiertas."
        windows: Dict[int, List[Dict[str, Any]]] = {}
        for t in self.tabs[:MAX_TABS_IN_STATE]:
            windows.setdefault(t.get("window_id", 0), []).append(t)
        lines = ["Pestañas de Opera (usa el número como tab_id):"]
        for n, (_, tabs) in enumerate(windows.items(), 1):
            if len(windows) > 1:
                lines.append(f" Ventana {n}:")
            for t in sorted(tabs, key=lambda t: t.get("index", 0)):
                marks = [m for m, on in (("activa", t.get("active")), ("fijada", t.get("pinned")),
                                         ("suena", t.get("audible")), ("abierta por Miku", t.get("id") == self.last_opened_tab)) if on]
                host = urllib.parse.urlparse(t.get("url", "")).hostname or t.get("url", "")
                lines.append(f"  [{t.get('id')}] {t.get('title', '')[:80]} ({host}){' — ' + ', '.join(marks) if marks else ''}")
        if len(self.tabs) > MAX_TABS_IN_STATE:
            lines.append(f"  ... y {len(self.tabs) - MAX_TABS_IN_STATE} pestañas más")
        if self.results and self.results.get("items"):
            lines.append(f"Resultados visibles en la pestaña {self.results.get('tab_id')}:")
            for i, r in enumerate(self.results["items"], 1):
                lines.append(f"  {i}. {r.get('title', '')} — {r.get('url', '')}")
        return "\n".join(lines)


bridge = BrowserBridge()
