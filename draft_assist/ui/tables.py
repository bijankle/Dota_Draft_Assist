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

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import (QHeaderView, QLabel, QTableWidget,
                             QTableWidgetItem, QVBoxLayout, QWidget)

from . import theme

SORT_ROLE = Qt.ItemDataRole.UserRole + 1


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
        layout.addWidget(self.table, 1)

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
