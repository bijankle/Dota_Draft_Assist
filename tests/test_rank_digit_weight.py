"""The number inside the heart and the shield is BLACK, not bold.

At the user's request: "a bit girthier? thicker? bolder? - maybe a
similar looking font that is bolder". It is the same family one weight
up - `assets/fonts/Alegreya-Black.ttf`, already bundled and already
registered for the app's own name in the title bar - so it costs no new
file and cannot read as a different typeface.

What is checked here is the property that was actually asked for (more
ink) and the two things it could have broken: the digit spilling outside
the shape, and the centring that took three goes to land.
"""

import os

import pytest

pytest.importorskip("PyQt6")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import QPointF, QRect                      # noqa: E402
from PyQt6.QtGui import (QColor, QFont, QFontMetricsF,       # noqa: E402
                         QImage, QPainter)
from PyQt6.QtWidgets import QApplication                     # noqa: E402

from draft_assist.ui import fonts, theme, tilekit            # noqa: E402

RANKS = (1, 2, 8, 9, 12, 20)
MARKS = (("heart", tilekit.paint_heart, tilekit.HEART_CENTRE),
         ("shield", tilekit.paint_shield, tilekit.SHIELD_CENTRE))


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    fonts.load_bundled()
    yield app


def _ink(families, weight, text, px=60):
    """Pixels actually covered by one string, laid out as `_paint_rank` does."""
    font = QFont()
    font.setFamilies(families)
    font.setPixelSize(px)
    if weight is not None:
        font.setWeight(weight)
    font.setBold(True)
    image = QImage(300, 300, QImage.Format.Format_ARGB32)
    image.fill(0)
    painter = QPainter(image)
    painter.setFont(font)
    painter.setPen(QColor("black"))
    box = QFontMetricsF(font).tightBoundingRect(text)
    painter.drawText(QPointF(150 - box.width() / 2 - box.left(),
                             150 + box.height() / 2), text)
    painter.end()
    return [(x, y) for y in range(300) for x in range(300)
            if image.pixelColor(x, y).alpha() > 60]


def _drawn(paint, size, rank):
    """The pixels the DIGIT adds, by differencing against the bare mark."""
    box = QRect(0, 0, size, size)
    blank = QImage(size, size, QImage.Format.Format_ARGB32)
    blank.fill(0)
    painter = QPainter(blank)
    paint(painter, box, None)
    painter.end()
    marked = QImage(size, size, QImage.Format.Format_ARGB32)
    marked.fill(0)
    painter = QPainter(marked)
    paint(painter, box, rank)
    painter.end()
    return blank, marked, [
        (x, y) for y in range(size) for x in range(size)
        if marked.pixelColor(x, y) != blank.pixelColor(x, y)]


def test_the_bundled_black_weight_is_actually_available(qapp):
    """The whole change rests on this file being registered; without it
    Qt silently substitutes and the digit gets no heavier."""
    from PyQt6.QtGui import QFontDatabase
    assert theme.TITLE_FAMILY in QFontDatabase.families()


@pytest.mark.parametrize("text", ["1", "2", "8", "12", "20"])
def test_black_lays_down_more_ink_than_bold_at_the_same_size(qapp, text):
    """THE REQUEST, measured rather than eyeballed."""
    bold = len(_ink([theme.BODY_FAMILY], None, text))
    black = len(_ink([theme.TITLE_FAMILY], QFont.Weight.Black, text))
    assert black > bold * 1.15, (
        f"'{text}' went from {bold} to {black} px of ink — that is not "
        "thicker enough to be worth a font change")


@pytest.mark.parametrize("text", ["1", "2", "8", "12", "20"])
def test_and_it_costs_almost_nothing_in_width(qapp, text):
    """A heavier face that were much wider would force the size down,
    which would undo the thickening it was chosen for."""
    def width(families, weight):
        xs = [x for x, _y in _ink(families, weight, text)]
        return max(xs) - min(xs)
    bold = width([theme.BODY_FAMILY], None)
    black = width([theme.TITLE_FAMILY], QFont.Weight.Black)
    assert black <= bold * 1.12


