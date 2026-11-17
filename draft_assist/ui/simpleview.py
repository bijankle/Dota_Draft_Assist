"""THE SAME DRAFT AS TEXT: a page of tables instead of a page of faces.

At the user's request, and the shape is theirs: "you know in SharePoint
how you can change the view to be like a grid view or a road view... I
kind of want something like that where I can toggle between view types
for this app... it will change to like a spreadsheet view where it's
just like simple data tables - it's got what's been drafted, what the
recommended hero selection is, what the synergies are, basically just
useful summary tables, and hero names are in text instead of any
portraits or anything like that. We'll call it a simplified view and I
want this to be off by default."

So this is not a second app and it must not become one. The rich Draft
tab is five sizes of portrait, two painted grids, three strips of tiles
and a callout; every one of those is there because a draft is read at a
glance over a running game. A TABLE is read the other way round - a
column at a time, by somebody who wants the figure rather than the
impression - and there are machines and moments where that is the
better answer: a small window, a screen share, a remote session with no
artwork downloaded, or simply wanting to read the numbers.

**EVERY FIGURE HERE IS THE ONE THE OTHER VIEW DRAWS, read from the same
object.** That is the whole discipline of this module. A delta goes
through `tilekit.delta_text`, the same function that writes the badge on
a pick; the pair figures come out of the very `SynergyGrid` the painted
triangles are drawn from; the counters table is the `Matrix` the painted
grid is handed; the board's values are `net_contributions`, which is
what rests on the ten tiles. Two surfaces that compute the same number
twice are two surfaces that will one day disagree about it, and the one
nobody is looking at is the one that goes wrong.

**NOTHING IN HERE IS CLICKABLE, and that is the same rule the suggestion
strip follows.** A pick is entered by clicking a slot on the board; a
second way to do it that behaved differently would be worse than no way.
The cells ARE selectable, because a table somebody cannot copy out of is
a picture of a table.

**AND NO TABLE EVER SCROLLS INSIDE ITSELF** (`TextTable._fit_height`).
It is `tables.MatrixTable`'s rule for the same reason: a table sized to
its rows has nothing of its own to scroll, so a scrollbar on one can
only mean the fit was wrong - and it hides part of the answer while
making the widget look correct. The page scrolls; the tables do not, and
they ignore the wheel outright so that scrolling PAST one does not catch
in it, which is the fault `BucketTable` on the History tab exists to
prevent.
"""

from dataclasses import dataclass

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QFont
from PyQt6.QtWidgets import (QAbstractItemView, QHeaderView, QLabel,
                             QTableWidget, QTableWidgetItem, QVBoxLayout,
                             QWidget)

from ..model import items as items_mod
from ..model import roles as roles_mod
from . import theme, tilekit
from .chrome import card

# What an empty slot prints. An EM DASH rather than a blank cell, for the
# same reason the board draws a dashed plate rather than nothing: the
# shape of the answer standing where the answer will appear, so the table
# does not change height as the draft fills in.
NOTHING = "—"


@dataclass
class Cell:
    """One cell: its text, and how to draw it.

    `colour` is a theme name resolved AT PAINT TIME, never a captured
    hex - `theme.set_greyscale` reassigns every colour in that module, so
    a value read at import would leave this page in colour on a grey app.
    """
    text: str
    colour: str | None = None       # an attribute name on `theme`
    align: str = "left"             # "left" | "right" | "centre"
    tip: str = ""
    numeric: bool = False           # lining figures, so columns line up

    ALIGN = {"left": Qt.AlignmentFlag.AlignLeft,
             "right": Qt.AlignmentFlag.AlignRight,
             "centre": Qt.AlignmentFlag.AlignHCenter}


