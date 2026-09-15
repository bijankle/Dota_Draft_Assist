"""A relation's figure is an ordinary signed number, and that is the end
of four rounds of trying to mark it.

Clicking a pick puts that hero's synergy or matchup on every other tile.
Saying WHICH kind of figure that is has now been asked for and withdrawn
four times: the words "with" and "vs", a capital delta, a gold rectangle
round the digits, and finally the digits themselves in the frame's gold —
"when i click on a hero portrait i dont want the numbers to be gold, i
actually prefer green / red... revert the change plz".

So the figure is printed exactly like every other signed number in the
app: green good, red bad, read from your own side. Which is not a gap.
What says which hero the board is measured against is the gold RING on
that portrait, and what says whether a figure is a synergy or a matchup
is the panel the tile sits in — an ally tile is in the ally panel. Every
mark tried here was a second answer to a question already answered
somewhere the eye was going anyway.

`kind` and `_boxed` survive all of it and still say WHETHER this is a
relation: an ally-to-ally pairing being scored as synergy rather than as
a matchup is a fact about the app worth being able to check. It just no
longer changes anything drawn.

The PAGE MARGIN from the same round does stand: "the number needs to be
tucked right into the corner and the heart ans shield a little closer to
the corner aswell so that they dont clash.... see page margin i drew in
green, i wanna kiss that for all 3, heart, shield, number".
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

def test_a_relation_keeps_green_and_red_like_every_other_figure(qapp):
    """"i dont want the numbers to be gold, i actually prefer green /
    red... revert the change plz"."""
    gold = tilekit.focus_colour()
    for text, colour in (("+5.2", theme.GOOD), ("-1.8", theme.BAD)):
        marked = _drawn(text, True, colour=colour)
        assert _near(marked, colour), f"{text} lost its own colour"
        assert not _near(marked, gold), f"{text} is still gold"


def test_a_relation_and_a_resting_figure_are_drawn_identically(qapp):
    """Nothing about the badge says which it is any more — not the text,
    not the colour, not a mark. The RING on the clicked portrait says
    which hero, and the panel says which kind of pairing."""
    for text, colour in (("+5.2", theme.GOOD), ("-1.8", theme.BAD)):
        relation = _ink(_drawn(text, True, colour=colour))
        resting = _ink(_drawn(text, False, colour=colour))
        assert _box(relation) == _box(resting)
        assert len(relation) == len(resting)


def test_nothing_is_drawn_round_the_digits(qapp):
    """The rectangle and every constant behind it are gone rather than
    left switched off: dead drawing code goes stale and then gets read as
    documentation."""
    assert not hasattr(tilekit, "badge_ring_reach")
    assert not hasattr(tilekit, "_ring_the_badge")
    assert not hasattr(tilekit, "BADGE_RING_PAD")
    # And no gold anywhere near a relation badge, at any sign.
    for text, colour in (("+5.2", theme.GOOD), ("-1.8", theme.BAD)):
        assert not _near(_drawn(text, True, colour=colour),
                         theme.FRAME_GOLD)


def test_a_relation_costs_the_figure_no_width(qapp):
    """The frame had to be fitted OUTSIDE the digits, so on a narrow tile
    it stepped the figure down a size to make room for itself. Nothing is
    drawn outside them now, so both badges are the same size."""
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

def test_a_pick_tile_still_knows_which_kind_of_figure_it_holds(qapp):
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
