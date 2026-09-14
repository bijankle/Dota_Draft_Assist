"""What each team is made of, on Valve's own role ratings.

The board says WHICH ten heroes; the two grids under it say how the pairs
interact. Neither says the thing a drafter asks out loud — "have we got a
front line", "who initiates", "are we all squishy" — and the game already
scores exactly that: every hero carries a 0-to-3 rating on each of eight
roles (`model/roles.py`). This card adds them up, one row per role, both
teams facing each other across the name.

**THE TWO SIDES FACE EACH OTHER ACROSS THE ROLE, and both bars grow
OUTWARD from it.** The question this card exists to answer is a
comparison, and two bars are only comparable when they start at the same
place: filled from the outside in, a four and a three would begin at
different x and the eye would have to measure rather than look. It is the
spread bar's rule from the History tab — each label runs away from its own
dot — one axis over.

**A PILL IS A ROUNDED SHARE, AND THE EMPTY ONES STAY DRAWN.** Five pills
is the user's number. Drawing only the filled ones would make "2 of 5"
and "2 of 3" the same picture, and the denominator is the whole point of
normalising by picks in the first place.

**EVERY PILL IS THE FRAME'S GOLD**, at the user's request — "i dont want
you to make the color red / green just make it all gold, like the border
of the app window... later on i may revisit color basis". This REVERSES
the red/green rule asked for one message earlier, where each half was to
be green on the roles that side led and red on the ones it trailed.
Gold is already the app's "this one" colour rather than a judgement — the
window's border, the focus ring and the suggestion star all wear it — so
a card of gold pills reads as a measurement, which is what it is.

**THE LEAD IS STILL COMPUTED AND STILL CARRIED**, though nothing paints
it: `PillRow.lead` is set on every row and the tooltip says which side is
ahead. Colouring by it again is one line in `_colour`, which is the point
of not deleting the arithmetic the moment it stopped being drawn.

**EXACT FIGURES LIVE IN THE TOOLTIP.** A pill count is rounded, so a row
that reads 3 against 3 can be 0.52 against 0.61 — the tooltip carries the
sums, the denominators and both percentages, and the row still says at a
glance which way it goes.
"""

from __future__ import annotations

from PyQt6.QtCore import QRectF, Qt
from PyQt6.QtGui import QColor, QPainter, QPen
from PyQt6.QtWidgets import (QGridLayout, QLabel, QSizePolicy, QVBoxLayout,
                             QWidget)

from ..model import roles as roles_mod
from . import theme

# A PILL IS SMALL ON PURPOSE. This card sits between the ten picks and
# the advice about them, so its height is paid for by the suggestion
# strip, the item strip and both grids below it — and at the first sizes
# tried it cost 174px, which took the Draft tab past the window's height
# and left the suggestion strip five pixels short of the two rows it had
# asked `heightForWidth` for. Ten tiles were laid out below the strip's
# own bottom edge. Smaller pills fit another group across the same width,
# which is a row of roles fewer, which is the height back.
PILL_W = 13
PILL_H = 10
PILL_GAP = 3
RADIUS = 2.5
EMPTY_PEN = 1.2


class PillRow(QWidget):
    """One side's share of one role, as `roles_mod.PILLS` pills."""

    def __init__(self, grows_right: bool, parent=None):
        super().__init__(parent)
        # Which end the filled pills start from. Both sides start at the
        # role's name and grow away from it, so the ALLY row — which sits
        # to the left of the name — fills from its right-hand end.
        self._grows_right = bool(grows_right)
        self._filled = 0
        self._lead = 0
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self.setFixedSize(
            roles_mod.PILLS * PILL_W + (roles_mod.PILLS - 1) * PILL_GAP,
            PILL_H + 6)

    def set_share(self, filled: int, lead: int) -> None:
        filled = max(0, min(int(filled), roles_mod.PILLS))
        if (filled, int(lead)) == (self._filled, self._lead):
            return
        self._filled, self._lead = filled, int(lead)
        self.update()

    @property
    def filled(self) -> int:
        return self._filled

    @property
    def lead(self) -> int:
        return self._lead

    def _colour(self) -> QColor:
        """One colour for every pill, at the user's request.

        `self._lead` is deliberately not consulted here — see the module
        docstring. It is kept up to date so that colouring by it again is
        a change to this method and nothing else.
        """
        return QColor(theme.FRAME_GOLD)

    def paintEvent(self, event) -> None:            # noqa: N802 - Qt naming
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        top = (self.height() - PILL_H) / 2.0
        fill = self._colour()
        outline = QPen(QColor(theme.BORDER), EMPTY_PEN)
        for slot in range(roles_mod.PILLS):
            # `slot` counts from the end the bar grows FROM, so the first
            # filled pill of each side is the one nearest the role name.
            at = slot if self._grows_right else roles_mod.PILLS - 1 - slot
            box = QRectF(at * (PILL_W + PILL_GAP), top, PILL_W, PILL_H)
            if slot < self._filled:
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(fill)
            else:
                painter.setPen(outline)
                painter.setBrush(Qt.BrushStyle.NoBrush)
                # HALF A PEN IN, or an outline centred on the rectangle's
                # own edge loses its outer half to the widget boundary and
                # the empty pills read thinner than they are. Same rule as
                # the focus ring.
                box = box.adjusted(EMPTY_PEN / 2, EMPTY_PEN / 2,
                                   -EMPTY_PEN / 2, -EMPTY_PEN / 2)
            painter.drawRoundedRect(box, RADIUS, RADIUS)
        painter.end()