def _delta(value: float | None) -> Cell:
    """A signed figure, in the app's own two colours.

    `tilekit.delta_text` is the ONE place a stored fraction becomes
    percentage points, so this cannot drift from the badge on a tile.
    Green good, red bad, read from your own side - exactly like every
    other signed number in the app.

    NO SIGN IS APPLIED HERE. Every caller is handed a figure already
    read from the user's own side (`net_contributions`, `matchup_matrix`)
    or deliberately not (`team_synergy_grid`'s enemy triangle, which the
    painted card does not flip either), so a convention in this function
    would be a second answer to a question the model has already
    settled.
    """
    if value is None:
        return Cell(NOTHING, "TEXT_DIM", "right", numeric=True)
    name = ("GOOD" if value > 0 else "BAD" if value < 0 else "TEXT_DIM")
    return Cell(tilekit.delta_text(value), name, "right", numeric=True)


class TextTable(QTableWidget):
    """A read-only data table that is exactly as tall as its rows."""

    def __init__(self, parent=None):
        super().__init__(0, 0, parent)
        # QT SORTS BY TEXT, so "10" lands before "9" and "+6.4%" before
        # "+62.1%" - and every column here is a number wearing a sign or
        # a suffix. The History tab re-renders rather than calling
        # `sortItems` for that reason; here the order is the one the app
        # already decided, so sorting is simply OFF.
        self.setSortingEnabled(False)
        self.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        # SELECTABLE, because a table nobody can copy out of is a picture
        # of a table - and the one thing somebody pasting a draft into a
        # message wants is the text.
        self.setSelectionMode(
            QAbstractItemView.SelectionMode.ContiguousSelection)
        self.setSelectionBehavior(
            QAbstractItemView.SelectionBehavior.SelectItems)
        self.verticalHeader().setVisible(False)
        self.setAlternatingRowColors(True)
        self.setWordWrap(False)
        self.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        head = self.horizontalHeader()
        head.setTextElideMode(Qt.TextElideMode.ElideRight)
        head.setHighlightSections(False)
        # A HEADING THAT CANNOT BE CLICKED, since clicking one would
        # otherwise look like it sorts and this table does not sort.
        head.setSectionsClickable(False)

    def wheelEvent(self, event) -> None:            # noqa: N802 - Qt naming
        """The PAGE scrolls; this does not.

        A control that answers the wheel while the reader is scrolling
        past it is the History tab's own fault one card over, and here it
        can only ever be wrong: the table is sized to hold every row it
        has, so there is nothing inside it to scroll to.
        """
        event.ignore()

    def show_rows(self, headers: list[str], rows: list[list],
                  stretch: tuple[int, ...] = ()) -> None:
        """Replace the whole table. `stretch` names the columns that
        absorb the card's spare width; the rest are cut to their
        contents."""
        self.clearContents()
        self.setColumnCount(len(headers))
        self.setHorizontalHeaderLabels(headers)
        self.setRowCount(len(rows))
        # A HEADING IS ALIGNED LIKE THE COLUMN UNDER IT. Qt centres
        # header text whatever the cells do, so "Hero" sat in the middle
        # of a stretched column with every name hard against its left
        # edge - which reads as two columns rather than one. The first
        # row's cell decides it, since a column is one kind of thing all
        # the way down.
        for r, line in enumerate(rows):
            for c, value in enumerate(line):
                cell = value if isinstance(value, Cell) else Cell(str(value))
                item = QTableWidgetItem(cell.text)
                item.setFlags(Qt.ItemFlag.ItemIsEnabled
                              | Qt.ItemFlag.ItemIsSelectable)
                item.setTextAlignment(Cell.ALIGN[cell.align]
                                      | Qt.AlignmentFlag.AlignVCenter)
                if cell.colour:
                    item.setForeground(QColor(getattr(theme, cell.colour)))
                if cell.tip:
                    item.setToolTip(cell.tip)
                if cell.numeric:
                    # ALEGREYA HAS OLD-STYLE FIGURES: 3 4 5 7 9 hang
                    # below the baseline and 0 1 2 sit at x-height, so a
                    # column of them is a ragged column. `lnum` makes
                    # every digit one height on one baseline, which is
                    # what a column of numbers is for.
                    font = QFont(self.font())
                    tilekit.lining_figures(font)
                    item.setFont(font)
                self.setItem(r, c, item)
        for c in range(len(headers)):
            item = self.horizontalHeaderItem(c)
            under = rows[0][c] if rows else None
            how = under.align if isinstance(under, Cell) else "left"
            if item is not None:
                item.setTextAlignment(Cell.ALIGN[how]
                                      | Qt.AlignmentFlag.AlignVCenter)
        head = self.horizontalHeader()
        for c in range(len(headers)):
            head.setSectionResizeMode(
                c, QHeaderView.ResizeMode.Stretch if c in stretch
                else QHeaderView.ResizeMode.ResizeToContents)
        self._fit_height()

    def showEvent(self, event) -> None:             # noqa: N802 - Qt naming
        """Re-fit once the header knows its own height.

        A header that has not been shown yet reports a stale height, so a
        fit taken while the rows were being filled is a few pixels short
        - which with both scrollbars off is invisible except as a page
        that will not quite settle. Same fix as `BucketTable`.
        """
        super().showEvent(event)
        self._fit_height()

    def _fit_height(self) -> None:
        head = self.horizontalHeader()
        header_h = max(head.height(), head.sizeHint().height())
        rows = self.verticalHeader().length()
        self.setFixedHeight(header_h + rows + 2 * self.frameWidth() + 2)


