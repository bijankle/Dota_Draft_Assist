"""A gold rectangle round a relation's figure, in place of two words.

At the user's request, in three messages: "when the user clicks on a
5 / 5 portrait the others say with or v.s.... i dont think this is needed
... just use the capital delta symbol", then "actually no scrap that...
just use a gold rectangle aroudn the score (bottom right)", and "no delta
required at all".

WHAT IT BUYS: a mark that is not a character cannot be mistaken for part
of the number, cannot resize away from it, and costs the badge no width
at all — which on a small tile is the whole budget.
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


def _drawn(text, boxed, size=(140, 80)):
    image = QImage(*size, QImage.Format.Format_ARGB32)
    image.fill(QColor(theme.BG_DEEP))
    painter = QPainter(image)
    tilekit.paint_badge(painter, QRect(0, 0, *size), text, theme.GOOD,
                        QFont(), boxed=boxed)
    painter.end()
    return image


def _gold(image):
    want = QColor(tilekit.focus_colour())
    return [(x, y) for x in range(image.width())
            for y in range(image.height())
            if all(abs(a - b) < 26 for a, b in
                   ((QColor(image.pixel(x, y)).red(), want.red()),
                    (QColor(image.pixel(x, y)).green(), want.green()),
                    (QColor(image.pixel(x, y)).blue(), want.blue())))]


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


# ---- the mark ----------------------------------------------------------

def test_a_relation_is_ringed_and_a_resting_figure_is_not(qapp):
    """The badge is the same in both states; what says "this is about the
    hero you clicked" is the box."""
    assert _gold(_drawn("+5.2", True)), "a relation has no gold box"
    assert not _gold(_drawn("+5.2", False)), (
        "a resting figure wears the relation's mark")


def test_the_ring_is_the_apps_this_one_colour(qapp):
    """Gold because that is what the window's border, the focus ring, the
    star and the pin all wear, and none of them means good or bad — green
    and red are spoken for by the figure INSIDE the box."""
    assert tilekit.focus_colour() == theme.FRAME_GOLD
    assert theme.GOOD != tilekit.focus_colour()
    assert theme.BAD != tilekit.focus_colour()


def test_the_ring_is_the_focus_rings_own_pen(qapp):
    """"i want the golden box to be the same line weight as the border on
    the selected hero".

    It was a 1px hairline beside a three-pixel ring on the tile next to
    it. `FOCUS_WIDTH` is the one number the app's gold lines are drawn
    at — the window's frame, the focus ring — so the box reads as the
    same kind of mark rather than as a thinner relative of one.
    """
    from draft_assist.ui import ornate

    assert tilekit.FOCUS_WIDTH == ornate.WIDTH

    seen = []
    real = tilekit.QPen

    class Spy(real):
        def __init__(self, *args):
            super().__init__(*args)
            if len(args) > 1:
                seen.append(args[1])

    tilekit.QPen = Spy
    try:
        _drawn("+5.2", True)
    finally:
        tilekit.QPen = real
    assert tilekit.FOCUS_WIDTH in seen, seen


def test_the_ring_hugs_the_ink_rather_than_the_fonts_ascent(qapp):
    """"and to be smaller as per the green box i drew".

    It was drawn round `metrics.ascent()`, which is the tallest thing the
    FACE can draw — and these are digits, so the box carried a band of
    empty portrait along its top. `tightBoundingRect` is what the glyphs
    actually cover.
    """
    from PyQt6.QtGui import QFont, QFontMetricsF

    text = "+5.2"
    font = QFont()
    font.setPixelSize(tilekit.number_px())
    font.setBold(True)
    metrics = QFontMetricsF(font)
    marks = _gold(_drawn(text, True))
    tall = max(y for _x, y in marks) - min(y for _x, y in marks)
    # The frame's own two pens and its padding, and nothing else.
    over = 2 * (tilekit.badge_ring_reach() + tilekit.FOCUS_WIDTH / 2)
    assert tall <= metrics.tightBoundingRect(text).height() + over + 2
    assert tall < metrics.ascent() + over, "still drawn round the ascent"


def test_the_frame_takes_the_corner_the_digits_would_have(qapp):
    """A boxed badge and a bare one line up along the same two edges:
    the figure moves in by exactly what the frame reaches, so the GOLD
    lands where the digits sit on every other tile."""
    bare = _drawn("+5.2", False)
    boxed = _drawn("+5.2", True)
    ink = [(x, y) for x in range(bare.width()) for y in range(bare.height())
           if QColor(bare.pixel(x, y)) != QColor(theme.BG_DEEP)]
    marks = _gold(boxed)
    # Within the halo's own reach: the bare badge's ink includes the
    # black stroke, which spills a pixel or two past the baseline and
    # past the last glyph, and the frame is placed against the GLYPHS.
    slack = tilekit.stroke_width() + 1
    assert abs(max(x for x, _y in marks) - max(x for x, _y in ink)) <= slack
    assert abs(max(y for _x, y in marks) - max(y for _x, y in ink)) <= slack


def test_the_ring_encloses_the_digits_and_stays_inside_the_tile(qapp):
    image = _drawn("-12.3", True)
    marks = _gold(image)
    left = min(x for x, _y in marks)
    right = max(x for x, _y in marks)
    top = min(y for _x, y in marks)
    bottom = max(y for _x, y in marks)
    assert left > 0 and top > 0
    assert right <= image.width() - 1 and bottom <= image.height() - 1
    # BOTTOM RIGHT, where the badge has always been: "just use a gold
    # rectangle aroudn the score (bottom right)".
    assert left > image.width() / 2
    assert top > image.height() / 2


def test_a_narrow_tile_fits_the_box_as_well_as_the_number(qapp):
    """The frame is drawn OUTSIDE the digits, so it is part of what has
    to fit — without that a relation badge on the narrowest tile would
    step its figure down to exactly the room available and then hang its
    box over the edge."""
    narrow = (64, 36)
    image = _drawn("+21.7", True, narrow)
    marks = _gold(image)
    assert marks, "no box at all on a narrow tile"
    assert max(x for x, _y in marks) <= narrow[0] - 1
    assert min(x for x, _y in marks) >= 0


# ---- what the tiles do with it ----------------------------------------

def test_a_pick_tile_rings_a_relation_and_forgets_it_again(qapp):
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
