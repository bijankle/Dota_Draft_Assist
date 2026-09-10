"""Where one bucket sits among the others, drawn on one line.

The Analysis tab's two summary cards used to be sentences: "More likely
to win on Tuesdays: 65% from 49 games", with the block's name in dim text
off to the right. Seven of those is a paragraph, and a paragraph is the
one shape this tab has been trimmed out of everywhere else.

At the user's request each finding is now three things across one line —
the block's name on the LEFT, a short form of the fact ("Tuesday win rate
65%"), and this: the range every bucket in that block covered, with a
marker where this one sits.

**IT IS A RANGE AND A REFERENCE, AND DELIBERATELY NOT A BOX PLOT.** A box
and whisker was the shape asked about and the quartiles were turned down:
"it's just about where the data sits relative to the others, min/max
creates the bounds and it sits on that range". Which is the right call
for this data — half these blocks have four to seven buckets, where an
interquartile box is drawn from two numbers and reads as precision
nobody has.

So there are exactly three marks:

- **the track**, low to high, with a cap at each end;
- **a tick at your own usual figure**, because a marker high on the range
  says nothing about whether it is GOOD until you know where neutral
  falls — several blocks have every bucket above or below the line;
- **the marker**, green or red by the direction the finding runs, which
  is what the small arrow beside the sentence used to carry. Position and
  colour say it together now, so the arrow is gone rather than repeated.

The bounds come from `analyse.spread_for`, which uses only buckets with
enough games behind them; everything about which numbers is decided
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
MIN_TRACK = 60
LABEL_PT = 0.78             # of the body size, as the status bar is


class SpreadBar(QWidget):
    """One finding's place in its block's range."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.spread = None
        self.positive = True
        self.low_text = ""
        self.high_text = ""
        self.setSizePolicy(QSizePolicy.Policy.Expanding,
                           QSizePolicy.Policy.Fixed)
        self.setFixedHeight(2 * (CAP + 3))

    def set_spread(self, spread, positive: bool, low_text: str,
                   high_text: str, datum_text: str) -> None:
        self.spread = spread
        self.positive = positive
        self.low_text = low_text
        self.high_text = high_text
        # The bar is three marks and no words, so what each one MEANS is
        # in the tooltip rather than printed under every row.
        self.setToolTip("" if spread is None else
                        f"{low_text} to {high_text} across this analysis. "
                        f"Your usual is {datum_text}.")
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

        # YOUR USUAL FIGURE, so a marker near the top of the range can be
        # read as good or bad rather than merely high.
        datum = left + span * self.spread.at(self.spread.datum)
        painter.setPen(QPen(QColor(theme.TEXT_DIM), 1, Qt.PenStyle.DashLine))
        painter.drawLine(QPointF(datum, middle - CAP),
                         QPointF(datum, middle + CAP))

        # THE MARKER IS OUTLINED, the way every other figure in this app
        # is: the track runs under it, and a filled dot alone reads as a
        # break in the line rather than as something sitting on it.
        at = left + span * self.spread.at(self.spread.value)
        painter.setPen(QPen(QColor(theme.BG_ELEVATED), 2))
        painter.setBrush(QColor(theme.GOOD if self.positive else theme.BAD))
        painter.drawEllipse(QPointF(at, middle), DOT, DOT)
        painter.end()
