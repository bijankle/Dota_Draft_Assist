"""A section's best and worst on one track.

The History tab's summary is one line per section, and this is its right
hand end: a track with three labelled dots on it — the section's best in
green, its worst in red, and your own usual figure in grey between
them.

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

**AND YOUR OWN FIGURE IS A DOT LIKE THE OTHER TWO**, at the user's
request: "a grey dot at the middle point that just has the average
number in grey text", replacing the dashed tick that stood there. It was
the one mark on the bar that said nothing about itself — its figure lived
in the tooltip — on a card whose whole argument is that a dot at 55%
means nothing until you know whether your own rate is 45% or 65%. It is
NAMED BY THE CARD rather than by the bar (`name_the_datum`), because
every win-rate section shares one datum and eight rows saying "51%" is
the middle column's fault all over again.

**BOTH NAMES ARE ON ONE LINE, AND EACH RUNS AWAY FROM ITS OWN DOT** —
the red one ending just left of the red marker, the green one starting
just right of the green. This REPLACES two label rows, best above worst,
which is what kept them from printing over each other while the two were
centred on their marks: "I don't like that the green is not on the same
level as the red". Anchoring each label to the INSIDE edge of its own dot
does the same job without the step, because the worst is always left of
the best — so the two texts point in opposite directions and the gap
between them only ever grows.

**EXCEPT WHERE THE DOT IS ALREADY AT THE END**, which is every
contribution section: there the scale runs worst-to-best, so the markers
stand on the two ends and there is nothing outside them to run into. A
label that insisted on running outward would simply fall off the widget,
so those turn and run INWARD instead — as the user put it, "the red and
green are on either side of the min/max extremes, so it doesn't make
sense to align them as I said before". One rule covers both: a label runs
whichever way it has room, preferring outward.
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
ROWS = 1                    # one label line above the track
DOT_GAP = 5                 # between a marker and its own name


class SpreadBar(QWidget):
    """One section's best and worst, named, on a track."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.spread = None
        self.low_text = ""
        self.high_text = ""
        self.best_text = ""
        self.worst_text = ""
        self.datum_text = ""
        # NAMED ON THE FIRST ROW OF A CARD AND NOWHERE ELSE — see
        # `name_the_datum`.
        self.names_datum = False
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
        self.datum_text = datum_text
        # The tick has no words beside it, so what it MEANS is here
        # rather than printed under every row in the card.
        self.setToolTip("" if spread is None else
                        (f"Scale {low_text} to {high_text}. "
                         f"Your usual is {datum_text}."
                         + (f"\n{note}" if note else "")))
        self._resize_to_font()
        self.update()

    def name_the_datum(self, named: bool) -> None:
        """Print the grey figure beside its dot, or draw the dot alone.

        Every win-rate section on a card shares ONE datum — your own
        overall rate — and the scale is the same 0 to 100 on all of them,
        so the grey dot lands at the same x on every row and the eight of
        them read as a single line down the card. Printing "49%" against
        each is the same number eight times, which is the fault the
        middle column was removed for. So the card names it on its FIRST
        row and lets the line speak for the rest.
        """
        self.names_datum = named
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

        datum_at = left + span * self.spread.at(self.spread.datum)

        # BOTH NAMES ON ONE LINE, each anchored to its own dot and running
        # away from the other. The worst is always the left-hand mark, so
        # its name reads leftward and the best's reads rightward, and the
        # space between them can only widen.
        worst_at = left + span * self.spread.at(self.spread.worst)
        best_at = left + span * self.spread.at(self.spread.best)
        places = self._label_places(worst_at, best_at, datum_at, metrics)

        # YOUR USUAL FIGURE, kept at the user's request and now a marker
        # like the other two: "a grey dot at the middle point that just
        # has the average number in grey text". It was a dashed tick with
        # its figure only in the tooltip — the one mark on the bar that
        # said nothing about itself, on a card where the whole point is
        # that a dot at 55% means nothing until you know your own rate.
        for at, (value, text, colour) in zip(
                (worst_at, datum_at, best_at),
                ((self.spread.worst, self.worst_text, theme.BAD),
                 (self.spread.datum, self.datum_text, theme.TEXT_DIM),
                 (self.spread.best, self.best_text, theme.GOOD))):
            rect, shown, align = places.pop(0)
            if shown:
                painter.setPen(QColor(colour))
                painter.drawText(rect,
                                 int(align | Qt.AlignmentFlag.AlignVCenter),
                                 shown)
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

    def _label_places(self, worst_at: float, best_at: float,
                      datum_at: float, metrics: QFontMetrics) -> list:
        """Where each name goes: (rect, text, alignment), worst then best.

        Each name runs AWAY from its own dot — the worst leftward, the
        best rightward — which is what lets the two share one line: the
        worst mark is always left of the best, so the two texts point in
        opposite directions and cannot approach each other.

        A dot standing ON the end of its scale has nothing outside it to
        run into, and every contribution section has both (the scale IS
        worst-to-best there). So a name with no room outward TURNS and
        runs inward instead, which is the arrangement those rows had
        before and the one the user asked to keep for them.

        Only then can the two meet, and only on a narrow window — both
        turned inward, approaching along the same line. They are held
        apart at the midpoint and elided into what is left, because a
        name printed over another name is unreadable twice over.
        """
        line = metrics.height()
        worst_wide = metrics.horizontalAdvance(self.worst_text)
        best_wide = metrics.horizontalAdvance(self.best_text)

        worst_right = worst_at - DOT - DOT_GAP
        if worst_right - worst_wide < 0:                 # no room outward
            worst_right = worst_at + DOT + DOT_GAP + worst_wide
        best_left = best_at + DOT + DOT_GAP
        if best_left + best_wide > self.width():
            best_left = best_at - DOT - DOT_GAP - best_wide

        if best_left < worst_right:                      # they would meet
            middle = (worst_right + best_left) / 2
            worst_right, best_left = middle, middle

        worst_rect = QRectF(max(0.0, worst_right - worst_wide), 0,
                            min(worst_wide, worst_right), line)
        best_rect = QRectF(best_left, 0,
                           min(best_wide, self.width() - best_left), line)
        # THE GREY FIGURE GOES BETWEEN THEM, which is always free space:
        # the worst's name runs left from its dot and the best's runs
        # right from its own, so nothing either of them draws can be
        # between the two marks. It is dropped rather than elided when
        # that gap is too narrow — "4..." is not a smaller percentage,
        # it is a wrong one, and the tooltip still carries the figure.
        datum_wide = metrics.horizontalAdvance(self.datum_text)
        datum_rect = QRectF(datum_at - datum_wide / 2, 0, datum_wide, line)
        room_from = max(0.0, worst_rect.right() + LABEL_GAP)
        room_to = min(float(self.width()), best_rect.left() - LABEL_GAP)
        if datum_rect.left() < room_from:
            datum_rect.moveLeft(room_from)
        if datum_rect.right() > room_to:
            datum_rect.moveRight(room_to)
        named = (self.names_datum and self.datum_text
                 and datum_rect.left() >= room_from
                 and datum_rect.right() <= room_to)

        return [
            (worst_rect, _fit(self.worst_text, worst_rect.width(), metrics),
             Qt.AlignmentFlag.AlignRight),
            (datum_rect, self.datum_text if named else "",
             Qt.AlignmentFlag.AlignHCenter),
            (best_rect, _fit(self.best_text, best_rect.width(), metrics),
             Qt.AlignmentFlag.AlignLeft),
        ]


def _fit(text: str, room: float, metrics: QFontMetrics) -> str:
    """The text, cut with an ellipsis only if it genuinely does not fit.

    `elidedText` CUTS A STRING THAT MEASURES EXACTLY ITS OWN WIDTH — it
    lays the text out rather than summing advances, and the two answers
    differ by a fraction of a pixel — so handing it a rectangle sized
    from `horizontalAdvance` elided every label on the card: "39% Crystal
    Maid...", with three hundred empty pixels to its left. Asking the
    question ourselves first is the whole fix, and it keeps the ellipsis
    for the case it is actually for: two dots close enough together that
    their names would otherwise print over each other.
    """
    if not text or metrics.horizontalAdvance(text) <= room:
        return text
    return metrics.elidedText(text, Qt.TextElideMode.ElideRight, int(room))
