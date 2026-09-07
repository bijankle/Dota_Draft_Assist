"""Why a suggestion is on the strip — clicked, not hovered.

The strip shows a number and a picture. The number is a SUM, and a sum is
exactly the thing that can look reasonable for bad reasons: a +5 built out
of one enormous matchup is a different suggestion from a +5 built out of
five small ones, and nothing on the tile says which it is.

**What this must never do is explain.** The dataset knows that this hero
wins more than expected against that one; it does not know why, and
neither does the app. So the hero popup lists the terms that made the
number and says outright that the reason is not in the data — the terms
are evidence and the interpretation is the reader's. An invented sentence
about lane pressure would be worse than the blank it replaces.

Item rules are the other way round: they are hand-authored, so they DO
carry a reason in words, and that reason is quoted with its authorship
attached. The label matters — "hand-authored, not measured" is the
difference between a rule and a finding.
"""

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QFrame, QLabel, QVBoxLayout

from . import theme

# How many terms are worth reading at a glance. Past this it is a table,
# and the Analysis tab already has the table.
TOP_TERMS = 6


def hero_reasons(name: str, fit: float, terms) -> tuple[str, list[str], str]:
    """(heading, lines, footnote) for a suggested hero.

    `terms` are `scoring.BreakdownTerm`s, already sorted by size. Only the
    ones that moved the number are worth printing, so a term of zero is
    dropped rather than listed as a reason for nothing.
    """
    heading = f"{name} · fit {fit * 100:+.2f}"
    lines = []
    for term in terms[:TOP_TERMS]:
        if abs(term.delta) < 0.0005:
            continue
        verb = "against" if term.kind == "vs" else "alongside"
        lines.append(f"{term.delta * 100:+.2f}   {verb} {term.other_name}")
    if not lines:
        return heading, [], (
            "Nothing on the board moves this hero either way yet.")
    return heading, lines, (
        "Measured win-rate deltas against the heroes already picked, "
        "biggest first. The data says THAT these pairings go this way, "
        "not why — that part is yours.")


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
