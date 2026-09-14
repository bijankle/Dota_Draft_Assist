"""What each team is made of, on Valve's own role ratings.

The board says WHICH ten heroes; the two grids under it say how the pairs
interact. Neither says the thing a drafter asks out loud — "have we got a
front line", "who initiates", "are we all squishy" — and the game already
scores exactly that: every hero carries a 0-to-3 rating on each of eight
roles (`model/roles.py`). This card adds them up, one cell per role per team.

**THE CARD IS SPLIT DOWN THE MIDDLE AND THE NAMES ARE REPEATED**, at the
user's request, and it REVERSES the arrangement that stood here — two
bars facing each other across one shared role name, under a "Radiant" and
"Dire" heading per group. Those headings are what went first: "there
should not be a header for radiant and dire... its just if it sits under
radiant its radiant and likewise for dire, divided by the same central
line". Asked which of two shapes that meant, they were explicit: "I mean
you repeat the header, and you know which team it belongs to because all
headers on the left are radiant, right are dire — by header I mean
support, carry, etc."

So POSITION carries the team, exactly as it does on the board above:
everything left of the centre rule is Radiant, everything right is Dire,
and the rule sits where the gap between the two team panels sits. A cell
is a role name and its five pills, which is what was asked for:

    Carry - XXXXX | Nuker - XXXXX | Durable - XXXXX | Pusher - XXXXX
    Support - XXXXX | Disabler - XXXXX | Escape - XXXXX | Initiator - XXXXX

per side. The cost is that each role is named twice on the card; the gain
is that no cell needs a label saying whose it is, and the card reads the
same way round as the ten portraits above it.

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
glance which way it goes. Both halves of a role carry the SAME tooltip,
so hovering either side answers the comparison the split no longer makes
on one line.

**AND ITS MINIMUM WIDTH IS ONE COLUMN, WHICH IS THE WHOLE REASON IT
REFLOWS.** The first version laid four groups out and reported all four
as its minimum — 1022px — against a window floor of 940. Inside the
Draft tab's scroll area that does not wrap or clip: the page simply
stops shrinking, so the team panels were pinned at 925px wide AT EVERY
WINDOW SIZE and a horizontal scrollbar appeared instead. "I also feel
like portraits are not scaling down as I make the window smaller" was
exactly that, and it was this card's doing. A widget's minimum is the
window's minimum; a card that reflows has to ask for one column.
"""

from __future__ import annotations

from PyQt6.QtCore import QRectF, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QPainter, QPen
from PyQt6.QtWidgets import (QGridLayout, QHBoxLayout, QLabel,
                             QSizePolicy, QWidget)

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


