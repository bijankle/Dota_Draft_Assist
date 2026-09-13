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
    fraction-of-width wrong on an ultrawide monitor. That half is
    CONFIRMED: on a real 3440x1440 client the draft timer sits exactly at
    the centre of the middle 2560 pixels, and the pick bar is symmetric
    about it.

    **THE NARROW HALF IS NOT CONFIRMED, and this is the honest state of
    it.** Horizontally there is nothing to decide — the largest 16:9
    rectangle that fits inside a display taller than 16:9 is the full
    width, which is what the `min` returns. What has never been measured
    is the VERTICAL: `SlotRect.to_pixels` reads `y` and `h` as fractions of
    the WINDOW height, so on a 1920x1200 panel it places the bar 11% lower
    and draws it 11% taller than on 1920x1080. If Dota scales its HUD by
    the width — which is what pillarboxing on the wide side implies — that
    is wrong, and 16:10 laptops are the commonest display this app has
    never run on.

    It is left alone rather than "fixed", because replacing an unverified
    guess with a different unverified guess is not progress, and the cost
    of being wrong is asymmetric: the fractions in a saved
    `calibration_local.json` mean whatever this function said when they
    were written, so changing the convention silently invalidates every
    calibration anybody already has.

    What makes it survivable is that the app no longer has to be right
    about it. `autocal.find_banks` MEASURES `y` and `slot_h` off the
    picture in whatever units this function implies, on the user's own
    machine, so the convention cancels out of the answer. It bites in
    exactly two places: the shipped defaults transferring to a display
    nobody has calibrated on, and the search region — and `BAR_FRACTION`
    is deliberately loose enough to hold the bar under either reading.
    Settle it with a real 16:10 frame, not with reasoning — and there is
    now a button that does exactly that from frames already on disk:
    Help > Recognition checks > Check other screen resolutions
    (`find_portraits._vertical`). It weighs THREE candidates, not two:
    this function's reading, a 16:9 HUD box hung at the TOP of a taller
    display, and one CENTRED. The first two differ by 4px on 1920x1200
    and the third by 56px, so only the third would actually miss the
    portraits. Only a display TALLER than 16:9 can tell them apart — at
    16:9 and wider the vertical slack is nought and all three are the
    same number — which is why the confirmed 3440x1440 measurement above
    says nothing whatever about this.
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

    def bank_span(self) -> float:
        """Left edge of a bank's first portrait to the right edge of its
        fifth, as a fraction of the HUD box.

        FOUR pitches plus ONE portrait, which is the arithmetic that has
        already been got wrong once: `4 * slot_w + 4 * pitch` hung the Dire
        calibration box a hundred pixels off the right of the screen, where
        it could not be dragged at all. Spelled once so nobody has to
        rederive it.
        """
        return 4 * self.pitch + self.slot_w

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


def load_layout(calibration_file: Path | None = None) -> DraftLayout:
    """Same rule as `save_calibration`: resolved at call time."""
    calibration_file = calibration_file or CALIBRATION_FILE
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
                     calibration_file: Path | None = None) -> None:
    """The destination is resolved at CALL time, never bound as a default.

    A default argument is evaluated once at import, so a test that repoints
    `CALIBRATION_FILE` still wrote into the real repository — which is how
    a test run left a stray calibration_local.json behind and broke an
    unrelated test on the next run. Same rule as `ui_settings.load`.
    """
    path = calibration_file or CALIBRATION_FILE
    path.write_text(json.dumps(asdict(layout), indent=2), encoding="utf-8")
