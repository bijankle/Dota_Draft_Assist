"""The History tab's sidebar: what is on the page, and what to measure.

A run is thirteen cards long and the only way to reach the ninth was to
scroll past eight. So the sections are listed down the left, the list
does NOT scroll with the page, clicking a name jumps to it, and the name
of whatever you are looking at is lit.

**AND THE ANALYSIS TICK BOXES LIVE HERE**, at the user's request — "if
you can have the tick boxes on the actual bookmarks as well that would be
nice... don't show tick boxes on the main menu in that case, duplication
will be confusing". They were a three-column grid on the "What to
measure" card, naming the same analyses this list already names,
which is two places to read one thing and two places for it to go stale.
Now the row IS the control: tick it and the section appears below, untick
it and the section goes and the row dims. One name per analysis, and the
switch is on the thing it switches.

Three rules this list lives by, each of them a bug avoided:

1. **IT IS FIXED AND ALWAYS COMPLETE.** Every analysis has a row whether
   it is ticked or not, always in the same order. Listing only what is
   ticked would make the rows jump under the cursor as you tick them,
   which is the fault `_hold_still` exists to prevent one axis over.
2. **A ROW IS DIM WHEN THERE IS NOTHING TO JUMP TO**, and that one rule
   covers every case: an unticked analysis, a findings card with no
   findings in it, and the whole list before a run. Its tick still
   works — that is how you turn the section on.
3. **IT SCROLLS ITSELF IF IT HAS TO.** Fifteen rows is taller than a
   short window, and a tall child sets the whole WINDOW's floor whether
   or not anybody is looking at it — the Debug tab did exactly this and
   took the entire desktop height with it. Inside its own scroll area it
   asks for nothing.

The two hit areas are separate on purpose: the box toggles, the name
jumps. One widget doing both would mean guessing which the user meant
from where in the row they clicked.
"""

from PyQt6.QtCore import QRectF, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QPainter
from PyQt6.QtWidgets import (QFrame, QLabel, QHBoxLayout, QScrollArea,
                             QVBoxLayout, QWidget)

from . import theme
from .chrome import TickBox

# Wide enough for two words of a wrapped name and no wider: this comes
# straight off the tables beside it, and the window's floor is 940.
WIDTH = 178
# How far below the top of the viewport a section has to have reached
# before it counts as the one being read.
LOOK_AHEAD = 28


class SectionRow(QWidget):
    """One line: its tick box if it has one, and its name."""

    jumped = pyqtSignal()
    MARK = 3                    # the lit bar down the left-hand edge

    def __init__(self, ident: str, label: str, tick: bool, parent=None):
        super().__init__(parent)
        self.ident = ident
        self.lit = False
        self.reachable = False
        row = QHBoxLayout(self)
        row.setContentsMargins(self.MARK + 6, 3, 4, 3)
        row.setSpacing(6)
        self.tick = TickBox("") if tick else None
        if self.tick is not None:
            row.addWidget(self.tick, 0, Qt.AlignmentFlag.AlignTop)
        self.name = QLabel(label)
        self.name.setWordWrap(True)
        # A name is only a link while there is something behind it, so the
        # cursor is set by `set_reachable` rather than here.
        self.name.mousePressEvent = self._pressed
        row.addWidget(self.name, 1)
        # PAINT THE STARTING STATE. `set_reachable` returns early when
        # the value has not changed, so a row that is born unreachable
        # and stays that way was never coloured at all — it kept the
        # stylesheet's ordinary TEXT and read as available. Invisible in
        # the History tab, where every row gets switched on and off as
        # analyses are ticked; plain on the setup wizard, where the steps
        # ahead of you are unreachable from the moment they are built and
        # dimming them is the whole way the order reads as forced.
        self._recolour()

    def _pressed(self, event) -> None:
        if self.reachable and event.button() == Qt.MouseButton.LeftButton:
            self.jumped.emit()

    def set_reachable(self, reachable: bool) -> None:
        """Is there a card on the page for this row to jump to?"""
        if reachable == self.reachable:
            return
        self.reachable = reachable
        self.name.setCursor(Qt.CursorShape.PointingHandCursor if reachable
                            else Qt.CursorShape.ArrowCursor)
        self._recolour()

    def set_lit(self, lit: bool) -> None:
        if lit == self.lit:
            return
        self.lit = lit
        self._recolour()
        self.update()

    def _recolour(self) -> None:
        # THE LIT ROW IS THE BRIGHT ONE and an unreachable row is the
        # dimmest, so the three states read apart at a glance without
        # colour meaning anything it does not mean elsewhere in the app.
        colour = (theme.TEXT_STRONG if self.lit
                  else theme.TEXT if self.reachable else theme.TEXT_DIM)
        self.name.setStyleSheet(f"color: {colour}; background: transparent;")

    def paintEvent(self, event) -> None:            # noqa: N802 - Qt naming
        if not self.lit:
            return
        painter = QPainter(self)
        painter.fillRect(QRectF(0, 0, self.MARK, self.height()),
                         QColor(theme.ACCENT))
        painter.end()


