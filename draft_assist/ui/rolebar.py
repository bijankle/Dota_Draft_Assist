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

from PyQt6.QtCore import QPointF, QRect, QRectF, Qt, pyqtSignal
from PyQt6.QtGui import (QColor, QPainter, QPainterPath, QPen, QPolygonF)
from PyQt6.QtWidgets import (QGridLayout, QHBoxLayout, QLabel,
                             QSizePolicy, QVBoxLayout, QWidget)

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
# BIGGER THAN THEY WERE (13x10, gap 3), at the user's request: "it would
# be nice to increase the size of the pills and shuffle thigns around so
# that the space is utilized better". The card is two columns of eight
# roles and the cells did not come close to filling it, so there was
# room to spend and the pills are what the card is FOR — five marks 13px
# wide read as punctuation beside the name rather than as a figure.
PILL_W = 18
PILL_H = 13
PILL_GAP = 4
RADIUS = 2.5
EMPTY_PEN = 1.2


class PillRow(QWidget):
    """A role as pills: `count` of them, `filled` of those solid.

    **THE COUNT IS A PARAMETER because two different scales are drawn in
    it.** A TEAM's row is a SHARE — `roles_mod.PILLS` of them, because a
    side's five picks can carry any fraction of what they could have
    scored — while one HERO's row is Valve's own 0-to-3 rating, and
    drawing three levels across five pills would invent a precision the
    game does not publish. Same pills either way, which is the point: the
    callout over a pick and the card under the board read as one kind of
    object.
    """

    def __init__(self, grows_right: bool, parent=None, count: int = None):
        super().__init__(parent)
        # Which end the filled pills start from. Both sides start at the
        # role's name and grow away from it, so the ALLY row — which sits
        # to the left of the name — fills from its right-hand end.
        self._grows_right = bool(grows_right)
        self._count = roles_mod.PILLS if count is None else max(1, int(count))
        self._filled = 0
        self._lead = 0
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self.setFixedSize(
            self._count * PILL_W + (self._count - 1) * PILL_GAP,
            PILL_H + 6)

    @property
    def count(self) -> int:
        return self._count

    def set_share(self, filled: int, lead: int) -> None:
        filled = max(0, min(int(filled), self._count))
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
        for slot in range(self._count):
            # `slot` counts from the end the bar grows FROM, so the first
            # filled pill of each side is the one nearest the role name.
            at = slot if self._grows_right else self._count - 1 - slot
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
        room = width
        for count in self.COLUMNS:
            if count * each - self.GAP <= room:
                return count
        return 1

    def minimumSizeHint(self):                  # noqa: N802 - Qt naming
        hint = super().minimumSizeHint()
        if not self._ready:
            return hint
        one = self._cell_width()
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
    """ONE team's eight roles. There are two of these, one per card.

    **IT IS ONE SIDE, NOT BOTH**, at the user's request, and that is the
    second reversal this card has had. It began as two bars facing each
    other across a shared role name under a Radiant/Dire heading pair;
    the headings went when position started carrying the team; and now
    the CARD goes too: "see the padding on the background that allows you
    to know that 5 heroes at the pick menu are radiant? that padding
    should encapsulate the roles".
    Which is right, and it is the same argument that removed the
    headings, carried one step further. The board already says which side
    is which by putting each five in its own card — so a roles block in
    its own card, under that card, needs nothing else to say whose it is.
    A centre rule drawn inside one wide card was this app inventing a
    second way to draw a division it already had.
    **AND THE CARD HAS NO HEADING**: "you don't need to state roles, it's
    obvious from the content". Eight role names with pills beside them
    are not mistakable for anything else on this tab.

    Everything about the reflow is `ReflowGrid`'s. The two cards are
    given equal stretch in the same row, so they are the same width and
    independently arrive at the same column count — there is nothing to
    keep in step.
    """

    def __init__(self, side: str, parent=None):
        super().__init__(parent)
        self.side = side
        self.setProperty("bare", True)
        grid = QGridLayout(self)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(6)
        grid.setVerticalSpacing(3)
        self._grid = grid
        self._cells: dict[str, tuple[QLabel, PillRow]] = {}
        for role in roles_mod.ROLES:
            name = QLabel(role, self)
            name.setProperty("dim", True)
            name.setAlignment(Qt.AlignmentFlag.AlignRight
                              | Qt.AlignmentFlag.AlignVCenter)
            # BOTH CARDS GROW THE SAME WAY, each pill row starting at its
            # own name. The original bars grew OUTWARD from one shared
            # name, which is what made two of them comparable by length;
            # with the sides in separate cards there is no shared origin
            # left, and the comparison lives in the tooltip instead.
            self._cells[role] = (name, PillRow(grows_right=True, parent=self))
        self._align_names()
        self._ready = True
        self._relayout(self.COLUMNS[0])

    # ---- how many fit ---------------------------------------------------
    def _cell_width(self) -> int:
        name, pills = self._cells[roles_mod.ROLES[0]]
        return (self._widest(name) + self._widest(pills)
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
            grid.setColumnMinimumWidth(column, 0)
        for index, role in enumerate(roles_mod.ROLES):
            line, column = index % per, (index // per) * 3
            name, pills = self._cells[role]
            grid.addWidget(name, line, column,
                           Qt.AlignmentFlag.AlignRight
                           | Qt.AlignmentFlag.AlignVCenter)
            grid.addWidget(pills, line, column + 1,
                           Qt.AlignmentFlag.AlignLeft
                           | Qt.AlignmentFlag.AlignVCenter)
            name.show()
            pills.show()
        # THE SLACK GOES BETWEEN THE CELLS, NOT ALL AT THE END. It used
        # to land in one trailing spacer column, which is the empty
        # quarter of the card the user drew a circle round — "there is
        # empty space here... shuffle thigns around so that the space is
        # utilized better".
        #
        # The rule this REPLACES was "a fixed gap between cells and the
        # slack at the end, so the two cards hold their cells the same
        # distance apart whatever width they are given; spread by
        # stretch, each card's spacing would follow its own width and the
        # pair would stop matching." The hazard was real and does not
        # apply: the two cards are given EQUAL stretch in the same row,
        # so they are the same width, so spreading gives both the same
        # spacing by construction. A test holds that equality, which is
        # what makes this safe to spend.
        #
        # `GAP` stays as the MINIMUM, so the cells can never end up
        # closer together than they were — only further apart.
        for column in range(columns - 1):
            separator = column * 3 + 2
            grid.setColumnMinimumWidth(separator, self.GAP)
            grid.setColumnStretch(separator, 1)
        if columns == 1:
            # Nothing to spread between, so the slack has to go
            # somewhere; at the end is the only place it can.
            grid.setColumnStretch(2, 1)

    def _align_names(self) -> None:
        widest = 0
        for name, _pills in self._cells.values():
            name.ensurePolished()     # or the font is not the stylesheet's
            widest = max(widest, name.sizeHint().width())
        for name, _pills in self._cells.values():
            name.setFixedWidth(widest)

    # ---- what it says ---------------------------------------------------
    def set_role(self, role: str, pills: int, lead: int, tip: str) -> None:
        name, row = self._cells[role]
        row.set_share(pills, lead)
        name.setToolTip(tip)
        row.setToolTip(tip)


class RoleCards:
    """The two role blocks, scored together and drawn apart.

    One object because the two cards answer ONE question: a role's pills
    are a share of what that side could have scored, and the tooltip on
    either card names both sides and says which leads. Splitting the
    widgets did not split the arithmetic.
    """

    def __init__(self, parent=None):
        self.bars = {side: RoleBar(side, parent)
                     for side in ("ally", "enemy")}
        self._ally_name = ""
        self._enemy_name = ""

    def set_sides(self, ally: str, enemy: str) -> None:
        """Which side is which, for the TOOLTIPS.

        Nothing on either card draws these — the card it is in says it —
        but a tooltip reading "this side" and "the other side" beside a
        card with no heading is worse than one that names them.
        """
        self._ally_name, self._enemy_name = ally, enemy

    def show_draft(self, allies, enemies) -> None:
        """Score both line-ups and redraw every cell on both cards."""
        ours = roles_mod.team_scores(allies)
        theirs = roles_mod.team_scores(enemies)
        verdict = roles_mod.compare(ours, theirs)
        for mine, yours, lead in zip(ours, theirs, verdict):
            tip = _explain(mine, yours, self._ally_name, self._enemy_name)
            self.bars["ally"].set_role(mine.role, mine.pills, lead, tip)
            self.bars["enemy"].set_role(mine.role, yours.pills, -lead, tip)


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


# The callout's own geometry. Its gaps are DELIBERATELY tighter than the
# Roles card's, at the user's request — "with the same pill look at the
# one for the team, but more ocmpact (there is too much space between
# carry and durable, support and escape".
# The card spreads its slack between its two columns on purpose (see
# `RoleBar._relayout`), which is right for a block as wide as the board
# and wrong for a box hanging over one portrait: there the gap the card
# earns is most of the width. So this one has a FIXED gap and no stretch
# at all — it is sized to its contents rather than given a width to fill.
CALLOUT_GAP = 16
# TIGHT, because the height is what decides whether it fits ABOVE the
# tile — which is where it was asked for, and the pick tiles are already
# near the top of the page. Below is the fallback and it is a poor one:
# directly under a pick is the side's own Roles card, drawn in the very
# same pills, so a callout that lands there reads as part of it.
CALLOUT_PAD = 7
CALLOUT_ROWS = 2
POINTER_W = 14
POINTER_H = 6
CALLOUT_RADIUS = 6


class HeroRoles(QWidget):
    """One hero's eight ratings, two columns of four.

    VALVE'S OWN 0-TO-3, not a share. The Roles card under the board asks
    "how much of what this side COULD have scored did it score", which is
    a fraction and is drawn across five pills; one hero has no fraction to
    take — it has the rating the game publishes — so it gets three pills
    and each one is a level.

    ALL EIGHT ROLES, ALWAYS, even the zeros. A list cut to what a hero
    scores would change shape from hero to hero, and "no initiation at
    all" is exactly the answer somebody clicks a portrait to get; the
    Roles card, the role filter and the History sidebar all keep their
    full list for the same reason.
    """

    COLUMNS = 2

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setProperty("bare", True)
        grid = QGridLayout(self)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(6)
        grid.setVerticalSpacing(1)
        self._cells: dict[str, tuple[QLabel, PillRow]] = {}
        per = -(-len(roles_mod.ROLES) // self.COLUMNS)
        for index, role in enumerate(roles_mod.ROLES):
            line, column = index % per, (index // per) * 3
            name = QLabel(role, self)
            name.setProperty("dim", True)
            name.setAlignment(Qt.AlignmentFlag.AlignRight
                              | Qt.AlignmentFlag.AlignVCenter)
            pills = PillRow(grows_right=True, parent=self,
                            count=roles_mod.MAX_LEVEL)
            grid.addWidget(name, line, column,
                           Qt.AlignmentFlag.AlignRight
                           | Qt.AlignmentFlag.AlignVCenter)
            grid.addWidget(pills, line, column + 1,
                           Qt.AlignmentFlag.AlignLeft
                           | Qt.AlignmentFlag.AlignVCenter)
            self._cells[role] = (name, pills)
        # A FIXED gap between the two columns and NO stretch. See
        # `CALLOUT_GAP`.
        grid.setColumnMinimumWidth(2, CALLOUT_GAP)
        self._align_names()

    def _align_names(self) -> None:
        widest = 0
        for name, _pills in self._cells.values():
            name.ensurePolished()     # or the font is not the stylesheet's
            widest = max(widest, name.sizeHint().width())
        for name, _pills in self._cells.values():
            name.setFixedWidth(widest)

    def set_hero(self, hero_id: int) -> bool:
        """Draw this hero's ratings. False when the table has none.

        A hero the bundled file has not been cut for yet is the same
        "unknown is a real state" this app follows everywhere: the caller
        shows nothing rather than eight empty rows, which would read as a
        hero that is good at nothing.
        """
        levels = roles_mod.levels_for(hero_id)
        if not levels:
            return False
        for role, (name, pills) in self._cells.items():
            rating = int(levels.get(role, 0))
            pills.set_share(rating, 0)
            tip = f"{role}: {rating} of {roles_mod.MAX_LEVEL} — Valve's own"
            name.setToolTip(tip)
            pills.setToolTip(tip)
        return True

    def rating(self, role: str) -> int:
        """What is DRAWN for one role, for a test to read."""
        return self._cells[role][1].filled


class RoleCallout(QWidget):
    """What a clicked hero is made of, in a box pointing down at it.

    At the user's request: "when i click on a hero in addition to the
    gold border i want to see the stats show up above in a callout above
    the hero". The gold ring says WHICH hero the board is being measured
    against; this says what that hero IS, which is the one thing the
    board around it cannot.

    **A CHILD OF THE WINDOW, NEVER A TOP-LEVEL WIDGET.** A parentless
    QWidget is a WINDOW the moment anything shows it, and this app has
    opened a stray second "Dota Draft Assist" that way three times. It is
    raised over its siblings instead, which is all "floating" has to mean
    inside one window.

    **AND IT FLIPS RATHER THAN OVERHANGING.** Above the tile is where it
    was asked for and where it goes — but the pick tiles sit at the top
    of the page, so on a short window there is no room up there and the
    honest answer is to put it under the tile rather than over the title
    bar. Same rule as every other placement here: clamped to the room
    that exists.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("roleCallout")
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self._below = False
        self._point_at = 0.5          # where the pointer sits, 0..1 across
        lay = QVBoxLayout(self)
        lay.setContentsMargins(CALLOUT_PAD, CALLOUT_PAD + POINTER_H,
                               CALLOUT_PAD, CALLOUT_PAD + POINTER_H)
        lay.setSpacing(0)
        # NO NAME ON IT. The tile it points at is an inch below with the
        # hero's own portrait on it — and where there is no artwork yet,
        # that tile draws the name. A callout that opens by repeating
        # what it is pointing at is the profile callout's lesson, and the
        # two rows it costs are exactly what decides whether this fits
        # ABOVE the tile, which is where it was asked for.
        self.roles = HeroRoles(self)
        lay.addWidget(self.roles)
        self.setVisible(False)

    def show_hero(self, hero_id: int, name: str = "") -> bool:
        if not self.roles.set_hero(hero_id):
            self.setVisible(False)
            return False
        self.setToolTip(name or "")
        self.adjustSize()
        return True

    def point_at(self, target: QRect, room: QRect = None) -> None:
        """Sit over `target`, inside `room` (both in the parent's space).

        `room` is the TAB'S CONTENT AREA rather than the whole window, so
        the box can never be pushed up over the title bar and the tabs —
        the chrome is not somewhere a callout about a portrait may go,
        and covering the window buttons with one would be worse than
        moving it. Left out, it falls back to the parent's own rect.

        IT FLIPS rather than overhanging: above the tile is where this was
        asked for, and on a short window there is no above, so it goes
        under. The pointer follows the TILE rather than the box, so a
        callout pushed sideways to stay inside still names the portrait
        it is about — which is the whole job of the pointer.
        """
        if room is None or room.isEmpty():
            parent = self.parentWidget()
            room = parent.rect() if parent is not None else QRect()
        size = self.sizeHint()
        above = target.top() - size.height()
        self._below = bool(room.height()) and above < room.top()
        top = target.bottom() if self._below else above
        left = target.center().x() - size.width() // 2
        if room.width():
            left = max(room.left(), min(left, room.right() - size.width()))
        self.setGeometry(left, top, size.width(), size.height())
        span = max(1, size.width())
        self._point_at = min(1.0, max(0.0,
                                      (target.center().x() - left) / span))
        self.update()

    def paintEvent(self, event) -> None:            # noqa: N802 - Qt naming
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        body = QRectF(self.rect()).adjusted(0.5, POINTER_H + 0.5,
                                            -0.5, -POINTER_H - 0.5)
        path = QPainterPath()
        path.addRoundedRect(body, CALLOUT_RADIUS, CALLOUT_RADIUS)
        # The pointer, on whichever edge faces the tile.
        tip_y = body.bottom() + POINTER_H if not self._below else body.top() \
            - POINTER_H
        mid = body.left() + self._point_at * body.width()
        mid = min(max(mid, body.left() + POINTER_W),
                  body.right() - POINTER_W)
        edge = body.bottom() if not self._below else body.top()
        arrow = QPolygonF([QPointF(mid - POINTER_W / 2, edge),
                           QPointF(mid + POINTER_W / 2, edge),
                           QPointF(mid, tip_y)])
        path.addPolygon(arrow)
        painter.setPen(QPen(QColor(theme.FRAME_GOLD), 1))
        painter.setBrush(QColor(theme.BG_ELEVATED))
        painter.drawPath(path.simplified())
        painter.end()
