"""A Warcraft-flavoured frame around the window, painted rather than shipped.

The user asked for the border from the Frozen Throne portrait frame: a
bevelled bronze band. That artwork is Blizzard's, so it is not in this
repository and never will be — the same rule the app icon follows. What
IS here is the SHAPE of it, drawn with a gradient and two lines: a warm
metal band and a dark inner lip, so the app sits in the frame rather than
on it.

**It is a HAIRLINE, and it has no studs.** The first version was ten
pixels of band with amethyst stones at the corners and the middle of each
side, and it read as jewellery round a tool. A frame's job here is to give
a frameless always-on-top window an edge against whatever is behind it;
past a few pixels it stops doing that job and starts competing with the
draft. Three tones, three pixels, no ornament.

Two constraints it has to respect and one thing it must not do:

* it is drawn UNDER everything — a border painted over the content would
  eat the resize corner and the first pixels of the tabs — so the shell
  layout is inset by `WIDTH` and this fills the inset.
* it has to survive being three pixels wide, which is the whole reason
  there is nothing in it but a gradient and two bevel lines.
* **SQUARE CORNERS.** A frameless window has square ones, so a rounded
  frame left the window's own corner poking out through the curve — four
  little grey triangles where the border should have been. The frame
  follows the window; it does not invent a shape for it.
* it must NOT reproduce Blizzard's frame.
"""

from PyQt6.QtCore import QPointF, QRectF, Qt
from PyQt6.QtGui import QColor, QLinearGradient, QPainter, QPen

from . import theme

# How thick the frame is: a quarter of what it started as. Enough for a
# gradient and a bevel line either side of it, and no more — a border, not
# a matte.
# THE NUMBER MOVED TO `theme`, and this reads it. Five things are drawn
# at it now — this frame, the ring round a clicked portrait, the box
# round a relation's figure, the hero callout and the three board
# buttons — and the last two are STYLESHEET rules, which cannot import
# from here. One number in the module everything already imports.
WIDTH = theme.FRAME_WIDTH
# Bronze, lit from the top-left the way every bevel in every game UI is.
# READ AT CALL TIME. These were `QColor` objects built at import, so
# View ▸ Greyscale left the window's own border — the most prominent
# thing on screen after the draft itself — in full gold round a grey
# app. `DARK` is the frame's shadow and has no constant of its own, so
# it is greyed here from its own brightness.
def _light() -> QColor:
    return QColor(theme.FRAME_GOLD)


def _own(colour: str) -> QColor:
    """One of this module's own shades, greyed when the app is.

    The frame is drawn from a gradient of four, and only the lightest of
    them has a constant in `theme`. The other three live here, so they
    have to follow the palette from here.
    """
    return QColor(theme.greyed_hex(colour) if theme.GREYSCALE else colour)


DARK_GOLD = "#4a3616"
MID_GOLD = "#8a6a30"
INNER_GOLD = "#1b1207"


def _dark() -> QColor:
    return _own(DARK_GOLD)
LIGHT = QColor(theme.FRAME_GOLD)   # the title text uses this too
MID = QColor(MID_GOLD)
DARK = QColor(DARK_GOLD)
# The lip between the frame and the app, so the content reads as inset.
INNER = QColor(INNER_GOLD)


def paint_frame(painter: QPainter, rect: QRectF, width: int = WIDTH) -> None:
    """Draw the band into the outer `width` pixels of `rect`."""
    painter.save()
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

    metal = QLinearGradient(rect.topLeft(), rect.bottomRight())
    light, dark = _light(), _dark()
    metal.setColorAt(0.0, light)
    mid = _own(MID_GOLD)
    metal.setColorAt(0.35, mid)
    metal.setColorAt(0.65, mid)
    metal.setColorAt(1.0, dark)

    outer = rect.adjusted(0.5, 0.5, -0.5, -0.5)
    inner = rect.adjusted(width, width, -width, -width)

    # One rectangle for the band and one for the hole, rather than four
    # mitred edges — there is no seam to get wrong at the corners. The hole
    # is FILLED with the app's own background rather than cleared: clearing
    # leaves black wherever the content does not cover it to the pixel, and
    # a black hairline round the app is exactly what a frame must not add.
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(metal)
    painter.drawRect(outer)
    painter.setBrush(QColor(theme.BG))
    painter.drawRect(inner)

    # Two lines and that is the whole illusion of a raised band: light on
    # the outside edge, dark on the inside one. At three pixels there is
    # no room for a third.
    painter.setBrush(Qt.BrushStyle.NoBrush)
    painter.setPen(QPen(_light().lighter(115), 1))
    painter.drawRect(outer)
    painter.setPen(QPen(_own(INNER_GOLD), 1))
    painter.drawRect(inner.adjusted(-0.5, -0.5, 0.5, 0.5))

    painter.restore()
