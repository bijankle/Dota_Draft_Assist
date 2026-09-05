"""Measure where the portraits are, using heroes the game has named.

Calibrating by hand needs someone looking at the screen, and this side of
the project cannot: the crop boxes were hundreds of pixels off on an
ultrawide for days with no way to see it. But at strategy time the app
holds both halves of the answer at once — a captured frame, and the ten
heroes the minimap named in it — so the geometry can be measured instead.

Each known hero's portrait is searched for in the top strip by normalised
cross-correlation. Scale is unknown, so one hero is used to find it (over a
grid of widths and aspect ratios) and the rest are then searched at that
size. Ten rectangles give the bank starts, the pitch, the size and the top
edge directly, with no assumption about resolution or HUD scaling.

It never invents a layout: too few confident hits, or a strip that does not
fall into two banks, and it returns nothing with a reason.
"""

from dataclasses import dataclass, field

import cv2
import numpy as np

from .layout import DraftLayout, hud_box

TOP_FRACTION = 0.30          # the pick bar is at the top; the hero is not
# Width as a fraction of the HUD box, height as a fraction of the frame.
# Both are searched, because the portrait's aspect ON SCREEN is not the
# aspect of the stored image — Dota stretches it into its own box, and
# matching is sharply scale-sensitive: at the true size a portrait scores
# 0.99 and four pixels out it scores 0.12. A grid this coarse only finds
# the neighbourhood; _refine walks in from there a pixel at a time.
WIDTHS = tuple(round(0.028 + 0.003 * i, 4) for i in range(19))
HEIGHTS = tuple(round(0.050 + 0.006 * i, 4) for i in range(17))
MIN_SCORE = 0.35
MIN_FOUND = 8
TEAM_SIZE = 5


@dataclass
class Located:
    hero_id: int
    x: int
    y: int
    w: int
    h: int
    score: float


@dataclass
class Calibration:
    layout: DraftLayout | None = None
    found: list = field(default_factory=list)
    note: str = ""

    @property
    def ok(self) -> bool:
        return self.layout is not None


def _grey(image):
    return (cv2.cvtColor(image, cv2.COLOR_BGR2GRAY) if image.ndim == 3
            else image)


def _best_at(strip, template, width, height):
    if (width < 8 or height < 8 or height >= strip.shape[0]
            or width >= strip.shape[1]):
        return None
    resized = cv2.resize(template, (width, height),
                         interpolation=cv2.INTER_AREA)
    result = cv2.matchTemplate(strip, resized, cv2.TM_CCOEFF_NORMED)
    _mn, score, _ml, location = cv2.minMaxLoc(result)
    return float(score), location


def _refine(strip, template, width, height, reach=6):
    """Walk out from a coarse hit a pixel at a time.

    Worth the extra passes: the coarse grid lands near the right size, and
    the difference between near and exact is the difference between 0.2 and
    0.99.
    """
    best = (width, height, -1.0)
    for w in range(max(8, width - reach), width + reach + 1):
        for h in range(max(8, height - reach), height + reach + 1):
            hit = _best_at(strip, template, w, h)
            if hit is not None and hit[0] > best[2]:
                best = (w, h, hit[0])
    return best


def find_scale(strip, templates, span: int, frame_height: int):
    """(width, height, score) of the portrait size that matches best.

    Found once, from a few heroes, rather than per hero: every portrait is
    the same size on screen, so searching the grid ten times over is ten
    times the work for one answer.
    """
    best = None
    for template in templates:
        for width_frac in WIDTHS:
            width = int(round(span * width_frac))
            for height_frac in HEIGHTS:
                height = int(round(frame_height * height_frac))
                hit = _best_at(strip, template, width, height)
                if hit is None:
                    continue
                if best is None or hit[0] > best[2]:
                    best = (width, height, hit[0])
    if best is None:
        return None
    return _refine(strip, templates[0], best[0], best[1])


def locate(frame, portraits: dict[int, np.ndarray]) -> list[Located]:
    height, width = frame.shape[:2]
    _left, span = hud_box(width, height)
    strip = _grey(frame)[:max(1, int(height * TOP_FRACTION)), :]
    greys = {hid: _grey(image) for hid, image in portraits.items()
             if image is not None and image.size}
    if not greys:
        return []

    probes = [greys[hid] for hid in list(greys)[:2]]
    scale = find_scale(strip, probes, int(span), height)
    if scale is None:
        return []
    box_w, box_h, _score = scale

    out = []
    for hero_id, template in greys.items():
        hit = _best_at(strip, template, box_w, box_h)
        if hit is None:
            continue
        score, (x, y) = hit
        if score >= MIN_SCORE:
            out.append(Located(hero_id, x, y, box_w, box_h, score))
    out.sort(key=lambda item: item.x)
    return out


def layout_from(found: list[Located], width: int, height: int,
                base: DraftLayout | None = None) -> Calibration:
    base = base or DraftLayout()
    if len(found) < MIN_FOUND:
        return Calibration(found=found, note=(
            f"only {len(found)} of the ten portraits were found — not "
            "enough to place the boxes"))

    left, span = hud_box(width, height)
    xs = [item.x for item in found]
    steps = [b - a for a, b in zip(xs, xs[1:])]
    split = steps.index(max(steps)) + 1
    if not (2 <= split <= len(found) - 2):
        return Calibration(found=found, note=(
            "the portraits found do not fall into two banks — this frame is "
            "probably not a pick or strategy screen"))

    banks = (xs[:split], xs[split:])
    within = [b - a for bank in banks for a, b in zip(bank, bank[1:])]
    if not within:
        return Calibration(found=found, note="not enough portraits per bank")
    pitch = float(np.median(within))
    if pitch <= 0:
        return Calibration(found=found, note="portraits overlap; no pitch")

    layout = DraftLayout(
        radiant_x=(banks[0][0] - left) / span,
        dire_x=(banks[1][0] - left) / span,
        y=float(np.median([i.y for i in found])) / height,
        slot_w=float(np.median([i.w for i in found])) / span,
        slot_h=float(np.median([i.h for i in found])) / height,
        pitch=pitch / span,
        role_dy=base.role_dy, role_h=base.role_h,
    )
    for value in (layout.radiant_x, layout.dire_x, layout.y, layout.slot_w,
                  layout.slot_h, layout.pitch):
        if not 0.0 <= value <= 1.0:
            return Calibration(found=found, note=(
                "the measured layout falls outside the frame; ignoring it"))
    return Calibration(layout=layout, found=found, note=(
        f"measured from {len(found)} portraits, mean confidence "
        f"{np.mean([i.score for i in found]):.2f}"))


def calibrate(frame, portraits: dict[int, np.ndarray],
              base: DraftLayout | None = None) -> Calibration:
    if frame is None or not portraits:
        return Calibration(note="no frame, or the game has named no heroes")
    height, width = frame.shape[:2]
    return layout_from(locate(frame, portraits), width, height, base)


def base_portraits(hero_ids) -> dict[int, np.ndarray]:
    """The downloaded base portrait for each of these heroes.

    Base only, never persona or arcana variants: those are alternative
    appearances of the same hero, and one of them matching in the wrong
    place would move the boxes rather than confirm them.
    """
    import cv2

    from . import library as library_mod

    wanted = set(hero_ids)
    out: dict[int, np.ndarray] = {}
    try:
        for hero_id, label, path in library_mod._iter_source_images():
            if hero_id not in wanted or not label.startswith("base/"):
                continue
            image = cv2.imread(str(path), cv2.IMREAD_COLOR)
            if image is not None and image.size:
                out[hero_id] = image
    except (FileNotFoundError, ValueError):
        return {}
    return out
