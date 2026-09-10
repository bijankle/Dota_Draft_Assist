"""A section's best and worst on one track.

The Analysis tab's summary is one line per section, and this is its right
hand end: a track with two labelled dots on it — the section's best in
green, its worst in red — and a single tick where your own usual figure
falls between them.

**A WIN RATE IS DRAWN 0 TO 100%**, at the user's request, rather than to
its own section's range. Scaled to itself, every section looked equally
spread: Radiant 55% against Dire 44% filled the same track as a hero list
running 25% to 61%, so the picture said nothing about how much was
actually at stake. On a fixed scale the DISTANCE between the two dots IS
the size of the effect, and it means the same thing on every row and in
every run. Contribution sections keep their own range, because there is
no 100 to scale damage per minute or a KDA against — see
`analyse.section_spread`, which decides every number here.

**THE NAME SITS ABOVE ITS OWN DOT**, also at the user's request and
sketched by hand: "25% Mirana" over the red one, "61% Rubick" over the
green. The figures used to be printed again in a column of their own and
that column is GONE — with the label on the mark it belongs to, a middle
column repeating both said everything twice on one line.

**AND EVERY OTHER BUCKET IS NO LONGER DRAWN** — "get rid of all those
small dashes in between, no one knows what they mean". They were there
for a real reason under the old scale: best and worst were the extremes
of the very set that SET the bounds, so those two dots sat on the two
ends for ever and only the ticks between them carried any information.
A fixed scale removes that problem at the root — the dots move because
the scale no longer moves with them — so the ticks stop paying for
themselves and go.

Two label rows, always, with the best above the worst. A section whose
two figures are close — Radiant 55% against Dire 44% is a third of an
inch apart on this scale — would otherwise print one name across the
other, and a row that is sometimes one line high and sometimes two makes
the bars beside them stop lining up.
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
DOT = 4.5                   # radius of a marker
MIN_TRACK = 90
SMALL = 0.78                # of the body size, as the status bar is
ROWS = 2                    # label lines above the track


class SpreadBar(QWidget):
    """One section's best and worst, named, on a track."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.spread = None
        self.low_text = ""
        self.high_text = ""
        self.best_text = ""
        self.worst_text = ""
        self.setSizePolicy(QSizePolicy.Policy.Expanding,
                           QSizePolicy.Policy.Fixed)
        self._resize_to_font()

    # ---- what to draw --------------------------------------------------
    def set_spread(self, spread, low_text: str, high_text: str,
                   datum_text: str, best_text: str = "",
                   worst_text: str = "", note: str = "") -> None:
        self.spread = spread
        self.low_text = low_text
        self.high_text = high_text
        self.best_text = best_text
        self.worst_text = worst_text
        # The tick has no words beside it, so what it MEANS is here
        # rather than printed under every row in the card.
        self.setToolTip("" if spread is None else
                        (f"Scale {low_text} to {high_text}. "
                         f"Your usual is {datum_text}."
                         + (f"\n{note}" if note else "")))
        self._resize_to_font()
        self.update()

    # ---- sizing --------------------------------------------------------
    def _font(self) -> QFont:
        """The labels, smaller than the body but sized from it.

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
            font.setPixelSize(max(9, round(pixels * SMALL)))
        else:
            font.setPointSizeF(max(7.0, self.font().pointSizeF() * SMALL))
        return font

    def _resize_to_font(self) -> None:
        line = QFontMetrics(self._font()).height()
        self.setFixedHeight(ROWS * line + 2 * (CAP + 2))

    def changeEvent(self, event) -> None:           # noqa: N802 - Qt naming
        super().changeEvent(event)
        self._resize_to_font()

    def minimumSizeHint(self):                      # noqa: N802 - Qt naming
        hint = super().minimumSizeHint()
        label = QFontMetrics(self._font()).horizontalAdvance(WIDEST_LABEL)
        hint.setWidth(2 * (label + LABEL_GAP) + MIN_TRACK)
        return hint

    # ---- drawing -------------------------------------------------------
    def paintEvent(self, event) -> None:            # noqa: N802 - Qt naming
        if self.spread is None:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        small = self._font()
        painter.setFont(small)
        metrics = painter.fontMetrics()
        width = metrics.horizontalAdvance(WIDEST_LABEL)
        line = metrics.height()
        middle = ROWS * line + CAP + 1

        # A BOUND IS NEVER PRINTED TWICE. On a contribution section the
        # scale runs from the worst bucket to the best, so the two dots
        # sit exactly on the ends — and the end labels then repeat what
        # the dots' own names already say, one line below them. A win
        # rate's ends are 0% and 100%, which no dot is ever on, so there
        # they stay.
        painter.setPen(QColor(theme.TEXT_DIM))
        if not self._dot_is_on_the_end():
            painter.drawText(QRectF(0, middle - CAP - 2, width, 2 * CAP + 4),
                             int(Qt.AlignmentFlag.AlignRight
                                 | Qt.AlignmentFlag.AlignVCenter),
                             self.low_text)
            painter.drawText(
                QRectF(self.width() - width, middle - CAP - 2, width,
                       2 * CAP + 4),
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

        # YOUR USUAL FIGURE. One tick, kept at the user's request — a dot
        # at 55% says nothing about whether it is good until you know
        # whether your own rate is 45% or 65%.
        datum = left + span * self.spread.at(self.spread.datum)
        painter.setPen(QPen(QColor(theme.TEXT), 1, Qt.PenStyle.DashLine))
        painter.drawLine(QPointF(datum, middle - CAP),
                         QPointF(datum, middle + CAP))

        # THE BEST ON THE UPPER LINE, THE WORST ON THE LOWER, always, so
        # two close figures cannot print over each other and every row in
        # the card is the same height.
        for row, (value, text, colour) in enumerate((
                (self.spread.best, self.best_text, theme.GOOD),
                (self.spread.worst, self.worst_text, theme.BAD))):
            at = left + span * self.spread.at(value)
            if text:
                painter.setPen(QColor(colour))
                painter.drawText(self._label_rect(at, row, text, metrics),
                                 int(Qt.AlignmentFlag.AlignLeft
                                     | Qt.AlignmentFlag.AlignVCenter), text)
            # OUTLINED, the way every other figure in this app is: the
            # track runs under it, and a filled dot alone reads as a
            # break in the line rather than as something sitting on it.
            painter.setPen(QPen(QColor(theme.BG_ELEVATED), 2))
            painter.setBrush(QColor(colour))
            painter.drawEllipse(QPointF(at, middle), DOT, DOT)
        painter.end()

    def _dot_is_on_the_end(self) -> bool:
        """Do the two markers already stand on the scale's own bounds?"""
        spread = self.spread
        return (spread is not None
                and spread.worst == spread.low and spread.best == spread.high)

    def _label_rect(self, at: float, row: int, text: str,
                    metrics: QFontMetrics) -> QRectF:
        """A label centred over its dot, and never off the widget.

        A dot at either end would otherwise hang its name past the edge,
        where Qt clips it — and a name clipped to "irana" is worse than
        one nudged a few pixels off centre.
        """
        wide = metrics.horizontalAdvance(text)
        line = metrics.height()
        x = min(max(0.0, at - wide / 2), max(0.0, self.width() - wide))
        return QRectF(x, row * line, wide, line)
