"""Finding the pick bar with nothing but the picture.

This is the step that removes the drag. Everything here runs on a frame
alone — no portrait library, no GSI, no minimap — because that is what
lets it run DURING hero selection instead of after the draft is over.

The suite it joins had never rendered a frame that was not 16:9, so the
whole question of aspect ratio was untested. It is exercised here at 16:9,
16:10, 5:4, 21:9 and 32:9, and at five HUD scales, because Dota's HUD scale
slider is the half of the problem that no shipped default can survive.
"""

import numpy as np
import pytest

from draft_assist.proving.synth import (Distortions, RESOLUTIONS,
                                        generate_case, procedural_portrait_set,
                                        scaled_layout)
from draft_assist.vision.autocal import find_banks
from draft_assist.vision.layout import DraftLayout, hud_box

# Measured off a real 3440x1440 Dota 2 client (an All Pick draft, empty pick
# bar): the Radiant bank runs 0.1137 to 0.4336 of the 16:9 HUD box and the
# Dire bank is its reflection. This is the only real-world geometry in the
# suite and it is deliberately NOT the shipped DraftLayout default, which
# measures about a slot wider on each side.
REAL = DraftLayout(radiant_x=0.1137, dire_x=0.5664, y=0.0015,
                   slot_w=0.0591, slot_h=0.0597, pitch=0.0652)

# A real pick bar is RIGID: every portrait is exactly one pitch from the
# next, and no HUD moves one of them by itself. `jitter_frac` models the
# CROP BOXES being off, which is a recognition problem and not a geometry
# one — leaving it on here would be asking the fit to measure a bar that
# cannot exist.
RIGID = Distortions(jitter_frac=0.0)

# What "measured" has to mean. The shift search in `recognize.match_slot`
# absorbs a few pixels, so this is comfortably inside what recognition
# needs, and far inside the ~150px the shipped defaults are out by.
TOLERANCE_X = 6.0
TOLERANCE_Y = 8.0


@pytest.fixture(scope="module")
def portraits():
    return procedural_portrait_set(40)


def _error(got: DraftLayout, want: DraftLayout, resolution):
    """Worst horizontal and vertical error, in FRAME PIXELS.

    Fractions are not comparable across resolutions — a thousandth of a
    3440-wide HUD box is three times a thousandth of a 1280 one — and
    pixels are what a crop box is wrong by.
    """
    width, height = resolution
    _left, span = hud_box(width, height)
    horizontal = max(abs(got.radiant_x - want.radiant_x) * span,
                     abs(got.dire_x - want.dire_x) * span,
                     abs(got.slot_w - want.slot_w) * span,
                     abs(got.pitch - want.pitch) * span)
    vertical = max(abs(got.y - want.y) * height,
                   abs(got.slot_h - want.slot_h) * height)
    return horizontal, vertical


@pytest.mark.parametrize("resolution", RESOLUTIONS)
def test_the_bar_is_found_at_every_aspect_ratio(portraits, resolution):
    """16:9, 16:10, 5:4, 21:9 and 32:9 alike.

    The HUD is pillarboxed into a centred 16:9 box on anything wider and
    takes the full width on anything narrower, so these are two different
    pieces of arithmetic and neither had ever been run against a frame.
    """
    rng = np.random.default_rng(17)
    case = generate_case(portraits, REAL, rng, resolution=resolution,
                         distort=RIGID, fill_range=(10, 10))
    layout, note = find_banks(case.frame)
    assert layout is not None, f"{resolution}: {note}"
    horizontal, vertical = _error(layout, REAL, resolution)
    assert horizontal <= TOLERANCE_X, f"{resolution}: {horizontal:.1f}px, {note}"
    assert vertical <= TOLERANCE_Y, f"{resolution}: {vertical:.1f}px, {note}"


@pytest.mark.parametrize("factor", [0.8, 0.9, 1.0, 1.1, 1.2])
def test_it_survives_dotas_own_hud_scale(portraits, factor):
    """The half of this problem that is invisible in the frame size.

    A stranger on a different notch of the HUD scale slider has every
    fraction in `DraftLayout` off by a multiplier, and no amount of tuning
    the shipped defaults answers it — only measuring does.
    """
    rng = np.random.default_rng(23)
    want = scaled_layout(REAL, factor)
    for resolution in RESOLUTIONS:
        case = generate_case(portraits, want, rng, resolution=resolution,
                             distort=RIGID, fill_range=(4, 10))
        layout, note = find_banks(case.frame)
        assert layout is not None, f"x{factor} {resolution}: {note}"
        horizontal, vertical = _error(layout, want, resolution)
        assert horizontal <= TOLERANCE_X, (
            f"x{factor} {resolution}: {horizontal:.1f}px, {note}")
        assert vertical <= TOLERANCE_Y, (
            f"x{factor} {resolution}: {vertical:.1f}px, {note}")


def test_it_needs_no_heroes_and_no_game_data(portraits):
    """An EMPTY pick bar measures the same as a full one.

    This is the whole reason the step exists where it does. `autocal.
    calibrate` needs the ten heroes the minimap names, so it can only run
    at strategy time — after the draft somebody just missed. The borders
    between portraits are there from the first frame of hero selection,
    whether or not anybody has picked.
    """
    rng = np.random.default_rng(29)
    full = generate_case(portraits, REAL, rng, resolution=(2560, 1440),
                         distort=RIGID, fill_range=(10, 10))
    empty = generate_case(portraits, REAL, rng, resolution=(2560, 1440),
                          distort=RIGID, fill_range=(0, 0))
    for name, case in (("full", full), ("empty", empty)):
        layout, note = find_banks(case.frame)
        assert layout is not None, f"{name}: {note}"
        horizontal, _v = _error(layout, REAL, (2560, 1440))
        assert horizontal <= TOLERANCE_X, f"{name}: {horizontal:.1f}px"


