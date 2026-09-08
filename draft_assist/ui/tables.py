"""Sortable tables for the draft window.

Two things live here that Qt does not give for free:

* numeric sorting. A QTableWidgetItem compares by its *text*, so "+10.0"
  sorts before "+9.0" and a percentage column orders alphabetically. Every
  numeric cell therefore carries the underlying float and compares on that.

* the breakdown panel's two independent banks. It shows allies beside
  enemies, which are separate lists that happen to share a table. Qt's
  built-in sorting reorders whole rows, so clicking "vs enemy" would drag
  the ally beside it along for the ride. Each bank is sorted on its own and
  the rows are then laid side by side.
"""

from PyQt6.QtCore import QRect, Qt, pyqtSignal
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import (QHeaderView, QLabel, QLineEdit,
                             QStyledItemDelegate, QTableWidget,
                             QTableWidgetItem, QVBoxLayout, QWidget)

from . import theme

SORT_ROLE = Qt.ItemDataRole.UserRole + 1

# The empty grid drawn before either team is known: a draft is five a side,
# so the outline is too.
BLANK_SIDE = 5
# The same height a filled row settles at, so nothing jumps when the first
# pair of heroes arrives.
BLANK_ROW = 26


class ValueItem(QTableWidgetItem):
    """A cell that sorts on the number it displays rather than its text."""

    def __init__(self, text: str, value: float):
        super().__init__(text)
        self.setData(SORT_ROLE, float(value))
        self.setTextAlignment(Qt.AlignmentFlag.AlignRight
                              | Qt.AlignmentFlag.AlignVCenter)

    def __lt__(self, other) -> bool:
        mine = self.data(SORT_ROLE)
        theirs = other.data(SORT_ROLE) if isinstance(other, QTableWidgetItem) \
            else None
        if mine is None or theirs is None:
            return super().__lt__(other)
        return mine < theirs


def delta_item(delta: float) -> ValueItem:
    """A signed interaction term, coloured by sign. Percentage points."""
    item = ValueItem(f"{delta * 100:+.2f}", delta)
    # Centred both ways: the grid sits under portraits that are centred in
    # their own columns, and a left-aligned number does not line up with
    # the hero it belongs to.
    item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
    if delta:
        item.setForeground(QColor(theme.GOOD if delta > 0 else theme.BAD))
    return item


