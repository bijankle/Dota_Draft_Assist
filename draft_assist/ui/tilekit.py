"""One look for every tile in the app, in one place.

There are three strips of tiles now — the ten picks, the suggested picks
and the items — and they were drifting apart: the hero names were 11pt
bold on a tinted band above the art, the item names were 9pt plain with no
band under the art, and nothing said they were the same kind of thing. The
user asked for one look, so the parts every tile shares live here and the
tiles are the layout around them.

The three shared parts:

* a NAME BAND across the top, tinted rather than transparent. It sits above
  the art rather than on it because a label over a portrait hides the half
  of the portrait you recognise the hero by, and the art is only worth
  drawing because it is quicker to read than the name.
* a NUMBER BADGE in the bottom-right, cut to the size of the digits and
  wearing the same tint, so the two pieces of text read as one layer over
  the picture instead of two ideas.
* the ART, scaled to FIT its box and centred, never to fill it: the window
  aspect must never be able to stretch a portrait.

One point size for both names, because the request was that they match:
10pt, between the items' 9 and the heroes' 11.
"""

from PyQt6.QtCore import QRect, QRectF, Qt
from PyQt6.QtGui import QColor, QFont, QFontMetricsF, QPainter, QPen

from . import theme
from .textfit import fit

# The name never grows past this and never shrinks below it; between them
# it gives way before the text does.
NAME_MAX_PT = 10
NAME_MIN_PT = 7
NUMBER_PT = 10

# The name strip and the number badge share one tint.
CHROME = QColor(0, 0, 0, 165)
BADGE_PAD_X = 5
BADGE_PAD_Y = 2

# A tile in one of the two STRIPS (items, suggested picks). The ten picks
# size themselves from the panel instead; these are fixed, because a strip
# scrolls sideways rather than reflowing.
STRIP_W = 78
STRIP_ART_H = 50
STRIP_BAND_H = 26
STRIP_H = STRIP_BAND_H + STRIP_ART_H


def band_height(box_height: int) -> int:
    """The name strip's share of a tile of this height."""
    return max(20, int(box_height * 0.28))


def paint_band(painter: QPainter, band: QRect, text: str, base: QFont,
               colour: str = theme.TEXT_STRONG) -> None:
    """Fill the strip and draw the name in it: shrink, wrap, then elide.

    The font gives way before the text does, because the name is the thing
    the tile exists to say. Two lines only happen at a size where two lines
    still fit the strip.
    """
    painter.fillRect(band, CHROME)
    avail = band.width() - 8
    size, lines = fit(text, avail, band.height(), base,
                      NAME_MAX_PT, NAME_MIN_PT, bold=True)
    font = QFont(base)
    font.setPointSize(size)
    font.setBold(True)
    painter.setFont(font)
    metrics = QFontMetricsF(font)
    painter.setPen(QColor(colour))
    painter.drawText(
        QRectF(band.adjusted(4, 1, -4, -1)), int(Qt.AlignmentFlag.AlignCenter),
        "\n".join(metrics.elidedText(line, Qt.TextElideMode.ElideRight, avail)
                  for line in lines))


def paint_badge(painter: QPainter, box: QRect, text: str, colour: str,
                base: QFont) -> None:
    """The signed number, bottom-right, no bigger than the digits need.

    A full-width bar there would hide as much of the picture as the name
    used to, which is the whole reason the badge is cut to fit.
    """
    if not text:
        return
    font = QFont(base)
    font.setPointSize(NUMBER_PT)
    font.setBold(True)
    painter.setFont(font)
    metrics = QFontMetricsF(font)
    width = metrics.horizontalAdvance(text)
    badge = QRectF(box.right() - 3 - width - 2 * BADGE_PAD_X,
                   box.bottom() - 3 - metrics.height() - 2 * BADGE_PAD_Y,
                   width + 2 * BADGE_PAD_X,
                   metrics.height() + 2 * BADGE_PAD_Y)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(CHROME)
    painter.drawRoundedRect(badge, 3, 3)
    painter.setPen(QColor(colour))
    painter.drawText(badge, int(Qt.AlignmentFlag.AlignCenter), text)


def paint_art(painter: QPainter, box: QRect, art) -> bool:
    """Centre `art` in `box`. Returns False when there is nothing to draw.

    A missing picture is NORMAL — a fresh install has downloaded neither
    portraits nor item icons — so the caller draws a plain plate instead
    rather than treating it as an error.
    """
    if art is None or box.height() < 4:
        return False
    painter.drawPixmap(box.left() + (box.width() - art.width()) // 2,
                       box.top() + (box.height() - art.height()) // 2, art)
    return True


def paint_plate(painter: QPainter, box: QRect, dashed: bool = False) -> None:
    """The empty plate an unfilled tile shows: a hole, not an error."""
    painter.fillRect(box, QColor(theme.BG_INPUT if not dashed
                                 else theme.BG_DEEP))
    painter.setPen(QPen(QColor(theme.BORDER), 1,
                        Qt.PenStyle.DashLine if dashed else Qt.PenStyle.SolidLine))
    painter.setBrush(Qt.BrushStyle.NoBrush)
    painter.drawRect(box.adjusted(0, 0, -1, -1))
