"""Close the media tab once the screen has gone quiet.

The use case: falling asleep in front of a video. The video eventually ends or
the platform pauses itself ("are you still watching?"), the screen freezes on
that prompt, and the browser then sits there all night holding memory, GPU and
a bright monitor. This watches for that state and closes the tab.

"Idle" deliberately requires BOTH of these, each for the full delay:

- **The screen stopped changing.** A playing video repaints constantly, so as
  long as anything is actually showing, nothing happens -- falling asleep
  mid-film does not cut the film. Measured on the same frames the skipper
  already captures, downscaled hard so a blinking taskbar clock or one
  spinner does not count as activity.
- **The user stopped touching the machine.** A static screen being *read* --
  an article, a recipe, code -- comes with occasional scrolls and mouse
  nudges, and any input resets the clock. This is what keeps a quiet screen
  with an awake human from being closed under them.

The close itself is Ctrl+W to the browser, not a click: in fullscreen video
there is no close button on screen to click, while the shortcut works
everywhere. Alt+F4 (whole window) is available behind a flag. Either way the
keystroke is only ever sent when the target application verifiably holds the
foreground, so it cannot land in an unrelated program.
"""

from __future__ import annotations

import time
from typing import Callable

import numpy as np

import winput

# Frames are judged on a tiny grayscale thumbnail: cheap, and small motion
# (a clock, one spinner) averages out to below the threshold while real
# playback sits far above it.
_THUMB_W, _THUMB_H = 96, 54
_CHANGE_THRESHOLD = 2.0  # mean absolute gray delta, 0-255 scale


def _thumbnail(frame: np.ndarray) -> np.ndarray:
    import cv2

    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    return cv2.resize(gray, (_THUMB_W, _THUMB_H)).astype(np.int16)


class IdleWatch:
    """Tracks how long every monitor's picture and the user's hands have been
    still, from frames pushed in by the scan loop.

    `observe(monitor, frame)` each tick; `idle()` answers whether both clocks
    have exceeded the delay. After acting on it, call `hold()`: the watch
    then stays quiet until the user demonstrably came back (fresh keyboard or
    mouse input), and only a NEW stretch of stillness after that can fire.

    One firing per sleep, by design. Without the hold, every close reveals
    the next tab, that tab is also static, and fifteen minutes later it gets
    closed too -- repeat until the browser has no tabs left by morning. The
    point is to end the one dead video, not to eat the session.
    """

    def __init__(
        self,
        minutes: float,
        seconds_since_input: Callable[[], float] = winput.seconds_since_input,
        clock: Callable[[], float] = time.monotonic,
    ):
        self.delay = minutes * 60.0
        self._input_idle = seconds_since_input
        self._clock = clock
        self._thumbs: dict[int, np.ndarray] = {}
        self._last_change: dict[int, float] = {}
        self._holding = False

    def observe(self, monitor: int, frame: np.ndarray) -> None:
        thumb = _thumbnail(frame)
        previous = self._thumbs.get(monitor)
        self._thumbs[monitor] = thumb
        changed = (
            previous is None
            or previous.shape != thumb.shape
            or float(np.abs(previous - thumb).mean()) > _CHANGE_THRESHOLD
        )
        if changed or monitor not in self._last_change:
            self._last_change[monitor] = self._clock()

    def screen_idle_seconds(self) -> float:
        """How long every watched monitor has been still (0 until all have)."""
        if not self._last_change:
            return 0.0
        now = self._clock()
        return min(now - t for t in self._last_change.values())

    def idle(self) -> bool:
        if self._holding:
            # Fresh input means the user is back; a sleeping user's idle
            # counter only ever grows.
            if self._input_idle() > 60.0:
                return False
            self._holding = False
            # The screen clocks restart too: being back must begin a whole
            # new stretch of stillness, not inherit the overnight one.
            now = self._clock()
            for monitor in self._last_change:
                self._last_change[monitor] = now
        return (self.screen_idle_seconds() >= self.delay
                and self._input_idle() >= self.delay)

    def hold(self) -> None:
        """Quiet the watch until the user has demonstrably returned."""
        self._holding = True


def close_media_tab(app: str = "opera", whole_window: bool = False) -> str | None:
    """Close the current tab (or window) of `app`, wherever it is.

    Returns a short description of what was done, or None with nothing done:
    the keystroke is sent only once `app` verifiably holds the foreground, so
    it can never close a tab of some other program.
    """
    app = app.lower()
    hwnd, name = winput.foreground_process()
    if app not in name:
        hwnd = winput.find_window(app)
        if not hwnd:
            return None
        if not winput.focus_window(hwnd):
            return None

    if whole_window:
        winput.send_close_window()
        return f"Alt+F4 sent to {app}"
    winput.send_close_tab()
    return f"Ctrl+W sent to {app}"
