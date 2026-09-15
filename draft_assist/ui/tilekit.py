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

from . import ornate, theme
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
# THE FOCUS RING IS THE WINDOW'S OWN FRAME, at the user's request:
# the same gold and the same three pixels `ornate` paints round the whole
# app. It was `theme.ACCENT` at 2px — the deep red that means "the one
# action this screen wants" everywhere else in the app, sitting on a
# portrait to mean "this is the hero everything else is measured
# against", which is not an action at all.
#
# ONE SELECTION, ONE RING, SPELLED ONCE. A pick, a suggestion and an axis
# portrait in either grid can each be the focused hero, and three
# implementations of "draw the gold box" is three chances for the ring to
# differ depending on where you clicked.
FOCUS_COLOUR = theme.FRAME_GOLD
FOCUS_WIDTH = ornate.WIDTH


def paint_focus_ring(painter: QPainter, box: QRect,
                     radius: int | None = None) -> None:
    """The gold box round the hero everything else is measured against.

    INSET BY HALF THE PEN, because a 3px pen is centred on its
    coordinate: drawn on the tile's own edge a third of it falls outside
    the widget and is clipped, so the ring reads thinner on the outside
    edges than on the inside — the even-width pen lesson from the grid
    borders, one width along.
    """
    # HALF A PEN IN, IN FLOAT. An odd pen is centred on its coordinate, so
    # a width-3 line drawn on an integer edge covers one pixel outside the
    # widget (clipped away) and half of the third one inside (drawn as a
    # blend) — the ring comes out two solid pixels and a smudge, thinner
    # than the frame it is meant to match. Centred at 1.5 it covers pixels
    # 0, 1 and 2 exactly. Same family as the even-width pen in the grid
    # borders, which paints x-1 and x rather than straddling x.
    half = FOCUS_WIDTH / 2.0
    ring = QRectF(box.x() + half, box.y() + half,
                  box.width() - FOCUS_WIDTH, box.height() - FOCUS_WIDTH)
    painter.setPen(QPen(QColor(FOCUS_COLOUR), FOCUS_WIDTH))
    painter.setBrush(Qt.BrushStyle.NoBrush)
    corner = PLATE_RADIUS if radius is None else radius
    painter.drawRoundedRect(ring, corner, corner)


# THE STAR IS THE FRAME'S GOLD TOO, and deliberately: it is the third
# thing in this app wearing that colour, beside the window's own border
# and the focus ring, and all three mean "this one" rather than "this is
# good" or "this is wrong". Green and red are spoken for — every signed
# number in the app uses them — so a star in either would read as a
# judgement about the fit beside it rather than about the hero.
STAR_POINTS = 5
# A share of the tile's SHORT side, so it is the same size on a wide
# strip tile and a narrow one, and capped so full-screening the window
# does not put a badge the size of the portrait on it.
# THE MARK'S SIZE, up 20% when the rank went inside it and 10% twice
# since. The second of those is what "make the number 10% bigger"
# actually comes to: the digit is already at the largest SHARE a heart
# can hold - going bold cost width, so that ceiling came DOWN from 0.66
# to 0.67 for one digit and 0.58 to 0.56 for two - so the only way left
# to grow the number is to grow what it sits in.
STAR_OF_TILE = 0.44
# A FLOOR THAT CAN HOLD A DIGIT. Rendered and counted: at 13px the mark's
# own outline took most of its interior and the rank came out as two
# stray dark pixels - drawn, unreadable, and worse than absent because it
# looks like dirt on the portrait.
STAR_MIN_PX = 20
STAR_MAX_PX = 32
STAR_INSET = 3
# THE RANK, drawn in the middle. BLACK AND BOLD: it was asked for not
# bold first and then bold once it was on screen at size, which is the
# right way round - a thin glyph inside a solid pink heart reads as a
# smudge, and weight is what this app uses for legibility everywhere
# else it is read at a glance.
#
# A SHARE PER SHAPE, because their interiors are not the same. Measured
# by filling each path and looking: the biggest square centred on the
# heart's middle covers 56% of its box, the shield's 68%. One number for
# both would either waste the shield or push the heart's digit through
# the taper at the bottom.
# A SHARE PER NUMBER OF DIGITS, and ONE pair for both shapes.
#
# Sized by rendering and counting the ink that escapes the outline, not
# by eye: 0.66 puts a single digit at almost exactly TWICE the area it
# had, which is what was asked for, and two digits need 0.58 to stay
# inside. Rank 1 is the one that matters and it is a single digit, so
# sizing per rank rather than globally is what buys the doubling - one
# share big enough for "20" would have left "1" at 1.55x.
#
# The HEART sets both numbers because it is the tighter shape; a shield
# could take 1.00 for a single digit. They share anyway, so that a 1 in
# a heart and a 1 in a shield are the same size - the two marks are the
# same box, and a reader comparing them should not see two conventions.
RANK_SHARE = {1: 0.67, 2: 0.56}
RANK_MIN_PX = 8
# WHERE THE MIDDLE OF EACH SHAPE ACTUALLY IS, as a share of its box, and
# neither is the box's own centre - "I want it smack bang in the middle
# of the symbol". Computed by filling the path and taking the centre of
# area: a heart is wide at the top and tapers to a point, so its mass
# sits ABOVE the middle of the rectangle drawn round it.
#
# Both previous attempts were wrong and in OPPOSITE directions, which is
# why this is measured rather than nudged: the heart was centred on the
# box (0.500, so 5% low) and the shield on a guessed 0.82-height body
# (0.410, so 7% high).
HEART_CENTRE = 0.447
SHIELD_CENTRE = 0.485