@pytest.mark.parametrize("size", [100, 140, 200])
@pytest.mark.parametrize("name,paint,_centre", MARKS)
@pytest.mark.parametrize("rank", RANKS)
def test_no_digit_escapes_its_shape(qapp, size, name, paint, _centre, rank):
    """A wider face is the one way this change could go wrong."""
    blank, _marked, digit = _drawn(paint, size, rank)
    spilled = [(x, y) for x, y in digit
               if blank.pixelColor(x, y).alpha() < 120]
    assert not spilled, (
        f"rank {rank} in the {name} at {size}px puts {len(spilled)} "
        "pixels outside the mark")


def _perceived(paint, rank, size=200):
    """Where the digit LOOKS like it sits, weighted by coverage.

    A hard threshold on alpha is the wrong instrument here and reports a
    fault that is not there. The mark is at most `STAR_MAX_PX` (32)
    across, so counting a pixel as in or out quantises the answer to
    1/32 - 3% - while Qt is positioning the glyph to a fraction of a
    pixel and carrying the remainder in the ANTIALIASING, which is
    exactly what the eye integrates. Weighting by how much each pixel
    actually changed measures the thing a reader sees.
    """
    box = QRect(0, 0, size, size)
    blank, marked, _digit = _drawn(paint, size, rank)
    total = across = down = 0.0
    for y in range(size):
        for x in range(size):
            before, after = blank.pixelColor(x, y), marked.pixelColor(x, y)
            weight = (abs(after.alpha() - before.alpha())
                      + abs(after.red() - before.red()))
            if weight:
                total += weight
                across += weight * (x + 0.5)
                down += weight * (y + 0.5)
    where = tilekit.star_box(box, left=(paint is tilekit.paint_shield))
    return ((across / total - where.left()) / where.width(),
            (down / total - where.top()) / where.height())


@pytest.mark.parametrize("name,paint,centre", MARKS)
@pytest.mark.parametrize("rank", RANKS)
def test_the_digit_is_still_centred_on_the_shape(qapp, name, paint, centre,
                                                 rank):
    """The centring took three goes to land — "it's still a little left"
    — so a font change has to be shown not to have moved it.

    The tolerance is ONE PIXEL of the mark and no tighter, because that
    is what there is to measure with: `STAR_MAX_PX` is 32, so a pixel is
    3% of the box, and asking for better is asking the instrument for
    precision it does not have.
    """
    box = QRect(0, 0, 200, 200)
    where = tilekit.star_box(box, left=(paint is tilekit.paint_shield))
    slack = 1.0 / where.width()
    middle_x, middle_y = _perceived(paint, rank)
    assert abs(middle_x - 0.5) <= slack, f"{name} rank {rank} x={middle_x:.4f}"
    # Vertically it is the SHAPE's own centroid, measured by filling the
    # path, never the box's middle — neither of these marks has its mass
    # in the middle of the rectangle drawn round it. Two pixels here: the
    # code centres the ink's BOX, which is what makes a 1 and an 8 line
    # up with each other, and a digit's MASS is not quite its box.
    assert abs(middle_y - centre) <= 2 * slack, (
        f"{name} rank {rank} y={middle_y:.4f} against {centre}")


@pytest.mark.parametrize("name,paint,_centre", MARKS)
def test_the_heavier_face_left_it_no_worse_than_it_found_it(qapp, name, paint,
                                                            _centre):
    """Black has its own side bearings and lining figures their own
    heights, so this is the specific thing the change could have broken.
    Measured across every rank against what the bold old-style face
    produced: x ran 0.481-0.530 before and must not spread wider."""
    across = [_perceived(paint, rank)[0] for rank in RANKS]
    assert min(across) >= 0.481 and max(across) <= 0.530
    assert max(across) - min(across) <= 0.049


