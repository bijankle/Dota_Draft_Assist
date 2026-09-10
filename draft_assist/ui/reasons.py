"""Why an ITEM is on the strip — clicked, not hovered.

An item rule is hand-authored, so it DOES carry a reason in words, and
that reason is quoted here with its authorship attached. The label
matters — "hand-authored, not measured" is the difference between a rule
and a finding, and it is the whole reason this popup still exists when
the hero one does not.

**What this must never do is explain a MEASUREMENT.** The dataset knows
that this hero wins more than expected against that one; it does not know
why, and neither does the app. That is why the hero popup listed terms
and never prose — and why, once those terms could be written on the ten
portraits themselves, the popup had nothing left that the board was not
already saying better.
"""

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QFrame, QLabel, QVBoxLayout

from . import theme

# HERO REASONS ARE GONE, and their terms are on the board instead.
# Clicking a suggestion used to open a box listing the six biggest terms
# behind its number. Those terms ARE the numbers now written on the ten
# portraits — "with +5.2" under each ally, "vs -1.8" under each enemy —
# so the popup was a second, smaller, worse copy of the answer, printed
# over the strip instead of on the heroes it was about. Items keep theirs
# below: an item rule is hand-authored PROSE, which no portrait can show.

def item_reasons(item: str, triggers, stale: bool) -> tuple[str, list[str], str]:
    """(heading, lines, footnote) for a suggested item."""
    lines = [f"{t.hero} (severity {t.severity}) — {t.reason}"
             for t in triggers]
    note = "Hand-authored rule, not measured."
    if stale:
        note += " Unverified this patch."
    return item, lines, note


class ReasonPopup(QFrame):
    """A small panel that closes when you click away.

    `Qt.Popup` rather than a dialog: a modal box in the middle of a draft
    is a box you dismiss without reading, and the draft timer does not
    stop for it.
    """

    def __init__(self, heading: str, lines: list[str], footnote: str,
                 parent=None):
        super().__init__(parent, Qt.WindowType.Popup)
        self.setProperty("card", True)
        self.setStyleSheet(
            f"QFrame {{ background: {theme.BG_ELEVATED}; "
            f"border: 1px solid {theme.BORDER}; border-radius: 6px; }}")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(4)

        title = QLabel(heading)
        title.setProperty("heading", True)
        layout.addWidget(title)
        for line in lines:
            row = QLabel(line)
            row.setWordWrap(True)
            row.setTextInteractionFlags(
                Qt.TextInteractionFlag.TextSelectableByMouse)
            layout.addWidget(row)
        if footnote:
            note = QLabel(footnote)
            note.setWordWrap(True)
            note.setProperty("dim", True)
            note.setMaximumWidth(360)
            layout.addWidget(note)
        self.adjustSize()

    def pop_at(self, global_pos) -> None:
        """Below the tile, nudged back on screen if it would fall off."""
        from PyQt6.QtWidgets import QApplication
        self.move(global_pos)
        screen = QApplication.screenAt(global_pos)
        if screen is not None:
            area = screen.availableGeometry()
            rect = self.frameGeometry()
            rect.moveTopLeft(global_pos)
            if rect.right() > area.right():
                rect.moveRight(area.right() - 4)
            if rect.bottom() > area.bottom():
                rect.moveBottom(area.bottom() - 4)
            self.move(rect.topLeft())
        self.show()
