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

from PyQt6.QtCore import QPointF, QRect, QRectF, Qt
from PyQt6.QtGui import (QColor, QFont, QFontMetricsF, QPainter,
                         QPainterPath, QPen)

from . import theme
from .textfit import fit

# The name never grows past this and never shrinks below it; between them
# it gives way before the text does.
# +20% on each, and every one is drawn BOLD (see `paint_band` and
# `paint_badge`): these sit over artwork, where weight is what keeps them
# readable rather than what makes them shout.
NAME_MAX_PT = 14
NAME_MIN_PT = 9
# THE NUMBER IS ONE FIXED SIZE, AND IT IS THE GRIDS'. It was briefly
# scaled to the tile — which fixed a badge covering the portrait on a
# narrow window, and then made the digits unreadable at exactly the size
# where the window is smallest and the number matters most. With the plate
# gone (see `paint_badge`) the size no longer has to buy back space from
# the art, so it is fixed and it stays fixed: shrink the window and the
# tiles get smaller under a number that goes on being legible.
#
# It was briefly the CARD HEADING's size, so a figure on a portrait was
# the height of the "-3.0" beside "Radiant". At the user's request it is
# now the BODY size, which is what the counters grid prints its deltas at
# — so every signed number in the app is one size, whether it sits on a
# pick, on a suggestion, in a triangle or in a counters cell, and there is
# one value to change rather than two to keep in step.
NUMBER_PX = theme.BODY_PX
# Only ever used when the tile is too narrow to print the figure at all.
NUMBER_MIN_PX = 9
# THE USER'S OWN MULTIPLIER (View ▸ Sizes ▸ Numbers). The size above is
# the base; this scales every number in the app at once, which is the only
# way it can be one setting — a figure on a pick, on a suggestion, in a
# triangle and in a counters cell all come through here.
SCALE = 1.0
SCALE_MIN, SCALE_MAX = 0.5, 2.0


def set_scale(factor: float) -> None:
    global SCALE
    SCALE = max(SCALE_MIN, min(SCALE_MAX, float(factor)))


def number_px() -> int:
    """The size a number is drawn at, the user's multiplier included.

    Read at CALL time, never captured into a constant: the setting can
    change while the app is running and a value copied at import would go
    on being the old one until a restart.
    """
    return max(NUMBER_MIN_PX, round(NUMBER_PX * SCALE))

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
# The outline round the digits, and how thick it is relative to the text
# size.
STROKE = QColor(0, 0, 0)
STROKE_OF_SIZE = 0.22
# How far the number sits off the tile's bottom-right corner.
BADGE_INSET = 1

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


def stroke_width(pixel_size: int | None = None) -> float:
    """How thick the outline round the digits is."""
    return max(2.0, (number_px() if pixel_size is None else pixel_size)
               * STROKE_OF_SIZE)


def paint_badge(painter: QPainter, box: QRect, text: str, colour: str,
                base: QFont) -> None:
    """The signed number, snug into the bottom-right, OUTLINED not plated.

    It used to sit on a solid black rounded plate. The plate is the part
    that hides the hero: even cut to the digits it is a rectangle of the
    portrait gone, and on a small tile that rectangle is most of the face
    you are reading the tile by. A stroke traced round the letterforms
    does the same job — it separates the number from whatever colour is
    behind it — and costs only the ink of the outline itself, so the art
    shows through between and around the characters.

    The stroke goes on first and the fill over it — see `stroked`.
    """
    if not text:
        return
    font = QFont(base)
    font.setPixelSize(number_px())
    font.setBold(True)
    metrics = QFontMetricsF(font)
    width = metrics.horizontalAdvance(text)
    # FIXED, except when it genuinely will not fit. The size does not
    # track the tile — that made it unreadable exactly where it matters —
    # but at the window's narrowest a "+21.7" is wider than the tile, and
    # a number clipped to "+21." is not a smaller number, it is a WRONG
    # one. So it steps down only far enough to fit, and only there.
    room = box.width() - 2 * (BADGE_INSET + stroke_width() / 2)
    size = number_px()
    while width > room and size > NUMBER_MIN_PX:
        size -= 1
        font.setPixelSize(size)
        metrics = QFontMetricsF(font)
        width = metrics.horizontalAdvance(text)
    # SNUG INTO THE CORNER, and the BASELINE is what sits on the bottom.
    # It used to float three pixels off both edges, which on a small tile
    # is a number apparently hovering in the middle of the art rather than
    # sitting in its corner. Then it was held a DESCENT off the bottom, so
    # that a figure which had to step down still stood on the same line as
    # its full-size neighbours — and none of these figures has a
    # descender. "+0.52", "-12.34", a sigma and a total: every glyph in
    # them stands on the baseline, so reserving room under it left a
    # visible band of empty portrait below the digits on every tile in the
    # app, which is what "they should be right on the bottom, snug" was
    # about.
    # Putting the baseline itself on the bottom edge keeps what the
    # descent was there for and costs nothing: the line no longer depends
    # on the font at all, so a badge that stepped down to fit still stands
    # exactly where its neighbours do. Only the stroke reaches below it,
    # and `edge` is what leaves it room.
    edge = BADGE_INSET + stroke_width() / 2
    stroked(painter, QPointF(box.right() - edge - width,
                             box.bottom() - edge),
            text, colour, font)


def paint_number(painter: QPainter, box: QRect, text: str, colour: str,
                 base: QFont) -> None:
    """The same number, CENTRED in a grid cell rather than in a corner.

    The two grids print their deltas as ordinary table text, which meant
    the one place in the app where a signed number had no outline round
    it — and the halo is not decoration: it is what keeps a figure legible
    against whatever is behind it, and what makes a number in a cell and a
    number on a portrait read as the same kind of thing. Same size, same
    stroke, same colour rule; only the position differs, because a cell
    has no picture to sit in the corner of.
    """
    if not text:
        return
    font = QFont(base)
    font.setPixelSize(number_px())
    font.setBold(True)
    metrics = QFontMetricsF(font)
    width = metrics.horizontalAdvance(text)
    origin = QPointF(box.center().x() - width / 2,
                     box.center().y() + (metrics.ascent()
                                         - metrics.descent()) / 2)
    stroked(painter, origin, text, colour, font)


def stroked(painter: QPainter, origin: QPointF, text: str, colour: str,
            font: QFont) -> None:
    """Text with a black halo round it, at a baseline-left origin.

    The stroke is drawn FIRST and the fill on top, because a centred
    stroke eats half its width into the glyph; painting the colour over it
    leaves the letter its full weight with the black only outside.
    """
    path = QPainterPath()
    path.addText(origin, font, text)
    painter.save()
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    painter.setBrush(Qt.BrushStyle.NoBrush)
    painter.setPen(QPen(STROKE, stroke_width(font.pixelSize()),
                        Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap,
                        Qt.PenJoinStyle.RoundJoin))
    painter.drawPath(path)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QColor(colour))
    painter.drawPath(path)
    painter.restore()


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
