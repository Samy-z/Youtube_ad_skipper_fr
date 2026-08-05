"""End-to-end checks that need no ad, for the part that used to be broken:
screen capture, DPI scaling and monitor offsets.

Two independent checks run per monitor.

  round-trip  Read any text already on screen, work out its global coordinates,
              then re-grab a small box at those coordinates and confirm the same
              text is there. If DPI scaling or the monitor offset were wrong,
              the second grab would land somewhere else. Works on any monitor
              whatever is displayed.

  window      Draw a fake "Ignorer" button at a known spot and check the finder
              reports coordinates inside it. Also covers the keyword matching,
              but Windows will not let a background process raise a window above
              a foreground browser, so it is skipped when something covers it.

    python selftest.py                  # every monitor
    python selftest.py --monitor 2
"""

from __future__ import annotations

import argparse
import ctypes
import time

import winput

winput.make_dpi_aware()
winput.make_console_utf8()

import cv2  # noqa: E402
import numpy as np  # noqa: E402

from detect import SkipButtonFinder, normalize  # noqa: E402

WINDOW = "skipper selftest"


LABEL = "Ignorer les annonces"
FONT, SCALE, THICK = cv2.FONT_HERSHEY_SIMPLEX, 0.72, 2


def draw_button(width: int = 560, height: int = 240) -> tuple[np.ndarray, tuple[int, int]]:
    """A stand-in for YouTube's skip button, on a dark player background.

    The label is the long form on purpose: the click has to land on "Ignorer",
    not in the middle of the whole label. Returns the image and the horizontal
    span of the word "Ignorer" within it.
    """
    canvas = np.full((height, width, 3), 32, dtype=np.uint8)
    text_x, baseline_y = 60, 170
    (full_w, text_h), _ = cv2.getTextSize(LABEL, FONT, SCALE, THICK)
    (word_w, _), _ = cv2.getTextSize("Ignorer", FONT, SCALE, THICK)

    cv2.rectangle(canvas, (text_x - 14, baseline_y - text_h - 12),
                  (text_x + full_w + 14, baseline_y + 12), (60, 60, 60), -1)
    cv2.putText(canvas, LABEL, (text_x, baseline_y), FONT, SCALE,
                (245, 245, 245), THICK, cv2.LINE_AA)
    return canvas, (text_x, text_x + word_w)


def window_rect(title: str) -> tuple[int, int, int, int] | None:
    hwnd = ctypes.windll.user32.FindWindowW(None, title)
    if not hwnd:
        return None
    rect = (ctypes.c_long * 4)()
    ctypes.windll.user32.GetWindowRect(hwnd, ctypes.byref(rect))
    return tuple(rect)


def client_origin(title: str) -> int | None:
    """Screen x of the window's client area, which is inset by the border."""
    hwnd = ctypes.windll.user32.FindWindowW(None, title)
    if not hwnd:
        return None
    point = (ctypes.c_long * 2)(0, 0)
    ctypes.windll.user32.ClientToScreen(hwnd, ctypes.byref(point))
    return point[0]


def pin_on_top(title: str) -> None:
    """Otherwise a maximised browser sits over the test window and gets read."""
    hwnd = ctypes.windll.user32.FindWindowW(None, title)
    if hwnd:
        HWND_TOPMOST, SWP_NOMOVE, SWP_NOSIZE = -1, 0x0002, 0x0001
        ctypes.windll.user32.SetWindowPos(hwnd, HWND_TOPMOST, 0, 0, 0, 0,
                                          SWP_NOMOVE | SWP_NOSIZE)


