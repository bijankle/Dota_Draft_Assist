"""Pick-slot geometry. ALL COORDINATES ARE FRACTIONS OF WINDOW WIDTH/HEIGHT,
never absolute pixels (see CLAUDE.md) — the Dota window is measured from its
handle at capture time and the layout survives resolution changes.

The draft screen's ten portraits sit in two mirrored banks of five along the
top, so the layout is parameterised by a handful of numbers instead of forty:
per-team first-slot position, slot size, and horizontal pitch. Calibration
mode nudges these parameters and saves to calibration_local.json
(gitignored), which overrides the shipped defaults.

The shipped defaults are a starting guess for a 16:9 Ranked All Pick screen
and are expected to be nudged against the user's first real frames — the
debug overlay draws the boxes so being off is visible instantly.
"""

import json
from dataclasses import asdict, dataclass
from pathlib import Path

from ..config import CALIBRATION_FILE


HUD_ASPECT = 16 / 9


def hud_box(width: int, height: int) -> tuple[float, float]:
    """(left edge, width) of the 16:9 area Dota draws its HUD into.

    On 16:9 and narrower this is the whole window. On anything wider the
    HUD is pillarboxed to a centred 16:9 box, which is what makes a plain
    fraction-of-width wrong on an ultrawide monitor.
    """
    if not width or not height:
        return 0.0, float(width)
    span = min(float(width), height * HUD_ASPECT)
    return (width - span) / 2.0, span


@dataclass
class SlotRect:
    team: str        # "radiant" | "dire"
    slot: int        # 0..4 within the team
    x: float         # all fractional [0..1]
    y: float
    w: float
    h: float

    def to_pixels(self, width: int, height: int) -> tuple[int, int, int, int]:
        """Fractions to pixels, anchored to Dota's 16:9 HUD box.

        Dota lays its HUD out in a 16:9 area centred horizontally, and on a
        wider display it pillarboxes that area rather than stretching it —
        so on 3440x1440 the ten portraits occupy the middle 2560 pixels and
        a fraction of the FULL width lands hundreds of pixels off. The
        vertical axis needs no such correction: the bar hugs the top edge.
        """
        left, span = hud_box(width, height)
        return (round(left + self.x * span), round(self.y * height),
                round(self.w * span), round(self.h * height))


@dataclass
class DraftLayout:
    # Radiant bank (left): first portrait's top-left, size, and pitch.
    radiant_x: float = 0.0575
    dire_x: float = 0.6250      # dire bank (right) mirrors radiant
    y: float = 0.0330
    slot_w: float = 0.0525
    slot_h: float = 0.0930
    pitch: float = 0.0640       # horizontal step between slots in a bank
    # Role icon strip relative to each slot (fraction of window, offset from
    # the slot's top-left). Ranked role queue shows assigned roles here.
    role_dy: float = 0.0960
    role_h: float = 0.0180

    def slots(self) -> list[SlotRect]:
        out = []
        for team, x0 in (("radiant", self.radiant_x), ("dire", self.dire_x)):
            for i in range(5):
                out.append(SlotRect(team, i, x0 + i * self.pitch,
                                    self.y, self.slot_w, self.slot_h))
        return out

    def role_rect(self, slot: SlotRect) -> SlotRect:
        return SlotRect(slot.team, slot.slot, slot.x,
                        slot.y + self.role_dy, slot.w, self.role_h)


def load_layout(calibration_file: Path = CALIBRATION_FILE) -> DraftLayout:
    layout = DraftLayout()
    if calibration_file.exists():
        overrides = json.loads(calibration_file.read_text(encoding="utf-8"))
        known = set(asdict(layout))
        bad = set(overrides) - known
        if bad:
            raise ValueError(f"{calibration_file} has unknown keys {sorted(bad)}; "
                             f"valid keys: {sorted(known)}")
        for k, v in overrides.items():
            setattr(layout, k, float(v))
    return layout


def save_calibration(layout: DraftLayout,
                     calibration_file: Path = CALIBRATION_FILE) -> None:
    calibration_file.write_text(
        json.dumps(asdict(layout), indent=2), encoding="utf-8")
