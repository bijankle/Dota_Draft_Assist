"""Win rate against a contribution figure, one dot per hero.

AT THE USER'S REQUEST: "plot it on an XY graph... the win rate is the Y
axis, where the highest win rate hero is the max value and the lowest is
the lowest, and the x axis is the lowest to highest GPM for example. And
each dot has the hero name labeled."

It answers a question the table underneath cannot. A ranking by gold per
minute says which heroes earn most; it cannot say whether earning more
went with WINNING more, because the two figures sit in different columns
and the eye has to join them up a row at a time. On a scatter that
relationship IS the shape.

ONE COLOUR FOR EVERY DOT. Colouring them by win rate would paint the Y
axis a second time - the position already says it - and burn the only
free channel on information the chart is already showing. The app's
green and red are spoken for by every signed number in it, so a dot in
either would read as a judgement rather than as a measurement.

BOTH AXES ARE SCALED TO THE DATA, not to 0-100%. This is deliberately
NOT the rule the summary bar follows, where a win rate is always drawn 0
to 100 so the distance between two marks means the same thing on every
row. That rule exists to make rows comparable; this chart is not being
compared with anything, and a correlation squashed into the middle third
of the plot is a correlation nobody can see.
"""

import math

from PyQt6.QtCore import QEvent, QPointF, QRect, QRectF, QSize, Qt
from PyQt6.QtGui import QColor, QFont, QFontMetrics, QPainter, QPen
from PyQt6.QtWidgets import QSizePolicy, QToolTip, QWidget

from . import theme, tilekit

DOT = 9                  # the marker's diameter; the skill's floor is 8
RING = 2                 # surface ring, so overlapping dots stay separable
PAD_LEFT = 52
PAD_RIGHT = 12
PAD_TOP = 14
PAD_BOTTOM = 30
HEIGHT = 260
LABEL_GAP = 5
MUTED = 0.38             # how faint a thin-sample hero is drawn


