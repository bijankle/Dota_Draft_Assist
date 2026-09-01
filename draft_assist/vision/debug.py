"""Inspectable evidence, not log lines: every debug dump is the captured
frame, the ten slot crops, and a text record of what each matched to at what
distance. Most vision bugs reduce to whether the right rectangle was cropped,
and a picture answers that instantly.
"""

import time
from pathlib import Path

import cv2
import numpy as np

from ..config import DEBUG_OUT
from .library import EMPTY_SLOT
from .recognize import DraftRead


def draw_overlay(frame: np.ndarray, read: DraftRead,
                 names: dict[int, str] | None = None) -> np.ndarray:
    """The captured frame with crop boxes and match confidences drawn on it —
    also used by the live debug view in the UI."""
    out = frame.copy()
    h, w = out.shape[:2]
    for s in read.slots:
        x, y, cw, ch = s.rect.to_pixels(w, h)
        if s.hero_id is None:
            color, text = (0, 0, 255), f"? d{s.distance} m{s.margin}"
        elif s.hero_id == EMPTY_SLOT:
            color, text = (160, 160, 160), f"empty d{s.distance}"
        else:
            name = (names or {}).get(s.hero_id, str(s.hero_id))
            color, text = (0, 255, 0), f"{name} d{s.distance} m{s.margin}"
        cv2.rectangle(out, (x, y), (x + cw, y + ch), color, 2)
        cv2.putText(out, text, (x, y + ch + 14), cv2.FONT_HERSHEY_SIMPLEX,
                    0.42, color, 1, cv2.LINE_AA)
    return out


def dump(frame: np.ndarray, read: DraftRead,
         names: dict[int, str] | None = None,
         out_root: Path | None = None) -> Path:
    """Writes frame.png, overlay.png, slot crops, and slots.txt into a
    timestamped folder; returns the folder.

    out_root is resolved at call time (not bound as a default) so the
    destination can be repointed."""
    folder = (out_root or DEBUG_OUT) / time.strftime("%Y%m%d_%H%M%S")
    folder.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(folder / "frame.png"), frame)
    cv2.imwrite(str(folder / "overlay.png"), draw_overlay(frame, read, names))
    lines = []
    for s in read.slots:
        tag = f"{s.rect.team}{s.rect.slot}"
        if s.crop is not None and s.crop.size:
            cv2.imwrite(str(folder / f"slot_{tag}.png"), s.crop)
        resolved = ("UNKNOWN" if s.hero_id is None else
                    "EMPTY" if s.hero_id == EMPTY_SLOT else
                    (names or {}).get(s.hero_id, str(s.hero_id)))
        lines.append(f"{tag}: {resolved}  nearest={s.best_label} "
                     f"distance={s.distance} margin={s.margin}")
    (folder / "slots.txt").write_text("\n".join(lines), encoding="utf-8")
    return folder