def _dim(text: str = "") -> QLabel:
    label = QLabel(text)
    label.setProperty("dim", True)
    return label


class SimpleView(QWidget):
    """The whole Draft tab as six tables, in the order the rich one reads.

    Board, then what each side is made of, then which hero to take, then
    what to build, then the pairs and the matchups - which is the
    argument the Draft tab makes top to bottom, in the same sequence, so
    switching views does not mean learning a second layout.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(12, 12, 12, 12)
        lay.setSpacing(10)

        self.cards: dict[str, QWidget] = {}

        # THE SIDE TOTALS RIDE ON THE HEADING, which is where the rich
        # view puts them too - beside the name of the side they are the
        # sum of. They are NOT a scoreline: every figure in this app is
        # read from your own side, so yours is what your draft is worth
        # and theirs is how well their five are handled.
        self.board_total = _dim()
        board_card, blay = card("Draft", self.board_total)
        self.board = TextTable()
        blay.addWidget(self.board)
        self.cards["board"] = board_card
        lay.addWidget(board_card)

        roles_card, rlay = card("Team roles")
        self.roles = TextTable()
        rlay.addWidget(self.roles)
        self.cards["roles"] = roles_card
        lay.addWidget(roles_card)

        picks_card, play = card("Top Heroes")
        self.picks = TextTable()
        self.picks_note = _dim()
        self.picks_note.setWordWrap(True)
        self.picks_note.hide()
        play.addWidget(self.picks)
        play.addWidget(self.picks_note)
        self.cards["picks"] = picks_card
        lay.addWidget(picks_card)

        items_card, ilay = card("Top Items")
        self.items = TextTable()
        ilay.addWidget(self.items)
        self.cards["items"] = items_card
        lay.addWidget(items_card)

        syn_card, slay = card("Synergies")
        self.synergy = TextTable()
        self.synergy_note = _dim()
        self.synergy_note.setWordWrap(True)
        self.synergy_note.hide()
        slay.addWidget(self.synergy)
        slay.addWidget(self.synergy_note)
        self.cards["synergy"] = syn_card
        lay.addWidget(syn_card)

        self.counters_axes = _dim()
        vs_card, vlay = card("Counters", self.counters_axes)
        self.counters = TextTable()
        vlay.addWidget(self.counters)
        self.cards["counters"] = vs_card
        lay.addWidget(vs_card)

        # The stretch goes at the BOTTOM, so every card is its own height
        # and the slack is slack. Giving it to a table would leave dead
        # space inside the widget and no shorter size for the window to
        # offer, which is the trap `_fit_height` is half of.
        lay.addStretch(1)

    # ---- the blocks ----------------------------------------------------
    def show_board(self, rows: list[tuple[str, str | None, str | None,
                                          float | None]],
                   mine: str, theirs: str,
                   ally_total: float | None,
                   enemy_total: float | None) -> None:
        """One row per SLOT, picked or not.

        Every slot is listed because the slots are what the board is: a
        table that grew a row per pick would change height under the
        reader five times a draft, and "Pos 2 is still open" is a thing
        worth reading.
        """
        self.board.show_rows(
            ["Side", "Pos", "Hero", "Value"],
            [[side, pos or NOTHING,
              Cell(hero or NOTHING, None if hero else "TEXT_DIM"),
              _delta(value)]
             for side, pos, hero, value in rows],
            stretch=(2,))
        parts = []
        for name, total in ((mine, ally_total), (theirs, enemy_total)):
            # A SIDE WITH NOTHING RESOLVED SHOWS NO TOTAL, rather than
            # "+0.0", which would claim a measurement nobody made.
            if total is None:
                continue
            # GREEN GOOD, RED BAD, like every other signed number here -
            # the painted heading beside the board colours the same two
            # figures, and one of them drawn in plain grey would read as
            # a different kind of thing. The colour is looked up NOW
            # rather than captured, so View - Greyscale reaches it.
            colour = getattr(theme, "GOOD" if total > 0
                             else "BAD" if total < 0 else "TEXT_DIM")
            parts.append(f'{name} <span style="color:{colour}">'
                         f'{tilekit.delta_text(total)}</span>')
        self.board_total.setText("&nbsp;&nbsp;&nbsp;".join(parts))

    def show_roles(self, rows: list[tuple[str, roles_mod.RoleScore,
                                          roles_mod.RoleScore]],
                   mine: str, theirs: str) -> None:
        """Valve's own 0-to-3 ratings, as each side's SHARE of what it
        could have scored.

        A share rather than a sum, which is what makes a 2v5 board
        readable: three picks can score at most 9 on one role, so 6 of 9
        reads the same as a full team's 10 of 15. Comparing raw sums
        would say the team with more picks is better at everything.
        """
        table = []
        for role, ours, yours in rows:
            line = [role]
            for score in (ours, yours):
                line.append(Cell(
                    f"{round(score.share * 100)}%" if score.possible
                    else NOTHING,
                    None if score.possible else "TEXT_DIM", "right",
                    tip=(f"{score.scored} of {score.possible} across "
                         f"{score.rated} rated pick"
                         f"{'' if score.rated == 1 else 's'}")
                    if score.possible else "",
                    numeric=True))
            table.append(line)
        self.roles.show_rows(["Role", mine, theirs], table, stretch=(0,))

    def show_heroes(self, rows: list[tuple[str, float | None, float, float]],
                    note: str = "") -> None:
        """The suggestion strip's own list, in its own order.

        Handed the rows the strip was handed, so the two cannot disagree
        about which hero is best or by how much - and `Fit` is empty for
        exactly the boards the strip draws no badge on, which is an
        undrafted one, where every fit is zero and the order is by how
        hard the field finds the hero to counter.
        """
        self.picks.show_rows(
            ["#", "Hero", "Fit", "Counter", "Synergy"],
            [[Cell(str(i), "TEXT_DIM", "right", numeric=True),
              name, _delta(fit), _delta(vs), _delta(with_)]
             for i, (name, fit, vs, with_) in enumerate(rows, start=1)],
            stretch=(1,))
        self.picks_note.setText(note)
        self.picks_note.setVisible(bool(note))

    def show_items(self, advice: list[items_mod.ItemAdvice]) -> None:
        """What to build, with the same percentage the tile's badge
        carries and the heroes that asked for it.

        `items.importance` is measured against the WORST CASE rather
        than against this draft, so the figure means the same thing in
        every draft - which is why it can be printed as a bare
        percentage here.
        """
        table = []
        for i, a in enumerate(advice, start=1):
            pct = items_mod.importance(a.score)
            who = ", ".join(t.hero for t in a.triggers)
            table.append([
                Cell(str(i), "TEXT_DIM", "right", numeric=True),
                Cell(a.item + (" *" if a.any_stale else ""),
                     tip="At least one rule behind this has not been "
                         "verified for the current patch."
                         if a.any_stale else ""),
                Cell(f"{pct}%",
                     "GOOD" if pct > items_mod.ONE_TRIGGER else "TEXT",
                     "right", numeric=True),
                Cell(who, tip="\n".join(
                    f"{t.hero} ({items_mod.severity_pct(t.severity)}%): "
                    f"{t.reason}" for t in a.triggers)),
            ])
        self.items.show_rows(["#", "Item", "Importance", "Asked for by"],
                             table, stretch=(3,))

    def show_synergy(self, pairs: list[tuple[str, str, str, float]],
                     note: str = "") -> None:
        """Every pair on the board, once, strongest first within its team.

        A LIST rather than the painted card's two triangles. Those exist
        because a square of portraits is read by position; a table read
        by column wants every row to be a pair, so half a square of
        blank cells would be half a table of nothing.

        **THE ENEMY HALF IS NOT SIGN-FLIPPED**, which keeps this in step
        with the painted grid and is the one place in the app where a
        green number is not good for you. Each row answers "how well
        does THIS pair work", so a strong enemy pairing is a big green
        number on their rows. The TEAM column is the rule for reading it,
        not the colour - which is exactly what the two outlined triangles
        say in the other view.
        """
        self.synergy.show_rows(
            ["Team", "Hero", "With", "Value"],
            [[Cell(team, "TEXT_DIM"), a, b, _delta(value)]
             for team, a, b, value in pairs],
            stretch=(1, 2))
        self.synergy_note.setText(note)
        self.synergy_note.setVisible(bool(note))

    def show_counters(self, rows: list[tuple[int, str]],
                      cols: list[tuple[int, str]],
                      cells: list[list[float | None]],
                      mine: str, theirs: str) -> None:
        """Your five down the side against their five across the top.

        A MATRIX rather than a list, which is the opposite choice from
        the synergies above it and for a stated reason: this grid is a
        full 5x5 with no spare half, and the thing it exists to show is
        the one lane losing badly that a comfortable total conceals. A
        column of 25 rows would bury that; a 5x5 puts it where the eye
        lands.

        WHICH AXIS IS WHOSE IS SAID IN WORDS. The painted card says it
        with a green box round one axis and a red one round the other,
        and a table has no boxes - so the corner cell names the side the
        ROWS are and the card's own corner names both. Ten heroes with
        nothing saying which five are yours is the one way this table
        can be read backwards, and every figure in it is read from your
        side.
        """
        self.counters_axes.setText(f"{mine} rows, {theirs} columns")
        self.counters.show_rows(
            [mine] + [name for _hid, name in cols],
            [[Cell(name, tip=name)]
             + [Cell(cell.text, cell.colour, "centre", numeric=True)
                for cell in (_delta(line[c]) for c in range(len(cols)))]
             for (_hid, name), line in zip(rows, cells)],
            stretch=tuple(range(1, len(cols) + 1)))

    def set_sections(self, shown: dict[str, bool]) -> None:
        """Hide a card the View menu has turned off.

        The SAME four tick boxes govern both views, so a block turned off
        is off wherever you look - the alternative is two answers to one
        question and no way to tell which you are reading.
        """
        for key, card_widget in self.cards.items():
            card_widget.setVisible(bool(shown.get(key, True)))
