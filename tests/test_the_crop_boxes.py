"""Where the crop boxes land, and why there is no end-to-end test here.

**THIS FILE REPLACES TWO THAT SHIPPED A REGRESSION**, and the way they
did it is the only thing in it worth remembering.

`test_reads_every_resolution.py` DREW a pick bar at
`round(layout.y * box_h)` and then asserted that `lineup.read_placed`
could read it with that same `layout`. The convention under test placed
the thing being tested, so it passed at every resolution under whichever
convention was in the code — and it was cited as the evidence for moving
`y` and `slot_h` off the window's height and onto the HUD box's. The
user's proof sheet over their own 22 screenshots then showed every row
cropping the player NAME strip instead of a portrait, at every
resolution, where 20 of the 22 had been landing on portraits.

`test_vertical_is_the_hud_box.py` was the other half: arithmetic about
fractions, asserting that the crop box comes out square because the
pick tile was measured square on a 3440x1440 client. True at 16:9 and an
inference everywhere else.

So the rule this file exists to keep: **a synthetic bar is evidence
about our own arithmetic and nothing else.** An end-to-end read test
earns its place here when it can draw its portraits at pixel positions
MEASURED off the user's screenshots — `tools/find_portraits.py <folder>
--boxes-only` is what produces them — rather than at positions computed
from the layout it is checking. Until then there is no such test, which
is honest, where one that cannot fail is not.

What IS checked below is what those two files could have checked all
along without asking any picture: that the numbers are the ones the real
sheet landed portraits with, that they stay on the frame, and that a
measurement survives the round trip through `autocal`.
"""

import ast
import pathlib

import pytest

from draft_assist.vision.layout import HUD_ASPECT, DraftLayout, hud_box

SIXTEEN_NINE = [(1280, 720), (1920, 1080), (2560, 1440), (3840, 2160)]
WIDER = [(2560, 1080), (3440, 1440), (5120, 1440)]
TALLER = [(1920, 1200), (1680, 1050), (1440, 900), (1280, 800),
          (1024, 768), (800, 600), (1280, 1024)]


def box(width, height, layout=None):
    return (layout or DraftLayout()).slots()[0].to_pixels(width, height)


@pytest.mark.parametrize("size,y,h", [
    # The first slot's top and height in pixels. These are what the
    # user's own proof sheet landed on portraits at 20 of its 22
    # resolutions; the four taller shapes are the ones an attempt to
    # anchor the vertical to the HUD box moved, and moving them put
    # every row on the player name strip.
    ((1920, 1080), 36, 100),     # 16:9   - unchanged by any of this
    ((3440, 1440), 48, 134),     # 21:9   - pillarboxed, full height
    ((1920, 1200), 40, 112),     # 16:10
    ((1440, 900), 30, 84),       # 16:10  - still an open failure
    ((1024, 768), 25, 71),       # 4:3
    ((800, 600), 20, 56),        # 4:3    - still an open failure
    ((1280, 1024), 34, 95),      # 5:4
])
def test_the_vertical_is_a_fraction_of_the_windows_height(size, y, h):
    _x, top, _w, high = box(*size)
    assert (top, high) == (y, h), (
        f"{size[0]}x{size[1]} moved; the real sheet read portraits at "
        f"y={y} h={h} and the name strip when this was changed")


@pytest.mark.parametrize("size", SIXTEEN_NINE + WIDER + TALLER)
def test_the_vertical_is_the_window_at_every_resolution(size):
    """Stated as the rule rather than as seven numbers, so a resolution
    nobody listed cannot quietly follow a different one."""
    width, height = size
    layout = DraftLayout()
    _x, y, _w, h = box(width, height)
    assert y == round(layout.y * height)
    assert h == round(layout.slot_h * height)


@pytest.mark.parametrize("size", SIXTEEN_NINE + WIDER)
def test_only_a_display_taller_than_sixteen_nine_could_ever_disagree(size):
    """At 16:9 and WIDER the HUD box is the full height, so the window
    and the box are one number and no reading of these frames can say
    anything about the convention. That is why 3440x1440 — which settled
    the HORIZONTAL from real artwork — could never settle this."""
    width, height = size
    _left, span = hud_box(width, height)
    assert span / HUD_ASPECT == pytest.approx(height, abs=1)


@pytest.mark.parametrize("size", SIXTEEN_NINE + WIDER + TALLER)
def test_the_horizontal_is_a_fraction_of_the_hud_box(size):
    """The settled half, and it was settled by artwork: on 3440x1440 the
    portraits are in the middle 2560 pixels and a fraction of the full
    width landed the boxes 440px left of them."""
    width, height = size
    left, span = hud_box(width, height)
    layout = DraftLayout()
    x, _y, w, _h = box(width, height)
    assert x == round(left + layout.radiant_x * span)
    assert w == round(layout.slot_w * span)


def test_no_box_hangs_off_the_frame():
    for width, height in SIXTEEN_NINE + WIDER + TALLER:
        for rect in DraftLayout().slots():
            x, y, w, h = rect.to_pixels(width, height)
            assert 0 <= x and x + w <= width, (width, height, x, w)
            assert 0 <= y and y + h <= height, (width, height, y, h)


def test_a_measurement_reads_back_as_the_box_it_was_taken_from():
    """pixels -> fractions -> pixels. `autocal` divides by whatever
    `to_pixels` multiplies by, or a layout measured on a 16:10 client is
    stored under one convention and drawn under another. This one is
    NOT circular: it fixes no convention, it only requires the two
    directions to be inverses."""
    for width, height in ((1920, 1080), (1440, 900), (800, 600)):
        top_px, high_px = 27, 75
        made = DraftLayout(y=top_px / height, slot_h=high_px / height)
        _x, y, _w, h = made.slots()[0].to_pixels(width, height)
        assert (y, h) == (top_px, high_px), (width, height)


def test_no_test_draws_a_pick_bar_with_the_numbers_it_is_checking():
    """THE GUARD, and it is the whole point of this file.

    A test that positions artwork from a `DraftLayout`'s own fractions
    and then asks `read_placed` to find it is asking our arithmetic to
    agree with itself. It passes under any convention, including a wrong
    one, which is how the vertical came to be changed against real
    screenshots that said otherwise.
    """
    reads = ("read_placed", "read_searched")
    offenders = []
    for path in pathlib.Path(__file__).parent.glob("test_*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        calls = [n for n in ast.walk(tree) if isinstance(n, ast.Call)]
        asked = any(
            (isinstance(c.func, ast.Attribute) and c.func.attr in reads)
            or (isinstance(c.func, ast.Name) and c.func.id in reads)
            for c in calls)
        if not asked:
            continue          # not an end-to-end read: nothing to be circular about
        for node in ast.walk(tree):
            if not isinstance(node, ast.BinOp) or not isinstance(
                    node.op, ast.Mult):
                continue
            for side in (node.left, node.right):
                if (isinstance(side, ast.Attribute)
                        and side.attr in ("y", "slot_h", "slot_w", "pitch",
                                          "radiant_x", "dire_x")):
                    offenders.append(f"{path.name}:{node.lineno}")
    assert not offenders, (
        "these tests place artwork with the layout fractions they then "
        "ask the app to read, which cannot fail: "
        + ", ".join(sorted(set(offenders))))
