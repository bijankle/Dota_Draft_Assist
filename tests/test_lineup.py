"""Reading which five are yours off the pick bar.

The screen has never had the ambiguity the game feed has — Radiant is the
left bank, Dire the right — so these tests are about whether the ten known
heroes can be put in their screen positions reliably, and about refusing
rather than guessing when they cannot.
"""

import numpy as np
import pytest

from draft_assist.proving.synth import procedural_portrait
from draft_assist.vision import lineup
from draft_assist.vision.layout import DraftLayout

TEN = [1, 5, 9, 14, 22, 36, 44, 57, 68, 91]


def portraits(hero_ids=TEN):
    return {hid: procedural_portrait(hid) for hid in hero_ids}


def bar(hero_ids, layout=None, size=(1920, 1080), art=None):
    """A synthetic pick bar with these ten heroes in these ten slots."""
    import cv2
    layout = layout or DraftLayout()
    width, height = size
    frame = np.full((height, width, 3), 24, dtype=np.uint8)
    art = art or portraits(hero_ids)
    for rect, hid in zip(layout.slots(), hero_ids):
        x, y, w, h = rect.to_pixels(width, height)
        frame[y:y + h, x:x + w] = cv2.resize(art[hid], (w, h))
    return frame


def test_the_placed_path_reads_both_banks_in_screen_order():
    layout = DraftLayout()
    frame = bar(TEN, layout)
    read = lineup.read_lineup(frame, TEN, layout, allow_search=False,
                              portraits=portraits(TEN))
    assert read.ok, read.note
    assert read.how == "placed"
    assert read.left == TEN[:5]
    assert read.right == TEN[5:]


def test_the_order_is_the_screens_not_the_callers():
    """The whole point is that the bar decides the order, so a caller
    handing the ten in any order must get the same reading back."""
    layout = DraftLayout()
    frame = bar(TEN, layout)
    shuffled = list(reversed(TEN))
    read = lineup.read_lineup(frame, shuffled, layout,
                          allow_search=False,
                          portraits=portraits(TEN))
    assert read.ok, read.note
    assert read.left == TEN[:5]
    assert read.right == TEN[5:]


def test_radiant_is_the_left_bank_and_the_player_decides_the_rest():
    read = lineup.ScreenLineup(left=TEN[:5], right=TEN[5:])
    assert read.sides_for("radiant") == (TEN[:5], TEN[5:])
    assert read.sides_for("dire") == (TEN[5:], TEN[:5])


def test_it_refuses_when_the_boxes_are_not_on_the_portraits():
    """Calibration hundreds of pixels off is the state this app has
    actually been in, and a confident wrong split is worse than none."""
    layout = DraftLayout()
    frame = bar(TEN, layout)
    wrong = DraftLayout(radiant_x=0.30, dire_x=0.80, y=0.55)
    read = lineup.read_lineup(frame, TEN, wrong, allow_search=False,
                          portraits=portraits(TEN))
    assert not read.ok
    assert read.note


def test_it_refuses_a_bar_that_is_not_ten_heroes():
    layout = DraftLayout()
    frame = bar(TEN, layout)
    read = lineup.read_lineup(frame, TEN[:6], layout,
                          allow_search=False,
                          portraits=portraits(TEN))
    assert not read.ok
    assert "ten" in read.note


def test_it_refuses_when_a_portrait_has_not_been_downloaded():
    layout = DraftLayout()
    frame = bar(TEN, layout)
    thin = portraits(TEN)
    thin[TEN[3]] = None
    read = lineup.read_placed(frame, TEN, layout, portraits=thin)
    assert not read.ok
    assert "portrait" in read.note


def test_it_refuses_a_blank_bar_rather_than_inventing_an_order():
    layout = DraftLayout()
    frame = np.full((1080, 1920, 3), 24, dtype=np.uint8)
    read = lineup.read_lineup(frame, TEN, layout, allow_search=False,
                              portraits=portraits(TEN))
    assert not read.ok