class RoleBar(QWidget):
    """Eight roles, both teams, facing each other across the names.

    **THE NUMBER OF GROUPS FOLLOWS THE WIDTH**, at the user's request —
    "you can actually make them multi column if they are very narrow...
    e.g. 6 rows make it 3 x 2". A role's row is two five-pill bars and a
    name, which is narrow; one column of eight was 294px tall in a window
    whose whole default height is 998, floating in the middle of a card
    with two empty thirds either side. This card sits between the ten
    picks and the advice about them, so every pixel it takes pushes the
    suggestions, the items and both grids down.

    So the widget measures what one group costs and fits as many across
    as the width allows, one to eight. It is the suggestion strips' rule
    — "as many as fit on one row" — for a block rather than a strip.

    **IT RE-LAYS OUT ONLY WHEN THE COUNT CHANGES.** `resizeEvent` fires
    during layout, and moving widgets lays the parent out again: reacting
    to every pixel would be the unbounded loop `_match_grid_portraits`
    carries a guard against, and Qt ABORTS the process for that rather
    than raising, so there is no traceback to find it by.

    **AND THE WIDGETS ARE MOVED, NEVER REBUILT.** Each row owns its
    tooltip and its current fill, so tearing the rows down on a window
    drag would drop what the card is showing and re-score it — and a
    destroyed C++ object behind a live Python wrapper is the trap the
    History tab's item block already found.

    **EACH GROUP CARRIES ITS OWN PAIR OF HEADINGS.** Side by side, the
    right-hand pills of one group sit next to the left-hand pills of the
    next, and with one pair of headings across the top there is nothing
    on the card saying that the run of pills in the middle is two
    different teams. Naming both sides over every group costs one line
    and removes the one way this layout can be misread.
    """

    # Room between one group and the next, and what a group needs before
    # another one is worth having.
    GROUP_GAP = 20

    def __init__(self, parent=None):
        super().__init__(parent)
        self._grid = QGridLayout(self)
        self._grid.setContentsMargins(0, 0, 0, 0)
        self._grid.setHorizontalSpacing(6)
        self._grid.setVerticalSpacing(3)
        self._rows: dict[str, tuple[PillRow, QLabel, PillRow]] = {}
        self._heads: list[tuple[QLabel, QLabel]] = []
        self._groups = 0
        self._ally_name = ""
        self._enemy_name = ""

        for role in roles_mod.ROLES:
            ally = PillRow(grows_right=False, parent=self)
            name = QLabel(role, self)
            name.setAlignment(Qt.AlignmentFlag.AlignCenter)
            enemy = PillRow(grows_right=True, parent=self)
            self._rows[role] = (ally, name, enemy)
        # One heading pair per group we could ever need. Built up front
        # and PARENTED: a parentless QWidget in this app is a second
        # window in the taskbar the moment anything shows it.
        for _ in roles_mod.ROLES:
            ally_head = QLabel("", self)
            ally_head.setProperty("dim", True)
            ally_head.setAlignment(Qt.AlignmentFlag.AlignRight
                                   | Qt.AlignmentFlag.AlignVCenter)
            enemy_head = QLabel("", self)
            enemy_head.setProperty("dim", True)
            enemy_head.setAlignment(Qt.AlignmentFlag.AlignLeft
                                    | Qt.AlignmentFlag.AlignVCenter)
            self._heads.append((ally_head, enemy_head))

        # The names are one width across every group, so the rows of one
        # group line up with the rows of the next rather than reproducing
        # a ragged edge per column. The History tab's `_align_names`
        # lesson: a grid aligns its own rows and cannot agree with
        # another grid's.
        self._align_names()
        self._relayout(1)

    # ---- how many fit ---------------------------------------------------
    def _group_width(self) -> int:
        ally, name, enemy = self._rows[roles_mod.ROLES[0]]
        return (ally.width() + name.width() + enemy.width()
                + 2 * self._grid.horizontalSpacing())

    def groups_for(self, width: int) -> int:
        """How many groups fit across `width`, at least one."""
        each = self._group_width() + self.GROUP_GAP
        if each <= 0:
            return 1
        return max(1, min(len(roles_mod.ROLES), (width + self.GROUP_GAP)
                          // each))

    @property
    def groups(self) -> int:
        return self._groups

    def resizeEvent(self, event) -> None:           # noqa: N802 - Qt naming
        super().resizeEvent(event)
        self._fit()

    def showEvent(self, event) -> None:             # noqa: N802 - Qt naming
        """Qt does not deliver a resize to a HIDDEN widget.

        This card lives on the Draft tab, and a tab widget hides the
        pages it is not showing — so a window resized while the History
        tab was open reaches here as one resize on the way back, and
        asking again when it appears is what makes that certain rather
        than probable. Same reason `BucketTable` re-fits on show.
        """
        super().showEvent(event)
        self._fit()

    def _fit(self) -> None:
        want = self.groups_for(self.width())
        if want != self._groups:
            self._relayout(want)

    def _relayout(self, groups: int) -> None:
        groups = max(1, int(groups))
        # NO EMPTY GROUP AT THE END. Eight roles across five groups is two
        # each and the fifth gets nothing — which drew a pair of "Radiant
        # Dire" headings over thin air in the corner of the card. The
        # width may allow five; the roles only fill four, so the count is
        # what the SLICES need rather than what the width would permit.
        per = -(-len(roles_mod.ROLES) // groups)         # ceiling
        groups = -(-len(roles_mod.ROLES) // per)         # and back again
        self._groups = groups
        grid = self._grid
        while grid.count():
            grid.takeAt(0)
        for column in range(grid.columnCount()):
            grid.setColumnStretch(column, 0)

        for group in range(groups):
            base = group * 4
            ally_head, enemy_head = self._heads[group]
            grid.addWidget(ally_head, 0, base + 0)
            grid.addWidget(enemy_head, 0, base + 2)
            ally_head.show()
            enemy_head.show()
            slice_ = roles_mod.ROLES[group * per:(group + 1) * per]
            for line, role in enumerate(slice_, start=1):
                ally, name, enemy = self._rows[role]
                grid.addWidget(ally, line, base + 0,
                               Qt.AlignmentFlag.AlignRight
                               | Qt.AlignmentFlag.AlignVCenter)
                grid.addWidget(name, line, base + 1)
                grid.addWidget(enemy, line, base + 2,
                               Qt.AlignmentFlag.AlignLeft
                               | Qt.AlignmentFlag.AlignVCenter)
                for widget in (ally, name, enemy):
                    widget.show()
            for offset in (0, 1, 2):
                grid.setColumnStretch(base + offset, 0)
            # The spacer between groups takes every spare pixel, so the
            # groups stay evenly spread rather than bunching left.
            grid.setColumnStretch(base + 3, 1)
        # Heading pairs this width does not use would otherwise sit at
        # (0, 0) drawing over the first group — the throwaway-QLabel trap
        # the History tab's sidebar already found.
        for spare in self._heads[groups:]:
            for widget in spare:
                widget.hide()

    def _align_names(self) -> None:
        widest = 0
        for _ally, name, _enemy in self._rows.values():
            name.ensurePolished()     # or the font is not the stylesheet's
            widest = max(widest, name.sizeHint().width())
        for _ally, name, _enemy in self._rows.values():
            name.setFixedWidth(widest)

    # ---- what it says ---------------------------------------------------
    def set_sides(self, ally: str, enemy: str) -> None:
        self._ally_name, self._enemy_name = ally, enemy
        for ally_head, enemy_head in self._heads:
            ally_head.setText(ally)
            enemy_head.setText(enemy)

    def show_draft(self, allies, enemies) -> None:
        """Score both line-ups and redraw every row."""
        ours = roles_mod.team_scores(allies)
        theirs = roles_mod.team_scores(enemies)
        verdict = roles_mod.compare(ours, theirs)
        for mine, yours, lead in zip(ours, theirs, verdict):
            ally, name, enemy = self._rows[mine.role]
            ally.set_share(mine.pills, lead)
            enemy.set_share(yours.pills, -lead)
            tip = _explain(mine, yours)
            for widget in (ally, name, enemy):
                widget.setToolTip(tip)


def _explain(mine, yours) -> str:
    """The exact figures a rounded pill count cannot carry."""
    def half(score) -> str:
        if not score.possible:
            return "nothing rated yet"
        return (f"{score.scored} of {score.possible} "
                f"({score.share * 100:.0f}%)")
    if not mine.possible or not yours.possible:
        lead = "Not comparable until both sides have a pick."
    elif abs(mine.share - yours.share) < 1e-9:
        lead = "The two sides are level here."
    elif mine.share > yours.share:
        lead = "This side leads this role."
    else:
        lead = "The other side leads this role."
    return (f"{mine.role}\n"
            f"This side: {half(mine)}\n"
            f"Other side: {half(yours)}\n"
            f"{lead}\n"
            f"Out of 3 per pick, so the two are comparable "
            f"before both teams are full.")
