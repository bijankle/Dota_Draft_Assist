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

    **THE NARROW HALF IS SETTLED NOW, and it went the other way.**
    Horizontally there was never anything to decide — the largest 16:9
    rectangle inside a display taller than 16:9 is the full width, which
    is what the `min` returns. The VERTICAL was the open question:
    `SlotRect.to_pixels` read `y` and `h` as fractions of the WINDOW
    height, which on a 1920x1200 panel put the bar 11% lower and drew it
    11% taller than on 1920x1080.

    It is a fraction of the HUD BOX — see `SlotRect.to_pixels`, which
    carries the three pieces of evidence. The one that settles it is not
    a measurement at all but arithmetic: the pick tile is SQUARE on a
    real 3440x1440 client, and read against the window the crop box came
    out 42x56 on 800x600. A portrait does not change shape because the
    monitor did.

    The old objection — that changing the convention silently invalidates
    every saved `calibration_local.json` — has expired. There are no
    hand-set calibrations any more (the drag is gone), a measurement now
    replaces the last one rather than being refused, so a file written
    under the old reading is re-measured at the next strategy time. And
    it can only have been wrong on a display taller than 16:9, where it
    was wrong anyway.

    Settle it with a real 16:10 frame, not with reasoning — and it has
    been, by `tools/find_portraits.py` run over a folder of the user's own
    screenshots (`find_portraits._vertical`; there is no menu item for it
    any more, since it was an instrument rather than a feature). It weighs
    THREE candidates, not two:
    this function's reading, a 16:9 HUD box hung at the TOP of a taller
    display, and one CENTRED. The first two differ by 4px on 1920x1200
    and the third by 56px, so only the third would actually miss the
    portraits. Only a display TALLER than 16:9 can tell them apart — at
    16:9 and wider the vertical slack is nought and all three are the
    same number — which is why the confirmed 3440x1440 measurement above
    says nothing whatever about this.

    THE CENTRED MODEL IS REFUTED, measured rather than argued. Over the
    user's own screenshots the bar's top read 0.0019 spread as a fraction
    of the WINDOW, 0.0031 against a top-hung HUD box, and **-0.2028 to
    -0.0491 against a centred one** — negative, on every frame: it puts
    the pick bar above the top of the box it claims Dota draws it in. That
    was the only one of the three that would have missed the portraits.
    The two survivors differ by 4px on 1920x1200 and are still not
    separated, which costs nothing.
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
        """Fractions to pixels, anchored to Dota's 16:9 HUD box — BOTH axes.

        Dota lays its HUD out in a 16:9 area centred horizontally, and on a
        wider display it pillarboxes that area rather than stretching it —
        so on 3440x1440 the ten portraits occupy the middle 2560 pixels and
        a fraction of the FULL width lands hundreds of pixels off.

        **THE VERTICAL IS THE SAME BOX, and it used to be the WINDOW.**
        This read `y` and `h` as fractions of the frame's height, which is
        identical at 16:9 and at every aspect WIDER than it — the HUD box
        is the full height there — and wrong on anything TALLER. It is the
        one thing the resolution sweep was built to settle, and three
        independent things now agree:

        * **The measurement.** Over the user's own screenshots the portrait
          height spread 0.0137 against the window and **0.0044 against the
          HUD box** — three times tighter, on a quantity of 46 to 74 pixels
          where a pixel of rounding is under 2%.
        * **The arithmetic, which is the one that settles it.** The pick
          tile is SQUARE: `slot_w` 0.0525 of the span against `slot_h`
          0.0930 of the height is 1.00 at 16:9, measured on a real
          3440x1440 client. A portrait cannot change shape because the
          monitor did — Dota scales its HUD uniformly. Read against the
          window, the box came out 42x56 on 800x600 and 76x84 on 1440x900;
          against the HUD box it is 42x42 and 76x75.
        * **The symptom.** Matching scores 0.99 at the true size and 0.12
          four pixels out. A box **33% too tall** is not a near miss, and
          800x600 was the resolution that located nothing at all while
          1440x900, 11% out, located its ten and fitted them wrong.

        Nothing changes at 16:9 or wider, which is every display this app
        has actually run on — so this cannot regress a working setup. Only
        16:10, 4:3 and 5:4 move, and they moved onto the portraits.
        """
        left, span = hud_box(width, height)
        # The HUD box is 16:9, so its height follows from its width. On
        # 16:9 and wider this IS `height`; below it, it is less.
        box_h = span / HUD_ASPECT
        return (round(left + self.x * span), round(self.y * box_h),
                round(self.w * span), round(self.h * box_h))


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