class BreakdownPanel(QWidget):
    """The 'Why this score' panel: allies in one bank, enemies in the other,
    each sorted by size so the terms that actually moved the number are at
    the top and a plausible total reached for poor reasons is obvious.

    Click a bank's header to re-sort just that bank — by name, or by value.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        self.heading = QLabel("")
        self.heading.setProperty("heading", True)
        layout.addWidget(self.heading)
        self.subtitle = QLabel("")
        self.subtitle.setWordWrap(True)
        self.subtitle.setProperty("dim", True)
        layout.addWidget(self.subtitle)

        self.table = QTableWidget(0, 4)
        self.table.verticalHeader().setVisible(False)
        self.table.setAlternatingRowColors(True)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setSelectionMode(QTableWidget.SelectionMode.NoSelection)
        self.table.horizontalHeader().setSectionsClickable(True)
        self.table.horizontalHeader().sectionClicked.connect(self._sort_bank)
        # TOP, not centred. `_fit_height` gives the table a fixed height, so
        # a QVBoxLayout puts the slack ABOVE it as well as below — and the
        # moment the two grids stopped being the same height (the synergy
        # one grew a bottom header row) the shorter one floated down the
        # middle of its card and the two stopped lining up.
        layout.addWidget(self.table, 1, Qt.AlignmentFlag.AlignTop)

        self.footnote = QLabel("")
        self.footnote.setWordWrap(True)
        self.footnote.setProperty("dim", True)
        layout.addWidget(self.footnote)

        # bank index -> (title, rows); sort state is (by_value, descending)
        self._banks: list[tuple[str, list[tuple[str, float]]]] = []
        self._sort: list[tuple[bool, bool]] = [(True, True), (True, True)]

    # -- public API ------------------------------------------------------

    def show_banks(self, heading: str, subtitle: str,
                   banks: list[tuple[str, list[tuple[str, float]]]],
                   footnote: str = "", empty: str = "") -> None:
        self.heading.setText(heading)
        self.subtitle.setText(subtitle)
        self.subtitle.setVisible(bool(subtitle))
        self._banks = banks
        self.footnote.setText(footnote if any(rows for _, rows in banks)
                              else empty)
        self.footnote.setVisible(bool(self.footnote.text()))
        self._rebuild()

    def show_message(self, heading: str, text: str) -> None:
        self.show_banks(heading, text, [])

    def rows_for(self, bank: int) -> list[tuple[str, float]]:
        """Sorted rows of one bank — what the panel is actually showing."""
        return self._sorted(bank)

    # -- internals -------------------------------------------------------

    def _sorted(self, bank: int) -> list[tuple[str, float]]:
        if bank >= len(self._banks):
            return []
        by_value, descending = self._sort[bank]
        rows = list(self._banks[bank][1])
        rows.sort(key=(lambda r: r[1]) if by_value
                  else (lambda r: r[0].lower()), reverse=descending)
        return rows

    def _sort_bank(self, column: int) -> None:
        bank, by_value = divmod(column, 2)
        if bank >= len(self._banks):
            return
        was_value, descending = self._sort[bank]
        # Clicking the column already sorted flips it; a new column starts
        # the way that column is most useful — biggest first for values,
        # A-Z for names.
        self._sort[bank] = (bool(by_value),
                            not descending if was_value == bool(by_value)
                            else bool(by_value))
        self._rebuild()

    def _rebuild(self) -> None:
        banks = self._banks
        columns = max(2 * len(banks), 1)
        self.table.setColumnCount(columns)
        labels = []
        for index, (title, _rows) in enumerate(banks):
            by_value, descending = self._sort[index]
            arrow = " ▾" if descending else " ▴"
            labels += [title + ("" if by_value else arrow),
                       "Δ" + (arrow if by_value else "")]
        self.table.setHorizontalHeaderLabels(labels or [""])
        self.table.setVisible(bool(banks))

        sorted_banks = [self._sorted(i) for i in range(len(banks))]
        self.table.setRowCount(max((len(r) for r in sorted_banks), default=0))
        for index, rows in enumerate(sorted_banks):
            for row in range(self.table.rowCount()):
                if row < len(rows):
                    name, delta = rows[row]
                    self.table.setItem(row, 2 * index, QTableWidgetItem(name))
                    self.table.setItem(row, 2 * index + 1, delta_item(delta))
                else:
                    self.table.setItem(row, 2 * index, QTableWidgetItem(""))
                    self.table.setItem(row, 2 * index + 1,
                                       QTableWidgetItem(""))
        header = self.table.horizontalHeader()
        for column in range(columns):
            header.setSectionResizeMode(
                column, QHeaderView.ResizeMode.ResizeToContents
                if column % 2 else QHeaderView.ResizeMode.Stretch)


class QuickEntry(QLineEdit):
    """A line edit that reports Tab instead of letting Qt move focus.

    During a draft the same field is used for both teams, so Tab has to
    mean 'other side' — losing focus mid-draft costs more than tab order
    is worth here.
    """

    tab_pressed = pyqtSignal()

    def keyPressEvent(self, event) -> None:  # noqa: N802 - Qt naming
        if event.key() in (Qt.Key.Key_Tab, Qt.Key.Key_Backtab):
            self.tab_pressed.emit()
            return
        super().keyPressEvent(event)


TOTAL_LABEL = "Σ"
# The in-game callout has to fit beside Dota, not compete with it, so the
# compact grid trades full hero names for a grid that fits without
# scrolling. Anyone reading it is looking at the same five portraits.
COMPACT_NAME = 7
COMPACT_COLUMN = 72
# The portrait head on a matrix column. This is the app's width UNIT: five
# of them plus a row header is the narrowest a grid can be drawn, two of
# those grids is the narrowest the window is worth having, and the pick
# tiles above size themselves against the same number so a column reads
# down from the tile it belongs to.
HEADER_ICON = 34
HEADER_ICON_MAX = 64
ROW_HEADER = HEADER_ICON + 4
# A cell has to hold "+12.34" without eliding, and that is wider than the
# portrait above it — so the column, not the icon, sets the floor.
CELL_MIN = 46


def minimum_grid_width(columns: int = 5) -> int:
    """The narrowest a grid of this many columns can honestly be drawn.

    Honestly: a narrower one still draws, it just shows "..." where the
    numbers were, which is a grid that has stopped being a grid.
    """
    return ROW_HEADER + columns * max(HEADER_ICON, CELL_MIN)


def short_name(name: str) -> str:
    return name if len(name) <= COMPACT_NAME else name[:COMPACT_NAME] + "…"


def _total_item(value: float) -> QTableWidgetItem:
    """A margin figure: same colour rule as a cell, but bold, so the eye
    can tell a summary apart from a pairing without reading the header."""
    item = delta_item(value)
    font = item.font()
    font.setBold(True)
    item.setFont(font)
    return item


class PortraitHeader(QHeaderView):
    """A header that draws hero portraits, because Qt will not.

    A QHeaderView under a stylesheet ignores `iconSize` and falls back to
    the style's small-icon metric — 16 pixels, whatever you asked for — so
    an icon set on the header item comes out a third of the size and there
    is no property that changes it. Painting the pixmap here is the only
    reliable way, and it is a dozen lines.
    """

    def __init__(self, orientation, parent=None):
        super().__init__(orientation, parent)
        self.heroes: dict[int, int] = {}
        self.box = HEADER_ICON

    def set_box(self, size: int) -> None:
        """The square every portrait is drawn inside, both headers alike.

        Without this the two headers scale differently and there is no way
        to see why: a column header's section is (stretched column width) x
        (fixed header height) while a row header's is (fixed header width)
        x (row height), so the two portraits are limited by different
        numbers and one grows with the window while the other does not.
        Same box, same picture.
        """
        self.box = max(8, int(size))
        self.updateGeometries()
        self.viewport().update()

    def set_heroes(self, heroes: dict) -> None:
        """Section index -> hero id. Ids rather than pixmaps, so the shared
        scaled-portrait cache does the work instead of this repainting."""
        self.heroes = heroes
        self.updateGeometries()
        self.viewport().update()

    def paintSection(self, painter, rect, index):   # noqa: N802 - Qt naming
        from .portraits import scaled
        hero_id = self.heroes.get(index)
        # The box's WIDTH, never the section's: see set_box. The height
        # comes from the section, which _apply_icon_box has already cut to
        # what this width draws, so both headers land on the same picture.
        art = (scaled(hero_id, min(self.box, rect.width()), rect.height())
               if hero_id is not None else None)
        if art is None:
            return super().paintSection(painter, rect, index)
        painter.save()
        painter.fillRect(rect, QColor(theme.BG_ELEVATED))
        painter.drawPixmap(
            rect.left() + (rect.width() - art.width()) // 2,
            rect.top() + (rect.height() - art.height()) // 2, art)
        painter.restore()


# The roles a paired-triangle cell carries: whose portrait backs it, the
# figure to print over that, and whether this is the bottom header row.
PAIR_HERO = int(Qt.ItemDataRole.UserRole) + 10
PAIR_VALUE = PAIR_HERO + 1
PAIR_HEADER = PAIR_HERO + 2
# How far the portrait behind a number is knocked back. It is a backdrop,
# not the subject: at full strength the artwork competes with the figure it
# is meant to be labelling.
PAIR_VEIL = 110


class PairCellDelegate(QStyledItemDelegate):
    """A grid cell with its hero's portrait behind the number.

    The synergy grid used to carry a column of portraits down its left
    edge to name the rows. Half that grid is blank — synergy is symmetric —
    so the row's own face goes INTO its cells instead: the pair names
    itself, the header column's width goes back to the numbers, and the
    blank half is free for the other team's triangle.

    The number is outlined rather than plated, the same way a tile's is and
    for the same reason: a plate behind it is a rectangle of the portrait
    gone.
    """

    def paint(self, painter, option, index):        # noqa: N802 - Qt naming
        from .portraits import scaled
        from . import tilekit
        rect = option.rect
        painter.save()
        painter.fillRect(rect, QColor(theme.BG))
        hero = index.data(PAIR_HERO)
        # FITTED, exactly as the header above fits its own — one portrait
        # at one shape everywhere in the grid. Filling the cell instead
        # (expand and crop) made these read as stretched: a cell is wider
        # than it is tall, so covering it threw away the top and bottom of
        # a 16:9 head shot and left a wide slice of the middle.
        art = scaled(hero, rect.width(), rect.height()) if hero else None
        box = rect
        if art is not None:
            box = QRect(rect.left() + (rect.width() - art.width()) // 2,
                        rect.top() + (rect.height() - art.height()) // 2,
                        art.width(), art.height())
            painter.drawPixmap(box.topLeft(), art)
            # Knocked back, so the figure over it stays the subject.
            painter.fillRect(box, QColor(0, 0, 0, PAIR_VEIL))
        value = index.data(PAIR_VALUE)
        if value is not None and not index.data(PAIR_HEADER):
            # THE TILE'S OWN BADGE: same font, same size, same corner as
            # the figure on a pick up at the top of the window, so the two
            # are read the same way rather than as two conventions.
            tilekit.paint_badge(painter, box, f"{float(value) * 100:+.2f}",
                                theme.GOOD if float(value) > 0 else theme.BAD,
                                option.font)
        painter.restore()


class MatrixTable(QWidget):
    """A drafted-hero grid: allies against enemies, or allies with allies.

    Reading a total tells you the draft is fine; reading the grid tells you
    which lane is not. Cells are coloured by sign and blank where a pair has
    no meaning (the diagonal, and the half a symmetric matrix would repeat).
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)
        self.caption = QLabel("")
        self.caption.setWordWrap(True)
        self.caption.setProperty("dim", True)
        layout.addWidget(self.caption)
        self.table = QTableWidget(0, 0)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setSelectionMode(QTableWidget.SelectionMode.NoSelection)
        self.table.setHorizontalHeader(
            PortraitHeader(Qt.Orientation.Horizontal, self.table))
        self.table.setVerticalHeader(
            PortraitHeader(Qt.Orientation.Vertical, self.table))
        # NEITHER BAR, EVER. The grid is five rows and it is sized to fit
        # them, so a scrollbar can only mean the fit was wrong — and it
        # hides part of the answer while making the widget look correct.
        # Off, so getting it wrong shows up as a squashed grid instead of
        # as a grid that quietly stopped showing a row.
        self.table.setVerticalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.table.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        # TOP, not centred. `_fit_height` gives the table a fixed height, so
        # a QVBoxLayout puts the slack ABOVE it as well as below — and the
        # moment the two grids stopped being the same height (the synergy
        # one grew a bottom header row) the shorter one floated down the
        # middle of its card and the two stopped lining up.
        layout.addWidget(self.table, 1, Qt.AlignmentFlag.AlignTop)
        self.empty_note = QLabel("")
        self.empty_note.setWordWrap(True)
        self.empty_note.setProperty("dim", True)
        layout.addWidget(self.empty_note)

    def _fit_height(self) -> None:
        """Size the table to its rows — EVERYWHERE, not just the callout.

        A five-row grid left to stretch fills whatever height the layout
        gives it, and the leftover is dead space inside the widget: half
        the window was blank and the window could not be made shorter,
        because a stretching table has no smaller size to offer. There are
        never more than six rows, so the exact height is cheap to compute
        and it is always the right one.
        """
        # `verticalHeader().length()` is the sum of the sections Qt has
        # actually laid out, which is not the same as adding up rowHeight
        # before the layout has run — and being short by a few pixels puts
        # a scrollbar on a five-row grid, which is a grid you cannot read
        # without moving it. The header is measured the same way: its
        # `height()` is stale until it has been shown, so the larger of
        # that and its size hint is the honest number.
        head = self.table.horizontalHeader()
        header_h = max(head.height(), head.sizeHint().height())
        rows = self.table.verticalHeader().length()
        self.table.setFixedHeight(
            header_h + rows + 2 * self.table.frameWidth() + 2)

    def set_compact(self, compact: bool = True,
                    short_names: bool = True) -> None:
        """Drop the explanatory caption, and optionally the full names.

        The caption goes everywhere: the card heading says which grid this
        is and the headers say what the axes are, so a paragraph repeating
        both only stands between the reader and the numbers. Short names
        are for the in-game callout alone, where width is scarce and the
        reader is looking at the same five portraits anyway.
        """
        self._compact = compact
        self._short_names = compact and short_names
        self.caption.setVisible(not compact)

    def set_icon_headers(self, on: bool = True,
                         size: int = HEADER_ICON) -> None:
        """Head the rows and columns with the heroes' own portraits.

        The grid sits directly under the tiles it describes, so a column
        headed by the same picture as the tile above it reads straight
        down; a name repeated in a narrow header does not. Falls back to
        the name for any hero whose portrait has not been downloaded.
        """
        self._icon_headers = on
        self._icon_size = size

    def set_margins(self, on: bool) -> None:
        """Draw the Sigma row and column, or leave them off.

        Off where each hero's own tile already carries its total: the same
        figure in two places, one of them in the corner of a grid, is one
        place too many.
        """
        self._margins = on

    def show_matrix(self, matrix, empty_text: str = "") -> None:
        self.caption.setText(matrix.caption)
        self.caption.setVisible(not getattr(self, "_compact", False))
        self.empty_note.setText("" if not matrix.empty else empty_text)
        self.empty_note.setVisible(bool(matrix.empty and empty_text))
        self.table.setVisible(True)
        if matrix.empty:
            # The grid stays on screen as an outline. A card that vanishes
            # until the draft fills in leaves the tab collapsing and
            # re-expanding under the reader; the shape of the answer is
            # itself information, and it is where the answer will appear.
            self._show_outline()
            return
        self.table.setStyleSheet("")            # back to the app's own

        # The sections this was last applied to are about to be replaced,
        # so the cached figure no longer describes anything.
        self._icon_box = None
        margins = getattr(self, "_margins", True)
        extra = 1 if margins else 0
        self.table.setRowCount(len(matrix.rows) + extra)
        self.table.setColumnCount(len(matrix.cols) + extra)
        self._set_headers(matrix, margins)

        for row, line in enumerate(matrix.cells):
            for col, value in enumerate(line):
                if value is None:
                    item = QTableWidgetItem("")
                    item.setFlags(Qt.ItemFlag.NoItemFlags)
                else:
                    item = delta_item(value)
                self.table.setItem(row, col, item)
        if margins:
            last_col, last_row = len(matrix.cols), len(matrix.rows)
            for row, value in enumerate(matrix.row_totals):
                self.table.setItem(row, last_col, _total_item(value))
            for col, value in enumerate(matrix.col_totals):
                self.table.setItem(last_row, col, _total_item(value))
            self.table.setItem(last_row, last_col, _total_item(matrix.total))

        header = self.table.horizontalHeader()
        header.setStretchLastSection(False)
        # Fixed narrow columns and a height fitted to the rows are the
        # CALLOUT's layout, not every compact one: in the main window the
        # grid should fill its card and the names should stay readable.
        cramped = getattr(self, "_short_names", False)
        for col in range(self.table.columnCount()):
            if cramped:
                header.setSectionResizeMode(col, QHeaderView.ResizeMode.Fixed)
                self.table.setColumnWidth(col, COMPACT_COLUMN)
            else:
                # Stretch, not fit-to-contents: a column pushed off the
                # right edge costs more than a name elided by a few pixels.
                header.setSectionResizeMode(col, QHeaderView.ResizeMode.Stretch)
        if not getattr(self, "_icon_headers", False):
            # With portrait headers the row height is set by _set_headers,
            # to the same square the columns use; resizing to contents here
            # would shrink it back to the height of a line of digits.
            self.table.verticalHeader().setSectionResizeMode(
                QHeaderView.ResizeMode.ResizeToContents)
        self._fit_height()

    def show_pairs(self, grid, empty_text: str = "") -> None:
        """Both teams' synergies, as the two triangles of one square.

        Yours above the diagonal read against the ally portraits along the
        TOP; theirs below it read against the enemy portraits along the
        BOTTOM, which is an ordinary last ROW of the table rather than a
        second header — Qt has no bottom header and a separate widget
        under the table would not keep its columns in step with it.

        There is no left-hand header at all: every cell carries its own row
        hero's portrait, so the pair names itself.
        """
        self.caption.setVisible(False)
        self.empty_note.setText("" if not grid.empty else empty_text)
        self.empty_note.setVisible(bool(grid.empty and empty_text))
        self.table.setVisible(True)
        self.table.setStyleSheet("")
        self._icon_box = None
        # Before the empty check too: an empty synergy grid is the same
        # grid waiting to fill, so it should not sprout a header column
        # that the filled one does not have.
        self.table.verticalHeader().setVisible(False)
        if grid.empty:
            self._show_outline()
            return
        side = grid.side
        self.table.setColumnCount(side)
        # One extra row: the enemy portraits, which are this grid's second
        # header and the axis its lower triangle is read against.
        self.table.setRowCount(side + 1)
        self.table.setItemDelegate(self._pair_delegate())

        for row in range(side):
            for col in range(side):
                cell = grid.cells[row][col]
                item = QTableWidgetItem()
                item.setFlags(Qt.ItemFlag.NoItemFlags)
                if cell is not None:
                    item.setData(PAIR_HERO, cell.hero_id)
                    item.setData(PAIR_VALUE, cell.delta)
                    item.setData(SORT_ROLE, cell.delta)
                self.table.setItem(row, col, item)
        for col, (hero_id, name) in enumerate(grid.enemies):
            item = QTableWidgetItem()
            item.setFlags(Qt.ItemFlag.NoItemFlags)
            item.setData(PAIR_HERO, hero_id)
            item.setData(PAIR_HEADER, True)
            item.setToolTip(name)
            self.table.setItem(side, col, item)

        self._set_pair_columns(grid)
        header = self.table.horizontalHeader()
        header.setStretchLastSection(False)
        for col in range(side):
            header.setSectionResizeMode(col, QHeaderView.ResizeMode.Stretch)
        self._apply_icon_box()
        self._fit_height()

    def _pair_delegate(self):
        if getattr(self, "_pairs", None) is None:
            # Kept on the widget: a delegate the table does not own is
            # garbage-collected the moment this method returns, and the
            # cells then draw with Qt's default one and no portraits.
            self._pairs = PairCellDelegate(self.table)
        return self._pairs

    def _set_pair_columns(self, grid) -> None:
        """The TOP header is the allies; there is no left header."""
        from .portraits import portrait
        by_index = {}
        for index, (hero_id, name) in enumerate(grid.allies):
            item = QTableWidgetItem()
            if portrait(hero_id) is None:
                item.setText(name)
            else:
                by_index[index] = hero_id
                item.setToolTip(name)
            self.table.setHorizontalHeaderItem(index, item)
        head = self.table.horizontalHeader()
        if isinstance(head, PortraitHeader):
            head.set_heroes(by_index)

    def _show_outline(self) -> None:
        """Five by five of nothing — the shape the grid will have."""
        self.table.setRowCount(BLANK_SIDE)
        self.table.setColumnCount(BLANK_SIDE)
        for header, setter in ((self.table.horizontalHeader(),
                                self.table.setHorizontalHeaderItem),
                               (self.table.verticalHeader(),
                                self.table.setVerticalHeaderItem)):
            if isinstance(header, PortraitHeader):
                header.set_heroes({})
            for index in range(BLANK_SIDE):
                setter(index, QTableWidgetItem(""))
        for row in range(BLANK_SIDE):
            for col in range(BLANK_SIDE):
                cell = QTableWidgetItem("")
                cell.setFlags(Qt.ItemFlag.NoItemFlags)
                self.table.setItem(row, col, cell)
        # Grid lines are on everywhere now (the numbers alone were not
        # enough structure to keep a column straight across five), so
        # nothing extra is needed here — an empty grid draws as a grid.
        head = self.table.horizontalHeader()
        head.setStretchLastSection(False)
        for col in range(BLANK_SIDE):
            head.setSectionResizeMode(col, QHeaderView.ResizeMode.Stretch)
        # Fixed rows, not ResizeToContents: empty cells have no contents,
        # so the outline would collapse to five hairlines.
        side = self.table.verticalHeader()
        side.setSectionResizeMode(QHeaderView.ResizeMode.Fixed)
        side.setDefaultSectionSize(BLANK_ROW)
        for row in range(BLANK_SIDE):
            self.table.setRowHeight(row, BLANK_ROW)
        self._fit_height()

    def _apply_icon_box(self) -> None:
        """Give both headers the SAME portrait, sized to the window.

        Without one number for both, the two headers scale from different
        measurements and nothing on screen says why: a column header's
        section is (stretched column width) x (fixed header height) and a
        row header's is (fixed header width) x (row height), so each
        portrait is limited by a different one — which is how a wide window
        ended up with big portraits along one axis and small ones along the
        other.

        So one WIDTH is chosen for both, and the sections are then cut to
        what that actually draws. A portrait is 256x144, so a square
        section would be 40% empty space; the height comes from measuring
        the scaled pixmap rather than assuming the picture is square.
        """
        if not getattr(self, "_icon_headers", False):
            return
        columns = self.table.columnCount()
        if columns < 1:
            return
        across = self.table.horizontalHeader()
        down = self.table.verticalHeader()
        floor = getattr(self, "_icon_size", HEADER_ICON)
        # Only grow for PICTURES. With no portraits downloaded the headers
        # fall back to names, and a 68px row header elides "Tidehunter"
        # while making every row 68px tall for nothing.
        heroes = list(getattr(across, "heroes", {}).values()) or \
            list(getattr(down, "heroes", {}).values())
        if not heroes:
            self._icon_box = None
            across.setFixedHeight(floor + 4)
            down.setFixedWidth(ROW_HEADER)
            down.setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
            return

        room = self.table.viewport().width() // columns - 6
        size = max(floor, min(HEADER_ICON_MAX, room))
        if size == getattr(self, "_icon_box", None):
            return
        self._icon_box = size

        from .portraits import scaled
        art = scaled(heroes[0], size, size)
        width, height = ((art.width(), art.height()) if art is not None
                         else (size, size))
        for header in (across, down):
            if isinstance(header, PortraitHeader):
                header.set_box(size)
        across.setFixedHeight(height + 4)
        down.setFixedWidth(width + 4)
        down.setSectionResizeMode(QHeaderView.ResizeMode.Fixed)
        down.setDefaultSectionSize(height + 4)
        for row in range(self.table.rowCount()):
            self.table.setRowHeight(row, height + 4)
        self._fit_height()

    def resizeEvent(self, event) -> None:       # noqa: N802 - Qt naming
        super().resizeEvent(event)
        self._apply_icon_box()

    def _set_headers(self, matrix, margins: bool) -> None:
        icons = getattr(self, "_icon_headers", False)
        label = (short_name if getattr(self, "_short_names", False)
                 else (lambda n: n))
        cols = [n for _i, n in matrix.cols] + ([TOTAL_LABEL] if margins else [])
        rows = [n for _i, n in matrix.rows] + ([TOTAL_LABEL] if margins else [])
        if not icons:
            self.table.setHorizontalHeaderLabels([label(n) for n in cols])
            self.table.setVerticalHeaderLabels([label(n) for n in rows])
            return

        from .portraits import portrait
        size = getattr(self, "_icon_size", HEADER_ICON)
        for ids, names, header, setter in (
                ([i for i, _n in matrix.cols], cols,
                 self.table.horizontalHeader(),
                 self.table.setHorizontalHeaderItem),
                ([i for i, _n in matrix.rows], rows,
                 self.table.verticalHeader(),
                 self.table.setVerticalHeaderItem)):
            by_index = {}
            for index, name in enumerate(names):
                item = QTableWidgetItem()
                art = portrait(ids[index]) if index < len(ids) else None
                if art is None:
                    # No portrait downloaded, or the margin column: the
                    # name still has to say which hero this is.
                    item.setText(label(name))
                else:
                    by_index[index] = ids[index]
                    item.setToolTip(name)
                setter(index, item)
            if isinstance(header, PortraitHeader):
                header.set_heroes(by_index)
        self._apply_icon_box()
