"""THE SAME DRAFT AS TEXT: a page of tables instead of a page of faces.

At the user's request, and the shape is theirs: "you know in SharePoint
how you can change the view to be like a grid view or a road view... I
kind of want something like that where I can toggle between view types
for this app... it will change to like a spreadsheet view where it's
just like simple data tables - it's got what's been drafted, what the
recommended hero selection is, what the synergies are, basically just
useful summary tables, and hero names are in text instead of any
portraits or anything like that. We'll call it a simplified view and I
want this to be off by default."

So this is not a second app and it must not become one. The rich Draft
tab is five sizes of portrait, two painted grids, three strips of tiles
and a callout; every one of those is there because a draft is read at a
glance over a running game. A TABLE is read the other way round - a
column at a time, by somebody who wants the figure rather than the
impression - and there are machines and moments where that is the
better answer: a small window, a screen share, a remote session with no
artwork downloaded, or simply wanting to read the numbers.

**EVERY FIGURE HERE IS THE ONE THE OTHER VIEW DRAWS, read from the same
object.** That is the whole discipline of this module. A delta goes
through `tilekit.delta_text`, the same function that writes the badge on
a pick; the pair figures come out of the very `SynergyGrid` the painted
triangles are drawn from; the counters table is the `Matrix` the painted
grid is handed; the board's values are `net_contributions`, which is
what rests on the ten tiles. Two surfaces that compute the same number
twice are two surfaces that will one day disagree about it, and the one
nobody is looking at is the one that goes wrong.

**NOTHING IN HERE IS CLICKABLE, and that is the same rule the suggestion
strip follows.** A pick is entered by clicking a slot on the board; a
second way to do it that behaved differently would be worse than no way.
The cells ARE selectable, because a table somebody cannot copy out of is
a picture of a table.

**AND NO TABLE EVER SCROLLS INSIDE ITSELF** (`TextTable._fit_height`).
It is `tables.MatrixTable`'s rule for the same reason: a table sized to
its rows has nothing of its own to scroll, so a scrollbar on one can
only mean the fit was wrong - and it hides part of the answer while
making the widget look correct. The page scrolls; the tables do not, and
they ignore the wheel outright so that scrolling PAST one does not catch
in it, which is the fault `BucketTable` on the History tab exists to
prevent.
"""

from dataclasses import dataclass

from PyQt6.QtCore import QPointF, QRectF, QSize, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QFont, QFontMetrics, QPainter, QPainterPath, QPen
from PyQt6.QtWidgets import (QAbstractItemView, QFrame, QGridLayout,
                             QHBoxLayout, QHeaderView, QLabel, QSizePolicy,
                             QTableWidget, QTableWidgetItem, QVBoxLayout,
                             QWidget)

from ..model import items as items_mod
from ..model import roles as roles_mod
from . import theme, tilekit
from .chrome import card

# ---- the one place this view's typography is set -------------------
#
# **THE REST OF THE APP IS A SERIF, BOLD, AT 18px, AND THIS IS NOT**, at
# the user's request: "I wanted it to be purely for you to pick fonts -
# very standardized, or ones that are notoriously easy to read and easy
# on the eyes. Same with the size of the font. I want this to be
# designed for readability and simplicity... purely the new view".
#
# The app's own face is Alegreya at `theme.BODY_PX`, bold everywhere,
# and that is RIGHT where it is: the board is read in the corner of the
# eye over a running game, where weight is legibility and a serif at 18
# is a glance. A table is the other kind of reading - a column at a
# time, by somebody who came for the figure - and this view already has
# the app's own precedent for the exception: `QLabel[prose="true"]`, the
# user manual, "THE ONE PLACE THIS APP IS NOT BOLD", because "a page of
# 18px bold is a wall whatever it says".
#
# **THE FACE IS THE PLATFORM'S OWN, AND NOTHING IS COMMITTED FOR IT.**
# "Standardized" and "notoriously easy to read" is Segoe UI on the
# machine this app runs on - Microsoft's own UI face, drawn for screen
# text at exactly these sizes and tested harder than anything that could
# be bundled here. Everything after it is a fallback so a checkout on
# another machine still gets a real sans rather than dropping back to
# the app's serif: Inter where somebody has it, then the two faces that
# ship with every Linux desktop (which is what the test machines render
# in), then Arial, then whatever the system calls its UI font.
# Committing a face was the alternative and is not needed: this app's
# own bar is that a committed font must state its own licence in its
# name table, and there is no file to clear it for.
SANS = ('"Segoe UI", "Inter", "Noto Sans", "DejaVu Sans", '
        '"Liberation Sans", "Helvetica Neue", Arial, system-ui, sans-serif')

# **SMALLER THAN THE APP AND IT READS LARGER.** A humanist sans has a
# much bigger x-height than Alegreya, so 15px here sets about the size
# 18px does there - and the rows it saves are rows of the answer. The
# header is smaller again and the only thing on the page carrying any
# weight, because in a table the heading's job is to be found rather
# than read.
CELL_PX = 15
HEAD_PX = 13
TITLE_PX = 17
# **THE BIGGEST SINGLE READABILITY WIN IS NOT THE FACE, IT IS THE
# LEADING.** The app-wide rule pads a cell by `2px 4px`, which is right
# for a 5x5 of deltas read as a block and far too tight for a row read
# across. Six and ten is a line of text with room to be a line of text.