def test_a_half_drafted_bar_measures_as_well_as_a_finished_one(portraits):
    """Which is the case it will actually meet: picks arrive one at a time."""
    rng = np.random.default_rng(31)
    for filled in range(0, 11, 2):
        case = generate_case(portraits, REAL, rng, resolution=(1920, 1080),
                             distort=RIGID, fill_range=(filled, filled))
        layout, note = find_banks(case.frame)
        assert layout is not None, f"{filled} picked: {note}"
        horizontal, _v = _error(layout, REAL, (1920, 1080))
        assert horizontal <= TOLERANCE_X, f"{filled} picked: {horizontal:.1f}px"


def test_it_never_takes_the_fit_that_is_one_portrait_out(portraits):
    """The degenerate fit, and the reason the gutters are scored.

    A candidate whose portrait width equals its pitch predicts every right
    edge on top of the next left edge: all twenty of its boundaries land on
    the ten real LEFT edges, counted twice, so it scores as well as the
    truth and places the whole bar a portrait to one side. It is what this
    fit produced on four of eleven resolutions before the gutters were
    scored, and the tell is always the same — a portrait as wide as its own
    pitch, which is a bar with no gaps in it.
    """
    rng = np.random.default_rng(37)
    for resolution in RESOLUTIONS:
        case = generate_case(portraits, REAL, rng, resolution=resolution,
                             distort=RIGID, fill_range=(3, 10))
        layout, note = find_banks(case.frame)
        assert layout is not None, f"{resolution}: {note}"
        assert layout.slot_w < layout.pitch, f"{resolution}: {note}"
        # And the real tell, which survives any future re-tuning: the bank
        # is where it should be, not a pitch away from it.
        _left, span = hud_box(*resolution)
        assert abs(layout.radiant_x - REAL.radiant_x) * span < layout.pitch * span / 2


def test_the_two_banks_come_out_as_each_others_mirror(portraits):
    """Which is what makes the search three numbers rather than ten.

    Asserted on the OUTPUT rather than taken on trust, because the day the
    fit stops being mirrored is the day this stops being the right model
    for Dota's pick bar.
    """
    rng = np.random.default_rng(41)
    case = generate_case(portraits, REAL, rng, resolution=(3440, 1440),
                         distort=RIGID, fill_range=(10, 10))
    layout, note = find_banks(case.frame)
    assert layout is not None, note
    left_gap = layout.radiant_x
    right_gap = 1.0 - (layout.dire_x + layout.bank_span())
    assert abs(left_gap - right_gap) < 1e-6, (left_gap, right_gap)


@pytest.mark.parametrize("name,frame", [
    ("a flat screen", np.full((1440, 3440, 3), 40, np.uint8)),
    ("pure noise", np.random.default_rng(3).integers(
        0, 255, (1080, 1920, 3), dtype=np.uint8)),
    ("a plain gradient", np.repeat(np.repeat(
        np.linspace(10, 60, 1080, dtype=np.uint8)[:, None, None],
        1920, axis=1), 3, axis=2)),
])
def test_it_refuses_a_frame_with_no_pick_bar(name, frame):
    """A guess here is worse than nothing: it would be saved as the user's
    calibration and quietly mis-crop every draft after it."""
    layout, note = find_banks(frame)
    assert layout is None, f"{name} was accepted: {note}"
    assert note, name


def test_it_refuses_a_frame_too_small_to_hold_a_bar():
    layout, note = find_banks(np.zeros((20, 40, 3), np.uint8))
    assert layout is None
    assert "too small" in note


def test_it_refuses_no_frame_at_all():
    layout, note = find_banks(None)
    assert layout is None
    assert note


@pytest.mark.parametrize("resolution", RESOLUTIONS)
def test_the_search_region_holds_the_bar_under_either_hud_convention(resolution):
    """`BAR_FRACTION` must not depend on a question nobody has settled.

    `hud_box` pillarboxes a display wider than 16:9 and takes the full
    width of one that is narrower — but whether Dota then scales the HUD's
    HEIGHT by the window or by the 16:9 box it fits inside has never been
    measured (see `hud_box`). The two readings put the pick bar in
    different places on a 16:10 panel, so the bound has to hold for both or
    it is tuned to a guess.
    """
    from draft_assist.vision.autocal import BAR_FRACTION

    width, height = resolution
    bottom = REAL.y + REAL.slot_h              # 6.0% on a real client
    # Reading one: fractions are of the window, which is what the code does
    # today. Reading two: the HUD is scaled by its own 16:9 box, so the bar
    # occupies fewer of a taller window's rows.
    by_window = bottom
    by_hud = bottom * min(1.0, (width * 9 / 16) / height)
    for name, share in (("window", by_window), ("hud", by_hud)):
        assert share < BAR_FRACTION, (
            f"{resolution} under the {name} reading: the bar reaches "
            f"{share:.1%} of the frame, inside a {BAR_FRACTION:.0%} search")