def test_a_checkout_with_no_fonts_still_gets_the_heaviest_it_can(qapp):
    """A missing font is NORMAL here — `FONT_STACK` names system serifs
    behind Alegreya for exactly that. Bold is set as well as the family
    so the fallback is not left at regular weight."""
    import inspect
    source = inspect.getsource(tilekit._paint_rank)
    assert "setWeight(QFont.Weight.Black)" in source
    assert "setBold(True)" in source


def test_alegreyas_own_figures_are_the_defect_this_fixes(qapp):
    """ALEGREYA HAS OLD-STYLE FIGURES, which is right for running prose
    and wrong inside a 32px mark.

    This measures the FACE rather than the mark, deliberately. The old
    `_paint_rank` took its family from `painter.font()`, so a bare
    QImage harness like this one drew in the default sans — which has
    lining figures — while the real app, where the painter's font comes
    from the stylesheet, drew in Alegreya and got these. The defect was
    real on screen and invisible to a test of the mark, which is why the
    family is now NAMED rather than inherited.
    """
    def extents(feature):
        font = QFont()
        font.setFamilies([theme.TITLE_FAMILY])
        font.setPixelSize(100)
        font.setWeight(QFont.Weight.Black)
        if feature:
            tilekit._lining_figures(font)
        metrics = QFontMetricsF(font)
        return [metrics.tightBoundingRect(d) for d in "0123456789"]

    plain = extents(False)
    assert max(r.height() for r in plain) - min(r.height() for r in plain) >= 8
    assert max(r.bottom() for r in plain) > 5, "3 4 5 7 9 hang below the line"

    lining = extents(True)
    assert max(r.height() for r in lining) - min(r.height() for r in lining) <= 4
    assert max(r.bottom() for r in lining) <= 2, "all of them on the baseline"


def test_every_rank_is_drawn_at_one_height(qapp):
    """What that buys in the mark itself. One pixel of spread is ordinary
    overshoot — a round or pointed glyph is cut slightly past the cap
    line so it does not read as short — and is not the defect above."""
    heights = {}
    for rank in range(1, 10):
        _blank, _marked, digit = _drawn(tilekit.paint_heart, 200, rank)
        ys = [y for _x, y in digit]
        heights[rank] = max(ys) - min(ys)
    spread = max(heights.values()) - min(heights.values())
    assert spread <= 1, f"ranks drawn at different heights: {heights}"


def test_the_mark_does_not_borrow_the_tiles_font(qapp):
    """The family is NAMED, so the digit looks the same wherever the mark
    is drawn. Everything else about these marks is painted for exactly
    this reason: a glyph that takes whatever font the tile carries cannot
    be relied on to be any particular shape."""
    painter_font = QFont()
    painter_font.setFamilies(["Courier"])
    painter_font.setPixelSize(9)
    image = QImage(200, 200, QImage.Format.Format_ARGB32)
    image.fill(0)
    painter = QPainter(image)
    painter.setFont(painter_font)
    tilekit.paint_heart(painter, QRect(0, 0, 200, 200), 8)
    painter.end()

    plain = QImage(200, 200, QImage.Format.Format_ARGB32)
    plain.fill(0)
    painter = QPainter(plain)
    tilekit.paint_heart(painter, QRect(0, 0, 200, 200), 8)
    painter.end()

    assert image == plain, "the digit changed with the painter's own font"


def test_the_lining_figures_request_survives_a_qt_without_it(qapp):
    """PyQt6>=6.6 is what this project asks for and `setFeature` is Qt
    6.7, so an older install must get the old figures rather than an
    AttributeError out of a paint handler."""
    class Older:
        def __init__(self):
            self.touched = False

        def __getattr__(self, name):
            raise AttributeError(name)

    tilekit._lining_figures(Older())      # must not raise
