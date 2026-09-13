"""The item's own percentage: on the tile, and in the callout.

At the user's request, three changes to one thing:
  - "a number in the bottom right hand corner of the item that is the %
    importance of the recommendation, most important is higher
    percentages and lower importance is red"
  - "exact same text that is used for the synergy / counter numbers, no
    decimals just whole number percentage"
  - "currently you say the hero, the severity score and then the reason.
    It would be simpler to just say e.g. Huskar | 72%"
  - and remove the "hand-authored rule" line.
"""

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from draft_assist.model import items as model
from draft_assist.ui import reasons


class FakeTrigger:
    def __init__(self, hero, severity, reason, stale=False):
        self.hero = hero
        self.severity = severity
        self.reason = reason
        self.stale = stale


# --- the number itself -------------------------------------------------

def test_a_whole_number_and_never_a_decimal():
    for score in (0.0, 2.0, 3.0, 4.8, 6.0, 5.37):
        share = model.importance(score)
        assert isinstance(share, int)


def test_more_severe_is_a_higher_percentage():
    """"The higher the severity the higher the percentage"."""
    rising = [model.importance(model.stacked_score(c))
              for c in ([1], [2], [3], [3, 2], [3, 3], [3, 3, 3])]
    assert rising == sorted(rising)
    assert rising[0] < rising[-1]


def test_the_worst_possible_draft_is_a_hundred():
    assert model.importance(model.MAX_SCORE) == 100
    # And it SATURATES rather than running over, which is the whole
    # point of the sublinear stacking.
    assert model.importance(model.MAX_SCORE * 2) == 100


def test_one_maximum_severity_trigger_is_exactly_half():
    """Which is what makes the colour mean something: above it, more
    than one enemy is asking for this item."""
    assert model.ONE_TRIGGER == 50
    one = model.importance(model.stacked_score([model.MAX_SEVERITY]))
    assert one == model.ONE_TRIGGER
    two = model.importance(model.stacked_score([3, 3]))
    assert two > model.ONE_TRIGGER


def test_a_severity_is_one_of_three_values_and_no_more():
    """Severity is 1..3 and "coarse by design" - a finer-looking number
    would be precision nobody measured."""
    assert {model.severity_pct(s) for s in (1, 2, 3)} == {33, 67, 100}


def test_it_is_measured_against_the_worst_case_not_against_this_draft():
    """A figure scaled to whatever else is on screen means something
    different in every draft, so two drafts could not be compared."""
    import inspect
    body = inspect.getsource(model.importance)
    assert "MAX_SCORE" in body


# --- the callout line --------------------------------------------------

def test_the_line_is_the_hero_then_its_percentage_then_why():
    heading, lines, note = reasons.item_reasons(
        "Black King Bar",
        [FakeTrigger("Huskar", 3, "Burning Spear pierces most defences")],
        stale=False)
    assert heading == "Black King Bar"
    assert lines == ["Huskar | 100% — Burning Spear pierces most defences"]
    assert note == ""


def test_the_severity_number_is_gone_from_the_line():
    _h, lines, _n = reasons.item_reasons(
        "Eul's Scepter", [FakeTrigger("Lion", 2, "chain stun")], False)
    assert "severity" not in lines[0]
    assert "Lion | 67% — chain stun" == lines[0]


def test_the_hand_authored_footnote_is_gone():
    for stale in (True, False):
        _h, _l, note = reasons.item_reasons(
            "Pipe", [FakeTrigger("Zeus", 3, "magic burst")], stale)
        assert "hand-authored" not in note.lower()
        assert "not measured" not in note.lower()


def test_but_a_stale_rule_still_says_so():
    """That one is a fact about the DATA, not a disclaimer about it."""
    _h, _l, note = reasons.item_reasons(
        "Pipe", [FakeTrigger("Zeus", 3, "magic burst")], stale=True)
    assert note == "Unverified this patch."


def test_every_trigger_gets_its_own_line():
    _h, lines, _n = reasons.item_reasons(
        "BKB", [FakeTrigger("Lion", 3, "a"), FakeTrigger("Shaman", 2, "b")],
        False)
    assert len(lines) == 2
    assert lines[0].startswith("Lion | 100%")
    assert lines[1].startswith("Shaman | 67%")


# --- and it is PAINTED, so the test renders it -------------------------

import os                                              # noqa: E402

pytest.importorskip("PyQt6")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtGui import QColor, QImage, QPainter       # noqa: E402
from PyQt6.QtWidgets import QApplication               # noqa: E402

from draft_assist.model.items import ItemAdvice, Trigger   # noqa: E402
from draft_assist.ui import theme                          # noqa: E402
from draft_assist.ui.item_row import ItemTile              # noqa: E402


@pytest.fixture(scope="module")
def qapp():
    yield QApplication.instance() or QApplication([])


def an_item(score, severities=(3,)):
    return ItemAdvice(
        item="Black King Bar", score=score, any_stale=False,
        triggers=[Trigger(hero="Lion", severity=s, reason="chains disables",
                          stale=False) for s in severities])


def painted(tile):
    image = QImage(tile.width(), tile.height(),
                   QImage.Format.Format_ARGB32)
    image.fill(QColor("#101010"))
    painter = QPainter(image)
    tile.render(painter)
    painter.end()
    return image


def ink_near(image, colour, corner=True):
    """Is there any pixel close to `colour`, in the bottom-right?"""
    want = QColor(colour)
    x0 = image.width() // 2 if corner else 0
    y0 = image.height() // 2 if corner else 0
    for y in range(y0, image.height()):
        for x in range(x0, image.width()):
            got = QColor(image.pixel(x, y))
            if (abs(got.red() - want.red()) < 40
                    and abs(got.green() - want.green()) < 40
                    and abs(got.blue() - want.blue()) < 40):
                return True
    return False


def test_an_important_item_prints_its_percentage_in_green(qapp):
    tile = ItemTile(an_item(model.MAX_SCORE))       # 100%
    image = painted(tile)
    assert ink_near(image, theme.GOOD), "no green figure in the corner"


def test_a_marginal_item_prints_it_in_red(qapp):
    tile = ItemTile(an_item(model.SEVERITY_FLOOR))  # 33%, at the floor
    image = painted(tile)
    assert ink_near(image, theme.BAD), "no red figure in the corner"


def test_the_two_are_not_the_same_colour(qapp):
    """"Most important is higher percentages and lower importance is
    red" - so the rule has to actually separate them."""
    top = painted(ItemTile(an_item(model.MAX_SCORE)))
    low = painted(ItemTile(an_item(model.SEVERITY_FLOOR)))
    assert ink_near(top, theme.GOOD) and not ink_near(top, theme.BAD)
    assert ink_near(low, theme.BAD) and not ink_near(low, theme.GOOD)


def test_it_is_the_same_painter_as_every_other_figure_in_the_app(qapp):
    """"Exact same text that is used for the synergy / counter numbers."
    One implementation, or the badge on a pick and the badge on an item
    drift into two conventions."""
    import inspect
    body = inspect.getsource(ItemTile.paintEvent)
    assert "tilekit.paint_badge" in body
    assert 'f"{share}%"' in body


def test_the_tooltip_carries_the_same_number_as_the_corner(qapp):
    tile = ItemTile(an_item(model.stacked_score([3, 3])))
    share = model.importance(tile.advice.score)
    assert f"{share}%" in tile.toolTip()
    assert "hand-authored" not in tile.toolTip().lower()
    assert "sev " not in tile.toolTip()
    assert "Lion | 100%" in tile.toolTip()
