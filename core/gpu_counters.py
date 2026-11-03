"""
Miku Assistant - GPU memory and use per process, from the same Windows counters Task Manager shows.

pdh.dll through ctypes: no pynvml or pywin32 needed, and it works for any GPU vendor. Instances are named
"pid_1234_luid_..._phys_0" (memory) and "pid_1234_luid_..._engtype_3D" (engines).
"""

from __future__ import annotations

import ctypes
import logging
import re
from ctypes import wintypes
from typing import Dict, Tuple

logger = logging.getLogger("miku.gpu")

PDH_FMT_DOUBLE = 0x00000200
PDH_FMT_NOCAP100 = 0x00008000
PDH_MORE_DATA = 0x800007D2
_PID = re.compile(r"pid_(\d+)_(.*)")  # the rest names the engine: "luid_..._phys_0_eng_3_engtype_3D"


class _Value(ctypes.Union):
    _fields_ = [("longValue", ctypes.c_long), ("doubleValue", ctypes.c_double), ("largeValue", ctypes.c_longlong)]


class _CounterValue(ctypes.Structure):
    _fields_ = [("CStatus", wintypes.DWORD), ("value", _Value)]


class _Item(ctypes.Structure):
    _fields_ = [("szName", wintypes.LPWSTR), ("FmtValue", _CounterValue)]


class GpuCounters:
    """Call read() every few seconds: utilization is a rate, so the first read gives 0 % for every process."""

    def __init__(self) -> None:
        self._pdh = ctypes.WinDLL("pdh")
        self._query = wintypes.HANDLE()
        self._mem = wintypes.HANDLE()
        self._util = wintypes.HANDLE()
        if self._pdh.PdhOpenQueryW(None, None, ctypes.byref(self._query)) != 0:
            raise OSError("PdhOpenQuery failed")
        for path, handle in ((r"\GPU Process Memory(*)\Dedicated Usage", self._mem),
                             (r"\GPU Engine(*)\Utilization Percentage", self._util)):
            if self._pdh.PdhAddEnglishCounterW(self._query, path, None, ctypes.byref(handle)) != 0:
                raise OSError(f"PdhAddEnglishCounter failed for {path}")
        self._pdh.PdhCollectQueryData(self._query)

    def _items(self, counter: wintypes.HANDLE) -> Dict[str, float]:
        size, count = wintypes.DWORD(0), wintypes.DWORD(0)
        fmt = PDH_FMT_DOUBLE | PDH_FMT_NOCAP100
        status = self._pdh.PdhGetFormattedCounterArrayW(counter, fmt, ctypes.byref(size), ctypes.byref(count), None)
        if status & 0xFFFFFFFF != PDH_MORE_DATA or not size.value:
            return {}
        buf = (ctypes.c_byte * size.value)()
        if self._pdh.PdhGetFormattedCounterArrayW(counter, fmt, ctypes.byref(size), ctypes.byref(count), buf) != 0:
            return {}
        items = ctypes.cast(buf, ctypes.POINTER(_Item))
        return {items[i].szName: items[i].FmtValue.value.doubleValue
                for i in range(count.value) if items[i].szName and items[i].FmtValue.CStatus == 0}

    def read(self) -> Tuple[Dict[int, float], Dict[int, float], float]:
        """({pid: dedicated GPU memory in bytes}, {pid: GPU use in %}, whole GPU in %).

        Like Task Manager: a process's GPU use is its busiest engine, the whole GPU's is the busiest engine with
        everyone's use of it added up. Adding all engines (3D, copy, video...) gave 100 % with a game open."""
        self._pdh.PdhCollectQueryData(self._query)
        vram: Dict[int, float] = {}
        for name, value in self._items(self._mem).items():
            if m := _PID.search(name):
                vram[int(m.group(1))] = vram.get(int(m.group(1)), 0.0) + value
        per_pid: Dict[int, Dict[str, float]] = {}
        per_engine: Dict[str, float] = {}
        for name, value in self._items(self._util).items():
            if m := _PID.search(name):
                engines = per_pid.setdefault(int(m.group(1)), {})
                engines[m.group(2)] = engines.get(m.group(2), 0.0) + value
                per_engine[m.group(2)] = per_engine.get(m.group(2), 0.0) + value
        use = {pid: max(engines.values()) for pid, engines in per_pid.items()}
        return vram, use, min(100.0, max(per_engine.values(), default=0.0))

    def close(self) -> None:
        self._pdh.PdhCloseQuery(self._query)