# **BUILT AT CALL TIME, BECAUSE IT CARRIES COLOURS NOW.** The first cut
# of this sheet named no colour at all, on the argument that
# `theme.set_greyscale` rebuilds the APPLICATION stylesheet and nothing
# sweeps a widget's own - which is still true. The slots and the chips
# need a ground and an edge, so instead of a constant this is a
# function that reads `theme` when it is asked, and `SimpleView.
# restyle` asks again whenever the page is redrawn (greyscale redraws
# it). The string is compared before it is set, since re-polishing a
# hundred widgets per pick for nothing is the smooth-scaled hidden
# widget in a new coat.
def stylesheet() -> str:
    return f"""
QWidget {{ font-family: {SANS}; font-size: {CELL_PX}px; font-weight: 400; }}
QLabel[heading="true"] {{ font-size: {TITLE_PX}px; font-weight: 600; }}
QLabel[dim="true"] {{ font-size: {HEAD_PX}px; font-weight: 400; }}
QLabel[strip="true"] {{ font-size: 14px; }}
QLabel[striphead="true"] {{ font-size: {HEAD_PX}px; font-weight: 600; color: {theme.TEXT_DIM}; }}
QLabel[totals="true"] {{ font-size: {CELL_PX}px; font-weight: 600; }}
QTableWidget {{ font-size: 14px; font-weight: 400; }}
QTableWidget::item {{ padding: 3px 4px; }}
QHeaderView::section {{
    font-size: 12px; font-weight: 600; padding: 3px 3px;
}}
QFrame[fold="true"] {{ background: {theme.BG_ELEVATED}; border-radius: 6px; }}
QPushButton[plain="true"] {{ font-family: {SANS}; font-size: 14px; font-weight: 600; }}
"""

# THE HEIGHT A CELL PADS TO, which is also what one chip row costs. One
# number rather than two measurements that have to agree.
CELL_PAD = "4px 8px"

# What an empty slot prints. An EM DASH rather than a blank cell, for the
# same reason the board draws a dashed plate rather than nothing: the
# shape of the answer standing where the answer will appear, so the table
# does not change height as the draft fills in.
NOTHING = "—"


@dataclass
class Cell:
    """One cell: its text, and how to draw it.

    `colour` is a theme name resolved AT PAINT TIME, never a captured
    hex - `theme.set_greyscale` reassigns every colour in that module, so
    a value read at import would leave this page in colour on a grey app.
    """
    text: str
    colour: str | None = None       # an attribute name on `theme`
    align: str = "left"             # "left" | "right" | "centre"
    tip: str = ""
    numeric: bool = False           # lining figures, so columns line up

    ALIGN = {"left": Qt.AlignmentFlag.AlignLeft,
             "right": Qt.AlignmentFlag.AlignRight,
             "centre": Qt.AlignmentFlag.AlignHCenter}


@dataclass
class Pair:
    """One pair for the synergy square: two names and the figure."""
    a: str
    b: str
    v: float


def _delta(value: float | None) -> Cell:
    """A signed figure, in the app's own two colours.

    `tilekit.delta_text` is the ONE place a stored fraction becomes
    percentage points, so this cannot drift from the badge on a tile.
    Green good, red bad, read from your own side - exactly like every
    other signed number in the app.

    NO SIGN IS APPLIED HERE. Every caller is handed a figure already
    read from the user's own side (`net_contributions`, `matchup_matrix`)
    or deliberately not (`team_synergy_grid`'s enemy triangle, which the
    painted card does not flip either), so a convention in this function
    would be a second answer to a question the model has already
    settled.
    """
    if value is None:
        return Cell(NOTHING, "TEXT_DIM", "right", numeric=True)
    name = ("GOOD" if value > 0 else "BAD" if value < 0 else "TEXT_DIM")
    return Cell(tilekit.delta_text(value), name, "right", numeric=True)


class FitHeader(QHeaderView):
    """A column heading that FITS its name rather than cutting it.

    Five hero names across half a card is the one place on this page
    where a word is wider than the room it has, and Qt's header gives
    two bad answers: elided, "Shadow Fiend" heads its column as
    "Sha..."; unelided, "Clockwerk" runs under the next column. Both
    name nobody. So the label is painted here - the background the way
    the stylesheet draws it, then the words broken onto two lines at a
    space, and a word that still does not fit set a size smaller until
    it does, down to `SMALLEST`. Eliding is the last resort, kept for a
    name that will not fit at any size this is prepared to use.
    """

    SMALLEST = 9

    def __init__(self, parent=None):
        super().__init__(Qt.Orientation.Horizontal, parent)
        self.setHighlightSections(False)
        self.setSectionsClickable(False)
        self.setDefaultAlignment(Qt.AlignmentFlag.AlignCenter)

    def sizeHint(self) -> QSize:                    # noqa: N802 - Qt naming
        hint = super().sizeHint()
        metrics = QFontMetrics(self.font())
        return QSize(hint.width(), 2 * metrics.lineSpacing() + 8)

    def paintSection(self, painter, rect, index):   # noqa: N802 - Qt naming
        model = self.model()
        text = ""
        if model is not None:
            text = str(model.headerData(index, self.orientation()) or "")
        painter.save()
        painter.fillRect(rect, QColor(theme.BG_ELEVATED))
        painter.setPen(QColor(theme.BORDER))
        painter.drawLine(rect.bottomLeft(), rect.bottomRight())
        inner = rect.adjusted(3, 2, -3, -2)
        font = QFont(self.font())
        align = (Qt.AlignmentFlag.AlignLeft if index == 0
                 else Qt.AlignmentFlag.AlignHCenter) | Qt.AlignmentFlag.AlignVCenter
        flags = int(align) | int(Qt.TextFlag.TextWordWrap)
        size = font.pixelSize() or 12
        while True:
            font.setPixelSize(size)
            metrics = QFontMetrics(font)
            needed = metrics.boundingRect(inner, flags, text)
            widest = max((metrics.horizontalAdvance(w) for w in text.split()),
                         default=0)
            if (widest <= inner.width() and needed.height() <= inner.height()) \
                    or size <= self.SMALLEST:
                break
            size -= 1
        painter.setFont(font)
        painter.setPen(QColor(theme.TEXT_DIM))
        if widest > inner.width():
            text = metrics.elidedText(text, Qt.TextElideMode.ElideRight,
                                      inner.width())
        painter.drawText(inner, flags, text)
        painter.restore()


