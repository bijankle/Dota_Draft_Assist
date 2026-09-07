"""A Warcraft-flavoured frame around the window, painted rather than shipped.

The user asked for the border from the Frozen Throne portrait frame: a
bevelled bronze band with gem studs down it. That artwork is Blizzard's,
so it is not in this repository and never will be — the same rule the app
icon follows. What IS here is the SHAPE of it, drawn with a gradient and
some ellipses: a warm metal band, a dark inner lip so the app sits in it
rather than on it, and studs at the corners and the middle of each side.

Two constraints it has to respect and one thing it must not do:

* it is drawn UNDER everything — a border painted over the content would
  eat the resize corner and the first pixels of the tabs — so the shell
  layout is inset by `WIDTH` and this fills the inset.
* it has to survive being 8 pixels wide. Detail that reads at 40px and
  turns to mush at 8 is worse than no detail, so there are three tones and
  three shapes, and that is all.
* it must NOT reproduce Blizzard's frame. A band, a bevel and round studs
  are the vocabulary of every fantasy UI ever drawn; the specific carving
  on theirs is theirs.
"""

from PyQt6.QtCore import QPointF, QRectF, Qt
from PyQt6.QtGui import QColor, QLinearGradient, QPainter, QPen

from . import theme

# How thick the frame is. Enough for a bevel and a stud, little enough
# that it is a border rather than a matte.
WIDTH = 10
# Bronze, lit from the top-left the way every bevel in every game UI is.
LIGHT = QColor("#c9a45a")
MID = QColor("#8a6a30")
DARK = QColor("#4a3616")
# The lip between the frame and the app, so the content reads as inset.
INNER = QColor("#1b1207")
# The stud. Amethyst, because the frame asked for is gold with purple
# stones in it, and a bronze band with no colour in it is a picture frame.
GEM = QColor("#a05bd6")
GEM_HOT = QColor("#e0b3ff")
STUD = 5.0


def paint_frame(painter: QPainter, rect: QRectF, width: int = WIDTH) -> None:
    """Draw the band into the outer `width` pixels of `rect`."""
    painter.save()
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

    metal = QLinearGradient(rect.topLeft(), rect.bottomRight())
    metal.setColorAt(0.0, LIGHT)
    metal.setColorAt(0.35, MID)
    metal.setColorAt(0.65, MID)
    metal.setColorAt(1.0, DARK)

    outer = rect.adjusted(0.5, 0.5, -0.5, -0.5)
    inner = rect.adjusted(width, width, -width, -width)

    # One rectangle for the band and one for the hole, rather than four
    # mitred edges — there is no seam to get wrong at the corners. The hole
    # is FILLED with the app's own background rather than cleared: clearing
    # leaves black wherever the content does not cover it to the pixel, and
    # a black hairline round the app is exactly what a frame must not add.
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(metal)
    painter.drawRoundedRect(outer, 7, 7)
    painter.setBrush(QColor(theme.BG))
    painter.drawRoundedRect(inner, 3, 3)

    # Bevel: a light line on the outside, a dark one on the inside. Two
    # lines are the whole illusion of a raised band.
    painter.setBrush(Qt.BrushStyle.NoBrush)
    painter.setPen(QPen(LIGHT.lighter(115), 1))
    painter.drawRoundedRect(outer, 7, 7)
    painter.setPen(QPen(DARK, 1))
    painter.drawRoundedRect(outer.adjusted(1, 1, -1, -1), 6, 6)
    painter.setPen(QPen(INNER, 2))
    painter.drawRoundedRect(inner.adjusted(-1, -1, 1, 1), 4, 4)

    _studs(painter, outer, width)
    painter.restore()


def _studs(painter: QPainter, outer: QRectF, width: int) -> None:
    """Four corners and the middle of each side — nine points, no more.

    A stud every N pixels turns into a dotted line at small sizes and into
    a chain at large ones; nine fixed points read the same at both.
    """
    half = width / 2.0
    xs = (outer.left() + half, outer.center().x(), outer.right() - half)
    ys = (outer.top() + half, outer.center().y(), outer.bottom() - half)
    points = [QPointF(x, y) for x in xs for y in ys
              if (x in (xs[0], xs[2])) or (y in (ys[0], ys[2]))]
    radius = min(STUD, width * 0.42)
    for point in points:
        seat = QRectF(point.x() - radius - 1, point.y() - radius - 1,
                      (radius + 1) * 2, (radius + 1) * 2)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(DARK)
        painter.drawEllipse(seat)
        painter.setBrush(GEM)
        painter.drawEllipse(QRectF(point.x() - radius, point.y() - radius,
                                   radius * 2, radius * 2))
        # One highlight, up and left, so the stones catch the same light
        # the bevel does.
        painter.setBrush(GEM_HOT)
        spark = radius * 0.34
        painter.drawEllipse(QRectF(point.x() - radius * 0.45 - spark / 2,
                                   point.y() - radius * 0.45 - spark / 2,
                                   spark, spark))