@pytest.mark.parametrize("size", [(1920, 1080), (2560, 1440), (3440, 1440)])
def test_it_reads_at_any_resolution_including_ultrawide(size):
    """The crop boxes are fractions of Dota's 16:9 HUD box, so a 21:9
    window must work without a special case."""
    layout = DraftLayout()
    frame = bar(TEN, layout, size=size)
    read = lineup.read_lineup(frame, TEN, layout, allow_search=False,
                              portraits=portraits(TEN))
    assert read.ok, f"{size}: {read.note}"
    assert read.left == TEN[:5]


def test_the_searched_path_needs_no_calibration_at_all():
    """The fallback for the state the user is in now: boxes wrong, but the
    portraits are on screen somewhere."""
    layout = DraftLayout()
    frame = bar(TEN, layout)
    read = lineup.read_searched(frame, TEN, portraits(TEN))
    assert read.ok, read.note
    assert read.how == "searched"
    assert read.left == TEN[:5]
    assert read.right == TEN[5:]


def test_read_lineup_falls_back_to_searching_when_the_boxes_are_wrong():
    layout = DraftLayout()
    frame = bar(TEN, layout)
    wrong = DraftLayout(radiant_x=0.30, dire_x=0.80, y=0.55)
    read = lineup.read_lineup(frame, TEN, wrong, allow_search=True,
                              portraits=portraits(TEN))
    assert read.ok, read.note
    assert read.how == "searched"
    assert read.left == TEN[:5]


# ---- the two sources combining -----------------------------------------

def test_the_minimap_and_the_screen_settle_the_split_together(monkeypatch):
    """Neither source can do it alone. The minimap is reliable about WHICH
    ten and unreliable about whose five; the screen is the other way round.
    Together there is nothing left to guess."""
    from draft_assist.ui.manual import ManualDraft
    from draft_assist.ui.providers import HybridProvider, Snapshot
    from draft_assist.vision import autocal

    layout = DraftLayout()
    frame = bar(TEN, layout)
    monkeypatch.setattr(autocal, "base_portraits",
                        lambda hero_ids: portraits(list(hero_ids)))

    class FakeGsi:
        def poll(self):
            # The minimap's guess: ten right heroes, split the wrong way.
            return Snapshot(left=TEN[5:], right=TEN[:5], my_team="radiant",
                            lineup_source="minimap", sides_certain=False,
                            match_id="42", sides_known=True)

    class FakeSession:
        layout = DraftLayout()

    class FakeVision:
        session = FakeSession()

        def poll(self):
            return Snapshot(frame=frame)

    gsi = FakeGsi()
    gsi.manual = ManualDraft()
    provider = HybridProvider(gsi, FakeVision())

    snap = provider.poll()
    assert snap.lineup_source == "minimap+screen"
    assert snap.sides_certain is True
    assert snap.left == TEN[:5]      # screen order, radiant bank, ours
    assert snap.right == TEN[5:]

    # Playing Dire flips which bank is yours, and nothing else.
    gsi.poll = lambda: Snapshot(left=TEN[5:], right=TEN[:5], my_team="dire",
                                lineup_source="minimap", sides_certain=False,
                                match_id="43", sides_known=True)
    snap = provider.poll()
    assert snap.left == TEN[5:] and snap.right == TEN[:5]


def test_a_screen_that_cannot_be_read_leaves_the_guess_alone(monkeypatch):
    """A bad reading must not make things worse than the guess the user was
    already correcting by hand."""
    from draft_assist.ui.manual import ManualDraft
    from draft_assist.ui.providers import HybridProvider, Snapshot

    class FakeGsi:
        def poll(self):
            return Snapshot(left=TEN[5:], right=TEN[:5], my_team="radiant",
                            lineup_source="minimap", sides_certain=False,
                            match_id="42", sides_known=True)

    class FakeSession:
        layout = DraftLayout()

    class FakeVision:
        session = FakeSession()

        def poll(self):    # a blank screen: nothing to match against
            return Snapshot(frame=np.full((1080, 1920, 3), 24, dtype=np.uint8))

    gsi = FakeGsi()
    gsi.manual = ManualDraft()
    snap = HybridProvider(gsi, FakeVision()).poll()
    assert snap.lineup_source == "minimap"
    assert snap.sides_certain is False
    assert snap.left == TEN[5:]
    assert any("not readable" in note for note in snap.gsi_notes)
