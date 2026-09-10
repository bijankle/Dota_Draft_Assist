"""Where one bucket sits among the others, drawn on one line.

The Analysis tab's two summary cards used to be sentences: "More likely
to win on Tuesdays: 65% from 49 games", with the block's name in dim text
off to the right. Seven of those is a paragraph, and a paragraph is the
one shape this tab has been trimmed out of everywhere else.

At the user's request each finding is now three things across one line —
the block's name on the LEFT, a short form of the fact ("Tuesday win rate
65%"), and this: the range every bucket in that block covered, with a
marker where this one sits.

**IT IS A DISTRIBUTION, AND DELIBERATELY NOT A BOX PLOT.** A box and
whisker was the shape asked about and the quartiles were turned down:
"it's just about where the data sits relative to the others, min/max
creates the bounds and it sits on that range". Which is the right call
for this data — half these sections have four to seven buckets, where an
interquartile box is drawn from two numbers and reads as precision
nobody has.

**AND IT SHOWS EVERY BUCKET, not only the two named ones.** The summary
is one line per section now, carrying that section's best and worst —
and best and worst are the two extremes of the very set that sets the
bar's bounds, so marking only those two puts one hard against each end
for ever. A bar whose marks cannot move carries nothing. Drawing all of
them puts the two in context: four days bunched with one outlier reads
differently from four days evenly spread, and that difference is the
whole reason a picture is here rather than two more numbers.

So the marks are:

- **the track**, low to high, with a cap at each end;
- **every eligible bucket**, a faint tick where it falls;
- **a tick at your own usual figure**, because a mark high on the range
  says nothing about whether it is GOOD until you know where neutral
  falls — whole sections sit above or below the line;
- **the best in green and the worst in red**, which is what the line's
  two named figures are.

The bounds come from `analyse.section_spread`, which uses only buckets
with enough games behind them; everything about WHICH numbers is decided
there, and this file only paints.
"""

from PyQt6.QtCore import QPointF, QRectF, Qt
from PyQt6.QtGui import QColor, QFont, QFontMetrics, QPainter, QPen
from PyQt6.QtWidgets import QSizePolicy, QWidget

from . import theme

# The end labels sit in a reserved column so that every track in a card
# starts and ends at the same x — measured against a worst case rather
# than each row's own text, or the bars would form a ragged edge down the
# page and stop being comparable at a glance, which is their whole job.
WIDEST_LABEL = "000.0"
LABEL_GAP = 6
CAP = 6                     # half-height of the end caps and the tick
DOT = 4.5                   # radius of the marker
MIN_TRACK = 70
TICK = 3                    # half-height of a plain bucket's mark
LABEL_PT = 0.78             # of the body size, as the status bar is


class SpreadBar(QWidget):
    """One finding's place in its block's range."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.spread = None
        self.low_text = ""
        self.high_text = ""
        self.setSizePolicy(QSizePolicy.Policy.Expanding,
                           QSizePolicy.Policy.Fixed)
        self.setFixedHeight(2 * (CAP + 3))

    def set_spread(self, spread, low_text: str, high_text: str,
                   datum_text: str, note: str = "") -> None:
        self.spread = spread
        self.low_text = low_text
        self.high_text = high_text
        # The bar is marks and no words, so what each one MEANS is in the
        # tooltip rather than printed under every row.
        self.setToolTip("" if spread is None else
                        (f"{len(spread.points)} buckets from {low_text} to "
                         f"{high_text}. Your usual is {datum_text}."
                         + (f"\n{note}" if note else "")))
        self.update()

    def _font(self) -> QFont:
        """The end labels, smaller than the body but sized from it.

        **IN PIXELS, because that is what this app's font is set in.**
        `theme.STYLESHEET` states `font-size` as pixels, so a widget's
        font answers `pointSizeF() == -1` and `pixelSize() == 18` — and
        scaling the point size therefore produced a 6px font, at which
        the reserved label column measured narrower than "43%" and every
        bar in the card printed a CLIPPED bound. Seven rows all reading
        "0%" was the tell, and no test could have seen it.
        """
        font = QFont(self.font())
        pixels = self.font().pixelSize()
        if pixels > 0:
            font.setPixelSize(max(9, round(pixels * LABEL_PT)))
        else:
            font.setPointSizeF(max(7.0, self.font().pointSizeF() * LABEL_PT))
        return font

    def minimumSizeHint(self):                      # noqa: N802 - Qt naming
        hint = super().minimumSizeHint()
        label = QFontMetrics(self._font()).horizontalAdvance(WIDEST_LABEL)
        hint.setWidth(2 * (label + LABEL_GAP) + MIN_TRACK)
        return hint

    def paintEvent(self, event) -> None:            # noqa: N802 - Qt naming
        if self.spread is None:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        small = self._font()
        painter.setFont(small)
        width = painter.fontMetrics().horizontalAdvance(WIDEST_LABEL)
        middle = self.height() / 2

        painter.setPen(QColor(theme.TEXT_DIM))
        painter.drawText(QRectF(0, 0, width, self.height()),
                         int(Qt.AlignmentFlag.AlignRight
                             | Qt.AlignmentFlag.AlignVCenter),
                         self.low_text)
        painter.drawText(
            QRectF(self.width() - width, 0, width, self.height()),
            int(Qt.AlignmentFlag.AlignLeft
                | Qt.AlignmentFlag.AlignVCenter), self.high_text)

        left = width + LABEL_GAP
        right = self.width() - width - LABEL_GAP
        span = max(1.0, right - left)

        painter.setPen(QPen(QColor(theme.BORDER), 1))
        painter.drawLine(QPointF(left, middle), QPointF(right, middle))
        for x in (left, right):
            painter.drawLine(QPointF(x, middle - CAP),
                             QPointF(x, middle + CAP))

        # EVERY BUCKET, faintly. Without these the two coloured marks sit
        # on the two ends by construction and the bar says nothing.
        painter.setPen(QPen(QColor(theme.TEXT_DIM), 1))
        for point in self.spread.points:
            x = left + span * self.spread.at(point)
            painter.drawLine(QPointF(x, middle - TICK),
                             QPointF(x, middle + TICK))

        # YOUR USUAL FIGURE, so a mark near the top of the range can be
        # read as good or bad rather than merely high.
        datum = left + span * self.spread.at(self.spread.datum)
        painter.setPen(QPen(QColor(theme.TEXT), 1, Qt.PenStyle.DashLine))
        painter.drawLine(QPointF(datum, middle - CAP),
                         QPointF(datum, middle + CAP))

        # THE BEST AND THE WORST, outlined the way every other figure in
        # this app is: the track runs under them, and a filled dot alone
        # reads as a break in the line rather than as something on it.
        for value, colour in ((self.spread.worst, theme.BAD),
                              (self.spread.best, theme.GOOD)):
            at = left + span * self.spread.at(value)
            painter.setPen(QPen(QColor(theme.BG_ELEVATED), 2))
            painter.setBrush(QColor(colour))
            painter.drawEllipse(QPointF(at, middle), DOT, DOT)
        painter.end()
