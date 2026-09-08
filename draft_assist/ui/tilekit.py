"""One look for every tile in the app, in one place.

There are three strips of tiles now — the ten picks, the suggested picks
and the items — and they were drifting apart: the hero names were 11pt
bold on a tinted band above the art, the item names were 9pt plain with no
band under the art, and nothing said they were the same kind of thing. The
user asked for one look, so the parts every tile shares live here and the
tiles are the layout around them.

**The names are gone, and the band is now a FALLBACK.** The user plays the
game; they know Pudge from his face faster than from four letters, and a
row of pictures reads at a glance where a row of labelled pictures reads
as a list. But a tile with no art AND no name is nothing, and a fresh
install has no art at all — so the band is still drawn, only when there is
no picture to draw instead. The name lives in the tooltip either way.

The shared parts:

* a NAME BAND across the top, tinted rather than transparent, drawn ONLY
  when the tile has no art. It sits above the art rather than on it
  because a label over a portrait hides the half of the portrait you
  recognise the hero by.
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
# +20% on each, and every one is drawn BOLD (see `paint_band` and
# `paint_badge`): these sit over artwork, where weight is what keeps them
# readable rather than what makes them shout.
NAME_MAX_PT = 14
NAME_MIN_PT = 9
NUMBER_PT = 14

# The name strip and the number badge share one plate, and it is SOLID
# BLACK. It was 65% black, which let the portrait through behind the
# digits — over a bright piece of art a "+12.34" had to be read against
# whatever colour happened to be under it, and the number is the one thing
# on the tile that has to be legible at a glance. Opaque, at the user's
# request: the plate is small and cut to the digits, so it costs almost
# none of the picture.
CHROME = QColor(0, 0, 0)
BADGE_PAD_X = 5
BADGE_PAD_Y = 2

# A tile in one of the two STRIPS (items, suggested picks). These are the
# FALLBACK size only — before the draft panel has been laid out there is
# no pick tile to match, and the strips take their real size from it (see
# `SuggestRow.set_tile_size`): every tile in the app is one box, so a
# suggestion is the same size as a pick and the placeholders before the
# game are the same size as the tiles after it. The strip WRAPS to another
# row rather than running off the window.
STRIP_W = 78
# 16:9, because that is the shape of a top-bar portrait — the art is the
# whole tile now that the name band has gone, so the tile is the picture's
# own shape rather than a picture with a label bolted above it.
STRIP_ART_H = 44
STRIP_BAND_H = 22          # only ever drawn when there is no art
STRIP_H = STRIP_ART_H


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


# An empty tile's corner radius. ONE number, because an empty pick slot
# and an empty plate in a strip are the same object seen twice: the picks
# rounded their corners and the strips squared theirs, so on a freshly
# opened app the two rows of identical boxes did not look identical.
PLATE_RADIUS = 6


def paint_plate(painter: QPainter, box: QRect, dashed: bool = False) -> None:
    """The empty plate an unfilled tile shows: a hole, not an error."""
    inner = box.adjusted(0, 0, -1, -1)
    painter.setPen(QPen(QColor(theme.BORDER), 1,
                        Qt.PenStyle.DashLine if dashed else Qt.PenStyle.SolidLine))
    painter.setBrush(QColor(theme.BG_INPUT if not dashed else theme.BG_DEEP))
    painter.drawRoundedRect(inner, PLATE_RADIUS, PLATE_RADIUS)
    painter.setBrush(Qt.BrushStyle.NoBrush)
