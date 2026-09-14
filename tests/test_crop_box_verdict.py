"""A hero in a costume is not a broken calibration.

"i got a popup durign drafting that said the image recognitio nwasnt
working and therere was a button to move the crop boxes to suit, but i
thought the latest system is all automatic??? also it looked liek the
boxxes were in the right locaation anyway".

They were in the right location. Two separate faults put that strip up:

* `read_placed` refuses unless ALL TEN boxes resolve, which is right for a
  LINE-UP — a permutation with one hero guessed is a wrong team — and is a
  hopeless test of the GEOMETRY. One hero wearing a persona, an arcana or a
  set the library has no picture of fails its box while the other nine land
  perfectly, and the refusal said "the boxes are probably not on the
  portraits" with nine of them sitting on portraits.
* The minimap's ten are LATCHED for the match, so the question went on
  being asked through PRE_GAME and the whole game, with the draft bar long
  gone. Their own debug log is one of those frames and says so in its own
  note: the pick bar is not up, so every slot reading UNKNOWN is right.

So the count is carried and read, and the question is only asked while
Dota is drawing the bar.
"""

import numpy as np
import pytest

from draft_assist.gsi.state import (STATE_HERO_SELECTION, STATE_IN_PROGRESS,
                                    STATE_PREGAME, STATE_STRATEGY)
from draft_assist.vision import lineup as lineup_mod
from draft_assist.vision.layout import DraftLayout


WIDTH, HEIGHT = 1920, 1080
TEN = [17, 54, 2, 86, 31, 22, 14, 111, 42, 47]


def art(hero_id):
    """One hero's portrait: a coarse block pattern, distinct per hero.

    Blocks rather than per-pixel noise because `_score` resizes the
    template down to the crop, and noise averages towards flat — a flat
    template correlates with nothing, including itself, which would make
    this test pass or fail for a reason that is not the one under test.
    """
    rng = np.random.default_rng(hero_id)
    blocks = rng.integers(0, 255, size=(9, 16), dtype=np.uint8)
    return np.kron(blocks, np.ones((16, 16), dtype=np.uint8))


def portraits(hero_ids):
    return {hid: art(hid) for hid in hero_ids}


def frame_with(hero_ids, layout=None):
    """The pick bar as the calibrated layout says it is: each hero's art
    painted into its own crop box, at the size the box will read it at."""
    import cv2

    layout = layout or DraftLayout()
    frame = np.zeros((HEIGHT, WIDTH, 3), dtype=np.uint8)
    for rect, hero_id in zip(layout.slots(), hero_ids):
        if hero_id is None:
            continue
        x, y, w, h = rect.to_pixels(WIDTH, HEIGHT)
        painted = cv2.resize(art(hero_id), (w, h),
                             interpolation=cv2.INTER_AREA)
        frame[y:y + h, x:x + w] = painted[:, :, None]
    return frame


def placed(frame, layout=None):
    return lineup_mod.read_placed(frame, TEN, layout or DraftLayout(),
                                  portraits=portraits(TEN))


# ---- what the count separates ------------------------------------------

def test_all_ten_in_their_boxes_reads_the_bar():
    read = placed(frame_with(TEN))
    assert read.ok, read.note
    assert read.matched == 10
    assert read.boxes_wrong is False
    assert read.left == TEN[:5] and read.right == TEN[5:]


@pytest.mark.parametrize("absent", [0, 4, 5, 9])
def test_one_hero_in_a_costume_does_not_accuse_the_boxes(absent):
    """THE BUG. Nine portraits found exactly where the calibration said
    they would be, and the app said the boxes were not on portraits."""
    shown = list(TEN)
    shown[absent] = None                 # artwork the library does not have
    read = placed(frame_with(shown))
    assert not read.ok, "a line-up still needs all ten"
    assert read.matched >= lineup_mod.BOXES_PROVE_THE_GEOMETRY
    assert read.boxes_wrong is False, read.note
    assert "the boxes are on the pick bar" in read.note


def test_boxes_on_nothing_still_accuse_the_boxes():
    """The fault this verdict exists for, and it must survive the fix: a
    real draft read two slots of ten for eighty seconds."""
    read = placed(np.full((HEIGHT, WIDTH, 3), 24, dtype=np.uint8))
    assert not read.ok
    assert read.matched < lineup_mod.BOXES_PROVE_THE_GEOMETRY
    assert read.boxes_wrong is True
    assert "not on the portraits" in read.note


def test_boxes_off_the_edge_of_the_picture_need_no_counting():
    """No doubt to weigh: a box outside the frame is on nothing whatever
    the artwork looks like."""
    read = placed(frame_with(TEN), layout=DraftLayout(radiant_x=0.97))
    assert read.boxes_wrong is True
    assert "outside the frame" in read.note


def test_the_bar_for_believing_the_boxes_is_a_whole_bank():
    """The boxes are one rigid set at one pitch, so a bank's worth of them
    landing on named heroes is not something a wrong geometry does."""
    assert lineup_mod.BOXES_PROVE_THE_GEOMETRY == lineup_mod.TEAM_SIZE


# ---- and only while Dota is drawing the bar ----------------------------

def _provider(frame, game_state):
    from draft_assist.ui.manual import ManualDraft
    from draft_assist.ui.providers import HybridProvider, Snapshot

    class FakeGsi:
        def poll(self):
            return Snapshot(left=TEN[5:], right=TEN[:5], my_team="radiant",
                            lineup_source="minimap", sides_certain=False,
                            match_id="42", sides_known=True,
                            game_state=game_state)

    class FakeSession:
        layout = DraftLayout()

    class FakeVision:
        session = FakeSession()

        def poll(self):
            return Snapshot(frame=frame)

    gsi = FakeGsi()
    gsi.manual = ManualDraft()
    return HybridProvider(gsi, FakeVision())


def _blank():
    return np.full((HEIGHT, WIDTH, 3), 24, dtype=np.uint8)


@pytest.mark.parametrize("state", [STATE_PREGAME, STATE_IN_PROGRESS, ""])
def test_a_screen_with_no_pick_bar_on_it_judges_nothing(state, monkeypatch):
    """Their debug log is a PRE_GAME frame whose own note says the pick bar
    is not up. The strip was raised off exactly that."""
    from draft_assist.vision import autocal
    monkeypatch.setattr(autocal, "base_portraits",
                        lambda hero_ids: portraits(list(hero_ids)))
    snap = _provider(_blank(), state).poll()
    assert snap.crop_boxes_wrong is False


@pytest.mark.parametrize("state", [STATE_STRATEGY, STATE_HERO_SELECTION])
def test_the_verdict_still_stands_where_the_bar_is_drawn(state, monkeypatch):
    from draft_assist.vision import autocal
    monkeypatch.setattr(autocal, "base_portraits",
                        lambda hero_ids: portraits(list(hero_ids)))
    snap = _provider(_blank(), state).poll()
    assert snap.crop_boxes_wrong is True
