# Youtube ad skipper (FR)

Watches the screen and clicks YouTube's **Ignorer** button when an ad becomes
skippable.

```bash
python skipper.py
```

A launcher also starts it without a terminal: double-click `run.exe`. It is not
shipped in the repository; build it once with `python build_exe.py`.

Stop with Ctrl+C. A step-by-step guide is available in [GUIDE.md](GUIDE.md),
in French; this page mostly explains **how it works**.
*La version française de cette page est dans [README.md](README.md).*

## Requirements

Windows, and Python 3.10 or newer.

```bash
pip install -r requirements.txt
```

No external software to install: the OCR model ships with the pip package and
runs on the CPU.

## How it works

It reads the screen. `rapidocr-onnxruntime` (a pip-only OCR model, no external
binary) finds text anywhere and returns its box, so the word "Ignorer" is found
at whatever size it happens to be.

Every monitor is scanned in full, so the player can be anywhere on any screen.
Monitors are enumerated at startup, so plugging in a third one just works.

## Why v0 never worked

Two separate bugs, either of which was fatal on its own.

**1. Display scaling.** The primary monitor runs at 125%. `mss` captures real
pixels (1920x1080) but pyautogui works in the scaled-down space Windows reports
to non-DPI-aware processes (1536x864). The button was located in one coordinate
system and clicked in the other, so every click landed about 1.25x too far right
and down. `winput.make_dpi_aware()` now settles this before anything measures the
screen, and clicking goes through `user32` directly instead of pyautogui.

**2. Template matching.** `ignore_button_fr_screen_*.png` were crops of the
button at one specific size. Template matching only matches at that size, so
anything that changed it — a different monitor, windowed vs. fullscreen, theater
mode, a YouTube restyle — meant no match. v0's workaround tried ~400 rescaled
copies of the template per frame, which was slow and still missed.

`legacy/` holds those files for reference; nothing imports them.

## What counts as the button

OCR hands back a whole line of text at a time, which is what made the first
version click things it shouldn't. Four rules keep it honest:

- **The word must start the text.** "gitignore" on GitHub's repo form and any
  sentence merely mentioning the word both have it in the middle, and that is
  the only thing separating them from a real button.
- **It must be a close read.** `Ignorer` and `Ignore` count, `Ignor` does not
  (`--min-similarity`, default 0.90). Accents are stripped and OCR lookalikes
  folded first, so `lgnorer`, `1gnorer` and `|gnorer` all still match — missing
  a real button is the failure that matters more.
- **It must be short.** A button label is a few words; a 60-character line
  containing the word is prose.
- **`Ignorer dans 5` is rejected** — that is the countdown before the ad is
  skippable, and clicking it does nothing.

The click aims at the **matched word**, not the centre of the OCR box. For
"Ignorer les annonces" read as one box, the centre sits over "annonces", which
is how clicks ended up landing away from the word.

If a label is still on screen after being clicked, it was not a skip button —
a real one disappears — so it is ignored instead of being clicked on every tick.

## Speed

Scanning whole screens naively costs about 12s per monitor, which would be
useless. Where that time actually goes, on a 1080p monitor showing a busy
YouTube page (240 text boxes):

| stage | cost | what is done about it |
| --- | --- | --- |
| detect text boxes | ~0.3s | cheap and roughly fixed; always run |
| crop the boxes | ~2.8s | RapidOCR warps the whole image once per box. Screen text is axis-aligned, so a plain array slice replaces it |
| recognise the text | ~11s | the real cost, and it scales with the number of boxes |

Recognition is therefore avoided rather than optimised:

- **Boxes that no label could be are dropped** before anything is cropped —
  too tall, too wide, wrong aspect.
- **Results are cached by crop content.** A polling loop stares at a mostly
  static screen, so nearly every crop is one already read.
- **Only crops that held still since the last frame are read.** Moving video
  invents text-like shapes that differ every frame and would never hit the
  cache; a button is an overlay that sits still. Anything still moving is read
  a few per sweep on rotation, so nothing is ruled out permanently — it just
  costs a sweep or two longer.

The result, measured across both monitors at full resolution:

| | cost |
| --- | --- |
| first sweep (cold cache) | ~2s |
| settled | **~0.8s for both monitors** (~0.4s each) |

The program prints its real rate once it settles. If a sweep takes longer than
`--tick`, the sweep time is the poll rate.

## Options

| Flag | Default | Meaning |
| --- | --- | --- |
| `--monitor` | `all` | `all` (however many are plugged in), or a 1-based monitor number. |
| `--region` | `full` | Narrow the scan to `br`, `bottom` or `right` to cut the cold-start cost. Rarely needed. |
| `--tick` | `1` | Minimum seconds between sweeps. A sweep that takes longer sets the real rate. |
| `--hours` | `6` | How long to run. |
| `--cooldown` | `4` | Pause after a click, so one button is not clicked repeatedly. |
| `--keyword` | `ignorer` | Text to hunt for. Repeatable, e.g. `--keyword ignorer --keyword skip`. |
| `--min-similarity` | `0.90` | How close the read text must be. Lower it if a button is being missed. |
| `--min-confidence` | `0.55` | Reject OCR reads below this confidence. |
| `--dry-run` | off | Report detections without clicking. |
| `--debug` | off | Write annotated scans to `debug/`. |
| `--keep-mouse` | off | Leave the cursor on the button instead of putting it back. |

The cursor is returned to where you left it after each click.

## If it misses a button

```bash
python skipper.py --dry-run --debug
```

`debug/` then holds the scanned image with every piece of text boxed and its OCR
confidence, which shows immediately whether the button was read as something odd
(add a `--keyword`), read with low confidence (lower `--min-confidence`), or not
read at all (it may have been moving — see Speed above).

The [guide](GUIDE.md#6-dépannage) breaks each symptom down in a table, in French.

## Tests

```bash
python -m pytest test_matching.py -q
```

covers the accept/reject rules against realistic OCR output, including the
misfires seen in real runs (`gitignore`, prose lines mentioning the word).

```bash
python selftest.py
```

checks capture, DPI scaling and monitor offsets end to end — it reads text
already on screen, computes its global coordinates, re-grabs at exactly those
coordinates and confirms the same text is there. It also draws a fake
"Ignorer les annonces" button and confirms the click point lands on the word
"Ignorer" rather than in the middle of the label. No ad needed.
