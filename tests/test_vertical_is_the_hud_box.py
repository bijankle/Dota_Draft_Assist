"""The pick bar scales with Dota's HUD box in BOTH axes.

`SlotRect.to_pixels` used to read `y` and `slot_h` as fractions of the
frame's height. That is identical at 16:9 and at every aspect WIDER than
it, because the HUD box is the full height there — and wrong on anything
TALLER, which is 16:10, 4:3 and 5:4.

Three independent things agree, and the second is the one that settles it:

* **The measurement.** Across the user's own screenshots the portrait
  height spread 0.0137 read against the window and 0.0044 against the HUD
  box - three times tighter, on a quantity of 46 to 74 pixels.
* **The arithmetic.** The pick tile is SQUARE, measured on a real
  3440x1440 client. A portrait cannot change shape because the monitor
  did; Dota scales its HUD uniformly. Against the window the crop box
  came out 42x56 on 800x600.
* **The symptom.** Matching scores 0.99 at the true size and 0.12 four
  pixels out, so a box 33% too tall is not a near miss - and 800x600 was
  the one resolution that located nothing at all, while 1440x900 (11%
  out) located its ten and fitted them wrong.
"""

import pytest

from draft_assist.vision.layout import HUD_ASPECT, DraftLayout, hud_box


# Every shape a Dota client is likely to be run at.
SIXTEEN_NINE = [(1280, 720), (1920, 1080), (2560, 1440), (3840, 2160)]
WIDER = [(2560, 1080), (3440, 1440), (5120, 1440)]
TALLER = [(1920, 1200), (1680, 1050), (1440, 900), (1280, 800),
          (1024, 768), (800, 600), (1280, 1024)]


def box(width, height, layout=None):
    return (layout or DraftLayout()).slots()[0].to_pixels(width, height)


@pytest.mark.parametrize("size", SIXTEEN_NINE + WIDER + TALLER)
def test_the_crop_box_is_square_at_every_resolution(size):
    """THE CHECK THAT SETTLES IT. The pick tile's own measured numbers —
    slot_w 0.0525 of the span, slot_h 0.0930 of the box height — are a
    1.00 aspect at 16:9, so they must stay 1.00 everywhere."""
    _x, _y, w, h = box(*size)
    assert w == pytest.approx(h, abs=2), (
        f"{size[0]}x{size[1]} gives a {w}x{h} crop box; a portrait does "
        "not change shape because the monitor did")


@pytest.mark.parametrize("size", SIXTEEN_NINE + WIDER)
def test_nothing_moves_at_sixteen_nine_or_wider(size):
    """Which is every display this app has actually run on, so the change
    cannot regress a working setup: the HUD box IS the full height there."""
    width, height = size
    _left, span = hud_box(width, height)
    assert span / HUD_ASPECT == pytest.approx(height, abs=1)
    layout = DraftLayout()
    _x, y, _w, h = box(width, height)
    assert y == round(layout.y * height)
    assert h == round(layout.slot_h * height)


@pytest.mark.parametrize("size,was,now", [
    ((800, 600), 56, 42),        # 4:3  - located nothing at all
    ((1024, 768), 71, 54),       # 4:3
    ((1440, 900), 84, 75),       # 16:10 - located ten, fitted them wrong
    ((1920, 1200), 112, 100),    # 16:10
])
def test_the_two_failing_resolutions_move_onto_the_portraits(size, was, now):
    """The old height in pixels, and the one the geometry actually wants."""
    layout = DraftLayout()
    _x, _y, _w, h = box(*size)
    assert h == pytest.approx(now, abs=1)
    assert round(layout.slot_h * size[1]) == pytest.approx(was, abs=1), (
        "the window-based reading this replaces")


def test_the_box_never_hangs_off_the_bottom_of_the_frame():
    for width, height in SIXTEEN_NINE + WIDER + TALLER:
        for rect in DraftLayout().slots():
            x, y, w, h = rect.to_pixels(width, height)
            assert 0 <= x and x + w <= width, (width, height, x, w)
            assert 0 <= y and y + h <= height, (width, height, y, h)


def test_a_measurement_reads_back_as_the_box_it_was_taken_from():
    """The round trip: pixels -> fractions -> pixels. `autocal` divides by
    the HUD box height for the same reason this multiplies by it, and a
    measurement stored under one convention and drawn under the other is
    the fault this whole file exists about."""
    from draft_assist.vision import autocal

    for width, height in ((1920, 1080), (1440, 900), (800, 600)):
        _left, span = hud_box(width, height)
        box_h = span / HUD_ASPECT
        # A layout measured off THIS frame, expressed the way autocal does.
        top_px, high_px = 27, 75
        made = DraftLayout(y=top_px / box_h, slot_h=high_px / box_h)
        _x, y, _w, h = made.slots()[0].to_pixels(width, height)
        assert (y, h) == (top_px, high_px), (width, height)
    assert autocal.HUD_ASPECT == HUD_ASPECT
