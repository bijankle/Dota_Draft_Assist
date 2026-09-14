"""The app reads a pick bar at every shape of monitor — end to end.

Not arithmetic about fractions: this DRAWS a pick bar the way Dota lays
one out, hands it to the app's own `lineup.read_placed` with the shipped
`DraftLayout`, and checks it comes back with all ten heroes named.

**WHY THE BAR IS DRAWN SQUARE.** Dota's HUD is a 16:9 box scaled as ONE
piece, so a portrait's size follows that box and not the monitor — which
is measurable on a real client: `slot_w` 0.0525 of the span against
`slot_h` 0.0930 of the height is a 1.00 aspect at 3440x1440. A hero's
portrait does not get taller because the monitor did.

**WHAT THIS CAUGHT.** Reading `y` and `slot_h` as fractions of the FRAME
is identical at 16:9 and wider and wrong on anything taller, and the
damage is not linear — matching scores 0.99 at the true size and 0.12
four pixels out:

    1920x1080   0.995 -> 0.995   (nothing changes at 16:9)
    1440x900    0.517 -> 0.993   located its ten and fitted them wrong
    1920x1200   0.510 -> 0.995
    1024x768    REFUSED -> 1.000
    800x600     REFUSED -> 1.000  located nothing at all

0.517 is barely over `MIN_PLACED_SCORE`, which is what "the crops are
half a portrait out" looks like from inside; the two 4:3 shapes did not
clear the floor at all.
"""

import cv2
import numpy as np
import pytest

from draft_assist.proving.synth import procedural_portrait
from draft_assist.vision import lineup as lineup_mod
from draft_assist.vision.layout import HUD_ASPECT, DraftLayout, hud_box

TEN = [1, 26, 8, 2, 5, 14, 29, 18, 11, 41]

SIXTEEN_NINE = [(1280, 720), (1920, 1080), (2560, 1440)]
WIDER = [(2560, 1080), (3440, 1440)]
TALLER = [(1920, 1200), (1680, 1050), (1440, 900), (1280, 800),
          (1024, 768), (800, 600), (1280, 1024)]


@pytest.fixture(scope="module")
def art():
    return {hero: procedural_portrait(hero) for hero in TEN}


def pick_bar(width, height, art):
    """A pick bar where Dota would put one, at the size it would be."""
    frame = np.full((height, width, 3), 22, np.uint8)
    left, span = hud_box(width, height)
    box_h = span / HUD_ASPECT
    layout = DraftLayout()
    side = round(layout.slot_w * span)        # SQUARE: the width sets it
    top = round(layout.y * box_h)
    for team, x0 in (("radiant", layout.radiant_x), ("dire", layout.dire_x)):
        for slot in range(5):
            x = round(left + (x0 + slot * layout.pitch) * span)
            hero = TEN[slot if team == "radiant" else 5 + slot]
            frame[top:top + side, x:x + side] = cv2.resize(
                art[hero], (side, side), interpolation=cv2.INTER_AREA)
    return frame


def as_it_was(width, height):
    """The layout that produced the OLD boxes: `y` and `slot_h` read
    against the frame's height rather than the HUD box's."""
    _left, span = hud_box(width, height)
    box_h = span / HUD_ASPECT
    layout = DraftLayout()
    return DraftLayout(y=layout.y * height / box_h,
                       slot_h=layout.slot_h * height / box_h)


@pytest.mark.parametrize("size", SIXTEEN_NINE + WIDER + TALLER)
def test_all_ten_are_read_at_every_shape_of_monitor(size, art):
    frame = pick_bar(*size, art)
    read = lineup_mod.read_placed(frame, TEN, DraftLayout(), portraits=art)
    assert read.ok, f"{size[0]}x{size[1]}: {read.note}"
    assert read.matched == 10
    assert read.left == TEN[:5] and read.right == TEN[5:]
    assert read.confidence > 0.9, (
        f"{size[0]}x{size[1]} read them at {read.confidence:.3f}")


@pytest.mark.parametrize("size", [(800, 600), (1024, 768)])
def test_the_four_three_shapes_could_not_be_read_before(size, art):
    """800x600 was the resolution that located NOTHING. The box was 33%
    too tall, and a matcher that scores 0.12 four pixels out does not
    survive that."""
    frame = pick_bar(*size, art)
    before = lineup_mod.read_placed(frame, TEN, as_it_was(*size),
                                    portraits=art)
    assert not before.ok, "this is the case the change exists for"
    assert before.matched < 10


@pytest.mark.parametrize("size", [(1440, 900), (1920, 1200)])
def test_sixteen_ten_used_to_read_them_badly_rather_than_not_at_all(size,
                                                                    art):
    """"1440x900 locates ten but fits them wrong". 11% out clears the
    floor and nothing else — which is what a proof sheet of crops half a
    portrait off its portrait looks like from inside the matcher."""
    frame = pick_bar(*size, art)
    before = lineup_mod.read_placed(frame, TEN, as_it_was(*size),
                                    portraits=art)
    after = lineup_mod.read_placed(frame, TEN, DraftLayout(), portraits=art)
    assert before.confidence < 0.6, before.confidence
    assert after.confidence > 0.9, after.confidence
    assert after.confidence > before.confidence * 1.5


@pytest.mark.parametrize("size", SIXTEEN_NINE + WIDER)
def test_nothing_changed_at_sixteen_nine_or_wider(size, art):
    """Which is every display this app has actually run on, so the change
    cannot have regressed a working setup."""
    frame = pick_bar(*size, art)
    before = lineup_mod.read_placed(frame, TEN, as_it_was(*size),
                                    portraits=art)
    after = lineup_mod.read_placed(frame, TEN, DraftLayout(), portraits=art)
    assert before.ok and after.ok
    assert before.confidence == pytest.approx(after.confidence, abs=1e-6)