class TextTable(QTableWidget):
    """A read-only data table that is exactly as tall as its rows."""

    def __init__(self, parent=None):
        super().__init__(0, 0, parent)
        # QT SORTS BY TEXT, so "10" lands before "9" and "+6.4%" before
        # "+62.1%" - and every column here is a number wearing a sign or
        # a suffix. The History tab re-renders rather than calling
        # `sortItems` for that reason; here the order is the one the app
        # already decided, so sorting is simply OFF.
        self.setSortingEnabled(False)
        self.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        # SELECTABLE, because a table nobody can copy out of is a picture
        # of a table - and the one thing somebody pasting a draft into a
        # message wants is the text.
        self.setSelectionMode(
            QAbstractItemView.SelectionMode.ContiguousSelection)
        self.setSelectionBehavior(
            QAbstractItemView.SelectionBehavior.SelectItems)
        self.verticalHeader().setVisible(False)
        self.setAlternatingRowColors(True)
        self.setWordWrap(False)
        self.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        # A HEADING THAT FITS ITS WORDS (`FitHeader`), and that cannot be
        # clicked, since clicking one would otherwise look like it sorts
        # and this table does not sort.
        self.setHorizontalHeader(FitHeader(self))

    def wheelEvent(self, event) -> None:            # noqa: N802 - Qt naming
        """The PAGE scrolls; this does not.

        A control that answers the wheel while the reader is scrolling
        past it is the History tab's own fault one card over, and here it
        can only ever be wrong: the table is sized to hold every row it
        has, so there is nothing inside it to scroll to.
        """
        event.ignore()

    def show_rows(self, headers: list[str], rows: list[list],
                  stretch: tuple[int, ...] = ()) -> None:
        """Replace the whole table. `stretch` names the columns that
        absorb the card's spare width; the rest are cut to their
        contents."""
        # THE FONT COMES FROM THE STYLESHEET, so it is not this
        # widget's font until Qt has polished it - and `_fit_height`
        # below and the numeric cells' `QFont(self.font())` both
        # measure against it. The History tab paid for this twice.
        self.ensurePolished()
        self.clearContents()
        self.setColumnCount(len(headers))
        self.setHorizontalHeaderLabels(headers)
        self.setRowCount(len(rows))
        # A HEADING IS ALIGNED LIKE THE COLUMN UNDER IT. Qt centres
        # header text whatever the cells do, so "Hero" sat in the middle
        # of a stretched column with every name hard against its left
        # edge - which reads as two columns rather than one. The first
        # row's cell decides it, since a column is one kind of thing all
        # the way down.
        for r, line in enumerate(rows):
            for c, value in enumerate(line):
                cell = value if isinstance(value, Cell) else Cell(str(value))
                item = QTableWidgetItem(cell.text)
                item.setFlags(Qt.ItemFlag.ItemIsEnabled
                              | Qt.ItemFlag.ItemIsSelectable)
                item.setTextAlignment(Cell.ALIGN[cell.align]
                                      | Qt.AlignmentFlag.AlignVCenter)
                if cell.colour:
                    item.setForeground(QColor(getattr(theme, cell.colour)))
                if cell.tip:
                    item.setToolTip(cell.tip)
                if cell.numeric:
                    # LINING AND TABULAR. Lining because Alegreya's
                    # figures hang below the baseline and sit at
                    # x-height, so a column of them is ragged wherever
                    # that face is still reached; tabular because a
                    # COLUMN of figures wants every digit the same width
                    # or the decimal points wander down the page. Both
                    # are no-ops on a face without them, which is the
                    # same outcome a checkout with no fonts has.
                    font = QFont(self.font())
                    tilekit.lining_figures(font, tabular=True)
                    item.setFont(font)
                self.setItem(r, c, item)
        for c in range(len(headers)):
            item = self.horizontalHeaderItem(c)
            under = rows[0][c] if rows else None
            how = under.align if isinstance(under, Cell) else "left"
            if item is not None:
                item.setTextAlignment(Cell.ALIGN[how]
                                      | Qt.AlignmentFlag.AlignVCenter)
        head = self.horizontalHeader()
        for c in range(len(headers)):
            head.setSectionResizeMode(
                c, QHeaderView.ResizeMode.Stretch if c in stretch
                else QHeaderView.ResizeMode.ResizeToContents)
        self._fit_height()

    def showEvent(self, event) -> None:             # noqa: N802 - Qt naming
        """Re-fit once the header knows its own height.

        A header that has not been shown yet reports a stale height, so a
        fit taken while the rows were being filled is a few pixels short
        - which with both scrollbars off is invisible except as a page
        that will not quite settle. Same fix as `BucketTable`.
        """
        super().showEvent(event)
        self._fit_height()

    def _fit_height(self) -> None:
        head = self.horizontalHeader()
        header_h = max(head.height(), head.sizeHint().height())
        rows = self.verticalHeader().length()
        self.setFixedHeight(header_h + rows + 2 * self.frameWidth() + 2)


