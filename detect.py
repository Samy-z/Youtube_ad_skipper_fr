"""Find YouTube's French "Ignorer" skip button on screen, by reading text.

The previous version matched cropped screenshots of the button with template
matching, which broke as soon as anything changed size: a different monitor,
window vs. fullscreen, theater mode, or a YouTube restyle. Reading the word
"Ignorer" instead is scale-free -- the OCR model finds the text wherever and
however large it is, and returns its box.
"""

from __future__ import annotations

import difflib
import hashlib
import re
import unicodedata
from dataclasses import dataclass

import cv2
import mss
import numpy as np

# Scan windows, as (left, top, right, bottom) fractions of one monitor.
# "full" is the default: a player can be anywhere on any screen, and the
# detect/filter/cache pipeline below makes scanning everything affordable.
REGIONS = {
    "full": (0.0, 0.0, 1.0, 1.0),
    "br": (0.45, 0.45, 1.0, 1.0),
    "bottom": (0.0, 0.45, 1.0, 1.0),
    "right": (0.45, 0.0, 1.0, 1.0),
}

# Shape limits for something that could be a button label, in pixels. Generous
# on purpose -- this only has to discard things no label could ever be, such as
# a full paragraph or a one-pixel sliver. Recognition is what costs, so every
# box dropped here is time saved.
_MIN_H, _MAX_H = 8, 80
_MIN_W, _MAX_W = 20, 600
_MIN_RATIO, _MAX_RATIO = 1.0, 14.0

# Recognised crops are memoised by content. Bounded so a long run cannot grow
# without limit; the screen only holds so many distinct labels at once.
_CACHE_LIMIT = 6000

# Moving video invents text-like shapes that are different every frame, so they
# never hit the cache and would otherwise dominate the cost. A button is an
# overlay that holds still, so only crops that barely changed since the last
# frame are worth reading. Anything still moving is read a few at a time, which
# bounds the cost without ever ruling a region out for good.
_STABLE_MEAN_DIFF = 12.0
_MOVING_BUDGET = 24

# The capital I of "Ignorer" is routinely read back as l, 1 or |.
_CONFUSABLES = str.maketrans({"l": "i", "1": "i", "|": "i", "!": "i"})

# "Ignorer dans 5" is the countdown *before* the ad becomes skippable, and
# clicking it does nothing. OCR frequently drops spaces, so this is matched
# against the compacted form ("ignorerdans5").
_COUNTDOWN = re.compile(r"dans\d|\d$")

# A button label is short ("Ignorer les annonces" is 18 characters once
# compacted). OCR returns a whole line at a time, so anything much longer than
# the keyword is a sentence that merely contains it, not a button.
_MAX_LABEL_RATIO = 3


def normalize(text: str) -> str:
    """Lowercase, strip accents, fold OCR lookalikes, drop everything else."""
    text = unicodedata.normalize("NFKD", text)
    text = "".join(c for c in text if not unicodedata.combining(c))
    text = text.lower().translate(_CONFUSABLES)
    return re.sub(r"[^a-z0-9]+", "", text)


def prefix_similarity(haystack: str, needle: str) -> float:
    """How well `haystack` *starts with* `needle`.

    Anchored at the start on purpose. The button's label begins with "Ignorer",
    whereas the false positives seen in practice only contain it further in:
    "gitignore" on GitHub's repo form, or a line of prose that happens to
    mention the word. Matching anywhere in the string cannot tell those apart.
    """
    if not haystack:
        return 0.0
    best = 0.0
    n = len(needle)
    for span in (n - 1, n, n + 1):
        window = haystack[:span]
        if window:
            best = max(best, difflib.SequenceMatcher(None, window, needle).ratio())
    return best


@dataclass
class Hit:
    """A skip button located in global (physical pixel) screen coordinates."""
    x: int
    y: int
    text: str
    confidence: float
    similarity: float
    monitor: int
    box: tuple[int, int, int, int]  # left, top, right, bottom


