"""Ranked-role-queue role reading. The draft interface displays each
player's ASSIGNED role — ground truth, better than inferring roles from
statistics — as a small icon strip under each portrait.

Icons are matched by template against assets/role_icons/<role>.png,
harvested from real frames (crop them from a debug dump once and they work
until Valve redraws the icons). Until templates exist, read_roles returns
None per slot and the UI's manual role selector is the source of the user's
own role — reading must degrade to 'unknown', never guess.
"""

from pathlib import Path

import cv2
import numpy as np

from ..config import ASSETS_DIR
from .layout import DraftLayout, SlotRect

ROLE_ICONS_DIR = ASSETS_DIR / "role_icons"
ROLES = ("carry", "mid", "offlane", "soft_support", "hard_support")
MATCH_THRESHOLD = 0.70  # normalised cross-correlation floor


def load_templates(icons_dir: Path = ROLE_ICONS_DIR) -> dict[str, np.ndarray]:
    templates = {}
    if icons_dir.is_dir():
        for role in ROLES:
            p = icons_dir / f"{role}.png"
            if p.exists():
                img = cv2.imread(str(p), cv2.IMREAD_GRAYSCALE)
                if img is not None:
                    templates[role] = img
    return templates


def read_role(frame: np.ndarray, role_rect: SlotRect,
              templates: dict[str, np.ndarray]) -> str | None:
    if not templates:
        return None
    h, w = frame.shape[:2]
    x, y, cw, ch = role_rect.to_pixels(w, h)
    strip = frame[max(0, y):y + ch, max(0, x):x + cw]
    if strip.size == 0 or ch < 4:
        return None
    grey = cv2.cvtColor(strip, cv2.COLOR_BGR2GRAY)
    best_role, best_score = None, MATCH_THRESHOLD
    for role, tpl in templates.items():
        scale = ch / tpl.shape[0]
        scaled = cv2.resize(tpl, (max(1, round(tpl.shape[1] * scale)), ch))
        if scaled.shape[1] > grey.shape[1]:
            continue
        res = cv2.matchTemplate(grey, scaled, cv2.TM_CCOEFF_NORMED)
        score = float(res.max())
        if score > best_score:
            best_role, best_score = role, score
    return best_role


def read_all_roles(frame: np.ndarray, layout: DraftLayout,
                   templates: dict[str, np.ndarray] | None = None
                   ) -> dict[tuple[str, int], str | None]:
    templates = templates if templates is not None else load_templates()
    return {(rect.team, rect.slot):
            read_role(frame, layout.role_rect(rect), templates)
            for rect in layout.slots()}
