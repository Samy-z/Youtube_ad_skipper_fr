"""Mouse and keyboard control via raw Win32 calls.

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

_KEYEVENTF_KEYUP = 0x0002
_VK_CONTROL = 0x11
_VK_MENU = 0x12  # Alt
_VK_F4 = 0x73
_VK_W = 0x57


class _POINT(ctypes.Structure):
    _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]


class _LASTINPUTINFO(ctypes.Structure):
    _fields_ = [("cbSize", ctypes.c_uint), ("dwTime", ctypes.c_uint)]


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


def seconds_since_input() -> float:
    """Seconds since the user last touched the keyboard or mouse.

    Synthetic events (our own clicks and keystrokes) also reset this counter,
    which is fine: they are rare, and treating them as activity only delays an
    idle decision, never forces one.
    """
    info = _LASTINPUTINFO(cbSize=ctypes.sizeof(_LASTINPUTINFO))
    if not ctypes.windll.user32.GetLastInputInfo(ctypes.byref(info)):
        return 0.0  # unknowable -> assume active, the safe direction
    # Both are milliseconds from the same 32-bit tick counter, so the
    # subtraction is wraparound-safe when kept in uint32.
    elapsed = (ctypes.windll.kernel32.GetTickCount() - info.dwTime) & 0xFFFFFFFF
    return elapsed / 1000.0


def _press(*keys: int) -> None:
    """Hold the keys in order, then release them in reverse."""
    for key in keys:
        ctypes.windll.user32.keybd_event(key, 0, 0, 0)
        time.sleep(0.02)
    for key in reversed(keys):
        ctypes.windll.user32.keybd_event(key, 0, _KEYEVENTF_KEYUP, 0)
        time.sleep(0.02)


def send_close_tab() -> None:
    """Ctrl+W to the foreground window. Works in fullscreen video, where a
    point-and-click close button may not even be on screen."""
    _press(_VK_CONTROL, _VK_W)


def send_close_window() -> None:
    """Alt+F4 to the foreground window."""
    _press(_VK_MENU, _VK_F4)


def foreground_process() -> tuple[int, str]:
    """The foreground window handle and its executable name, lowercased
    without the .exe suffix ('' when it cannot be read)."""
    hwnd = ctypes.windll.user32.GetForegroundWindow()
    return hwnd, _process_name(hwnd)


def _process_name(hwnd: int) -> str:
    pid = ctypes.c_ulong()
    ctypes.windll.user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    handle = ctypes.windll.kernel32.OpenProcess(0x1000, False, pid.value)
    if not handle:
        return ""
    try:
        size = ctypes.c_ulong(512)
        buffer = ctypes.create_unicode_buffer(size.value)
        if not ctypes.windll.kernel32.QueryFullProcessImageNameW(
                handle, 0, buffer, ctypes.byref(size)):
            return ""
        name = buffer.value.rsplit("\\", 1)[-1].lower()
        return name[:-4] if name.endswith(".exe") else name
    finally:
        ctypes.windll.kernel32.CloseHandle(handle)


def find_window(process: str) -> int:
    """A visible, titled top-level window whose executable matches `process`
    (substring), or 0. Prefers the largest one, which for a browser is the
    main window rather than a tooltip or a hidden helper."""
    user32 = ctypes.windll.user32
    best = {"hwnd": 0, "area": 0}

    @ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)
    def visit(hwnd, _):
        if not user32.IsWindowVisible(hwnd) or not user32.GetWindowTextLengthW(hwnd):
            return True
        if process not in _process_name(hwnd):
            return True
        rect = (ctypes.c_long * 4)()
        user32.GetWindowRect(hwnd, ctypes.byref(rect))
        area = max(0, rect[2] - rect[0]) * max(0, rect[3] - rect[1])
        if area > best["area"]:
            best.update(hwnd=hwnd, area=area)
        return True

    user32.EnumWindows(visit, None)
    return best["hwnd"]


def focus_window(hwnd: int) -> bool:
    """Bring `hwnd` to the foreground; True when it actually got there.

    Windows refuses SetForegroundWindow from a background process unless the
    caller recently sent input, so tap Alt first -- the standard unlock.
    """
    user32 = ctypes.windll.user32
    ctypes.windll.user32.keybd_event(_VK_MENU, 0, 0, 0)
    ctypes.windll.user32.keybd_event(_VK_MENU, 0, _KEYEVENTF_KEYUP, 0)
    user32.SetForegroundWindow(hwnd)
    time.sleep(0.3)
    return user32.GetForegroundWindow() == hwnd
