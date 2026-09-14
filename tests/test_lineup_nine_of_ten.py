"""Nine located portraits still determine the sides.

Ground truth, match 8000000001: the user's teams came out INVERTED. The
recording's own notes say why, and both halves are here —

    sides not readable from the screen: the ten heroes could not be told
    apart in the crop boxes - the boxes are probably not on the portraits;
    then found 9 of the ten portraits on screen; all ten are needed before
    the sides can be read off

- so the screen abstained, the minimap's coin-flip split won, and Axe and
Storm Spirit went to the other team. The board scored 6/10: three heroes
advised against who were on the user's own side.

The ninth portrait was never the problem. The game NAMES all ten at
strategy time, so nine located leaves exactly one hero and exactly one
bank of four, and which side it is on follows by elimination - the same
elimination `harvest.by_elimination` already runs against the library.
What has to hold is the GEOMETRY: the gap between the banks must still be
distinguishable from the two-pitch hole a missed portrait leaves. On the
measured 16:9 bar the banks are 4.87 pitches apart, so it is.
"""

import numpy as np
import pytest

from draft_assist.vision import lineup as lineup_mod
from draft_assist.vision.autocal import Located
from draft_assist.vision.layout import DraftLayout, hud_box


WIDTH, HEIGHT = 1920, 1080
# The ten of match 8000000001, in bar order: the user's five on Radiant.
TEN = [17, 54, 2, 86, 31, 22, 14, 111, 42, 47]


def bar(hero_ids, layout=None, missing=None):
    """The ten portraits where the measured layout puts them."""
    layout = layout or DraftLayout()
    left, span = hud_box(WIDTH, HEIGHT)
    out = []
    for rect, hero_id in zip(layout.slots(), hero_ids):
        if hero_id == missing:
            continue
        x, y, w, h = rect.to_pixels(WIDTH, HEIGHT)
        out.append(Located(hero_id, x, y, w, h, 0.8))
    out.sort(key=lambda item: item.x)
    return out


def test_the_bank_gap_is_wider_than_a_missed_portraits_hole():
    """The measurement the whole fix rests on."""
    layout = DraftLayout()
    xs = [rect.to_pixels(WIDTH, HEIGHT)[0] for rect in layout.slots()]
    steps = [b - a for a, b in zip(xs, xs[1:])]
    pitch = float(np.median(steps))
    gap = max(steps)
    assert gap >= lineup_mod.BANK_GAP_STEPS * pitch, (
        f"the banks are {gap / pitch:.2f} pitches apart; a missed portrait "
        f"leaves a hole of 2, so the threshold of "
        f"{lineup_mod.BANK_GAP_STEPS} has to sit between them")
    # And with room to spare on both sides of the threshold.
    assert 2.0 < lineup_mod.BANK_GAP_STEPS < gap / pitch


def test_all_ten_still_split_five_and_five():
    split, why = lineup_mod.split_banks(bar(TEN))
    assert why == ""
    assert split == 5


@pytest.mark.parametrize("absent", TEN)
def test_any_one_missing_portrait_still_lands_on_the_right_side(absent):
    """The bug: nine of ten used to abstain, and the coin flip won."""
    found = bar(TEN, missing=absent)
    assert len(found) == 9
    left, right, note = lineup_mod._place_missing(
        found, TEN, lineup_mod.split_banks(found)[0])
    assert sorted(left) == sorted(TEN[:5]), (
        f"{absent} missing put the wrong five on Radiant")
    assert sorted(right) == sorted(TEN[5:])
    assert note


def test_a_missing_portrait_in_the_middle_of_a_bank_keeps_bar_order():
    found = bar(TEN, missing=TEN[2])
    left, right, note = lineup_mod._place_missing(
        found, TEN, lineup_mod.split_banks(found)[0])
    assert left == TEN[:5], "the hole it left says exactly where it was"
    assert "gap it left" in note


def test_a_missing_portrait_at_the_end_of_a_bank_says_it_cannot_tell():
    found = bar(TEN, missing=TEN[0])
    _left, _right, note = lineup_mod._place_missing(
        found, TEN, lineup_mod.split_banks(found)[0])
    assert "which end cannot be read" in note


def searched(monkeypatch, found):
    """`read_searched` over a fixed set of located portraits.

    `locate` is the expensive hunt and is not what is under test here -
    what is under test is what `read_searched` DOES with what it found,
    which is the half that refused a perfectly readable bar.
    """
    from draft_assist.vision import autocal
    monkeypatch.setattr(autocal, "locate",
                        lambda *a, **k: sorted(found, key=lambda i: i.x))
    return lineup_mod.read_searched(_frame(), TEN, portraits=_art(found))


def test_nine_located_now_reads_the_sides(monkeypatch):
    """THE BUG. This returned `ok is False` and the coin flip won."""
    read = searched(monkeypatch, bar(TEN, missing=TEN[7]))
    assert read.ok, read.note
    assert read.how == "searched"
    assert sorted(read.left) == sorted(TEN[:5])
    assert sorted(read.right) == sorted(TEN[5:])
    assert "located 9 of the ten" in read.note


def test_ten_located_reads_the_sides_exactly_as_it_always_did(monkeypatch):
    read = searched(monkeypatch, bar(TEN))
    assert read.ok
    assert read.left == TEN[:5] and read.right == TEN[5:]
    assert "located all ten" in read.note


def test_eight_is_still_refused(monkeypatch):
    """One missing is elimination; two is a guess about which bank each
    went to, and this module never guesses."""
    found = [item for item in bar(TEN) if item.hero_id not in (TEN[1], TEN[7])]
    assert len(found) == 8
    read = searched(monkeypatch, found)
    assert not read.ok
    assert "found 8 of the ten" in read.note


def test_a_bar_that_is_not_five_a_side_is_refused(monkeypatch):
    found = bar(TEN)
    # Move one of Dire's over into the Radiant bank: 6/4 is not a pick bar,
    # and a 6/4 accepted is a hero advised against its own team.
    found[5] = Located(found[5].hero_id, found[4].x + 60, found[5].y,
                       found[5].w, found[5].h, 0.8)
    found.sort(key=lambda item: item.x)
    assert lineup_mod.split_banks(found)[0] == 6
    read = searched(monkeypatch, found)
    assert not read.ok
    assert "6/4" in read.note


def test_portraits_all_at_one_x_are_refused():
    same = [Located(hid, 100, 20, 40, 22, 0.8) for hid in TEN]
    split, why = lineup_mod.split_banks(same)
    assert split == -1 and why


def test_one_even_bar_with_no_bank_gap_is_refused():
    """No gap clears the threshold, so there is no boundary to read."""
    even = [Located(hid, 100 + i * 60, 20, 40, 22, 0.8)
            for i, hid in enumerate(TEN)]
    split, why = lineup_mod.split_banks(even)
    assert split == -1
    assert "banks cannot be told apart" in why


def _frame():
    return np.zeros((HEIGHT, WIDTH, 3), dtype=np.uint8)


def _art(found):
    return {item.hero_id: np.zeros((144, 256), dtype=np.uint8)
            for item in found}