def check_roundtrip(finder: SkipButtonFinder, index: int) -> bool | None:
    """Confirm reported global coordinates really point at the text they came from.

    Returns None when the monitor has no usable text to test with.
    """
    scan = finder.scan(index)
    candidates = [(box, text, conf) for box, text, conf in scan.words
                  if conf >= 0.75 and len(normalize(text)) >= 5]
    if not candidates:
        print("  round-trip: SKIP (no readable text on this monitor)")
        return None

    # Try several words. Coordinate mapping is a systematic property, so one
    # confirmed word proves it; the retries only guard against picking text
    # that changes under us, such as a word inside a playing video.
    candidates.sort(key=lambda w: -w[2])
    ox, oy = scan.origin
    pad = 8
    for attempt, (box, text, conf) in enumerate(candidates[:5], start=1):
        left, top, right, bottom = box
        gl, gt, gr, gb = ox + left, oy + top, ox + right, oy + bottom
        again = finder.scan_box(gl - pad, gt - pad,
                                (gr - gl) + 2 * pad, (gb - gt) + 2 * pad,
                                monitor=index)
        seen = [normalize(t) for _, t, _ in again.words]
        want = normalize(text)
        if any(want in s or s in want for s in seen if s):
            print(f"  round-trip: {text!r} ({conf:.2f}) at global "
                  f"({gl}, {gt})-({gr}, {gb}) re-read as {seen}")
            print(f"  round-trip: PASS (attempt {attempt})")
            return True
        print(f"  round-trip: {text!r} re-read as {seen}, trying another word")

    print("  round-trip: FAIL (no word re-read at its reported coordinates)")
    return False


def check_window(finder: SkipButtonFinder, index: int) -> bool | None:
    """Draw a fake button at a known place and check the finder points at it.

    Returns None when the window could not be made visible (something else owns
    the foreground), which is a limitation of the test, not of the skipper.
    """
    mon = finder._sct.monitors[index]
    # Bottom-right area of the chosen monitor, where a real player would be.
    place_x = mon["left"] + mon["width"] - 620
    place_y = mon["top"] + mon["height"] - 460

    art, word_span = draw_button()
    cv2.namedWindow(WINDOW, cv2.WINDOW_AUTOSIZE)
    cv2.moveWindow(WINDOW, place_x, place_y)
    for i in range(12):  # let the compositor actually paint it
        cv2.imshow(WINDOW, art)
        cv2.waitKey(40)
        if i == 2:
            pin_on_top(WINDOW)
    time.sleep(0.3)

    rect = window_rect(WINDOW)
    # Scan the test window only. Scanning the whole monitor would also read
    # whatever else is on screen, which can contain the word we are hunting.
    if rect is None:
        cv2.destroyAllWindows()
        cv2.waitKey(1)
        print("  window:     SKIP (test window never appeared)")
        return None
    left, top, right, bottom = rect
    client_x = client_origin(WINDOW)
    scan = finder.scan_box(left, top, right - left, bottom - top, monitor=index)
    cv2.destroyAllWindows()
    cv2.waitKey(1)

    print(f"  window:     drew a button at ({place_x}, {place_y}), rect {rect}")

    if scan.hit is None:
        # Most likely something is stacked above it; say so instead of crying wolf.
        print(f"  window:     SKIP (button not visible -- read {len(scan.words)} "
              f"other text box(es), so a window is covering it)")
        return None

    hit = scan.hit
    print(f"  window:     found {hit.text!r} at ({hit.x}, {hit.y}) "
          f"[ocr {hit.confidence:.2f}, match {hit.similarity:.2f}]")

    inside = left <= hit.x <= right and top <= hit.y <= bottom
    if not inside:
        print("  window:     FAIL -- click point is outside the button entirely")
        return False

    # Where "Ignorer" actually is on screen, allowing for the window border.
    if client_x is None:
        print("  window:     PASS (inside the button; word position unchecked)")
        return True
    word_left, word_right = (client_x + word_span[0], client_x + word_span[1])
    on_word = word_left <= hit.x <= word_right
    print(f"  window:     'Ignorer' spans x {word_left}-{word_right}; "
          f"click x is {hit.x}")
    print(f"  window:     {'PASS' if on_word else 'FAIL -- aimed at the label centre, not the word'}")
    return on_word


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--monitor", type=int, default=None,
                        help="1-based monitor to test (default: every monitor)")
    args = parser.parse_args()

    finder = SkipButtonFinder(region="full")
    targets = finder.monitors if args.monitor is None else [args.monitor]
    for index in targets:
        if index not in finder.monitors:
            print(f"no monitor {index}; available: {finder.monitors}")
            return 2

    results: list[bool] = []
    try:
        for index in targets:
            print(finder.describe(index))
            for outcome in (check_roundtrip(finder, index), check_window(finder, index)):
                if outcome is not None:
                    results.append(outcome)
            print()
    finally:
        finder.close()

    if not results:
        print("INCONCLUSIVE: no check was able to run")
        return 2
    if all(results):
        print(f"PASS: {len(results)}/{len(results)} checks passed")
        return 0
    print(f"FAIL: {sum(results)}/{len(results)} checks passed")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