@dataclass
class Scan:
    """Everything one pass over one monitor saw -- `hit` plus context for --debug."""
    monitor: int
    origin: tuple[int, int]  # global coords of the crop's top-left corner
    frame: np.ndarray
    words: list[tuple[tuple[int, int, int, int], str, float]]
    hit: Hit | None


class SkipButtonFinder:
    def __init__(
        self,
        region: str = "full",
        keywords: tuple[str, ...] = ("ignorer",),
        min_confidence: float = 0.55,
        min_similarity: float = 0.90,
    ):
        from rapidocr_onnxruntime import RapidOCR  # slow import, so keep it local

        self._ocr = RapidOCR()
        self._sct = mss.mss()
        self._seen: dict[bytes, tuple[str, float]] = {}
        self._previous: dict[tuple | None, np.ndarray] = {}
        self._rotation: dict[tuple | None, int] = {}
        self.region = REGIONS[region]
        self.keywords = tuple(normalize(k) for k in keywords)
        self.min_confidence = min_confidence
        self.min_similarity = min_similarity

    @property
    def monitors(self) -> list[int]:
        """1-based monitor indices; index 0 is the whole virtual desktop."""
        return list(range(1, len(self._sct.monitors)))

    def describe(self, index: int) -> str:
        m = self._sct.monitors[index]
        return f"monitor {index} ({m['width']}x{m['height']} at {m['left']},{m['top']})"

    def region_of(self, index: int) -> tuple[int, int, int, int]:
        """Absolute (left, top, width, height) of the scan window on a monitor."""
        m = self._sct.monitors[index]
        fl, ft, fr, fb = self.region
        return (
            m["left"] + int(m["width"] * fl),
            m["top"] + int(m["height"] * ft),
            int(m["width"] * (fr - fl)),
            int(m["height"] * (fb - ft)),
        )

    @staticmethod
    def _could_be_a_label(box: np.ndarray) -> bool:
        xs, ys = box[:, 0], box[:, 1]
        w, h = float(xs.max() - xs.min()), float(ys.max() - ys.min())
        if not (_MIN_H <= h <= _MAX_H and _MIN_W <= w <= _MAX_W):
            return False
        return _MIN_RATIO <= w / max(h, 1.0) <= _MAX_RATIO

    @staticmethod
    def _bounds(box: np.ndarray, shape: tuple) -> tuple[int, int, int, int]:
        xs, ys = box[:, 0], box[:, 1]
        return (max(0, int(xs.min())), max(0, int(ys.min())),
                min(shape[1], int(xs.max())), min(shape[0], int(ys.max())))

    def _held_still(self, before: np.ndarray | None, after: np.ndarray,
                    box: np.ndarray) -> bool:
        """Whether this box looks the same as it did on the previous frame."""
        if before is None or before.shape != after.shape:
            return False
        x0, y0, x1, y1 = self._bounds(box, after.shape)
        if x1 - x0 < 2 or y1 - y0 < 2:
            return False
        a = before[y0:y1, x0:x1].astype(np.int16)
        b = after[y0:y1, x0:x1].astype(np.int16)
        return float(np.abs(a - b).mean()) <= _STABLE_MEAN_DIFF

    def _read_text(self, frame: np.ndarray, key: tuple | None = None) -> list:
        """Find text in `frame` as [box, text, score], the way RapidOCR returns it.

        Split into stages rather than one call because they cost very different
        amounts, measured on a 1080p monitor showing a busy YouTube page:

          detect      ~0.3s, roughly fixed
          crop         2.8s via RapidOCR's helper, which runs a whole-image
                       perspective warp per box -- replaced here by a plain
                       array slice, since screen text is axis-aligned
          recognise   ~11s for all 240 boxes, and it scales with how many

        So: detect, discard boxes no label could be, slice only the survivors,
        and reuse results for crops that have not changed. A polling loop looks
        at a mostly static screen, so nearly every crop is a repeat and a warm
        scan of a whole monitor costs about as much as detection alone.
        """
        boxes, _ = self._ocr.text_detector(frame)
        if boxes is None or len(boxes) == 0:
            self._previous[key] = frame
            return []

        candidates = []
        for box in boxes:
            if not self._could_be_a_label(box):
                continue
            x0, y0, x1, y1 = self._bounds(box, frame.shape)
            if x1 - x0 >= 2 and y1 - y0 >= 2:
                candidates.append((box, frame[y0:y1, x0:x1]))
        if not candidates:
            self._previous[key] = frame
            return []

        before = self._previous.get(key)
        self._previous[key] = frame

        keys = [hashlib.blake2b(cv2.resize(c, (32, 12)).tobytes(),
                                digest_size=8).digest()
                for _, c in candidates]

        still, moving = [], []
        for k, (box, crop) in zip(keys, candidates):
            if k in self._seen:
                continue
            (still if self._held_still(before, frame, box) else moving).append((k, crop))

        # Everything moving is queued rather than dropped, and the starting
        # point rotates, so a busy screen is covered over a few ticks.
        if moving:
            start = self._rotation.get(key, 0) % len(moving)
            ordered = moving[start:] + moving[:start]
            self._rotation[key] = start + _MOVING_BUDGET
            still.extend(ordered[:_MOVING_BUDGET])

        pending = still
        if pending:
            if len(self._seen) > _CACHE_LIMIT:
                self._seen.clear()
            recognised, _ = self._ocr.text_recognizer([c for _, c in pending])
            for (key, _), result in zip(pending, recognised):
                text, score = result[0], result[1]
                self._seen[key] = (text, float(score))

        out = []
        for key, (box, _) in zip(keys, candidates):
            found = self._seen.get(key)
            if found and found[0]:
                out.append([box.tolist(), found[0], found[1]])
        return out

    def scan(self, index: int) -> Scan:
        return self.scan_box(*self.region_of(index), monitor=index)

    def scan_box(self, left: int, top: int, width: int, height: int,
                 monitor: int = 0) -> Scan:
        """Scan an arbitrary absolute screen rectangle."""
        shot = self._sct.grab({"left": left, "top": top,
                               "width": width, "height": height})
        frame = np.array(shot)[:, :, :3]  # BGRA -> BGR
        ox, oy = left, top
        raw = self._read_text(frame, key=(left, top, width, height))

        words: list[tuple[tuple[int, int, int, int], str, float]] = []
        hit: Hit | None = None
        best_similarity = 0.0

        for points, text, score in raw or []:
            xs = [p[0] for p in points]
            ys = [p[1] for p in points]
            local = (int(min(xs)), int(min(ys)), int(max(xs)), int(max(ys)))
            confidence = float(score)
            words.append((local, text, confidence))

            if confidence < self.min_confidence:
                continue
            compact = normalize(text)
            if _COUNTDOWN.search(compact):
                continue  # ad not skippable yet

            keyword, similarity = max(
                ((k, prefix_similarity(compact, k)) for k in self.keywords),
                key=lambda pair: pair[1],
            )
            if similarity < self.min_similarity or similarity <= best_similarity:
                continue
            if len(compact) > _MAX_LABEL_RATIO * len(keyword):
                continue  # a line of text containing the word, not a label

            best_similarity = similarity
            left, top, right, bottom = local
            # Aim at the matched word, not the middle of the box: "Ignorer les
            # annonces" is read as one box, and its centre sits over "annonces".
            share = min(1.0, len(keyword) / max(1, len(compact)))
            hit = Hit(
                x=ox + left + int((right - left) * share / 2),
                y=oy + (top + bottom) // 2,
                text=text,
                confidence=confidence,
                similarity=similarity,
                monitor=monitor,
                box=(ox + left, oy + top, ox + right, oy + bottom),
            )

        return Scan(monitor, (ox, oy), frame, words, hit)

    def close(self) -> None:
        self._sct.close()
