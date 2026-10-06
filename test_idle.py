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


def test_rearm_waits_a_full_delay_before_firing_again():
    h = Harness()
    for _ in range(16):
        h.tick(60, {1: frame(7)})
    assert h.watch.idle()
    h.watch.rearm()
    h.tick(60, {1: frame(7)})
    assert not h.watch.idle()
    for _ in range(15):
        h.tick(60, {1: frame(7)})
    assert h.watch.idle()  # input was idle throughout; only the screen rearmed


def test_no_frames_yet_is_not_idle():
    h = Harness()
    h.input_idle = DELAY_S + 1
    assert not h.watch.idle()


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