class SectionBar(QScrollArea):
    """The whole sidebar. Rows are added once and then only re-lit."""

    jumped = pyqtSignal(str)            # ident of the section to show
    picked = pyqtSignal(str, bool)      # ident, and whether it is now on

    def __init__(self, parent=None):
        super().__init__(parent)
        self.rows: dict[str, SectionRow] = {}
        self.order: list[str] = []
        self.ticks: dict[str, TickBox] = {}
        self._lit: str | None = None
        body = QWidget()
        self._lay = QVBoxLayout(body)
        self._lay.setContentsMargins(6, 12, 6, 12)
        self._lay.setSpacing(1)
        self._lay.addStretch(1)
        self.setWidget(body)
        self.setWidgetResizable(True)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setFixedWidth(WIDTH)

    def add(self, ident: str, label: str, tick: bool = False) -> SectionRow:
        row = SectionRow(ident, label, tick)
        row.jumped.connect(lambda ident=ident: self.jumped.emit(ident))
        if row.tick is not None:
            self.ticks[ident] = row.tick
            row.tick.toggled.connect(
                lambda on, ident=ident: self.picked.emit(ident, on))
        self.rows[ident] = row
        self.order.append(ident)
        self._lay.insertWidget(self._lay.count() - 1, row)
        return row

    def separator(self) -> None:
        """A rule between the controls at the top and the report below.

        A PLAIN WIDGET with a background, never `QFrame.Shape.HLine`: the
        shape is drawn by the frame, and the `border: none` needed to
        stop the stylesheet drawing a second one takes the line away with
        it. Nothing appeared at all. The tick box, the window buttons,
        the count box's arrows and the rules between menu items are all
        painted in this app for the same family of reason.
        """
        line = QWidget()
        line.setFixedHeight(1)
        line.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        line.setStyleSheet(f"background: {theme.BORDER};")
        self._lay.insertSpacing(self._lay.count() - 1, 5)
        self._lay.insertWidget(self._lay.count() - 1, line)
        self._lay.insertSpacing(self._lay.count() - 1, 5)

    def set_reachable(self, idents) -> None:
        """Say which sections are actually on the page right now."""
        have = set(idents)
        for ident, row in self.rows.items():
            row.set_reachable(ident in have)
        if self._lit is not None and self._lit not in have:
            self.light(None)

    def light(self, ident: str | None) -> None:
        if ident == self._lit:
            return
        self._lit = ident
        for key, row in self.rows.items():
            row.set_lit(key == ident)
        if ident is not None:
            self.ensureWidgetVisible(self.rows[ident], 0, 24)

    def lit(self) -> str | None:
        return self._lit


def edge() -> QWidget:
    """A one-pixel vertical rule.

    Used twice: between the sidebar and the page it maps, and between the
    block name and the figure on every summary line. ONE implementation,
    because two would be two chances to draw a different grey.

    A WIDGET OF ITS OWN, not a `border-right` on the SectionBar. This is
    a QScrollArea with `NoFrame`, so its frame width is nought and a
    stylesheet border has nothing to paint into — the rule was declared,
    parsed, and drew absolutely nothing. Same shape of trap as
    `QWidget#titleBar { background: ... }` being ignored without
    `WA_StyledBackground`, and the reason the tick box, the window
    buttons and the rules between menu items are all drawn rather than
    styled. Verified against the PIXELS in `tests/test_section_bar.py`,
    because "it is in the stylesheet" has now twice not meant "it is on
    the screen".

    Without it the list and the cards beside it are one flat expanse of
    one colour, and a sidebar that does not look like a sidebar reads as
    a column of stray text beside the report.
    """
    rule = QWidget()
    rule.setFixedWidth(1)
    rule.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
    rule.setStyleSheet(f"background: {theme.BORDER};")
    return rule
