"""A layout that wraps its items onto the next row instead of scrolling.

The tile strips — the suggested picks and the suggested items — used to be
a QHBoxLayout, which means one row however many tiles are in it. That row
was as wide as its contents, and a widget's minimum is the WINDOW's
minimum, so twenty tiles would have left a window that could not be made
narrow again. Wrapping it in a scroll area fixed the width and bought two
new problems: a strip you have to scroll to read is a strip you do not
read at a glance, which is the one thing these are for, and the wrapper
kept getting its own height wrong.

Wrapping answers all of it. The strip is as wide as it is given, as tall
as the rows it needs, and every tile is on screen.

`heightForWidth` is the whole mechanism: Qt asks the layout how tall it
would be at a given width, and the answer is however many rows the tiles
fall into. A layout that does not answer that question honestly gets its
last row cut off.
"""

from PyQt6.QtCore import QPoint, QRect, QSize, Qt
from PyQt6.QtWidgets import QLayout


class FlowLayout(QLayout):
    def __init__(self, parent=None, margin: int = 0, spacing: int = 8):
        super().__init__(parent)
        self._items: list = []
        self._spacing = spacing
        self.setContentsMargins(margin, margin, margin, margin)

    # -- QLayout plumbing ------------------------------------------------
    def addItem(self, item) -> None:                 # noqa: N802 - Qt naming
        self._items.append(item)

    def insertWidget(self, index: int, widget) -> None:   # noqa: N802
        """The same call QHBoxLayout offered, so the strips read the same.

        The index is where the tile belongs in READING ORDER, which is what
        the strips care about: best fit first, left to right, then down.
        """
        self.addWidget(widget)
        item = self._items.pop()
        self._items.insert(max(0, min(index, len(self._items))), item)

    def count(self) -> int:
        return len(self._items)

    def itemAt(self, index: int):                    # noqa: N802
        return self._items[index] if 0 <= index < len(self._items) else None

    def takeAt(self, index: int):                    # noqa: N802
        if 0 <= index < len(self._items):
            return self._items.pop(index)
        return None

    def expandingDirections(self):                   # noqa: N802
        return Qt.Orientation(0)

    def spacing(self) -> int:
        return self._spacing

    def setSpacing(self, spacing: int) -> None:      # noqa: N802
        self._spacing = spacing

    # -- the wrapping itself ---------------------------------------------
    def hasHeightForWidth(self) -> bool:             # noqa: N802
        return True

    def heightForWidth(self, width: int) -> int:     # noqa: N802
        return self._lay_out(QRect(0, 0, width, 0), apply=False)

    def setGeometry(self, rect: QRect) -> None:      # noqa: N802
        super().setGeometry(rect)
        self._lay_out(rect, apply=True)

    def sizeHint(self) -> QSize:                     # noqa: N802
        return self.minimumSize()

    def minimumSize(self) -> QSize:                  # noqa: N802
        """ONE tile wide. That is the point of wrapping: the strip never
        asks the window to be wide enough for all of it."""
        size = QSize()
        for item in self._items:
            size = size.expandedTo(item.minimumSize())
        left, top, right, bottom = self.getContentsMargins()
        return size + QSize(left + right, top + bottom)

    def _lay_out(self, rect: QRect, apply: bool) -> int:
        """Place the items and return the total height they need."""
        left, top, right, bottom = self.getContentsMargins()
        area = rect.adjusted(left, top, -right, -bottom)
        x, y, row_height = area.x(), area.y(), 0
        for item in self._items:
            hint = item.sizeHint()
            widget = item.widget()
            if widget is not None and not widget.isVisibleTo(
                    widget.parentWidget()):
                # A hidden message label must not reserve a whole row.
                continue
            nudge = x + hint.width()
            if row_height and nudge > area.right() + 1:
                x, y = area.x(), y + row_height + self._spacing
                row_height = 0
            if apply:
                item.setGeometry(QRect(QPoint(x, y), hint))
            x += hint.width() + self._spacing
            row_height = max(row_height, hint.height())
        return y + row_height - rect.y() + bottom


def fits_in_one_row(width: int, tile_width: int, spacing: int = 8) -> int:
    """How many tiles of `tile_width` fit across `width`, at least one.

    This is what "as many as fit on one row" means as a DEFAULT: the strip
    fills the width it has been given and wraps beyond that, so the number
    is a starting point rather than a limit.
    """
    if tile_width <= 0:
        return 1
    return max(1, (width + spacing) // (tile_width + spacing))