class ReflowGrid(QWidget):
    """A block of equal cells that picks its column count from its width.

    TWO THINGS IN THIS APP NEED THIS and they sit one above the other:
    the Roles card and the role filter on the Suggested picks heading.
    Both are eight roles in a tidy grid, both are read at a glance, and
    both were written with a FIXED number of columns — which is how the
    Draft tab ended up with a minimum width of 1314px against a window
    floor of 940, a permanent horizontal scrollbar, and ten portraits
    that could not shrink. One implementation, because two would be two
    chances to get the arithmetic that caused that wrong again.

    **THE COUNTS ARE DIVISORS OF EIGHT** (4, 2, 1), so the last column is
    never short — a ragged final column reads as a cell having gone
    missing rather than as a layout choice.

    **AND THE MINIMUM IS ONE COLUMN.** A widget's minimum is the window's
    minimum, so a block that reflows has to SAY it reflows; left to Qt
    this reports whatever layout happens to be in place, which is the
    widest one it has ever been given.

    Subclasses say how wide a cell is and how to place them.
    """

    COLUMNS = (4, 2, 1)
    GAP = 18            # between one column and the next
    HALVES = 1          # how many independent blocks share the width

    def __init__(self, parent=None):
        super().__init__(parent)
        self._columns = 0
        self._fitting = False
        # NOTHING BELOW MAY BE ASKED ANYTHING UNTIL THE SUBCLASS HAS
        # BUILT ITS CELLS. `minimumSizeHint`, `resizeEvent` and
        # `showEvent` are Qt VIRTUALS: Qt calls them from C++ while the
        # constructor is still running — installing a layout is enough to
        # trigger one — and they reach `_cell_width`, which reads widgets
        # that do not exist yet. The result is not a tidy AttributeError
        # from inside a virtual: the process SEGFAULTS, and only when
        # some earlier test happened to leave Qt in a state that asked
        # the question at the wrong moment. Subclasses set this last.
        self._ready = False

    # ---- what a subclass supplies --------------------------------------
    def _cell_width(self) -> int:
        raise NotImplementedError

    @staticmethod
    def _widest(widget) -> int:
        """A widget's width, or what it WANTS if it has not been laid out.

        `_cell_width` is asked during construction — before the first
        layout pass — and `width()` is the default 100 until then. The
        filter measured its cell at that and concluded one column fitted
        in any width at all, so it never reflowed to the two rows of four
        it was asked for. Both numbers are right at different moments;
        the larger is right at both.
        """
        return max(widget.width(), widget.sizeHint().width())

    def _extra(self) -> int:
        """Room the layout needs that is not cells (a centre rule)."""
        return 0

    def _relayout(self, columns: int) -> None:
        raise NotImplementedError

    # ---- the fit --------------------------------------------------------
    @property
    def columns(self) -> int:
        return self._columns

    def columns_for(self, width: int) -> int:
        """How many columns each half gets at `width`, at least one."""
        each = self._cell_width() + self.GAP
        if each <= 0:
            return 1
        room = (width - self._extra()) / max(1, self.HALVES)
        for count in self.COLUMNS:
            if count * each - self.GAP <= room:
                return count
        return 1

    def minimumSizeHint(self):                  # noqa: N802 - Qt naming
        hint = super().minimumSizeHint()
        if not self._ready:
            return hint
        one = self._cell_width() * self.HALVES + self._extra()
        hint.setWidth(one if hint.width() <= 0 else min(hint.width(), one))
        return hint

    def resizeEvent(self, event) -> None:       # noqa: N802 - Qt naming
        super().resizeEvent(event)
        self._fit()

    def showEvent(self, event) -> None:         # noqa: N802 - Qt naming
        """Qt does not deliver a resize to a HIDDEN widget.

        Both users of this live on the Draft tab, and a tab widget hides
        the pages it is not showing — so a window resized while the
        History tab was open reaches here as one resize on the way back.
        Asking again when it appears is what makes that certain rather
        than probable; the same reason `BucketTable` re-fits on show.
        """
        super().showEvent(event)
        self._fit()

    def _fit(self) -> None:
        """RE-LAY OUT ONLY WHEN THE COUNT CHANGES, AND NEVER INSIDE
        ITSELF.

        Two guards, and the second one was paid for. `resizeEvent` fires
        during layout and moving widgets lays the parent out again — and
        when this block is the thing that decides its own width (the
        role filter takes the Suggested picks heading's spare space), the
        new column count changes the width that chose it. That is the
        unbounded loop `_match_grid_portraits` carries a guard against,
        and Qt does not raise for it: the process SEGFAULTS, with the
        traceback pointing at whatever test happened to be running.
        """
        if self._fitting or not self._ready:
            return
        want = self.columns_for(self.width())
        if want == self._columns:
            return
        self._fitting = True
        try:
            self._relayout(want)
        finally:
            self._fitting = False


