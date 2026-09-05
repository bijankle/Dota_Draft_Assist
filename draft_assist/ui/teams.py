"""The two team columns on the Draft tab.

The draft is the thing the user actually reads, so it gets the whole top
half of the window: your five on the left, theirs on the right, in the
order the feed gives them. Each slot reserves a line ABOVE the hero for a
signed number, which is how one hero's relationship to the other nine is
shown — click Sniper and every other portrait says, in green or red, what
it is worth beside or against him.

The line is reserved whether or not it holds a number: slots that jumped by
a text height every time something was clicked made the whole column
restless, and a draft panel that moves under the cursor is one you misclick.
"""

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (QFrame, QHBoxLayout, QLabel, QPushButton,
                             QVBoxLayout, QWidget)

from . import theme

# "with" and "vs" are different questions and the eye should not have to
# read a legend to tell which it is looking at. Words rather than glyphs:
# a symbol that falls back to a box on the user's font would say nothing.
KIND_MARK = {"with": "with", "vs": "vs"}


class HeroSlot(QWidget):
    """One pick: a signed relation above, the hero button below."""

    def __init__(self, side: str, index: int, parent=None):
        super().__init__(parent)
        self.side = side
        self.index = index

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        # No gap at all between a number and the hero it describes; the
        # breathing room goes BETWEEN slots instead, so a delta can never
        # look like it belongs to the row above.
        lay.setSpacing(0)

        self.delta = QLabel("")
        self.delta.setTextFormat(Qt.TextFormat.RichText)
        self.delta.setAlignment(Qt.AlignmentFlag.AlignHCenter
                                | Qt.AlignmentFlag.AlignBottom)
        self.delta.setMinimumHeight(self.fontMetrics().height() + 2)
        lay.addWidget(self.delta)

        self.button = QPushButton("+")
        self.button.setProperty("slot", True)
        self.button.setProperty("side", side)
        self.button.setProperty("slot_index", index)
        # Font metrics rather than a guessed pixel count: the user's Windows
        # font is not this machine's and may be scaled.
        self.button.setMinimumHeight(self.fontMetrics().height() + 16)
        self.button.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        lay.addWidget(self.button)

    # ---- the relation line ---------------------------------------------
    def show_delta(self, delta: float, kind: str) -> None:
        colour = theme.GOOD if delta >= 0 else theme.BAD
        mark = KIND_MARK.get(kind, "")
        self.delta.setText(
            f"<span style='color:{theme.TEXT_DIM}'>{mark}</span> "
            f"<span style='color:{colour}'><b>{delta * 100:+.1f}</b></span>")

    def show_note(self, text: str) -> None:
        self.delta.setText(
            f"<span style='color:{theme.TEXT_DIM}'>{text}</span>")

    def clear_delta(self) -> None:
        self.delta.setText("")

    # ---- the focused pick ----------------------------------------------
    def set_focused(self, on: bool) -> None:
        self.button.setProperty("focused", bool(on))
        # Qt only re-reads dynamic properties in a stylesheet when told to.
        self.button.style().unpolish(self.button)
        self.button.style().polish(self.button)


class TeamColumn(QFrame):
    """Five slots under one heading — one half of the draft."""

    def __init__(self, side: str, caption: str, parent=None):
        super().__init__(parent)
        self.side = side
        self.setProperty("card", True)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(12, 10, 12, 12)
        lay.setSpacing(12)

        head = QHBoxLayout()
        self.caption = QLabel(caption)
        self.caption.setProperty("heading", True)
        head.addWidget(self.caption)
        head.addStretch(1)
        self.note = QLabel("")
        self.note.setProperty("dim", True)
        head.addWidget(self.note)
        lay.addLayout(head)

        self.slots = [HeroSlot(side, i, self) for i in range(5)]
        for slot in self.slots:
            lay.addWidget(slot)
        lay.addStretch(1)

    @property
    def buttons(self) -> list[QPushButton]:
        return [s.button for s in self.slots]

    def clear_deltas(self) -> None:
        for slot in self.slots:
            slot.clear_delta()
            slot.set_focused(False)