def star_box(box: QRect, left: bool = False) -> QRect:
    """Where a mark goes: a TOP corner, inset off both edges.

    The bottom-right is the number's (`paint_badge`) and the whole border
    is the focus ring's, so the two top corners are the only ones with
    nothing already in them. The HEART takes the right, which is where
    the star it replaces always sat, so nothing moves for a reader who
    already knows where to look; the SHIELD takes the left.
    """
    side = min(box.width(), box.height())
    size = max(STAR_MIN_PX, min(STAR_MAX_PX, round(side * STAR_OF_TILE)))
    x = (box.left() + STAR_INSET if left
         else box.right() - STAR_INSET - size)
    return QRect(x, box.top() + STAR_INSET, size, size)


def _stamp(painter: QPainter, path: QPainterPath, colour: str,
           weight: float) -> None:
    """Stroke in black, then fill - the app's one way of drawing a mark.

    The stroke is what stops it disappearing into the portrait behind it,
    and drawing it FIRST leaves the shape its full area with the black
    only outside, exactly as `stroked` does for a number.
    """
    painter.save()
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    painter.setPen(QPen(STROKE, max(1.0, weight), Qt.PenStyle.SolidLine,
                        Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
    painter.setBrush(Qt.BrushStyle.NoBrush)
    painter.drawPath(path)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QColor(colour))
    painter.drawPath(path)
    painter.restore()


def _shape(where: QRect, points) -> QPainterPath:
    """A path from unit coordinates, so the outlines read as drawings
    rather than as arithmetic scattered through the painter."""
    def at(u, v):
        return QPointF(where.left() + u * where.width(),
                       where.top() + v * where.height())

    path = QPainterPath()
    for kind, *coords in points:
        if kind == "m":
            path.moveTo(at(*coords[:2]))
        elif kind == "l":
            path.lineTo(at(*coords[:2]))
        else:
            path.cubicTo(at(coords[0], coords[1]), at(coords[2], coords[3]),
                         at(coords[4], coords[5]))
    path.closeSubpath()
    return path


HEART = (("m", 0.50, 0.97),
         ("c", 0.10, 0.68, 0.00, 0.42, 0.00, 0.28),
         ("c", 0.00, 0.06, 0.30, 0.00, 0.50, 0.22),
         ("c", 0.70, 0.00, 1.00, 0.06, 1.00, 0.28),
         ("c", 1.00, 0.42, 0.90, 0.68, 0.50, 0.97))

# A HAND, for the box that says how many heroes to suggest.
# "i want the qty of suggested picks to have a hand symbol to symbolize
# picking". A pointing hand is what everybody already reads as choosing
# this one, and it is the only mark here that names an ACTION rather than
# a property of a hero - which is why it is dim rather than pink or gold:
# those two are marks ON a suggestion, this is a label for a control.
HAND = (("m", 0.30, 0.06),
        ("c", 0.30, 0.00, 0.46, 0.00, 0.46, 0.06),   # the fingertip
        ("l", 0.46, 0.40),
        ("c", 0.52, 0.34, 0.62, 0.36, 0.62, 0.44),   # three folded knuckles
        ("c", 0.68, 0.38, 0.78, 0.40, 0.78, 0.48),
        ("c", 0.84, 0.44, 0.94, 0.46, 0.94, 0.56),
        ("l", 0.94, 0.74),
        ("c", 0.94, 0.92, 0.78, 1.00, 0.58, 1.00),
        ("l", 0.44, 1.00),
        ("c", 0.26, 1.00, 0.16, 0.90, 0.12, 0.76),
        ("l", 0.04, 0.52),                           # the thumb, out to the left
        ("c", 0.02, 0.44, 0.12, 0.38, 0.18, 0.46),
        ("l", 0.30, 0.62))

SHIELD = (("m", 0.50, 0.00),
          ("l", 0.96, 0.16),
          ("l", 0.96, 0.52),
          ("c", 0.96, 0.80, 0.74, 0.95, 0.50, 1.00),
          ("c", 0.26, 0.95, 0.04, 0.80, 0.04, 0.52),
          ("l", 0.04, 0.16))


def _lining_figures(font: QFont) -> None:
    """Ask for digits that are all one height and all on the baseline.

    **ALEGREYA HAS OLD-STYLE FIGURES BY DEFAULT**, which is right for
    running prose and wrong inside a 32px mark. Measured off the face:
    3 4 5 7 9 hang BELOW the baseline, 6 and 8 rise above it, and 0 1 2
    sit at x-height - so the ink is 53px tall for a "1" and 64px for a
    "5" at the same pixel size. A rank of 1 and a rank of 9 were
    therefore drawn at different sizes and at different heights inside
    the same heart, with nothing about the code saying why.
    `lnum` is the OpenType feature for lining figures and Alegreya ships
    it: every digit becomes 61-65 tall and bottoms out on the baseline.
    It also makes the digits CAP HEIGHT rather than x-height, so 1 and 2
    - the ranks that matter - grow about a sixth at no cost in weight.

    Guarded twice. `QFont.setFeature` is Qt 6.7 and this project asks
    only for PyQt6>=6.6, so an older install must get the old figures
    rather than an AttributeError out of a paint handler; and a font
    without the feature simply ignores it, which is the same outcome a
    checkout with no `assets/fonts` already has.
    """
    setter = getattr(font, "setFeature", None)
    tag = getattr(QFont, "Tag", None)
    if setter is None or tag is None:
        return
    try:
        setter(tag("lnum"), 1)
    except (TypeError, ValueError):       # a Qt that spells it differently
        pass


def _paint_rank(painter: QPainter, where: QRect, rank,
                centre: float) -> None:
    """The rank, centred on the SHAPE. Nothing when there is no rank.

    WHY A NUMBER IS IN HERE AT ALL, at the user's request: "if the shield
    has a 1 in it, that means that out of all the suggested heroes this
    particular hero is the hardest to counter." The mark used to say only
    that a hero cleared a bar; it now says WHERE IT STANDS among the
    heroes actually on screen, which is the thing a reader is choosing
    between.

    `centre` is where the shape's middle is, as a share of its box -
    never 0.5, because neither of these shapes has its mass in the middle
    of the rectangle drawn round it.

    Not stroked, unlike every other figure in this app. The halo exists
    to separate a number from whatever is behind it, and what is behind
    this one is a solid pink heart or a solid gold shield - the contrast
    is already there, and an outline at this size closes up the counters
    of an 8.
    """
    if rank is None:
        return
    text = str(rank)
    # BY HOW MANY DIGITS IT HAS. See `RANK_SHARE`.
    share = RANK_SHARE.get(len(text), RANK_SHARE[max(RANK_SHARE)])
    size = max(RANK_MIN_PX, round(where.height() * share))
    font = QFont(painter.font())
    font.setFamilies([theme.TITLE_FAMILY, theme.BODY_FAMILY])
    font.setPixelSize(size)
    # BLACK, NOT BOLD, at the user's request - "a bit girthier? thicker?
    # bolder? maybe a similar looking font that is bolder". It is the
    # SAME FAMILY one weight up: `assets/fonts/Alegreya-Black.ttf` is
    # already bundled and already registered for the app's own name in
    # the title bar, so this costs no new file and cannot look like a
    # different typeface. A synthetic weight would be Qt smearing the
    # bold face sideways, which at this size closes up the counter of an
    # 8 - the same reason this figure is not stroked.
    # Bold is set as well as the family for the checkout that has NO
    # fonts folder: a missing font is normal here, and the fallback
    # should still be as heavy as it can be.
    font.setWeight(QFont.Weight.Black)
    font.setBold(True)
    _lining_figures(font)
    painter.save()
    painter.setFont(font)
    painter.setPen(QPen(STROKE))
    # THE INK'S box, not the font's. A font's line box carries ascent and
    # descent for glyphs this string does not have, so centring on it
    # sits a digit visibly high inside a small mark.
    ink = QFontMetricsF(font).tightBoundingRect(text)
    # THE MIDDLE IN FLOAT, NEVER `QRect.center()`. That returns an
    # INTEGER and biases low - for a 200px box it answers 99, which is
    # 0.495 rather than 0.500 - so every digit sat about one per cent
    # left of the mark. Small, and visible: "it's still a little left".
    middle_x = where.left() + where.width() / 2.0
    middle_y = where.top() + where.height() * centre
    painter.drawText(
        QPointF(middle_x - ink.width() / 2.0 - ink.left(),
                middle_y + ink.height() / 2.0), text)
    painter.restore()


def paint_heart(painter: QPainter, box: QRect, rank=None) -> None:
    """A hero you play a lot and win on. TOP-RIGHT, where the star was.

    PAINTED, like every other mark here: a glyph would resize with
    whatever font the tile carries and could not be coloured apart from
    it - the reason the tick box, the window buttons and the count box's
    arrows are all drawn rather than typed.

    `rank` is where this hero stands among the suggestions on screen for
    pick rate and win rate together; 1 is the best of them.
    """
    where = star_box(box)
    _stamp(painter, _shape(where, HEART), theme.HEART_PINK,
           where.width() * 0.22)
    _paint_rank(painter, where, rank, HEART_CENTRE)


def paint_shield(painter: QPainter, box: QRect, rank=None) -> None:
    """A hero the field struggles to counter. TOP-LEFT, and GOLD.

    The frame's own gold, the fourth thing in this app wearing it beside
    the window border, the focus ring and (until now) the star - and all
    of them mean "this one" rather than "this is good". Green and red are
    spoken for by every signed number here, so a mark in either would
    read as a judgement about the figure below it.

    `rank` is where this hero stands among the suggestions on screen for
    difficulty to counter; 1 is the hardest of them to counter.
    """
    where = star_box(box, left=True)
    _stamp(painter, _shape(where, SHIELD), FOCUS_COLOUR,
           where.width() * 0.20)
    _paint_rank(painter, where, rank, SHIELD_CENTRE)


def delta_text(delta: float, kind: str | None = None) -> str:
    """"with +5.2" — the badge on any tile showing a RELATION.

    Spelled here because the ten picks and the suggestion strip both draw
    it and two spellings of one badge is one of them going stale. The
    figures are stored as fractions of a win rate and read as percentage
    points, which is the only place that conversion happens.
    """
    mark = {"with": "with", "vs": "vs"}.get(kind or "", "")
    return f"{mark} {delta * 100:+.1f}".strip()


PLATE_RADIUS = 6


def paint_plate(painter: QPainter, box: QRect, dashed: bool = False) -> None:
    """The empty plate an unfilled tile shows: a hole, not an error."""
    inner = box.adjusted(0, 0, -1, -1)
    painter.setPen(QPen(QColor(theme.BORDER), 1,
                        Qt.PenStyle.DashLine if dashed else Qt.PenStyle.SolidLine))
    painter.setBrush(QColor(theme.BG_INPUT if not dashed else theme.BG_DEEP))
    painter.drawRoundedRect(inner, PLATE_RADIUS, PLATE_RADIUS)
    painter.setBrush(Qt.BrushStyle.NoBrush)