def _dim(text: str = "") -> QLabel:
    label = QLabel(text)
    label.setProperty("dim", True)
    return label




# ---- the pieces layout A is made of ----------------------------------
#
# **BANDS, NOT COLUMNS**, chosen by the user from five previews: "go with
# A, show as many as fit is fine". The window is wider than it is tall,
# so everything runs across it - the board as two rows of five, the
# roles as one strip of eight, the suggested heroes as a grid of chips,
# the items as a row, and the two matrices side by side at the bottom.
# Nothing scrolls: the one block that can grow without bound, the hero
# chips, is cut to the rows the page has left after everything else has
# been placed (`SimpleView._refit`).

# How a chip and a slot are drawn. Painted rather than laid out from
# QLabels, because a name that does not fit has to ELIDE and a QLabel
# will not - it clips mid-glyph or pushes the figure off the end.
CHIP_H = 26
CHIP_PAD = 7
CHIP_GAP = 4
CHIP_MIN_W = 168        # what "Nature's Prophet  +1.6" needs at 13px
SLOT_H = 32
RADIUS = 4


def _text_pen(name: str) -> QColor:
    return QColor(getattr(theme, name))


class Chevron(QWidget):
    """The fold mark on a card heading: down when open, right when
    closed. Painted, because a glyph resizes with whatever font the
    heading carries and cannot be coloured apart from it."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.closed = False
        self.setFixedSize(12, 12)

    def paintEvent(self, event) -> None:            # noqa: N802 - Qt naming
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(_text_pen("TEXT_DIM"))
        path = QPainterPath()
        if self.closed:
            path.moveTo(3, 1); path.lineTo(10, 6); path.lineTo(3, 11)
        else:
            path.moveTo(1, 3); path.lineTo(11, 3); path.lineTo(6, 10)
        path.closeSubpath()
        painter.drawPath(path)


class Fold(QFrame):
    """A card whose heading folds its body away - and says so.

    At the user's request: "i wanna be able to show / hide the different
    tables (collapsible) and you remember the last state". The heading
    stays whatever happens, so a folded card is one line naming what is
    behind it rather than a gap where a card was. `toggled` carries the
    card's KEY and whether it is now closed, and the window writes that
    to the settings file; `set_closed` restores it with no signal, since
    setting a control to what the file already says is not the user
    pressing it.
    """

    toggled = pyqtSignal(str, bool)

    def __init__(self, key: str, title: str, parent=None):
        super().__init__(parent)
        self.key = key
        self.setProperty("fold", True)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(8, 5, 8, 7)
        lay.setSpacing(4)
        self.head = QWidget()
        self.head.setProperty("bare", True)
        self.head.setCursor(Qt.CursorShape.PointingHandCursor)
        row = QHBoxLayout(self.head)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(8)
        self.chevron = Chevron()
        self.title = QLabel(title)
        self.title.setProperty("heading", True)
        self.sub = _dim()
        row.addWidget(self.chevron, 0, Qt.AlignmentFlag.AlignVCenter)
        row.addWidget(self.title)
        row.addWidget(self.sub)
        row.addStretch(1)
        self.body = QWidget()
        self.body.setProperty("bare", True)
        self.body_lay = QVBoxLayout(self.body)
        self.body_lay.setContentsMargins(0, 0, 0, 0)
        self.body_lay.setSpacing(4)
        lay.addWidget(self.head)
        lay.addWidget(self.body)
        self.head.mousePressEvent = self._pressed      # type: ignore[method-assign]

    def _pressed(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self.set_closed(not self.closed)
            self.toggled.emit(self.key, self.closed)

    @property
    def closed(self) -> bool:
        return self.body.isHidden()

    def set_closed(self, closed: bool) -> None:
        self.body.setVisible(not closed)
        self.chevron.closed = closed
        self.chevron.update()

    def set_sub(self, text: str) -> None:
        self.sub.setText(text)
        self.sub.setVisible(bool(text))


class Chip(QWidget):
    """One line of text with a figure at its right end, in a plate.

    Used for a pick slot, a suggested hero and an item alike, so the
    three strips of the picture view are three rows of one object here
    too. `rank` is drawn small and dim ahead of the name; `tail` is a
    dim suffix after it (the heroes an item is for); the whole left
    side ELIDES as one string so the figure never moves.
    """

    def __init__(self, height: int = CHIP_H, parent=None):
        super().__init__(parent)
        self.rank = ""
        self.name = ""
        self.tail = ""
        self.figure = ""
        self.colour = "TEXT"
        self.strong = False
        self.open = False
        self.setFixedHeight(height)
        self.setSizePolicy(QSizePolicy.Policy.Expanding,
                           QSizePolicy.Policy.Fixed)

    def set(self, name: str, figure: str = "", colour: str = "TEXT",
            rank: str = "", tail: str = "", strong: bool = False,
            open_slot: bool = False, tip: str = "") -> None:
        self.rank, self.name, self.tail = rank, name, tail
        self.figure, self.colour, self.strong = figure, colour, strong
        self.open = open_slot
        self.setToolTip(tip or name)
        self.update()

    def paintEvent(self, event) -> None:            # noqa: N802 - Qt naming
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        box = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        if self.open:
            pen = QPen(QColor(theme.BORDER), 1, Qt.PenStyle.DashLine)
            painter.setPen(pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
        else:
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(theme.BG_INPUT))
        painter.drawRoundedRect(box, RADIUS, RADIUS)
        font = QFont(self.font())
        font.setPixelSize(13 if self.height() <= CHIP_H else 14)
        painter.setFont(font)
        metrics = QFontMetrics(font)
        x = CHIP_PAD
        right = self.width() - CHIP_PAD
        mid = self.height() / 2.0 + (metrics.ascent() - metrics.descent()) / 2.0
        # THE FIGURE FIRST, from the right, so the name knows how much
        # room it has.
        if self.figure:
            number = QFont(font)
            tilekit.lining_figures(number, tabular=True)
            painter.setFont(number)
            w = QFontMetrics(number).horizontalAdvance(self.figure)
            painter.setPen(_text_pen(self.colour))
            painter.drawText(QPointF(right - w, mid), self.figure)
            right -= w + 8
            painter.setFont(font)
        if self.rank:
            small = QFont(font)
            small.setPixelSize(11)
            painter.setFont(small)
            painter.setPen(_text_pen("TEXT_DIM"))
            painter.drawText(QPointF(x, mid), self.rank)
            x += QFontMetrics(small).horizontalAdvance(self.rank) + 5
            painter.setFont(font)
        room = max(0, int(right - x))
        if self.strong:
            font.setWeight(QFont.Weight.DemiBold)
            painter.setFont(font)
            metrics = QFontMetrics(font)
        name = metrics.elidedText(self.name, Qt.TextElideMode.ElideRight, room)
        painter.setPen(_text_pen("TEXT_DIM" if self.open else
                                 ("FRAME_GOLD" if self.strong else "TEXT")))
        painter.drawText(QPointF(x, mid), name)
        used = metrics.horizontalAdvance(name)
        if self.tail and name == self.name and room - used > 24:
            painter.setPen(_text_pen("TEXT_DIM"))
            tail = metrics.elidedText(self.tail, Qt.TextElideMode.ElideRight,
                                      room - used - 6)
            painter.drawText(QPointF(x + used + 6, mid), tail)


class ChipGrid(QWidget):
    """Chips in as many columns as the width allows, in the rows asked
    for. `set_rows` is how the page tells it how much height is left."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setProperty("bare", True)
        self.grid = QGridLayout(self)
        self.grid.setContentsMargins(0, 0, 0, 0)
        self.grid.setSpacing(CHIP_GAP)
        self.entries: list[tuple] = []
        self.rows = 1
        self.cols = 5
        self.chips: list[Chip] = []
        self.setSizePolicy(QSizePolicy.Policy.Expanding,
                           QSizePolicy.Policy.Fixed)

    def set_entries(self, entries: list[tuple]) -> None:
        """Each entry is the arguments to `Chip.set`, as a dict."""
        self.entries = entries
        self._rebuild()

    def columns_for(self, width: int) -> int:
        return max(2, (width + CHIP_GAP) // (CHIP_MIN_W + CHIP_GAP))

    def set_shape(self, rows: int, cols: int) -> bool:
        rows, cols = max(1, rows), max(2, cols)
        if (rows, cols) == (self.rows, self.cols):
            return False
        self.rows, self.cols = rows, cols
        self._rebuild()
        return True

    @property
    def shown(self) -> int:
        return min(len(self.entries), self.rows * self.cols)

    def row_height(self) -> int:
        return CHIP_H + CHIP_GAP

    def _rebuild(self) -> None:
        for chip in self.chips:
            self.grid.removeWidget(chip)
            chip.deleteLater()
        self.chips = []
        for i, entry in enumerate(self.entries[:self.rows * self.cols]):
            chip = Chip(parent=self)
            chip.set(**entry)
            self.grid.addWidget(chip, i // self.cols, i % self.cols)
            self.chips.append(chip)
        # EVERY COLUMN THE SAME WIDTH, including the ones a short last
        # row leaves empty - or the last row's chips stretch to fill it
        # and read as a different kind of thing.
        for c in range(self.cols):
            self.grid.setColumnStretch(c, 1)
        for c in range(self.cols, self.grid.columnCount()):
            self.grid.setColumnStretch(c, 0)
        self.updateGeometry()


class RoleStrip(QWidget):
    """Eight roles across, two rows of shares under them.

    The picture view spends a card per side on this; here it is one
    strip, because a share is a number and eight numbers read across in
    a line. The names head the columns so the two sides line up under
    each role by construction.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setProperty("bare", True)
        self.grid = QGridLayout(self)
        self.grid.setContentsMargins(0, 0, 0, 0)
        self.grid.setHorizontalSpacing(8)
        self.grid.setVerticalSpacing(2)
        self.cells: dict[tuple[int, int], QLabel] = {}

    def _cell(self, r: int, c: int, head: bool = False) -> QLabel:
        if (r, c) not in self.cells:
            label = QLabel()
            label.setProperty("striphead" if head else "strip", True)
            label.setAlignment(Qt.AlignmentFlag.AlignRight
                               | Qt.AlignmentFlag.AlignVCenter
                               if c else Qt.AlignmentFlag.AlignLeft
                               | Qt.AlignmentFlag.AlignVCenter)
            self.grid.addWidget(label, r, c)
            self.cells[(r, c)] = label
        return self.cells[(r, c)]

    def fill(self, rows: list[tuple[str, roles_mod.RoleScore,
                                    roles_mod.RoleScore]],
             mine: str, theirs: str) -> None:
        for c, (role, _a, _b) in enumerate(rows, start=1):
            self._cell(0, c, head=True).setText(role)
        self._cell(0, 0, head=True).setText("")
        for r, name in ((1, mine), (2, theirs)):
            label = self._cell(r, 0)
            label.setText(name)
            label.setProperty("dim", True)
        for c, (_role, ours, yours) in enumerate(rows, start=1):
            for r, score in ((1, ours), (2, yours)):
                label = self._cell(r, c)
                if score.possible:
                    label.setText(f"{round(score.share * 100)}%")
                    label.setToolTip(f"{score.scored} of {score.possible} "
                                     f"across {score.rated} rated pick"
                                     f"{'' if score.rated == 1 else 's'}")
                else:
                    label.setText(NOTHING)
                    label.setToolTip("")
        for c in range(1, len(rows) + 1):
            self.grid.setColumnStretch(c, 1)


class SimpleView(QWidget):
    """The whole Draft tab in bands, in the order the rich one reads.

    Board, roles, the top heroes, the items, then the pairs and the
    matchups side by side - the argument the Draft tab makes top to
    bottom, so switching views does not mean learning a second layout.
    """

    # The card keys, in page order. `set_sections` and the fold memory
    # both speak in these.
    KEYS = ("board", "roles", "picks", "items", "synergy", "counters")

    folded = pyqtSignal(str, bool)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._sheet = ""
        self.restyle()
        self._budget = 0
        lay = QVBoxLayout(self)
        lay.setContentsMargins(12, 8, 12, 8)
        lay.setSpacing(8)
        self.lay = lay

        # THE BOARD ACTIONS AND THE TOTALS, on one row above everything.
        # The buttons are handed in by the window (`set_actions`): they
        # are the same three commands the picture view has between the
        # Radiant and Dire headings - "i also dont have those 3 buttons at
        # the top" - and a page without them is a page you have to leave
        # to clear. The totals sit at the far right AT THE TABLE SIZE,
        # since "the total synergy value is a smaller font than the
        # tables themselves" was the first thing noticed about the draft
        # before this one.
        self.bar = QWidget()
        self.bar.setProperty("bare", True)
        bar = QHBoxLayout(self.bar)
        bar.setContentsMargins(0, 0, 0, 0)
        bar.setSpacing(8)
        self.actions_lay = bar
        bar.addStretch(1)
        self.totals = QLabel()
        self.totals.setProperty("totals", True)
        bar.addWidget(self.totals)
        lay.addWidget(self.bar)

        self.cards: dict[str, Fold] = {}

        def fold(key: str, title: str) -> Fold:
            card = Fold(key, title)
            card.toggled.connect(self._folded)
            self.cards[key] = card
            return card

        # ----- the board: two rows of five
        board = fold("board", "Draft")
        self.slots: dict[str, list[Chip]] = {"top": [], "bottom": []}
        for row_key in ("top", "bottom"):
            row = QWidget()
            row.setProperty("bare", True)
            hl = QHBoxLayout(row)
            hl.setContentsMargins(0, 0, 0, 0)
            hl.setSpacing(CHIP_GAP)
            for _ in range(5):
                chip = Chip(SLOT_H)
                hl.addWidget(chip, 1)
                self.slots[row_key].append(chip)
            board.body_lay.addWidget(row)
        lay.addWidget(board)

        roles = fold("roles", "Team roles")
        self.roles = RoleStrip()
        roles.body_lay.addWidget(self.roles)
        lay.addWidget(roles)

        picks = fold("picks", "Top Heroes")
        self.picks = ChipGrid()
        self.picks_note = _dim()
        self.picks_note.setWordWrap(True)
        self.picks_note.hide()
        picks.body_lay.addWidget(self.picks)
        picks.body_lay.addWidget(self.picks_note)
        lay.addWidget(picks)

        items = fold("items", "Top Items")
        self.items = ChipGrid()
        items.body_lay.addWidget(self.items)
        lay.addWidget(items)

        # ----- the two matrices, side by side
        bottom = QWidget()
        bottom.setProperty("bare", True)
        pair = QHBoxLayout(bottom)
        pair.setContentsMargins(0, 0, 0, 0)
        pair.setSpacing(8)
        synergy = fold("synergy", "Synergies")
        self.synergy = TextTable()
        synergy.body_lay.addWidget(self.synergy)
        self.synergy_note = _dim()
        self.synergy_note.setWordWrap(True)
        self.synergy_note.hide()
        synergy.body_lay.addWidget(self.synergy_note)
        counters = fold("counters", "Counters")
        self.counters = TextTable()
        counters.body_lay.addWidget(self.counters)
        pair.addWidget(synergy, 1)
        pair.addWidget(counters, 1)
        self.bottom = bottom
        lay.addWidget(bottom)
        lay.addStretch(1)

    # ---- plumbing -------------------------------------------------------
    def restyle(self) -> None:
        sheet = stylesheet()
        if sheet != self._sheet:
            self._sheet = sheet
            self.setStyleSheet(sheet)

    def set_actions(self, widgets) -> None:
        """The board buttons, inserted ahead of the stretch."""
        for i, widget in enumerate(widgets):
            self.actions_lay.insertWidget(i, widget)

    def _folded(self, key: str, closed: bool) -> None:
        self.folded.emit(key, closed)
        self._refit()

    def set_folded(self, keys) -> None:
        """Restore which cards are closed, with no signal."""
        wanted = set(keys or ())
        for key, card in self.cards.items():
            card.set_closed(key in wanted)
        self._refit()

    def set_sections(self, shown: dict[str, bool]) -> None:
        """Hide a card the View menu has turned off; the same four ticks
        govern both views, so a block turned off is off wherever you
        look."""
        for key, card in self.cards.items():
            card.setVisible(bool(shown.get(key, True)))
        self.bottom.setVisible(self.cards["synergy"].isVisibleTo(self)
                               or self.cards["counters"].isVisibleTo(self))
        self._refit()

    def set_budget(self, height: int) -> None:
        """How tall the page may be - the viewport's height - so the hero
        grid can take what is left rather than a fixed count.

        "Show as many as fit is fine." Every other card is as tall as its
        own rows; this is the one block that could grow without bound,
        so it is cut to the rows the page has left after the others have
        been placed. The sum deliberately leaves the hero card itself
        OUT, which is what makes it converge in one step rather than
        chase its own height.
        """
        if height == self._budget:
            return
        self._budget = height
        self._refit()

    def resizeEvent(self, event) -> None:          # noqa: N802 - Qt naming
        super().resizeEvent(event)
        self._refit()

    def _refit(self) -> None:
        card = self.cards["picks"]
        if not self._budget or card.isHidden() or card.closed:
            return
        margins = self.lay.contentsMargins()
        used = margins.top() + margins.bottom() + self.bar.sizeHint().height()
        blocks = [c for k, c in self.cards.items()
                  if k not in ("picks", "synergy", "counters")
                  and not c.isHidden()]
        if not self.bottom.isHidden():
            blocks.append(self.bottom)
        for block in blocks:
            used += block.sizeHint().height()
        used += self.lay.spacing() * (len(blocks) + 1)
        # The hero card's own chrome: its margins, heading and spacing.
        head = card.head.sizeHint().height() + 6 + 8 + 4
        if not self.picks_note.isHidden():
            head += self.picks_note.sizeHint().height() + 4
        spare = self._budget - used - head
        rows = max(1, (spare + CHIP_GAP) // self.picks.row_height())
        width = self.picks.width() or (self.width() - 2 * 10 - 24)
        cols = self.picks.columns_for(width)
        wanted = len(self.picks.entries)
        if wanted:
            rows = min(rows, -(-wanted // cols))
        self.picks.set_shape(rows, cols)
        self._say_how_many()

    def _say_how_many(self) -> None:
        total = len(self.picks.entries)
        shown = self.picks.shown
        self.cards["picks"].set_sub(
            f"all {total}" if shown >= total else f"first {shown} of {total}")

    # ---- the blocks -----------------------------------------------------
    def set_totals(self, mine: str, theirs: str,
                   ally_total: float | None, enemy_total: float | None,
                   radiant_first: bool = True) -> None:
        parts = []
        order = ((mine, ally_total), (theirs, enemy_total))
        if not radiant_first:
            order = order[::-1]
        for name, total in order:
            # A SIDE WITH NOTHING RESOLVED SHOWS NO TOTAL, rather than
            # "+0.0", which would claim a measurement nobody made.
            if total is None:
                continue
            colour = getattr(theme, "GOOD" if total > 0
                             else "BAD" if total < 0 else "TEXT_DIM")
            parts.append(f'{name} <span style="color:{colour}">'
                         f'{tilekit.delta_text(total)}</span>')
        self.totals.setText("&nbsp;&nbsp;&nbsp;&nbsp;".join(parts))

    def show_board(self, top: list, bottom: list) -> None:
        """Two rows of five slots: (name or None, value or None, is_you).

        Every slot is drawn, picked or not - the open ones dashed, the
        way the picture view's empty plates are - so the band is the
        shape of the answer standing where the answer will appear and
        does not change height as the draft fills in.
        """
        for chips, slots in ((self.slots["top"], top),
                             (self.slots["bottom"], bottom)):
            for chip, slot in zip(chips, list(slots) + [None] * 5):
                if slot is None or slot[0] is None:
                    chip.set("open slot", open_slot=True, tip="No pick yet")
                    continue
                name, value, you = slot
                cell = _delta(value)
                chip.set(name, cell.text, cell.colour or "TEXT",
                         strong=bool(you),
                         tip=f"{name} (you)" if you else name)

    def show_roles(self, rows, mine: str, theirs: str) -> None:
        self.roles.fill(rows, mine, theirs)

    def show_heroes(self, rows: list[tuple[str, float | None, float, float]],
                    note: str = "") -> None:
        """The suggestion strip's own list, in its own order, as chips.

        Handed the rows the strip was handed, so the two cannot disagree
        about which hero is best or by how much. `fit` is None for the
        boards the strip draws no badge on - an undrafted one - and the
        chip then carries no figure either.
        """
        entries = []
        for i, (name, fit, vs, with_) in enumerate(rows, start=1):
            cell = _delta(fit)
            entries.append(dict(
                name=name, figure=cell.text if fit is not None else "",
                colour=cell.colour or "TEXT", rank=str(i),
                tip=(f"{name}\nCounter Score = {vs * 100:+.1f}"
                     f"\nSynergy Score = {with_ * 100:+.1f}")))
        self.picks.set_entries(entries)
        self.picks_note.setText(note)
        self.picks_note.setVisible(bool(note))
        self._refit()

    def show_items(self, advice: list[items_mod.ItemAdvice]) -> None:
        """What to build, with the same percentage the tile's badge
        carries and the heroes that asked for it after the name.

        `items.importance` is measured against the WORST CASE rather
        than against this draft, so the figure means the same thing in
        every draft - which is why it can be printed as a bare
        percentage here.
        """
        entries = []
        for i, a in enumerate(advice, start=1):
            pct = items_mod.importance(a.score)
            entries.append(dict(
                name=a.item + (" *" if a.any_stale else ""),
                tail="· " + ", ".join(t.hero for t in a.triggers),
                figure=f"{pct}%",
                colour="GOOD" if pct > items_mod.ONE_TRIGGER else "TEXT",
                tip="\n".join(
                    f"{t.hero} ({items_mod.severity_pct(t.severity)}%): "
                    f"{t.reason}" for t in a.triggers)
                + ("\n\nAt least one rule behind this has not been "
                   "verified for the current patch." if a.any_stale else "")))
        self.items.set_entries(entries)
        # ITEMS NEVER NEED CUTTING: the strip is already capped by the
        # severity floor and the count box, so three across and however
        # many rows that takes.
        self.items.set_shape(-(-len(entries) // 3) or 1, 3)

    def show_synergy(self, mine: str, theirs: str,
                     mine_names: list[str], theirs_names: list[str],
                     pairs: list, note: str = "") -> None:
        """Both teams' pairs in one square, as the painted card draws
        them: LOWER-LEFT is the first team against the row names,
        UPPER-RIGHT the second against the column names.

        `pairs` is `SynergyGrid.pairs` - every pair once, off the very
        grid the triangles are drawn from - with each cell's side saying
        which triangle it belongs to. **THE ENEMY HALF IS NOT
        SIGN-FLIPPED**, which keeps this in step with the painted grid:
        each triangle answers "how well does THIS pair work", so a strong
        enemy pairing is a big green number in their half. The halves
        are the rule for reading it, not the colour.
        """
        look = {}
        for cell in pairs:
            look[(cell.a, cell.b)] = cell.v
            look[(cell.b, cell.a)] = cell.v
        rows_n = [n or NOTHING for n in list(mine_names) + [None] * 5][:5]
        cols_n = [n or NOTHING for n in list(theirs_names) + [None] * 5][:5]
        table = []
        for r in range(5):
            line = [Cell(rows_n[r], None if rows_n[r] != NOTHING else "TEXT_DIM",
                         tip=rows_n[r])]
            for c in range(5):
                if c == r:
                    line.append(Cell(""))
                elif c < r:
                    v = look.get((rows_n[r], rows_n[c]))
                    line.append(self._centre(v))
                else:
                    v = look.get((cols_n[r], cols_n[c]))
                    line.append(self._centre(v))
            table.append(line)
        self.synergy.show_rows([""] + cols_n, table,
                               stretch=tuple(range(1, 6)))
        self.cards["synergy"].set_sub(
            f"lower-left {mine}, upper-right {theirs}")
        self.synergy_note.setText(note)
        self.synergy_note.setVisible(bool(note))

    @staticmethod
    def _centre(value) -> Cell:
        cell = _delta(value)
        return Cell(cell.text if value is not None else "",
                    cell.colour, "centre", numeric=True)

    def show_counters(self, rows: list[tuple[int, str]],
                      cols: list[tuple[int, str]],
                      cells: list[list[float | None]],
                      mine: str, theirs: str) -> None:
        """Your five down the side against their five across the top.

        WHICH AXIS IS WHOSE IS SAID IN WORDS, in the corner cell: the
        painted card says it with a green box round one axis and a red
        one round the other, and a table has no boxes. Ten heroes with
        nothing saying which five are yours is the one way this table
        can be read backwards.
        """
        col_names = [n for _h, n in cols] + [NOTHING] * (5 - len(cols))
        table = []
        for i in range(5):
            if i < len(rows):
                name = rows[i][1]
                line = [Cell(name, tip=name)]
                for c in range(5):
                    v = cells[i][c] if c < len(cols) else None
                    line.append(self._centre(v))
            else:
                line = [Cell(NOTHING, "TEXT_DIM")] + [Cell("")] * 5
            table.append(line)
        self.counters.show_rows([f"{mine} ↓  {theirs} →"]
                                + col_names, table,
                                stretch=tuple(range(1, 6)))
