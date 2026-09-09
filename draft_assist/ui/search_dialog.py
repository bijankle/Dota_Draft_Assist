"""Help ▸ Search: type what you want, press Enter, it happens.

The menu bar is three headings and everything else is a tab in Settings,
which is a better place to keep a control and a worse place to find one.
This is the way back: the app's whole list of what it can do, matched
against what a person would actually type for it (`commands.SYNONYMS`),
with where it lives shown beside each answer so the next time they can
go straight there.

Two ways to take a result, at the user's request: press Enter for the top
match, or CLICK any of them. A search box that only obeys Enter makes the
list a display rather than a control, and the list is the part that
answers "what else is there".
"""

from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (QDialog, QLabel, QLineEdit, QListWidget,
                             QListWidgetItem, QVBoxLayout)

from .commands import search

MAX_SHOWN = 12


class SearchDialog(QDialog):
    def __init__(self, commands, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Search")
        self.setMinimumWidth(520)
        self.commands = list(commands)
        self.chosen = None

        layout = QVBoxLayout(self)
        self.box = QLineEdit()
        self.box.setPlaceholderText(
            "What do you want to do?  (pictures, my rank, it's broken…)")
        self.box.textChanged.connect(self._refresh)
        # RETURN TAKES THE TOP MATCH, wherever the cursor is. Enter in a
        # one-line box means "do it", and making somebody arrow down to a
        # list they can already read is a keystroke for nothing.
        self.box.returnPressed.connect(self._take_top)
        layout.addWidget(self.box)

        self.results = QListWidget()
        # A single click, not a double: this list IS the control.
        self.results.itemClicked.connect(self._take)
        self.results.itemActivated.connect(self._take)
        layout.addWidget(self.results)

        self.note = QLabel("")
        self.note.setProperty("dim", True)
        self.note.setWordWrap(True)
        layout.addWidget(self.note)
        self._refresh("")

    # ---- the list -------------------------------------------------
    def matches(self, query: str) -> list:
        """Everything, until there is something to narrow it by: an empty
        box should show what the app CAN do rather than nothing at all,
        because half of searching is finding out what is there."""
        if not query.strip():
            return [c for c in self.commands if c.run is not None]
        return search(query, self.commands)

    def _refresh(self, query: str = "") -> None:
        found = self.matches(query)
        self.results.clear()
        for command in found[:MAX_SHOWN]:
            item = QListWidgetItem(command.title)
            item.setToolTip(command.detail)
            item.setData(Qt.ItemDataRole.UserRole, command)
            self.results.addItem(item)
        if found:
            self.results.setCurrentRow(0)
        extra = len(found) - MAX_SHOWN
        self.note.setText(
            "Nothing matches that — try a plainer word, like "
            "“pictures” or “rank”." if not found
            else f"{extra} more — keep typing." if extra > 0
            else "Enter takes the top match; click any of them.")

    # ---- taking one -----------------------------------------------
    def _take_top(self) -> None:
        if self.results.count():
            self._take(self.results.item(0))

    def _take(self, item) -> None:
        command = item.data(Qt.ItemDataRole.UserRole)
        if command is None or command.run is None:
            return
        self.chosen = command
        # CLOSED FIRST. Several of these open a window of their own, and a
        # search box left sitting in front of the thing it just opened is
        # the search having got in the way of its own answer.
        self.accept()
        command.run()