class RoleBar(ReflowGrid):
    """Eight roles, twice: Radiant's on the left, Dire's on the right.

    **THE COLUMN COUNT FOLLOWS THE WIDTH.** A cell is a name and five
    pills, which is narrow; eight of them in one column would be a card
    294px tall in a window whose whole default height is 998. This card
    sits between the ten picks and the advice about them, so every pixel
    it takes pushes the suggestions, the items and both grids down — and
    every pixel of WIDTH it demands is width the ten picks do not get.

    So each half fits as many columns as it has room for, and BOTH HALVES
    ALWAYS USE THE SAME COUNT: they are mirror images about the centre
    rule, and two halves wrapping differently would break the one thing
    that says which team a cell belongs to. The counts are the divisors
    of eight — 4, 2, 1 — so the last column is never short.

    **IT RE-LAYS OUT ONLY WHEN THE COUNT CHANGES.** `resizeEvent` fires
    during layout, and moving widgets lays the parent out again: reacting
    to every pixel would be the unbounded loop `_match_grid_portraits`
    carries a guard against, and Qt ABORTS the process for that rather
    than raising, so there is no traceback to find it by.

    **AND THE WIDGETS ARE MOVED, NEVER REBUILT.** Each cell owns its
    tooltip and its current fill, so tearing them down on a window drag
    would drop what the card is showing and re-score it — and a destroyed
    C++ object behind a live Python wrapper is the trap the History tab's
    item block already found.
    """

    # Two halves — Radiant's roles and Dire's — sharing the width, with
    # the centre rule between them.
    HALVES = 2
    CENTRE_GAP = 14

    def __init__(self, parent=None):
        super().__init__(parent)
        # TWO EQUAL HALVES WITH THE RULE BETWEEN THEM, rather than one
        # grid with a rule column somewhere in the middle of it. The
        # halves carry the same stretch, so the rule is at the card's
        # centre BY CONSTRUCTION — where a column index has to be
        # arithmetic that happens to come out even, and did not: it
        # landed 13px left of centre, which is exactly the kind of
        # "looks like the right number" error the grid borders were
        # got wrong four times by.
        line = QHBoxLayout(self)
        line.setContentsMargins(0, 0, 0, 0)
        line.setSpacing(self.CENTRE_GAP)
        self._halves: dict[str, tuple[QWidget, QGridLayout]] = {}
        self._cells: dict[str, dict[str, tuple[QLabel, PillRow]]] = {
            "ally": {}, "enemy": {}}

        for side in ("ally", "enemy"):
            half = QWidget(self)
            half.setProperty("bare", True)
            grid = QGridLayout(half)
            grid.setContentsMargins(0, 0, 0, 0)
            grid.setHorizontalSpacing(6)
            grid.setVerticalSpacing(3)
            self._halves[side] = (half, grid)
            for role in roles_mod.ROLES:
                name = QLabel(role, half)
                name.setProperty("dim", True)
                name.setAlignment(Qt.AlignmentFlag.AlignRight
                                  | Qt.AlignmentFlag.AlignVCenter)
                # BOTH SIDES GROW THE SAME WAY now that each has its own
                # name to its left. The old card had them growing outward
                # from a SHARED name, which is what made two bars
                # comparable on one line; with the halves split there is
                # no shared origin to grow away from, and a mirrored
                # right half would put Dire's names down the middle of
                # the card where the rule goes.
                self._cells[side][role] = (name, PillRow(grows_right=True,
                                                         parent=half))
            if side == "ally":
                line.addWidget(half, 1)
                # THE CENTRE RULE, the same 1px widget the History tab's
                # sidebar and name column use — two implementations of
                # one grey line is two chances to draw a different grey.
                # PARENTED AT ONCE: `edge()` hands back a parentless
                # QWidget, and a parentless QWidget in this app is a
                # second window in the taskbar the moment anything shows
                # it.
                from .section_bar import edge
                self._rule = edge()
                self._rule.setParent(self)
                line.addWidget(self._rule)
            else:
                line.addWidget(half, 1)

        self._ally_name = ""
        self._enemy_name = ""
        self._align_names()
        self._ready = True
        self._relayout(self.COLUMNS[0])

    # ---- how many fit ---------------------------------------------------
    def _cell_width(self) -> int:
        name, pills = self._cells["ally"][roles_mod.ROLES[0]]
        _half, grid = self._halves["ally"]
        return (self._widest(name) + self._widest(pills)
                + grid.horizontalSpacing())

    def _extra(self) -> int:
        return self.CENTRE_GAP * 2 + 1

    def _relayout(self, columns: int) -> None:
        columns = max(1, int(columns))
        per = -(-len(roles_mod.ROLES) // columns)       # rows per column
        columns = -(-len(roles_mod.ROLES) // per)       # and back again
        self._columns = columns
        for side, (_half, grid) in self._halves.items():
            while grid.count():
                grid.takeAt(0)
            for column in range(grid.columnCount()):
                grid.setColumnStretch(column, 0)
                grid.setColumnMinimumWidth(column, 0)
            for index, role in enumerate(roles_mod.ROLES):
                line, column = index % per, (index // per) * 3
                name, pills = self._cells[side][role]
                grid.addWidget(name, line, column,
                               Qt.AlignmentFlag.AlignRight
                               | Qt.AlignmentFlag.AlignVCenter)
                grid.addWidget(pills, line, column + 1,
                               Qt.AlignmentFlag.AlignLeft
                               | Qt.AlignmentFlag.AlignVCenter)
                name.show()
                pills.show()
            # The gap between cells is FIXED and the slack goes at the
            # end, so the two halves hold their cells the same distance
            # apart whatever width they are given. Spread by stretch
            # instead, each half's spacing followed its own width and
            # the mirror stopped being a mirror.
            for column in range(columns - 1):
                grid.setColumnMinimumWidth(column * 3 + 2, self.GAP)
            grid.setColumnStretch((columns - 1) * 3 + 2, 1)

    def _align_names(self) -> None:
        widest = 0
        for side in self._cells.values():
            for name, _pills in side.values():
                name.ensurePolished()   # or the font is not the stylesheet's
                widest = max(widest, name.sizeHint().width())
        for side in self._cells.values():
            for name, _pills in side.values():
                name.setFixedWidth(widest)

    # ---- what it says ---------------------------------------------------
    def set_sides(self, ally: str, enemy: str) -> None:
        """Which side is which, for the TOOLTIPS.

        Nothing on the card draws these any more — position says it — but
        a tooltip that reads "this side" and "the other side" beside a
        card with no headings is worse than one that names them.
        """
        self._ally_name, self._enemy_name = ally, enemy

    def show_draft(self, allies, enemies) -> None:
        """Score both line-ups and redraw every cell."""
        ours = roles_mod.team_scores(allies)
        theirs = roles_mod.team_scores(enemies)
        verdict = roles_mod.compare(ours, theirs)
        for mine, yours, lead in zip(ours, theirs, verdict):
            ally_name, ally_pills = self._cells["ally"][mine.role]
            enemy_name, enemy_pills = self._cells["enemy"][mine.role]
            ally_pills.set_share(mine.pills, lead)
            enemy_pills.set_share(yours.pills, -lead)
            tip = _explain(mine, yours, self._ally_name, self._enemy_name)
            for widget in (ally_name, ally_pills, enemy_name, enemy_pills):
                widget.setToolTip(tip)


class RoleFilter(ReflowGrid):
    """How strong a suggestion has to be in each role, 0 to 3.

    THE OTHER HALF OF THE ROLES CARD, and it sits on the Suggested picks
    heading for the reason every count box in this app moved out of
    Settings: a number you tune by looking at the result belongs beside
    the result. The card above says what the draft is short of; this cuts
    the strip to heroes that answer it.

    **A NUMBER, NOT A TICK**, at the user's request: "instead of a tick
    box it would be nice to have a number input (up / down arrow) for
    each allowing 1, 2, 3 only... that way if you need a really strong
    support example you can filter the suggested heroes well". The value
    is the LOWEST rating that passes on Valve's own 0-to-3 scale, so
    nought is the filter off — exactly what an unticked box meant, with 1
    being what a ticked one meant, so nobody's saved filter was lost to
    the change.

    **TWO ROWS OF FOUR**, as asked, which is a clean shape only because
    Valve scores EIGHT roles; the nine everybody lists includes Jungler,
    which has no hero data behind it at all, and a 3x3 with a dead corner
    is what a ninth would have cost. **Nothing draws a grid** — no lines,
    no header, no cell borders — also at their request: "when you say
    grid i dont want it to look like a grid, just said it in terms of row
    / column so that they fit nicely".

    **AND IT REFLOWS**, which is new and is why it lives here beside the
    card it belongs to rather than as a method on the window. Fixed at
    four columns it asked for 644px, which made the Suggested picks card
    1030px wide at its narrowest — over the window's own 940 floor, so
    the Draft page stopped shrinking and the ten portraits could not
    scale down. See `ReflowGrid`.
    """

    picked = pyqtSignal()

    def __init__(self, wanted: dict, parent=None):
        super().__init__(parent)
        from . import chrome
        self.setProperty("bare", True)      # see `_picks_controls`
        # It must be ALLOWED to grow, or the heading's layout hands it
        # its own sizeHint and it can never see room it is not already
        # using. `minimumSizeHint` still says one column, so growing
        # freely costs the window's floor nothing.
        self.setSizePolicy(QSizePolicy.Policy.Expanding,
                           QSizePolicy.Policy.Preferred)
        grid = QGridLayout(self)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(6)
        grid.setVerticalSpacing(2)
        self._grid = grid
        self.boxes: dict[str, object] = {}
        self._labels: dict[str, QLabel] = {}
        for role in roles_mod.ROLES:
            name = QLabel(role, self)
            name.setProperty("dim", True)
            name.setAlignment(Qt.AlignmentFlag.AlignRight
                              | Qt.AlignmentFlag.AlignVCenter)
            box = chrome.CountBox(int(wanted.get(role, 0)), 0,
                                  roles_mod.MAX_LEVEL)
            box.setParent(self)
            box.setToolTip(
                f"Only suggest heroes Dota scores at least this highly in "
                f"{role}, on its own 1-to-3 scale.\n"
                "Nought is off. Several set means a hero has to clear "
                "all of them.")
            # WIRED AFTER THE VALUE IS SET: restoring what the file said
            # is not the user choosing it, and an unblocked restore would
            # write the settings file on every start and re-cut a strip
            # that does not exist yet.
            box.valueChanged.connect(lambda _v: self.picked.emit())
            self._labels[role], self.boxes[role] = name, box
        self._align_names()
        self._ready = True
        self._relayout(self.COLUMNS[0])

    def _align_names(self) -> None:
        widest = 0
        for name in self._labels.values():
            name.ensurePolished()    # or the font is not the stylesheet's
            widest = max(widest, name.sizeHint().width())
        for name in self._labels.values():
            name.setFixedWidth(widest)

    def _cell_width(self) -> int:
        role = roles_mod.ROLES[0]
        return (self._widest(self._labels[role])
                + self._widest(self.boxes[role])
                + self._grid.horizontalSpacing())

    def _relayout(self, columns: int) -> None:
        columns = max(1, int(columns))
        per = -(-len(roles_mod.ROLES) // columns)       # rows per column
        columns = -(-len(roles_mod.ROLES) // per)       # and back again
        self._columns = columns
        grid = self._grid
        while grid.count():
            grid.takeAt(0)
        for column in range(grid.columnCount()):
            grid.setColumnStretch(column, 0)
        for index, role in enumerate(roles_mod.ROLES):
            line, column = index % per, (index // per) * 3
            grid.addWidget(self._labels[role], line, column,
                           Qt.AlignmentFlag.AlignRight
                           | Qt.AlignmentFlag.AlignVCenter)
            grid.addWidget(self.boxes[role], line, column + 1)
            self._labels[role].show()
            self.boxes[role].show()
        # SNUG, WITH THE SLACK ON THE RIGHT. Spreading the cells across
        # whatever width this is given put a hand's width of nothing
        # between "Carry 0" and "Nuker 0", which reads as four unrelated
        # controls rather than one block of eight — and the whole point
        # of this round was "try and compact everything closer together".
        # It is the grids' rule (`_fit_width`, AlignLeft) one card up.
        for column in range(columns):
            grid.setColumnMinimumWidth(column * 3 + 2, self.GAP)
            grid.setColumnStretch(column * 3 + 2, 0)
        grid.setColumnStretch(columns * 3, 1)

    def values(self) -> dict:
        """Only the roles actually asked for — nought is not STORED.

        Seven roles at nought would be seven dead keys in everybody's
        settings file, which is the write-filter lesson `DEFAULTS`
        carries.
        """
        return {role: box.value() for role, box in self.boxes.items()
                if box.value() > 0}


def _explain(mine, yours, ours: str = "", theirs: str = "") -> str:
    """The exact figures a rounded pill count cannot carry.

    It NAMES the two sides, because the card no longer does: with the
    headings gone, "this side" beside a cell whose team is carried by
    which half of the card it is in would be the one sentence on screen
    that made the reader work it out.
    """
    ours = ours or "This side"
    theirs = theirs or "Other side"
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
        lead = f"{ours} leads this role."
    else:
        lead = f"{theirs} leads this role."
    return (f"{mine.role}\n"
            f"{ours}: {half(mine)}\n"
            f"{theirs}: {half(yours)}\n"
            f"{lead}\n"
            f"Out of 3 per pick, so the two are comparable "
            f"before both teams are full.")