class ScatterPlot(QWidget):
    """One metric block's heroes, plotted."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.points: list = []
        # Where each dot was last drawn, so a hover can name it. Filled
        # in `paintEvent`, because that is the only place that knows the
        # widget's real size.
        self._at: list = []
        self.x_label = ""
        self.x_suffix = ""
        self.y_label = "Win rate"
        self.setSizePolicy(QSizePolicy.Policy.Expanding,
                           QSizePolicy.Policy.Fixed)
        self.setMinimumHeight(HEIGHT)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, False)

    def set_points(self, points, x_label: str, x_suffix: str = "") -> None:
        """`points` is (name, x, y, eligible, games), y as a fraction.

        `x_suffix` is stuck on the two axis ends. The counters chart plots
        a PERCENTILE across the bottom, and an end reading "97" beside a
        table saying "97%" is the same number wearing two faces.
        """
        self.points = list(points)
        self.x_label = x_label
        self.x_suffix = x_suffix
        self.setToolTip(
            "" if not self.points else
            f"{self.x_label} across the bottom, win rate up the side. "
            "One dot per hero, and the line is the trend through the "
            "heroes with enough games to count.")
        self.update()

    def sizeHint(self) -> QSize:                    # noqa: N802 - Qt naming
        return QSize(0, HEIGHT)

    # ---- the maths ------------------------------------------------------
    def bounds(self) -> tuple:
        """(x low, x high, y low, y high) over EVERY dot drawn.

        Including the faint ones. They stretch the axes - a three-game
        hero at 100% is exactly the outlier that squashes everybody else
        into a band - and that was the trade the user chose when they
        asked for them to be shown rather than dropped.
        """
        xs = [x for _, x, _, _, _ in self.points]
        ys = [y for _, _, y, _, _ in self.points]
        return (min(xs), max(xs), min(ys), max(ys))

    def trend(self) -> tuple | None:
        """Least squares through the heroes with enough games.

        THE THIN ONES ARE LEFT OUT OF THE FIT even though they are drawn.
        A bucket under `MIN_BUCKET` is one there is not enough behind to
        act on - it may not produce a finding anywhere else in this tab -
        so letting a three-game hero at 100% tilt the line would be that
        same claim made in a way nobody can see.
        """
        solid = [(x, y) for _, x, y, ok, _ in self.points if ok]
        if len(solid) < 3:
            return None
        n = len(solid)
        mean_x = sum(x for x, _ in solid) / n
        mean_y = sum(y for _, y in solid) / n
        span = sum((x - mean_x) ** 2 for x, _ in solid)
        if not span > 0:
            return None            # every hero on one figure: no slope
        slope = sum((x - mean_x) * (y - mean_y) for x, y in solid) / span
        return slope, mean_y - slope * mean_x

    def _plot_rect(self) -> QRectF:
        return QRectF(PAD_LEFT, PAD_TOP,
                      max(1, self.width() - PAD_LEFT - PAD_RIGHT),
                      max(1, self.height() - PAD_TOP - PAD_BOTTOM))

    def _inner(self, box: QRectF) -> QRectF:
        """The box the DOTS live in, inset by a marker's radius.

        The axis ends are the real minimum and maximum, so the extreme
        heroes sit exactly on them - and a dot centred on the frame is
        half outside the plot, drawn over its own border and clipped by
        the widget at the corners. Insetting where the dots go, rather
        than padding the data range, keeps "231" under the leftmost hero
        instead of under empty space a little to its left.
        """
        edge = DOT / 2 + RING
        return box.adjusted(edge, edge, -edge, -edge)

    def _place(self, box: QRectF, x: float, y: float, low_x: float,
               high_x: float, low_y: float, high_y: float) -> QPointF:
        """A figure to a pixel. A zero span centres rather than dividing
        by nothing - one hero, or several on the same figure, is a real
        state and not an error."""
        inner = self._inner(box)
        across = 0.5 if high_x <= low_x else (x - low_x) / (high_x - low_x)
        up = 0.5 if high_y <= low_y else (y - low_y) / (high_y - low_y)
        return QPointF(inner.left() + across * inner.width(),
                       inner.bottom() - up * inner.height())

    # ---- drawing --------------------------------------------------------
    def paintEvent(self, event) -> None:            # noqa: N802 - Qt naming
        if not self.points:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        box = self._plot_rect()
        low_x, high_x, low_y, high_y = self.bounds()

        self._frame(painter, box)
        self._axis_text(painter, box, low_x, high_x, low_y, high_y)
        self._trend_line(painter, box, low_x, high_x, low_y, high_y)
        self._dots(painter, box, low_x, high_x, low_y, high_y)
        painter.end()

    # ---- naming a dot that lost its label -------------------------------
    def event(self, happening):
        """EVERY DOT CAN BE NAMED, whether or not its label survived.

        Twenty heroes will not fit twenty names in a plot this tall, so
        the ones that would print over a neighbour are dropped - and a
        dot with no name is a hero the reader cannot identify at all.
        The hover gives it back, with the two figures it is plotted from
        and the sample behind them.
        """
        if happening.type() == QEvent.Type.ToolTip and self._at:
            where = happening.pos()
            near = min(self._at,
                       key=lambda dot: (dot[1].x() - where.x()) ** 2
                       + (dot[1].y() - where.y()) ** 2)
            name, at, x, y, games = near
            gap = (at.x() - where.x()) ** 2 + (at.y() - where.y()) ** 2
            if gap <= (DOT * 2) ** 2:
                QToolTip.showText(
                    happening.globalPos(),
                    f"{name}\n{_figure(x)}{self.x_suffix} {self.x_label}"
                    f"\n{y * 100:.0f}% win rate over {games} games", self)
                return True
            QToolTip.hideText()
        return super().event(happening)

    def _frame(self, painter: QPainter, box: QRectF) -> None:
        """A hairline box and three gridlines, SOLID and one shade off the
        surface. Dashes read as a threshold or a projection when they are
        only a grid."""
        painter.setPen(QPen(QColor(theme.BORDER), 1))
        painter.drawRect(box)
        for step in (0.25, 0.5, 0.75):
            y = box.bottom() - step * box.height()
            painter.drawLine(QPointF(box.left() + 1, y),
                             QPointF(box.right() - 1, y))

    def _font(self, scale: float = 0.72) -> QFont:
        font = QFont(self.font())
        # The app sets font-size in PIXELS, so `pointSizeF()` answers -1
        # and scaling it collapses the text to the floor. Same trap the
        # summary bar's end labels fell into.
        size = self.font().pixelSize()
        if size <= 0:
            size = theme.BODY_PX
        font.setPixelSize(max(9, int(size * scale)))
        return font

    def _axis_text(self, painter: QPainter, box: QRectF, low_x: float,
                   high_x: float, low_y: float, high_y: float) -> None:
        """The ends of each axis and what it measures, and nothing else.

        Not a tick every so often: this plot is 260px tall on a card that
        already carries a table of the same figures, so the axis only has
        to say which way is more and roughly how far.
        """
        font = self._font()
        painter.setFont(font)
        metrics = QFontMetrics(font)
        dim = QColor(theme.TEXT_DIM)
        painter.setPen(QPen(dim))

        for value, y in ((high_y, box.top()), (low_y, box.bottom())):
            text = f"{value * 100:.0f}%"
            painter.drawText(
                QRectF(0, y - metrics.height() / 2, PAD_LEFT - 6,
                       metrics.height()),
                int(Qt.AlignmentFlag.AlignRight
                    | Qt.AlignmentFlag.AlignVCenter), text)

        bottom = QRectF(box.left(), box.bottom() + 4, box.width(),
                        metrics.height())
        painter.drawText(bottom, int(Qt.AlignmentFlag.AlignLeft),
                         _figure(low_x) + self.x_suffix)
        painter.drawText(bottom, int(Qt.AlignmentFlag.AlignRight),
                         _figure(high_x) + self.x_suffix)
        painter.drawText(bottom, int(Qt.AlignmentFlag.AlignHCenter),
                         self.x_label)

    def _trend_line(self, painter: QPainter, box: QRectF, low_x: float,
                    high_x: float, low_y: float, high_y: float) -> None:
        fit = self.trend()
        if fit is None:
            return
        slope, intercept = fit
        # CLIPPED TO THE PLOT rather than drawn and allowed to escape: a
        # steep fit leaves the box long before the axis ends, and a line
        # running out over the labels claims win rates nobody measured.
        painter.setClipRect(box)
        painter.setPen(QPen(QColor(theme.TEXT_DIM), 2))
        start = self._place(box, low_x, slope * low_x + intercept,
                            low_x, high_x, low_y, high_y)
        end = self._place(box, high_x, slope * high_x + intercept,
                          low_x, high_x, low_y, high_y)
        painter.drawLine(start, end)
        painter.setClipping(False)

    def _dots(self, painter: QPainter, box: QRectF, low_x: float,
              high_x: float, low_y: float, high_y: float) -> None:
        font = self._font()
        painter.setFont(font)
        metrics = QFontMetrics(font)
        # MOST-PLAYED FIRST, because a label is dropped when it would
        # land on something already there - so the hero with the most
        # games behind it is the one that keeps its name.
        taken: list = []
        order = sorted(self.points, key=lambda p: -p[4])
        placed = [(name, self._place(box, x, y, low_x, high_x, low_y, high_y),
                   eligible)
                  for name, x, y, eligible, _games in order]
        self._at = [(name, self._place(box, x, y, low_x, high_x, low_y,
                                       high_y), x, y, games)
                    for name, x, y, _eligible, games in order]

        # EVERY DOT IS DRAWN FIRST, and every dot is an obstacle. Checking
        # labels against each other alone let a name print straight over
        # another hero's marker - which loses a data point and reads as
        # a smudge in the middle of a word.
        blocked = []
        for _name, at, eligible in placed:
            self._dot(painter, at, eligible)
            blocked.append(QRect(int(at.x() - DOT / 2 - RING),
                                 int(at.y() - DOT / 2 - RING),
                                 DOT + 2 * RING, DOT + 2 * RING))

        for index, (name, at, eligible) in enumerate(placed):
            rect = self._label_rect(at, name, metrics, box)
            if rect is None:
                continue
            others = blocked[:index] + blocked[index + 1:]
            if any(rect.intersects(other) for other in others):
                continue
            if any(rect.intersects(other) for other in taken):
                continue
            taken.append(rect)
            colour = theme.TEXT if eligible else theme.TEXT_DIM
            # HALOED like every other figure in this app, because the
            # label sits over a grid and possibly over the trend line.
            tilekit.stroked(
                painter,
                QPointF(rect.left(), rect.top() + metrics.ascent()),
                name, colour, font)

    def _dot(self, painter: QPainter, at: QPointF, eligible: bool) -> None:
        """A 2px ring in the SURFACE colour, not a border: two heroes on
        nearly the same figures overlap, and without it they merge into
        one larger blob that reads as a single hero."""
        painter.setPen(QPen(QColor(theme.BG_ELEVATED), RING))
        fill = QColor(theme.TEXT_STRONG)
        if not eligible:
            fill.setAlphaF(MUTED)
        painter.setBrush(fill)
        painter.drawEllipse(at, DOT / 2, DOT / 2)

    def _label_rect(self, at: QPointF, name: str, metrics: QFontMetrics,
                    box: QRectF) -> QRect | None:
        """Beside the dot, turning inward at the right-hand edge."""
        wide = metrics.horizontalAdvance(name)
        top = at.y() - metrics.height() / 2
        left = at.x() + DOT / 2 + LABEL_GAP
        if left + wide > box.right():
            left = at.x() - DOT / 2 - LABEL_GAP - wide
        if left < box.left() - PAD_LEFT:
            return None
        return QRect(int(left), int(top), int(wide), metrics.height())


def _figure(value: float) -> str:
    """An axis end, in the block's own magnitude.

    Gold per minute runs in the hundreds and denies in single figures, so
    a fixed number of decimals is wrong for one of them whichever is
    chosen. This is the same judgement `analyse.sig` makes and for the
    same reason, kept separate only because an axis end wants a round
    number rather than two significant figures.
    """
    if not math.isfinite(value):
        return ""
    if abs(value) >= 100:
        return f"{value:,.0f}"
    if abs(value) >= 10:
        return f"{value:.0f}"
    if abs(value) >= 1:
        return f"{value:.1f}"
    return f"{value:.2f}"
