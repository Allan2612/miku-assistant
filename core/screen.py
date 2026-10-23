"""
Miku Assistant - Screen capture for "¿qué ves en mi pantalla?"
Primary screen as PNG via GDI + numpy + zlib (no Pillow). Only taken when the user asks about the screen,
and sent inside the turn's single Gemini request.
"""

from __future__ import annotations

import ctypes
import struct
import zlib
from ctypes import wintypes

import numpy as np

_SRCCOPY = 0x00CC0020
# Per-monitor DPI aware for this thread only: real pixels on scaled displays, not the 96-DPI virtual size
_DPI_AWARE_PER_MONITOR_V2 = ctypes.c_void_p(-4)


class _BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [
        ("biSize", wintypes.DWORD), ("biWidth", wintypes.LONG), ("biHeight", wintypes.LONG),
        ("biPlanes", wintypes.WORD), ("biBitCount", wintypes.WORD), ("biCompression", wintypes.DWORD),
        ("biSizeImage", wintypes.DWORD), ("biXPelsPerMeter", wintypes.LONG), ("biYPelsPerMeter", wintypes.LONG),
        ("biClrUsed", wintypes.DWORD), ("biClrImportant", wintypes.DWORD),
    ]


def _win32():
    user32, gdi32 = ctypes.windll.user32, ctypes.windll.gdi32
    # 64-bit handles: without explicit types ctypes truncates them to int and GDI calls crash
    user32.GetDC.restype = wintypes.HDC
    user32.GetDC.argtypes = [wintypes.HWND]
    user32.ReleaseDC.argtypes = [wintypes.HWND, wintypes.HDC]
    user32.SetThreadDpiAwarenessContext.restype = ctypes.c_void_p
    user32.SetThreadDpiAwarenessContext.argtypes = [ctypes.c_void_p]
    gdi32.CreateCompatibleDC.restype = wintypes.HDC
    gdi32.CreateCompatibleDC.argtypes = [wintypes.HDC]
    gdi32.CreateCompatibleBitmap.restype = wintypes.HBITMAP
    gdi32.CreateCompatibleBitmap.argtypes = [wintypes.HDC, ctypes.c_int, ctypes.c_int]
    gdi32.SelectObject.restype = wintypes.HGDIOBJ
    gdi32.SelectObject.argtypes = [wintypes.HDC, wintypes.HGDIOBJ]
    gdi32.BitBlt.argtypes = [wintypes.HDC, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
                             wintypes.HDC, ctypes.c_int, ctypes.c_int, wintypes.DWORD]
    gdi32.GetDIBits.argtypes = [wintypes.HDC, wintypes.HBITMAP, wintypes.UINT, wintypes.UINT,
                                ctypes.c_void_p, ctypes.c_void_p, wintypes.UINT]
    gdi32.DeleteObject.argtypes = [wintypes.HGDIOBJ]
    gdi32.DeleteDC.argtypes = [wintypes.HDC]
    return user32, gdi32


def encode_png(rgb: np.ndarray) -> bytes:
    """Encodes an (h, w, 3) uint8 RGB array as PNG."""
    h, w, _ = rgb.shape
    # Each row starts with filter byte 0 (none)
    raw = np.concatenate([np.zeros((h, 1), np.uint8), np.ascontiguousarray(rgb).reshape(h, w * 3)], axis=1).tobytes()

    def chunk(kind: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data))

    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw, 6)) + chunk(b"IEND", b""))


def capture_screen_png() -> bytes:
    """Screenshot of the primary screen as PNG bytes. Blocking (~0.2-0.5 s): call it from a thread."""
    user32, gdi32 = _win32()
    old_ctx = user32.SetThreadDpiAwarenessContext(_DPI_AWARE_PER_MONITOR_V2)
    screen_dc = user32.GetDC(None)
    mem_dc = gdi32.CreateCompatibleDC(screen_dc)
    w, h = user32.GetSystemMetrics(0), user32.GetSystemMetrics(1)
    bmp = gdi32.CreateCompatibleBitmap(screen_dc, w, h)
    try:
        gdi32.SelectObject(mem_dc, bmp)
        if not gdi32.BitBlt(mem_dc, 0, 0, w, h, screen_dc, 0, 0, _SRCCOPY):
            raise OSError("BitBlt failed")
        header = _BITMAPINFOHEADER(biSize=ctypes.sizeof(_BITMAPINFOHEADER), biWidth=w, biHeight=-h,  # top-down rows
                                   biPlanes=1, biBitCount=32, biCompression=0)
        buf = ctypes.create_string_buffer(w * h * 4)
        if gdi32.GetDIBits(mem_dc, bmp, 0, h, buf, ctypes.byref(header), 0) != h:
            raise OSError("GetDIBits failed")
    finally:
        gdi32.DeleteObject(bmp)
        gdi32.DeleteDC(mem_dc)
        user32.ReleaseDC(None, screen_dc)
        if old_ctx:
            user32.SetThreadDpiAwarenessContext(old_ctx)
    bgra = np.frombuffer(buf.raw, np.uint8).reshape(h, w, 4)
    return encode_png(bgra[:, :, 2::-1])  # BGR(A) -> RGB
