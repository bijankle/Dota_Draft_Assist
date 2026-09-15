"""A relation's figure is GOLD, and there is no box round anything.

At the user's request, and it reverses the gold rectangle that stood
here: "instead of showing that mini border around all heroes when you
click on a 5 /5 portrait hero, i want it to be that the number changes
from green / red to gold".

The box came out of three earlier messages ("i dont think this is needed
... just use the capital delta symbol", then "just use a gold rectangle
aroudn the score (bottom right)", then "no delta required at all"), each
of which was trying to say the same thing: what a reader needs to know is
that THIS figure is about the hero they clicked, and it must not cost the
number any width. A colour costs it none at all, where a frame had to be
fitted outside the digits and stepped the figure down a size to make room
for itself on a narrow tile.

The second half of the same request is the tile's PAGE MARGIN: "the
number needs to be tucked right into the corner and the heart ans shield
a little closer to the corner aswell so that they dont clash.... see page
margin i drew in green, i wanna kiss that for all 3, heart, shield,
number".
"""

import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

pytest.importorskip("PyQt6")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import QRect                              # noqa: E402
from PyQt6.QtGui import QColor, QFont, QImage, QPainter     # noqa: E402
from PyQt6.QtWidgets import QApplication                    # noqa: E402

from draft_assist.ui import teams, theme, tilekit           # noqa: E402


@pytest.fixture(scope="module")
def qapp():
    yield QApplication.instance() or QApplication([])


def _drawn(text, boxed, size=(140, 80), colour=None):
    image = QImage(*size, QImage.Format.Format_ARGB32)
    image.fill(QColor(theme.BG_DEEP))
    painter = QPainter(image)
    tilekit.paint_badge(painter, QRect(0, 0, *size), text,
                        theme.GOOD if colour is None else colour,
                        QFont(), boxed=boxed)
    painter.end()
    return image


def _near(image, colour):
    """Every pixel drawn in (something very close to) this colour."""
    want = QColor(colour)
    found = []
    for x in range(image.width()):
        for y in range(image.height()):
            got = QColor(image.pixel(x, y))
            if (abs(got.red() - want.red()) < 26
                    and abs(got.green() - want.green()) < 26
                    and abs(got.blue() - want.blue()) < 26):
                found.append((x, y))
    return found


def _ink(image):
    """Everything the painter touched, halo included."""
    ground = QColor(theme.BG_DEEP)
    return [(x, y) for x in range(image.width())
            for y in range(image.height())
            if QColor(image.pixel(x, y)) != ground]


def _box(points):
    return (min(x for x, _y in points), min(y for _x, y in points),
            max(x for x, _y in points), max(y for _x, y in points))


# ---- the text ----------------------------------------------------------

def test_the_figure_is_the_whole_text(qapp):
    """"no delta required at all" — not the words, and not a symbol
    standing in for them either."""
    assert tilekit.delta_text(0.052, "with") == "+5.2"
    assert tilekit.delta_text(-0.018, "vs") == "-1.8"
    assert tilekit.delta_text(0.021) == "+2.1"
    for kind in ("with", "vs", None):
        text = tilekit.delta_text(0.05, kind)
        assert "with" not in text and "vs" not in text
        assert "Δ" not in text and "△" not in text


# ---- the colour --------------------------------------------------------

def test_a_relation_is_gold_and_a_resting_figure_keeps_its_own_colour(qapp):
    """"i want it to be that the number changes from green / red to
    gold"."""
    gold = tilekit.focus_colour()
    assert _near(_drawn("+5.2", True), gold), "a relation is not gold"
    assert not _near(_drawn("+5.2", False), gold), (
        "a resting figure wears the relation's colour")
    assert _near(_drawn("+5.2", False), theme.GOOD), (
        "a resting figure lost its own green")
    # And a NEGATIVE relation is gold too — the box it replaces never
    # cared about the sign either, and green/red are what is being taken
    # away from a figure that is not a judgement.
    assert _near(_drawn("-1.8", True, colour=theme.BAD), gold)
    assert not _near(_drawn("-1.8", True, colour=theme.BAD), theme.BAD)


def test_gold_is_the_apps_this_one_colour(qapp):
    """The window's border, the focus ring, the star and the pin all wear
    it, and none of them means good or bad — which is exactly why it can
    be spent on a figure that is not a judgement."""
    assert tilekit.focus_colour() == theme.FRAME_GOLD
    assert theme.GOOD != tilekit.focus_colour()
    assert theme.BAD != tilekit.focus_colour()


