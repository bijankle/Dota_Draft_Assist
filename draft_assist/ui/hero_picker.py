"""Type-to-filter hero picker for entering draft slots by hand.

Kept deliberately fast: the dialog opens with the filter focused, typing
narrows the list, Enter takes the top match. Filling five enemy slots during
a draft should cost seconds, not attention.

**A HERO ALREADY IN THE DRAFT IS SHOWN AND REFUSED, NEVER DELETED.** The
duplicate rule stands - a hero cannot be in two slots - but it used to be
enforced by leaving that hero OUT of the list entirely, and an absence
explains nothing. Reported from a real session: "I typed in his name to
manually add him and I couldn't find [him]", about a hero who was on the
board at the time. An empty list is indistinguishable from the app never
having heard of that hero, which is what it was read as.

So the row stays, dimmed, saying which team already holds it, and cannot
be selected - and a filter that matches nothing says so rather than
showing a blank box. Same rule as the item tile that names WHY its icon
is missing, and as the status line saying a hero came from the game
rather than doing nothing: doing nothing silently is indistinguishable
from being broken.
"""

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import (QDialog, QHBoxLayout, QLabel, QLineEdit,
                             QListWidget, QListWidgetItem, QPushButton,
                             QVBoxLayout)

from . import theme


IN_DRAFT = "already in this draft"


class HeroPickerDialog(QDialog):
    def __init__(self, dataset, taken=frozenset(),
                 current: int | None = None, title: str = "Choose hero",
                 parent=None):
        """`taken` is either a set of hero ids or a {hero id: where} map.

        The map is what lets a refused row say WHERE the hero already is,
        which is the difference between "you have already got Mars" and a
        list that appears not to contain him. A bare set still works and
        falls back to a plain phrase.
        """
        super().__init__(parent)
        self.ds = dataset
        self.selected: int | None = None
        self.cleared = False
        self.setWindowTitle(title)
        self.resize(360, 460)

        layout = QVBoxLayout(self)
        self.filter_box = QLineEdit()
        self.filter_box.setPlaceholderText("Type to filter…")
        self.filter_box.textChanged.connect(self._apply_filter)
        self.filter_box.returnPressed.connect(self._accept_top)
        layout.addWidget(self.filter_box)

        self.list = QListWidget()
        self.list.itemActivated.connect(lambda _i: self._accept_current())
        self.list.itemDoubleClicked.connect(lambda _i: self._accept_current())
        layout.addWidget(self.list, 1)

        where = dict(taken) if isinstance(taken, dict) else {
            hero_id: IN_DRAFT for hero_id in taken}
        for hero_id in sorted(dataset.hero_ids, key=dataset.name):
            name = dataset.name(hero_id)
            spoken = hero_id in where and hero_id != current
            item = QListWidgetItem(
                f"{name} — {where[hero_id]}" if spoken else name)
            item.setData(Qt.ItemDataRole.UserRole, hero_id)
            # The row is the ANSWER to "why can I not find this hero", so
            # it has to be reachable by typing the hero's name and no
            # more: the suffix is not part of what anybody types.
            item.setData(Qt.ItemDataRole.ToolTipRole, name)
            if spoken:
                item.setFlags(Qt.ItemFlag.NoItemFlags)
                item.setForeground(QColor(theme.TEXT_DIM))
            self.list.addItem(item)
            if hero_id == current:
                self.list.setCurrentItem(item)

        # Said in the dialog rather than left to an empty list, for the
        # same reason the rows above are: nothing on screen is not an
        # answer. Hidden until there is something to say.
        self.note = QLabel()
        self.note.setProperty("dim", True)
        self.note.setWordWrap(True)
        self.note.hide()
        layout.addWidget(self.note)

        if dataset.is_empty:
            layout.addWidget(QLabel(
                "No heroes yet — run\nSettings ▸ Downloads ▸ Statistics and portraits first."))

        buttons = QHBoxLayout()
        clear = QPushButton("Clear slot")
        clear.clicked.connect(self._clear)
        buttons.addWidget(clear)
        buttons.addStretch(1)
        cancel = QPushButton("Cancel")
        cancel.clicked.connect(self.reject)
        buttons.addWidget(cancel)
        ok = QPushButton("Select")
        ok.setProperty("accent", True)
        ok.setDefault(True)
        ok.clicked.connect(self._accept_current)
        buttons.addWidget(ok)
        layout.addLayout(buttons)

        self.filter_box.setFocus()

    def _apply_filter(self, text: str) -> None:
        """Match against the HERO'S NAME, never the row's text.

        A refused row reads "Mars - your team", so filtering on what is
        drawn would let "team" match half the list and would make the
        suffix part of what has to be typed.
        """
        needle = text.strip().lower()
        first_visible = None
        shown = 0
        for row in range(self.list.count()):
            item = self.list.item(row)
            name = item.data(Qt.ItemDataRole.ToolTipRole) or item.text()
            hidden = bool(needle and needle not in name.lower())
            item.setHidden(hidden)
            if hidden:
                continue
            shown += 1
            if first_visible is None and self._selectable(item):
                first_visible = item
        if first_visible is not None:
            self.list.setCurrentItem(first_visible)
        self._say(needle, shown)

    @staticmethod
    def _selectable(item) -> bool:
        return item.flags() != Qt.ItemFlag.NoItemFlags

    def _say(self, needle: str, shown: int) -> None:
        """Why the list looks the way it does, when that needs saying."""
        if not needle:
            self.note.hide()
            return
        if not shown:
            self.note.setText(f"No hero matches “{needle}”.")
        elif not any(self._selectable(self.list.item(row))
                     for row in range(self.list.count())
                     if not self.list.item(row).isHidden()):
            # The case this whole dialog was reported over: the hero IS
            # there and is already drafted. Name the way out, since a
            # picker cannot take a hero off the board.
            self.note.setText(
                "Already in this draft. Right-click the tile it is on to "
                "clear or change it, or drag it across.")
        else:
            self.note.hide()
            return
        self.note.show()

    def _accept_top(self) -> None:
        self._accept_current()

    def _accept_current(self) -> None:
        item = self.list.currentItem()
        if (item is not None and not item.isHidden()
                and self._selectable(item)):
            self.selected = item.data(Qt.ItemDataRole.UserRole)
            self.accept()

    def _clear(self) -> None:
        self.cleared = True
        self.selected = None
        self.accept()
