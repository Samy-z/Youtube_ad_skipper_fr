"""Checks the idle decision without touching the screen, input or windows.

Frames are synthetic numpy images, the wall clock and the input-idle counter
are injected, so every rule is exercised deterministically:

    python -m pytest test_idle.py -q
"""

from __future__ import annotations

import numpy as np
import pytest

from idle import IdleWatch

DELAY_MIN = 15.0
DELAY_S = DELAY_MIN * 60


def frame(seed: int) -> np.ndarray:
    """A deterministic 'screenshot'; a different seed is a changed screen."""
    rng = np.random.default_rng(seed)
    return rng.integers(0, 255, size=(216, 384, 3), dtype=np.uint8)


def frame_with_clock(seed: int, minute: int) -> np.ndarray:
    """Same screen, except a taskbar-clock-sized patch that ticks over."""
    img = frame(seed)
    img[205:215, 350:380] = (minute * 37) % 255
    return img


class Harness:
    def __init__(self):
        self.now = 1000.0
        self.input_idle = 0.0
        self.watch = IdleWatch(DELAY_MIN,
                               seconds_since_input=lambda: self.input_idle,
                               clock=lambda: self.now)

    def tick(self, seconds: float, frames: dict[int, np.ndarray]) -> None:
        self.now += seconds
        self.input_idle += seconds
        for monitor, img in frames.items():
            self.watch.observe(monitor, img)


def test_still_screen_and_still_user_is_idle():
    h = Harness()
    for _ in range(20):
        h.tick(60, {1: frame(7)})
    assert h.watch.idle()


def test_playing_video_is_never_idle():
    h = Harness()
    for second in range(20):
        h.tick(60, {1: frame(second)})  # every frame different
    assert not h.watch.idle()


def test_user_input_blocks_an_idle_screen():
    """A static page being read: screen still, human occasionally active."""
    h = Harness()
    for _ in range(20):
        h.tick(60, {1: frame(7)})
        h.input_idle = 30.0  # nudged the mouse within the last half-minute
    assert not h.watch.idle()


def test_one_active_monitor_blocks_the_other():
    h = Harness()
    for second in range(20):
        h.tick(60, {1: frame(7), 2: frame(second)})
    assert not h.watch.idle()


def test_a_ticking_clock_patch_does_not_count_as_activity():
    h = Harness()
    for minute in range(20):
        h.tick(60, {1: frame_with_clock(7, minute)})
    assert h.watch.idle()


def test_change_resets_the_screen_clock():
    h = Harness()
    for _ in range(14):
        h.tick(60, {1: frame(7)})
    h.tick(60, {1: frame(8)})  # screen changed at the last moment
    for _ in range(5):
        h.tick(60, {1: frame(8)})
    assert not h.watch.idle()  # only ~5 min still since the change
    for _ in range(10):
        h.tick(60, {1: frame(8)})
    assert h.watch.idle()


def test_hold_fires_once_per_sleep():
    """After one firing, nothing more happens all night: each close reveals
    the next static tab, and without the hold they would all be eaten."""
    h = Harness()
    for _ in range(16):
        h.tick(60, {1: frame(7)})
    assert h.watch.idle()
    h.watch.hold()
    for second in range(480):  # eight more hours of static screens
        h.tick(60, {1: frame(100 + second // 15)})  # a tab closes now and then
    assert not h.watch.idle()


def test_our_own_keystroke_does_not_release_the_hold():
    """Field bug, 2026-10-07: the close sends Ctrl+W, synthetic input resets
    Windows' last-input counter, and the latch read its own echo as 'the
    user is back' -- then re-fired every delay, all night (35 closes). The
    echo arrives within a second of hold(); a real return cannot be told
    apart that fast, so everything inside the grace window stays held."""
    h = Harness()
    for _ in range(16):
        h.tick(60, {1: frame(7)})
    assert h.watch.idle()
    h.watch.hold()
    h.input_idle = 1.0  # the Ctrl+W we just sent, seen as fresh input
    for _ in range(480):  # the rest of the night, screen static
        h.tick(60, {1: frame(50)})
    assert not h.watch.idle()


def test_hold_releases_when_the_user_returns():
    h = Harness()
    for _ in range(16):
        h.tick(60, {1: frame(7)})
    assert h.watch.idle()
    h.watch.hold()

    for _ in range(10):  # the night goes on, well past the echo grace
        h.tick(60, {1: frame(8)})
    h.input_idle = 2.0  # the user is genuinely back at the machine
    h.tick(1, {1: frame(9)})
    h.input_idle = 3.0
    assert not h.watch.idle()  # released, but a NEW stretch must build up

    for _ in range(20):  # user walks away again, same static screen
        h.tick(60, {1: frame(9)})
    assert h.watch.idle()  # a second sleep can fire a second time


def test_no_frames_yet_is_not_idle():
    h = Harness()
    h.input_idle = DELAY_S + 1
    assert not h.watch.idle()


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
