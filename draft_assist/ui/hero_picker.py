"""Type-to-filter hero picker for entering draft slots by hand.

Kept deliberately fast: the dialog opens with the filter focused, typing
narrows the list, Enter takes the top match. Filling five enemy slots during
a draft should cost seconds, not attention.
"""

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (QDialog, QHBoxLayout, QLabel, QLineEdit,
                             QListWidget, QListWidgetItem, QPushButton,
                             QVBoxLayout)


class HeroPickerDialog(QDialog):
    def __init__(self, dataset, taken: set[int] = frozenset(),
                 current: int | None = None, title: str = "Choose hero",
                 parent=None):
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

        for hero_id in sorted(dataset.hero_ids, key=dataset.name):
            if hero_id in taken and hero_id != current:
                continue          # already drafted elsewhere
            item = QListWidgetItem(dataset.name(hero_id))
            item.setData(Qt.ItemDataRole.UserRole, hero_id)
            self.list.addItem(item)
            if hero_id == current:
                self.list.setCurrentItem(item)

        if dataset.is_empty:
            layout.addWidget(QLabel(
                "No heroes yet — run Data ▸ Update statistics first."))

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
        needle = text.strip().lower()
        first_visible = None
        for row in range(self.list.count()):
            item = self.list.item(row)
            hidden = bool(needle and needle not in item.text().lower())
            item.setHidden(hidden)
            if not hidden and first_visible is None:
                first_visible = item
        if first_visible is not None:
            self.list.setCurrentItem(first_visible)

    def _accept_top(self) -> None:
        self._accept_current()

    def _accept_current(self) -> None:
        item = self.list.currentItem()
        if item is not None and not item.isHidden():
            self.selected = item.data(Qt.ItemDataRole.UserRole)
            self.accept()

    def _clear(self) -> None:
        self.cleared = True
        self.selected = None
        self.accept()
