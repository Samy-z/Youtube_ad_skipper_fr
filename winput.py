"""Mouse control via raw Win32 calls.

pyautogui is avoided on purpose: it reports and accepts *logical* coordinates,
which do not match the *physical* pixels mss captures whenever a monitor uses
display scaling (this machine's primary screen is at 125%). Talking to user32
directly, in a DPI-aware process, keeps one coordinate system end to end.
"""

from __future__ import annotations

import ctypes
import sys
import time

_MOUSEEVENTF_LEFTDOWN = 0x0002
_MOUSEEVENTF_LEFTUP = 0x0004


class _POINT(ctypes.Structure):
    _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]


def make_dpi_aware() -> None:
    """Opt into physical pixels. Must run before any screen size is queried."""
    if sys.platform != "win32":
        return
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)  # PER_MONITOR_DPI_AWARE
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass


def make_console_utf8() -> None:
    """Stop the cp1252 console from raising on button text it cannot encode."""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


def get_pos() -> tuple[int, int]:
    point = _POINT()
    ctypes.windll.user32.GetCursorPos(ctypes.byref(point))
    return point.x, point.y


def set_pos(x: int, y: int) -> None:
    ctypes.windll.user32.SetCursorPos(int(x), int(y))


def click(x: int, y: int, settle: float = 0.12) -> None:
    """Move to (x, y), let the UI react to the hover, then click there."""
    set_pos(x, y)
    time.sleep(settle)  # YouTube reveals/arms controls on hover
    ctypes.windll.user32.mouse_event(_MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0)
    time.sleep(0.02)
    ctypes.windll.user32.mouse_event(_MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)