def test_there_is_no_box_round_anything_any_more(qapp):
    """"instead of showing that mini border around all heroes".

    The gold has to be the DIGITS, so a relation badge covers no more of
    the tile than a resting one: same glyphs, same ink, same corner.
    """
    bare = _ink(_drawn("+5.2", False))
    boxed = _ink(_drawn("+5.2", True))
    assert _box(bare) == _box(boxed), "the relation badge is bigger"
    # A rectangle would be a LOT more ink than a "+5.2".
    assert abs(len(boxed) - len(bare)) <= len(bare) * 0.05
    assert not hasattr(tilekit, "badge_ring_reach")
    assert not hasattr(tilekit, "BADGE_RING_PAD")


def test_a_relation_costs_the_figure_no_width(qapp):
    """The frame had to be fitted OUTSIDE the digits, so on a narrow tile
    it stepped the figure down a size to make room for itself. A colour
    cannot crowd anything, so both badges are now the same size."""
    narrow = (64, 36)
    bare = _box(_ink(_drawn("+21.7", False, narrow)))
    boxed = _box(_ink(_drawn("+21.7", True, narrow)))
    assert bare == boxed
    assert boxed[2] <= narrow[0] - 1 and boxed[0] >= 0


# ---- the margin --------------------------------------------------------

def test_every_mark_on_a_tile_kisses_one_margin(qapp):
    """"i wanna kiss that for all 3, heart, shield, number".

    It was two numbers measured to two different things — 1 for the badge
    and 3 for the marks — which put a heart hard against the top edge and
    a figure four pixels in from the bottom one. Measured to the COLOUR,
    since the black halo every mark here wears is drawn outside the shape
    it describes and deliberately runs off the tile.
    """
    side = (108, 61)
    image = QImage(*side, QImage.Format.Format_ARGB32)
    image.fill(QColor(theme.BG_DEEP))
    painter = QPainter(image)
    box = QRect(0, 0, *side)
    tilekit.paint_heart(painter, box, 1)
    tilekit.paint_shield(painter, box, 2)
    tilekit.paint_badge(painter, box, "+2.9", theme.GOOD, QFont())
    painter.end()

    width, height = side
    shield = _box([p for p in _near(image, theme.FRAME_GOLD)
                   if p[0] < width / 2 and p[1] < height / 2])
    heart = _box([p for p in _near(image, theme.HEART_PINK)
                  if p[0] > width / 2 and p[1] < height / 2])
    badge = _box([p for p in _near(image, theme.GOOD)
                  if p[0] > width / 2 and p[1] > height / 2])

    inset = (shield[0], shield[1],                  # left, top
             width - 1 - heart[2], heart[1],        # right, top
             width - 1 - badge[2], height - 1 - badge[3])
    # ONE margin, within the pixel or two the three outlines differ by:
    # a heart's stroke is 0.22 of its box and a shield's 0.20, and a
    # digit's halo is a share of the text size.
    assert max(inset) - min(inset) <= 3, inset
    assert min(inset) >= tilekit.MARGIN, inset
    assert max(inset) <= tilekit.MARGIN + 4, inset


def test_the_margin_is_one_number_read_by_both_painters(qapp):
    """Two constants is two of them drifting, which is what produced the
    mismatch in the first place."""
    assert not hasattr(tilekit, "STAR_INSET")
    assert not hasattr(tilekit, "BADGE_INSET")
    box = QRect(0, 0, 120, 68)
    assert tilekit.star_box(box, left=True).left() == tilekit.MARGIN
    assert tilekit.star_box(box).top() == tilekit.MARGIN
    # SYMMETRICAL, which it was not: `right()` is the last PIXEL rather
    # than the edge, so without the +1 inside `star_box` a mark on the
    # right sat one pixel further in than its twin on the left.
    assert (box.right() - tilekit.star_box(box).right()) == tilekit.MARGIN


# ---- what the tiles do with it ----------------------------------------

def test_a_pick_tile_golds_a_relation_and_forgets_it_again(qapp):
    tile = teams.HeroTile("ally", 0)
    tile.set_pick("Lion", None, 26)
    assert not tile._boxed and tile.relation_kind() == ""
    tile.show_delta(0.052, "with")
    assert tile._boxed and tile.relation_kind() == "with"
    tile.show_delta(0.031)              # back to its own net figure
    assert not tile._boxed and tile.relation_kind() == ""
    tile.show_delta(-0.02, "vs")
    tile.clear_delta()
    assert not tile._boxed and tile.relation_kind() == ""
    tile.deleteLater()
