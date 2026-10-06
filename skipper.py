"""YouTube ad skipper -- clicks the French "Ignorer" button when it appears.

    python skipper.py                 # watch every monitor, click for 6 hours
    python skipper.py --monitor 2     # only the second screen (faster)
    python skipper.py --dry-run       # report what it would click, click nothing
    python skipper.py --debug         # also write annotated scans to debug/

Stop it with Ctrl+C.
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import winput

# Physical vs. logical pixels must be settled before anything measures the
# screen, so this runs at import time, ahead of mss.
winput.make_dpi_aware()
winput.make_console_utf8()

from detect import REGIONS, Scan, SkipButtonFinder, normalize  # noqa: E402

DEBUG_DIR = Path(__file__).parent / "debug"
# A frame per tick for six hours would be thousands of files, so cap it.
DEBUG_FILE_LIMIT = 300


def stamp() -> str:
    return time.strftime("%H:%M:%S")


def save_debug(scan: Scan, tag: str) -> Path:
    import cv2

    DEBUG_DIR.mkdir(exist_ok=True)
    canvas = scan.frame.copy()
    for (left, top, right, bottom), text, confidence in scan.words:
        matched = scan.hit is not None and scan.hit.text == text
        color = (0, 0, 255) if matched else (0, 200, 0)
        cv2.rectangle(canvas, (left, top), (right, bottom), color, 2)
        cv2.putText(canvas, f"{text} {confidence:.2f}", (left, max(12, top - 4)),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.45, color, 1, cv2.LINE_AA)
    path = DEBUG_DIR / f"{tag}_mon{scan.monitor}_{time.strftime('%H%M%S')}.png"
    cv2.imwrite(str(path), canvas)
    return path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--monitor", default="all",
                        help="'all' (default) or a 1-based monitor number")
    parser.add_argument("--region", default="full", choices=sorted(REGIONS),
                        help="part of each monitor to scan (default: full -- a "
                             "player can be anywhere)")
    parser.add_argument("--tick", type=float, default=1.0,
                        help="minimum seconds between scans (default: 1). A scan "
                             "that takes longer than this sets the real rate")
    parser.add_argument("--hours", type=float, default=6.0,
                        help="how long to keep running (default: 6)")
    parser.add_argument("--cooldown", type=float, default=4.0,
                        help="seconds to wait after a click (default: 4)")
    parser.add_argument("--keyword", action="append", default=None,
                        help="text to look for (repeatable; default: Ignorer)")
    parser.add_argument("--min-confidence", type=float, default=0.55,
                        help="reject OCR reads below this confidence")
    parser.add_argument("--min-similarity", type=float, default=0.90,
                        help="how close the read text must be to the keyword "
                             "(0.90 takes 'Ignorer' and 'Ignore', not 'Ignor')")
    parser.add_argument("--close-idle-after", type=float, default=0.0,
                        metavar="MINUTES",
                        help="close the browser tab once the screen AND the "
                             "user have both been still this long (default: "
                             "0 = never). Playing video counts as activity, "
                             "so this fires on the 'video over, everyone "
                             "asleep' state, not mid-film")
    parser.add_argument("--idle-app", default="opera",
                        help="which program's tab to close, by executable "
                             "name substring (default: opera). The keystroke "
                             "is only sent when this program verifiably holds "
                             "the foreground")
    parser.add_argument("--idle-window", action="store_true",
                        help="close the whole window (Alt+F4) instead of the "
                             "tab (Ctrl+W)")
    parser.add_argument("--on-idle-close", default=None, metavar="CMD",
                        help="shell command to run after an idle close, e.g. "
                             "a script that reclaims the machine for batch "
                             "work")
    parser.add_argument("--dry-run", action="store_true",
                        help="log detections without moving or clicking")
    parser.add_argument("--debug", action="store_true",
                        help="write annotated scans to debug/")
    parser.add_argument("--keep-mouse", action="store_true",
                        help="do not restore the cursor after clicking")
    args = parser.parse_args(argv)

    if args.tick <= 0 or args.hours <= 0:
        parser.error("--tick and --hours must both be positive")

    finder = SkipButtonFinder(
        region=args.region,
        keywords=tuple(args.keyword or ("ignorer",)),
        min_confidence=args.min_confidence,
        min_similarity=args.min_similarity,
    )

    if args.monitor == "all":
        targets = finder.monitors
    else:
        try:
            targets = [int(args.monitor)]
        except ValueError:
            parser.error("--monitor must be 'all' or a number")
        if targets[0] not in finder.monitors:
            parser.error(f"no monitor {targets[0]}; available: {finder.monitors}")

    idle_watch = None
    if args.close_idle_after > 0:
        from idle import IdleWatch, close_media_tab
        idle_watch = IdleWatch(args.close_idle_after)

    print(f"YouTube ad skipper -- started {time.ctime()}")
    for index in targets:
        print(f"  watching {finder.describe(index)}, region '{args.region}'")
    print(f"  looking for {list(args.keyword or ['ignorer'])}, "
          f"every {args.tick}s, for {args.hours}h"
          f"{' [DRY RUN]' if args.dry_run else ''}")
    if idle_watch:
        print(f"  closing {args.idle_app}'s "
              f"{'window' if args.idle_window else 'tab'} after "
              f"{args.close_idle_after:g} min of stillness")
    print("  Ctrl+C to stop\n")

    deadline = time.time() + 3600 * args.hours
    clicks = 0
    debug_written = 0
    # A real skip button disappears the moment it is clicked. If the very same
    # label is still sitting in the same place afterwards, the click achieved
    # nothing and re-clicking it forever only makes noise.
    clicked_already: tuple[str, int, int] | None = None
    suppress_logged = False
    recent: list[float] = []
    reported_rate = False
    try:
        while time.time() < deadline:
            started = time.time()
            seen_now: set[tuple[str, int, int]] = set()
            for index in targets:
                scan = finder.scan(index)
                if idle_watch:
                    idle_watch.observe(index, scan.frame)

                if args.debug and (scan.hit is not None or debug_written < DEBUG_FILE_LIMIT):
                    # Hits are always kept; the routine misses stop once capped.
                    save_debug(scan, "hit" if scan.hit else "scan")
                    if scan.hit is None:
                        debug_written += 1
                        if debug_written == DEBUG_FILE_LIMIT:
                            print(f"{stamp()}  debug: {DEBUG_FILE_LIMIT} scans saved, "
                                  f"only saving hits from now on")

                hit = scan.hit
                if hit is None:
                    continue

                fingerprint = (normalize(hit.text), hit.x // 25, hit.y // 25)
                seen_now.add(fingerprint)
                if fingerprint == clicked_already:
                    if not suppress_logged:
                        print(f"{stamp()}  {hit.text!r} is still there after being "
                              f"clicked, so it is not a skip button -- ignoring it")
                        suppress_logged = True
                    continue

                print(f"{stamp()}  found {hit.text!r} on monitor {hit.monitor} "
                      f"at ({hit.x}, {hit.y})  "
                      f"[ocr {hit.confidence:.2f}, match {hit.similarity:.2f}]")

                if args.dry_run:
                    continue

                origin = winput.get_pos()
                winput.click(hit.x, hit.y)
                clicks += 1
                clicked_already = fingerprint
                if not args.keep_mouse:
                    time.sleep(0.1)
                    winput.set_pos(*origin)
                    print(f"{stamp()}  clicked, cursor back at {origin}")
                else:
                    print(f"{stamp()}  clicked")

                time.sleep(args.cooldown)
                break  # one click per tick

            if clicked_already is not None and clicked_already not in seen_now:
                clicked_already = None  # it went away, so it may be clicked again
                suppress_logged = False

            if idle_watch and idle_watch.idle():
                minutes = idle_watch.screen_idle_seconds() / 60
                if args.dry_run:
                    print(f"{stamp()}  idle for {minutes:.0f} min -- would close "
                          f"{args.idle_app}'s tab [DRY RUN]")
                else:
                    done = close_media_tab(args.idle_app,
                                           whole_window=args.idle_window)
                    if done is None:
                        print(f"{stamp()}  idle for {minutes:.0f} min, but no "
                              f"{args.idle_app!r} window to close")
                    else:
                        print(f"{stamp()}  idle for {minutes:.0f} min -- {done}")
                        if args.on_idle_close:
                            import subprocess
                            print(f"{stamp()}  running: {args.on_idle_close}")
                            subprocess.Popen(args.on_idle_close, shell=True)
                # Either way, wait one full delay before trying again, so a
                # close that changed nothing does not repeat every tick.
                idle_watch.rearm()

            elapsed = time.time() - started
            recent.append(elapsed)
            # The first couple of sweeps fill the text cache and are far slower
            # than the rest, so wait for it to settle before quoting a rate.
            if len(recent) == 1:
                print(f"{stamp()}  first sweep of {len(targets)} monitor(s): "
                      f"{elapsed:.1f}s (building the text cache)")
            elif len(recent) == 6 and not reported_rate:
                settled = sorted(recent[-4:])[2]
                print(f"{stamp()}  settled -- sweeping all {len(targets)} "
                      f"monitor(s) every {max(settled, args.tick):.1f}s")
                reported_rate = True

            time.sleep(max(0.0, args.tick - elapsed))
    except KeyboardInterrupt:
        print("\nstopped by user")
    finally:
        finder.close()

    print(f"done -- {clicks} button{'' if clicks == 1 else 's'} clicked")
    return 0


if __name__ == "__main__":
    sys.exit(main())
