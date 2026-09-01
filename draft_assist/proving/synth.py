"""The proving ground's frame generator: synthetic draft screens composited
from hero portraits, with ground-truth labels, so the recognition pipeline
can be exercised, tuned and regression-tested without anyone sending
screenshots.

Distortions model what real capture does to portraits: resolution scaling,
brightness/contrast drift, sensor-ish noise, JPEG-like compression, slight
crop misalignment (calibration error), and the dimming/hover tints the draft
UI applies. If recognition survives these, live frames are the easy case —
and when a live frame still fails, its crop goes into the variants library
and (via replay) back into this suite as a regression case.

Portraits come from the real downloaded library when present; tests and
network-less environments use deterministic procedural portraits instead.
"""

from dataclasses import dataclass, field

import cv2
import numpy as np

from ..vision.layout import DraftLayout
from ..vision.library import EMPTY_SLOT


def procedural_portrait(hero_id: int, size: tuple[int, int] = (128, 72)) -> np.ndarray:
    """Deterministic fake portrait for a hero id: unique enough to stand in
    for real art in tests, similar enough in family to make matching
    non-trivial."""
    rng = np.random.default_rng(hero_id * 7919 + 13)
    w, h = size
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    img = np.zeros((h, w, 3), np.float32)
    for c in range(3):
        a, b, ph = rng.uniform(0.3, 1.0), rng.uniform(0.01, 0.09), rng.uniform(0, 6)
        img[:, :, c] = 90 + 70 * a * np.sin(b * (xx + yy * rng.uniform(0.3, 2)) + ph)
    for _ in range(6):
        center = (int(rng.uniform(0, w)), int(rng.uniform(0, h)))
        radius = int(rng.uniform(6, 22))
        color = tuple(int(x) for x in rng.uniform(30, 225, 3))
        cv2.circle(img, center, radius, color, -1)
    return np.clip(img, 0, 255).astype(np.uint8)


def empty_slot_image(size: tuple[int, int] = (128, 72)) -> np.ndarray:
    w, h = size
    img = np.full((h, w, 3), 26, np.uint8)
    cv2.rectangle(img, (2, 2), (w - 3, h - 3), (48, 44, 40), 1)
    return img


@dataclass
class Distortions:
    brightness: tuple[float, float] = (-18, 18)     # additive
    contrast: tuple[float, float] = (0.88, 1.12)    # multiplicative
    noise_sigma: tuple[float, float] = (0.0, 4.0)
    jpeg_quality: tuple[int, int] = (60, 95)
    # Calibration error: crop boxes off by up to this fraction of slot size.
    jitter_frac: float = 0.06
    dim_chance: float = 0.3      # draft UI dims already-picked portraits
    dim_factor: tuple[float, float] = (0.55, 0.8)


@dataclass
class SynthCase:
    frame: np.ndarray
    truth: list[int]             # per layout slot: hero id or EMPTY_SLOT
    resolution: tuple[int, int]


RESOLUTIONS = [(1920, 1080), (2560, 1440), (1600, 900), (1366, 768)]


def generate_case(portraits: dict[int, np.ndarray], layout: DraftLayout,
                  rng: np.random.Generator,
                  resolution: tuple[int, int] | None = None,
                  distort: Distortions | None = None,
                  fill_range: tuple[int, int] = (0, 10)) -> SynthCase:
    d = distort or Distortions()
    width, height = resolution or RESOLUTIONS[rng.integers(len(RESOLUTIONS))]

    # Menu-ish background: dark vertical gradient with mild texture.
    grad = np.linspace(18, 42, height, dtype=np.float32)[:, None]
    frame = np.repeat(grad, width, axis=1)
    frame = np.stack([frame * 1.1, frame, frame * 0.9], axis=2)
    frame += rng.normal(0, 2, frame.shape)
    frame = np.clip(frame, 0, 255).astype(np.uint8)

    slots = layout.slots()
    n_fill = int(rng.integers(fill_range[0], fill_range[1] + 1))
    hero_pool = rng.permutation(list(portraits))
    filled_idx = set(rng.choice(len(slots), size=n_fill, replace=False).tolist())

    truth = []
    pool_i = 0
    for si, rect in enumerate(slots):
        x, y, w, h = rect.to_pixels(width, height)
        # Calibration-error jitter is applied to WHERE we paste, while the
        # recogniser still crops at the nominal rect — same effect as the
        # boxes being slightly off on a real screen.
        jx = int(rng.uniform(-d.jitter_frac, d.jitter_frac) * w)
        jy = int(rng.uniform(-d.jitter_frac, d.jitter_frac) * h)
        if si in filled_idx:
            hid = int(hero_pool[pool_i]); pool_i += 1
            tile = portraits[hid]
        else:
            hid = EMPTY_SLOT
            tile = empty_slot_image()
        truth.append(hid)

        tile = cv2.resize(tile, (w, h), interpolation=cv2.INTER_AREA).astype(np.float32)
        tile = tile * rng.uniform(*d.contrast) + rng.uniform(*d.brightness)
        if hid != EMPTY_SLOT and rng.uniform() < d.dim_chance:
            tile *= rng.uniform(*d.dim_factor)
        sigma = rng.uniform(*d.noise_sigma)
        if sigma > 0:
            tile += rng.normal(0, sigma, tile.shape)
        tile = np.clip(tile, 0, 255).astype(np.uint8)

        px, py = x + jx, y + jy
        px = min(max(px, 0), width - w)
        py = min(max(py, 0), height - h)
        frame[py:py + h, px:px + w] = tile

    quality = int(rng.integers(*d.jpeg_quality))
    ok, enc = cv2.imencode(".jpg", frame,
                           [cv2.IMWRITE_JPEG_QUALITY, quality])
    assert ok
    frame = cv2.imdecode(enc, cv2.IMREAD_COLOR)
    return SynthCase(frame=frame, truth=truth, resolution=(width, height))


def procedural_portrait_set(n_heroes: int = 126) -> dict[int, np.ndarray]:
    return {hid: procedural_portrait(hid) for hid in range(1, n_heroes + 1)}
