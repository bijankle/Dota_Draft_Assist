"""Sortable tables for the draft window.

Two things live here that Qt does not give for free:

* numeric sorting. A QTableWidgetItem compares by its *text*, so "+10.0"
  sorts before "+9.0" and a percentage column orders alphabetically. Every
  numeric cell therefore carries the underlying float and compares on that.

* the breakdown panel's two independent banks. It shows allies beside
  enemies, which are separate lists that happen to share a table. Qt's
  built-in sorting reorders whole rows, so clicking "vs enemy" would drag
  the ally beside it along for the ride. Each bank is sorted on its own and
  the rows are then laid side by side.
"""

from PyQt6.QtCore import QPoint, QRect, QRectF, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QPainter, QPainterPath, QPen
from PyQt6.QtWidgets import (QHeaderView, QLabel, QLineEdit,
                             QStyledItemDelegate, QTableWidget,
                             QTableWidgetItem, QVBoxLayout, QWidget)

from . import theme

SORT_ROLE = Qt.ItemDataRole.UserRole + 1

# The empty grid drawn before either team is known: a draft is five a side,
# so the outline is too.
BLANK_SIDE = 5
# The height a filled row settles at where the headers are plain text.
# With portrait headers a row is the height of the picture in it, so the
# outline works its own out (`MatrixTable._blank_metrics`) rather than
# using this — an empty grid should be the SHAPE the filled one will have,
# and a number written down here stopped being that the moment the
# portraits started setting the size.
BLANK_ROW = 26


class ValueItem(QTableWidgetItem):
    """A cell that sorts on the number it displays rather than its text."""

    def __init__(self, text: str, value: float):
        super().__init__(text)
        self.setData(SORT_ROLE, float(value))
        self.setTextAlignment(Qt.AlignmentFlag.AlignRight
                              | Qt.AlignmentFlag.AlignVCenter)

    def __lt__(self, other) -> bool:
        mine = self.data(SORT_ROLE)
        theirs = other.data(SORT_ROLE) if isinstance(other, QTableWidgetItem) \
            else None
        if mine is None or theirs is None:
            return super().__lt__(other)
        return mine < theirs


def delta_item(delta: float) -> ValueItem:
    """A signed interaction term, coloured by sign. Percentage points."""
    item = ValueItem(f"{delta * 100:+.2f}", delta)
    # Centred both ways: the grid sits under portraits that are centred in
    # their own columns, and a left-aligned number does not line up with
    # the hero it belongs to.
    item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
    if delta:
        item.setForeground(QColor(theme.GOOD if delta > 0 else theme.BAD))
    return item


class QuickEntry(QLineEdit):
    """A line edit that reports Tab instead of letting Qt move focus.

    During a draft the same field is used for both teams, so Tab has to
    mean 'other side' — losing focus mid-draft costs more than tab order
    is worth here.
    """

    tab_pressed = pyqtSignal()

    def keyPressEvent(self, event) -> None:  # noqa: N802 - Qt naming
        if event.key() in (Qt.Key.Key_Tab, Qt.Key.Key_Backtab):
            self.tab_pressed.emit()
            return
        super().keyPressEvent(event)


TOTAL_LABEL = "Σ"
# The in-game callout has to fit beside Dota, not compete with it, so the
# compact grid trades full hero names for a grid that fits without
# scrolling. Anyone reading it is looking at the same five portraits.
COMPACT_NAME = 7
COMPACT_COLUMN = 72
# The portrait head on a matrix column. This is the app's width UNIT: five
# of them plus a row header is the narrowest a grid can be drawn, two of
# those grids is the narrowest the window is worth having, and the pick
# tiles above size themselves against the same number so a column reads
# down from the tile it belongs to.
HEADER_ICON = 34
# `chrome.card`'s horizontal padding: the grid has to take it off the
# width it is given, exactly as a team panel takes off its own margin,
# or the two are not measuring the same room.
CARD_MARGIN = 12
# Slack around the portrait inside its cell, each side. It was 2, which
# left the team outline nowhere to sit but ON the picture — "they cut
# into the portraits ... they should run directly on the edge". At 4 the
# line lives in the margin with its inner edge against the portrait, and
# the two teams' borders have real background between them.
CELL_PAD = 3
# How big a header portrait grows on its own account. It is no longer the
# ceiling: a column must print "+12.34" whatever the picture would have
# liked to be, so where the number is wider the number wins.
HEADER_ICON_MAX = 64
ROW_HEADER = HEADER_ICON + 4
# The line drawn round a team's own region — green for Radiant, red for
# Dire. Two triangles that touch need something between them saying which
# is which, and the same box round a header strip says which axis of the
# counters grid is whose. It is the ONE thing these colours mean here:
# inside a team's own region a green number is that team's pair working,
# whichever team it is.
PAIR_EDGE_W = 2
# WHERE A TEAM'S BORDER SITS, measured from the edge of whatever it is
# drawn inside — a grid cell or a header section, which must agree or the
# line jogs sideways where the strip meets the triangle under it.
#
# The portrait starts CELL_PAD in and a centred pen reaches half its width
# either way, so this puts the pen's INNER edge exactly on the picture:
# the line runs along the portrait's boundary without covering a pixel of
# it. Two neighbouring cells then hold their two lines back to back with a
# hairline of background between them, which is the "only just visible"
# gap that was asked for, and it is the whole reason CELL_PAD exists.
# THE BORDER IS NOT PLACED BY ARITHMETIC. Three rounds of this were spent
# deriving an inset from CELL_PAD, and each was a pixel or two out for a
# reason nothing in the sum could see: Qt's own grid line takes a column
# out of `visualRect`, and a 16:9 portrait fitted into a cell lands on
# whatever height the rounding gives it. So the line is drawn round the
# rectangle the portrait was ACTUALLY drawn in, which the painter that
# drew it reports (`PairCellDelegate.drawn`, `PortraitHeader` passing its
# own box down) — one pixel of background outside the picture, so the pen
# traces the edge of the art without ever covering a pixel of it.
# MEASURED, NOT ASSUMED: a width-2 pen drawn at x paints columns x-1 and
# x — Qt lays an even pen out BACKWARDS from its coordinate, so it is not
# symmetric about it. That asymmetry is a whole pixel, which is why one
# inset used on all four sides cleared the picture on the left and top and
# covered a column of it on the right and bottom. It is exactly the last
# of "the line cuts into the portrait", and no amount of tuning a single
# number could ever have fixed it.
# What a line is extended by to cross the grid line into the next cell.
# Without it a border along five portraits is five separate segments with
# a break at every one of them, which is what this kept looking like.
GRID_GAP = 1
# The four edges of a cell as (row, column) steps, which of them run
# perpendicular to each, and how to read one side off a rectangle. A
# border turning a corner has to name the edge it is turning into, and
# spelling that out four times over is where the earlier versions of this
# quietly disagreed with themselves.
DELTA = {"top": (-1, 0), "bottom": (1, 0), "left": (0, -1), "right": (0, 1)}
OPPOSITE = {"top": "bottom", "bottom": "top", "left": "right",
            "right": "left"}
PERPENDICULAR = {"top": ("left", "right"), "bottom": ("left", "right"),
                 "left": ("top", "bottom"), "right": ("top", "bottom")}


def _ring(art):
    """Where to draw so the pen sits FLUSH against this rectangle.

    Four coordinates, one per side, each chosen so the band the pen
    actually paints is the pixels immediately outside the picture and not
    one of the picture's own — "directly on the edge of the portraits",
    which is what was asked for, rather than across them.
    """
    half = PAIR_EDGE_W // 2
    return art.adjusted(-half, -half, 1 + half, 1 + half)


def _reach(rect, which: str) -> int:
    """How far a line must run to close the corner on a `_ring` side.

    A perpendicular line drawn at a ring's left or top paints one pixel
    BACK from it (see the note on the pen above), so a line stopping on
    that coordinate leaves a single pixel of the corner unpainted — a
    notch at every step of the staircase, twenty of them across a grid.
    Reaching past by the same half-pen closes it, and on the right and
    bottom the coordinate already covers its own band.
    """
    edge = _side_of(rect, which)
    return edge - PAIR_EDGE_W // 2 if which in ("left", "top") else edge


def _side_of(rect, which: str) -> int:
    """One edge's coordinate: x for left/right, y for top/bottom."""
    return {"top": rect.top(), "bottom": rect.bottom(),
            "left": rect.left(), "right": rect.right()}[which]
# A cell has to hold "+12.34" without eliding, and that is wider than the
# portrait above it — so the column, not the icon, sets the floor.
# The narrowest a cell can be and still print a signed delta. It is a
# static estimate, used for the WINDOW's floor before any table exists;
# the live column measures `WIDEST_CELL` against the real font instead,
# because the body size has been raised twice and a constant does not
# follow it.
CELL_MIN = 82
# A TOTAL wears a capital sigma, at the user's request: it is the one
# thing on these cards that sums the row or column it sits on rather than
# reporting one pair, and nothing on screen said so.
SIGMA = "\u03a3"
WIDEST_CELL = "+12.34"
# A column has to fit the widest thing it can be asked to draw, and a
# total is that: the sigma sits ahead of the digits, so measuring the bare
# number would put "..." where the totals are.
WIDEST_TOTAL = SIGMA + " " + WIDEST_CELL


def sigma(value: float) -> str:
    """A total, written like every other figure in the app with the sigma
    in front of it."""
    # A SPACE after it: the sigma is a word, not a sign, and set hard
    # against a "+" it read as one glyph.
    return f"{SIGMA} {float(value) * 100:+.2f}"


def minimum_grid_width(columns: int = 5) -> int:
    """The narrowest a grid of this many columns can honestly be drawn.

    Honestly: a narrower one still draws, it just shows "..." where the
    numbers were, which is a grid that has stopped being a grid.
    """
    return ROW_HEADER + columns * max(HEADER_ICON, CELL_MIN)


def short_name(name: str) -> str:
    return name if len(name) <= COMPACT_NAME else name[:COMPACT_NAME] + "…"


def _total_item(value: float) -> QTableWidgetItem:
    """A margin figure: same colour rule as a cell, but bold, so the eye
    can tell a summary apart from a pairing without reading the header."""
    item = delta_item(value)
    font = item.font()
    font.setBold(True)
    item.setFont(font)
    return item


class PortraitHeader(QHeaderView):
    """A header that draws hero portraits, because Qt will not.

    A QHeaderView under a stylesheet ignores `iconSize` and falls back to
    the style's small-icon metric — 16 pixels, whatever you asked for — so
    an icon set on the header item comes out a third of the size and there
    is no property that changes it. Painting the pixmap here is the only
    reliable way, and it is a dozen lines.
    """

    def __init__(self, orientation, parent=None):
        super().__init__(orientation, parent)
        self.heroes: dict[int, int] = {}
        self.values: dict[int, float] = {}
        self.outline: str = ""
        # Which team each section belongs to, and the sections whose edge
        # FACING the grid is left open — see `set_outline`.
        self.sides: dict[int, str] = {}
        self.open_edges: set[int] = set()
        self.box = HEADER_ICON

    def set_box(self, size: int) -> None:
        """The square every portrait is drawn inside, both headers alike.

        Without this the two headers scale differently and there is no way
        to see why: a column header's section is (stretched column width) x
        (fixed header height) while a row header's is (fixed header width)
        x (row height), so the two portraits are limited by different
        numbers and one grows with the window while the other does not.
        Same box, same picture.
        """
        self.box = max(8, int(size))
        self.updateGeometries()
        self.viewport().update()

    def set_heroes(self, heroes: dict) -> None:
        """Section index -> hero id. Ids rather than pixmaps, so the shared
        scaled-portrait cache does the work instead of this repainting."""
        self.heroes = heroes
        self.updateGeometries()
        self.viewport().update()

    def set_outline(self, colour: str = "", open_edges=(),
                    side: str = "") -> None:
        """Box this whole strip of faces in one team's colour.

        Counters is your five DOWN the side against their five ACROSS the
        top, and nothing on it said which was which — the numbers are read
        from your point of view either way, so the grid looked symmetrical
        while meaning two different things by its axes. One green box round
        Radiant's portraits and one red box round Dire's answers it in the
        same vocabulary the synergy triangles use, and costs no space at
        all.
        """
        self.outline = colour
        self.open_edges = set(open_edges)
        self.sides = {i: side for i in self.heroes} if side and colour else {}
        self.viewport().update()

    def _paint_outline(self, painter, rect, index, art=None) -> None:
        """This section's share of the box round the whole strip.

        A header paints one section at a time, so the box has to be drawn
        in pieces: the two long edges on every section, and an end cap on
        the first and last. Drawn per section rather than over the viewport
        afterwards because there is no hook for that, and a box painted on
        top of a scrolled header would be in the wrong place anyway.

        The long edges run the section's WHOLE width, with no inset: an
        inset one stops a pixel short at each end, and across five
        sections that is a border with a break at every portrait.

        `open_edges` names the sections whose edge FACING the grid is left
        out. That is what stops a box being drawn round the pair grid's
        axis strip: where the cells below a header section are the same
        team, the header and the triangle are ONE region and a line
        between them rules through the middle of it.
        """
        if not self.outline:
            return
        # Only round the sections that HAVE a hero. The pair grid is as
        # wide as the longer team, so a 5v4 leaves a column heading
        # nothing, and a box drawn round it claims a fifth pick that has
        # not been made. With no portraits at all the header is names and
        # every section counts.
        heads = sorted(self.heroes) if self.heroes else list(range(self.count()))
        if index not in heads:
            return
        painter.save()
        painter.setPen(QPen(QColor(self.outline), PAIR_EDGE_W))
        # ROUND THE PICTURE, one pixel of background clear of it — the
        # same rule `PairGrid.paintEvent` draws by, and it has to be the
        # same or the line jogs sideways where the strip meets the
        # triangle under it. Deriving an inset from the section instead
        # put this border hard against the section edge, several pixels
        # off the portrait it is meant to be tracing, while the cells'
        # own borders were somewhere else again.
        face = art if art is not None else rect
        ring = _ring(face)
        across = self.orientation() == Qt.Orientation.Horizontal
        first, last = heads[0], heads[-1]
        open_here = index in self.open_edges
        # A long edge runs the section's WHOLE span and one pixel over
        # into the next, so the segment along one portrait meets the
        # segment along the next and the strip is one line rather than a
        # box round every face. At the two ends it stops on the end cap
        # instead of poking out past it.
        if across:
            head = ring.left() if index == first else rect.left()
            tail = (ring.right() if index == last
                    else rect.right() + GRID_GAP)
            # OUTER first, then the one facing the grid unless it is open.
            lines = [(QPoint(head, ring.top()), QPoint(tail, ring.top()))]
            if not open_here:
                lines.append((QPoint(head, ring.bottom()),
                              QPoint(tail, ring.bottom())))
            if index == first:
                lines.append((QPoint(ring.left(), ring.top()),
                              QPoint(ring.left(), ring.bottom())))
            if index == last:
                lines.append((QPoint(ring.right(), ring.top()),
                              QPoint(ring.right(), ring.bottom())))
        else:
            head = ring.top() if index == first else rect.top()
            tail = (ring.bottom() if index == last
                    else rect.bottom() + GRID_GAP)
            lines = [(QPoint(ring.left(), head), QPoint(ring.left(), tail))]
            if not open_here:
                lines.append((QPoint(ring.right(), head),
                              QPoint(ring.right(), tail)))
            if index == first:
                lines.append((QPoint(ring.left(), ring.top()),
                              QPoint(ring.right(), ring.top())))
            if index == last:
                lines.append((QPoint(ring.left(), ring.bottom()),
                              QPoint(ring.right(), ring.bottom())))
        for line in lines:
            painter.drawLine(*line)
        painter.restore()

    def set_values(self, values: dict) -> None:
        """Section index -> a figure to print on the portrait.

        The synergy grid's two axes are its two teams, so the obvious place
        for a hero's total with its own four is on the face heading its
        row — bottom-right of the portrait, the same corner and the same
        badge every other number in the app sits in.
        """
        self.values = values
        self.viewport().update()

    def paintSection(self, painter, rect, index):   # noqa: N802 - Qt naming
        from .portraits import scaled
        hero_id = self.heroes.get(index)
        # The box's WIDTH, never the section's: see set_box. The height
        # comes from the section, which _apply_icon_box has already cut to
        # what this width draws, so both headers land on the same picture.
        art = (scaled(hero_id, min(self.box, rect.width()), rect.height())
               if hero_id is not None else None)
        if art is None:
            super().paintSection(painter, rect, index)
            return self._paint_outline(painter, rect, index)
        painter.save()
        painter.fillRect(rect, QColor(theme.BG_ELEVATED))
        box = QRect(rect.left() + (rect.width() - art.width()) // 2,
                    rect.top() + (rect.height() - art.height()) // 2,
                    art.width(), art.height())
        painter.drawPixmap(box.topLeft(), art)
        value = self.values.get(index)
        if value is not None:
            from . import tilekit
            # Always a TOTAL here — a header names a hero and the figure
            # on it sums that hero's whole row or column — so it wears
            # the sigma.
            tilekit.paint_badge(painter, box, sigma(value),
                                theme.GOOD if float(value) > 0 else theme.BAD,
                                self.font())
        painter.restore()
        self._paint_outline(painter, rect, index, box)


# The roles a paired-triangle cell carries: whose portrait backs it, the
# figure to print over that, and whether this is the bottom header row.
PAIR_HERO = int(Qt.ItemDataRole.UserRole) + 10
PAIR_VALUE = PAIR_HERO + 1
PAIR_HEADER = PAIR_HERO + 2
PAIR_SIDE = PAIR_HERO + 3
# How far the portrait behind a number is knocked back. It is a backdrop,
# not the subject: at full strength the artwork competes with the figure it
# is meant to be labelling. THE TWO HEADER ROWS ARE NOT VEILED: they are
# the grid's axes, they name the ten heroes the whole card is about, and
# knocking them back made the bottom row read as another kind of thing
# from the identical portraits along the top.
PAIR_VEIL = 110


class PairGrid(QTableWidget):
    """A grid that outlines each team's cells as ONE continuous border.

    The outline was drawn by the DELEGATE, each cell stroking the edges
    where its four neighbours disagreed with it. That is the right shape
    and the wrong place to draw it from: a cell paints inside its own
    rectangle, and between two rectangles there is the grid line — so
    every edge stopped a pixel short of the next one and the border came
    out as a row of dashes with a break at each portrait.

    Drawing it over the viewport instead fixes that with one change: the
    lines are placed IN the gap between cells (`GAP`) and run the full
    span plus the gap at each end, so the segment along one cell meets the
    segment along the next exactly, and the corners close. Nothing else
    about the rule changes — an edge is drawn where the neighbour is a
    different team, which is what gives the stepped diagonal, the outer
    edge, and no line at all between a triangle and its own axis row.

    A union of rectangles was tried first and is NOT the answer:
    `QPainterPath.simplified` leaves rectangles that merely touch as
    separate subpaths, so every cell came out with a box round it.

    Computed at PAINT time from `visualRect`, so it cannot go stale when
    the columns resize. Showing a plain matrix draws nothing here: no cell
    carries a side.
    """

    # Where the border sits. INSIDE its own cell rather than out in the
    # grid line, which is what lets two teams' borders both be seen: an
    # edge drawn in the gutter is drawn at the same coordinates by the
    # cell on each side of it, so one colour simply painted over the
    # other and WHICH one won depended on iteration order. Inset into
    # each cell instead and the two lines sit apart, with a hairline of
    # background between them — visible, but only just, which is what
    # was asked for.
    GAP = GRID_GAP

    def _side(self, row: int, col: int) -> str | None:
        item = self.item(row, col)
        return (item.data(PAIR_SIDE) or None) if item is not None else None

    def _edges(self) -> dict:
        """Which cell edges are a boundary, keyed by (side, which).

        An edge exists where the neighbour is a different team — the rule
        that gives the stepped diagonal, the outer border, and no line at
        all between a triangle and its own axis row.
        """
        heads = getattr(self.horizontalHeader(), "sides", {})
        found: dict = {}
        for row in range(self.rowCount()):
            for col in range(self.columnCount()):
                side = self._side(row, col)
                if not side:
                    continue
                # The header above row 0 counts as a neighbour: where it
                # is the same team the strip and the triangle are ONE
                # region, and a line between them would rule through the
                # middle of it.
                above = (heads.get(col) if row == 0
                         else self._side(row - 1, col))
                for which, neighbour in (
                        ("top", above),
                        ("bottom", self._side(row + 1, col)),
                        ("left", self._side(row, col - 1) if col else None),
                        ("right", self._side(row, col + 1))):
                    if neighbour != side:
                        found.setdefault((side, which), set()).add((row, col))
        return found

    def paintEvent(self, event) -> None:            # noqa: N802 - Qt naming
        """Outline each team's region as one continuous border.

        Two things decide whether this looks like an outline or like a row
        of boxes, and both had been got wrong by reasoning about pixels
        instead of looking at them.

        **WHERE the line goes.** Round the portrait the delegate actually
        drew, one pixel of background clear of it, so it traces the edge
        of the picture without covering any of it. Derived insets kept
        landing a pixel or two inside the art, because the cell is not the
        picture: Qt's grid line takes a column out of `visualRect` and the
        fitted 16:9 portrait lands wherever the rounding puts it. Asking
        the painter that drew it cannot be off.

        **HOW FAR it runs.** A line held inside its own portrait's width
        stops short of the next portrait's, so a border along five cells
        comes out as five separate rectangles with a break at every face —
        which is exactly what this looked like. So each segment is
        measured against the neighbour ON ITS OWN LINE: it runs to the
        cell's full edge, and a step over the grid line (`GAP`), wherever
        that neighbour is the same team, so the next segment carries on
        from precisely where this one stopped; and it stops on the
        portrait's own corner where the neighbour is not, which is where
        the perpendicular edge is waiting for it. Every join is exact by
        construction rather than by an overshoot that has to be tuned.
        """
        super().paintEvent(event)
        cells = self.itemDelegate()
        colours = getattr(cells, "colours", {})
        drawn = getattr(cells, "drawn", {})
        edges = self._edges()
        if not edges:
            return
        heads = getattr(self.horizontalHeader(), "sides", {})

        def side_at(row: int, col: int):
            """The neighbour, with the header standing in above row 0."""
            if row < 0:
                return heads.get(col)
            if col < 0:
                return None
            return self._side(row, col)

        painter = QPainter(self.viewport())
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, False)
        for (side, which), members in edges.items():
            painter.setPen(QPen(QColor(colours.get(side, theme.GOOD)),
                                PAIR_EDGE_W))
            for row, col in sorted(members):
                cell = self.visualRect(self.model().index(row, col))
                if cell.isEmpty():
                    continue
                # The picture, or the whole cell where there is none to
                # trace (no portraits downloaded yet).
                art = drawn.get((row, col), cell)
                ring = _ring(art)
                ends = [self._end(row, col, side, which, step, cell,
                                  ring, drawn, side_at)
                        for step in PERPENDICULAR[which]]
                if which in ("top", "bottom"):
                    y = ring.top() if which == "top" else ring.bottom()
                    painter.drawLine(ends[0], y, ends[1], y)
                else:
                    x = ring.left() if which == "left" else ring.right()
                    painter.drawLine(x, ends[0], x, ends[1])
        painter.end()

    def _end(self, row, col, side, which, step, cell, ring, drawn, side_at):
        """Where one end of one edge stops, and why there are three cases.

        A border turns three different ways at a step of the staircase and
        each needs a different answer, which is what made every attempt at
        one blanket rule leave either a gap or a stub:

        1. **It carries on.** The cell along this line is the same team and
           does not have this edge's neighbour behind it, so it draws this
           same edge — run to the cell's own boundary and one pixel over
           the grid line, and the next segment starts exactly there.
        2. **It turns at this cell.** The cell along the line belongs to
           the other team, so THIS cell has a perpendicular edge, drawn at
           this cell's own ring — so stop on that ring and the two meet in
           the corner.
        3. **It turns at the cell diagonally across.** The cell along the
           line is ours and so is the one diagonally beyond it, which
           means the border steps out and away: the perpendicular edge
           belongs to that DIAGONAL cell and is drawn on ITS ring, so this
           segment has to reach that far to meet it. This is the case a
           staircase is made of, and the one that was missing.
        """
        dr, dc = DELTA[step]
        wr, wc = DELTA[which]
        far = step in ("right", "bottom")
        if side_at(row + dr, col + dc) != side:                    # case 2
            return _reach(ring, step)
        if side_at(row + dr + wr, col + dc + wc) != side:          # case 1
            return _side_of(cell, step) + (self.GAP if far else 0)
        turn = drawn.get((row + dr + wr, col + dc + wc))           # case 3
        if turn is None:
            return _side_of(cell, step) + (self.GAP if far else 0)
        return _reach(_ring(turn), OPPOSITE[step])


class DeltaCellDelegate(QStyledItemDelegate):
    """A grid cell's number, with the same black halo the tiles' numbers have.

    The two grids printed their deltas as ordinary table text, which made
    them the one place in the app where a signed number had no outline
    round it. The halo is not decoration: it separates the figure from
    whatever is behind it, and it is what makes a number in a cell and a
    number on a portrait read as the same kind of object rather than as
    two conventions. Nothing else about the cell changes — same text, same
    colour rule, same centred position.
    """

    def paint(self, painter, option, index):        # noqa: N802 - Qt naming
        from . import tilekit
        text = index.data(Qt.ItemDataRole.DisplayRole)
        if not text:
            return
        # The colour the item was given, which is the sign's colour; a
        # cell of exactly zero is given none and takes the body colour.
        brush = index.data(Qt.ItemDataRole.ForegroundRole)
        colour = brush.color().name() if brush is not None else theme.TEXT
        tilekit.paint_number(painter, option.rect, str(text), colour,
                             option.font)


class PairCellDelegate(QStyledItemDelegate):
    """A grid cell with its hero's portrait behind the number.

    The synergy grid used to carry a column of portraits down its left
    edge to name the rows. Half that grid is blank — synergy is symmetric —
    so the row's own face goes INTO its cells instead: the pair names
    itself, the header column's width goes back to the numbers, and the
    blank half is free for the other team's triangle.

    The number is outlined rather than plated, the same way a tile's is and
    for the same reason: a plate behind it is a rectangle of the portrait
    gone.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        # ALLY and ENEMY, not Radiant and Dire: the model does not know
        # which is which, and the answer changes between matches. The UI
        # sets it (`MatrixTable.set_team_colours`), so a triangle is
        # outlined in its own team's real colour. Read by `PairGrid` when
        # it strokes the two regions.
        self.colours = {"ally": theme.GOOD, "enemy": theme.BAD}
        # THE SAME BOX THE HEADERS GET (`MatrixTable._apply_icon_box`),
        # and getting this wrong is what made the borders look ragged. A
        # cell is CELL_PAD wider than its portrait on each side, so
        # fitting the art to the whole cell rect drew it a few pixels
        # WIDER than the identical portrait in the header above — and
        # left it touching the cell edge, with the result that a border
        # inset to clear the picture ran straight across it instead. One
        # box, one picture, everywhere in the grid; None until the table
        # has been sized, where the cell is all there is to go on.
        self.box: int | None = None
        # Where each cell's portrait actually landed, keyed by (row,
        # column) — read by `PairGrid.paintEvent`, which runs after every
        # cell has been painted, so the border traces the real picture
        # rather than a prediction of it.
        self.drawn: dict[tuple[int, int], QRect] = {}

    def paint(self, painter, option, index):        # noqa: N802 - Qt naming
        from .portraits import scaled
        from . import tilekit
        rect = option.rect
        painter.save()
        painter.fillRect(rect, QColor(theme.BG))
        hero = index.data(PAIR_HERO)
        # FITTED, exactly as the header above fits its own — one portrait
        # at one shape everywhere in the grid. Filling the cell instead
        # (expand and crop) made these read as stretched: a cell is wider
        # than it is tall, so covering it threw away the top and bottom of
        # a 16:9 head shot and left a wide slice of the middle.
        room = min(self.box or rect.width(), rect.width())
        art = scaled(hero, room, rect.height()) if hero else None
        box = rect
        if art is not None:
            box = QRect(rect.left() + (rect.width() - art.width()) // 2,
                        rect.top() + (rect.height() - art.height()) // 2,
                        art.width(), art.height())
            painter.drawPixmap(box.topLeft(), art)
            self.drawn[(index.row(), index.column())] = QRect(box)
            if not index.data(PAIR_HEADER):
                # Knocked back, so the figure over it stays the subject.
                # Not the axis rows: those ARE the subject.
                painter.fillRect(box, QColor(0, 0, 0, PAIR_VEIL))
        value = index.data(PAIR_VALUE)
        if value is not None:
            # THE TILE'S OWN BADGE: same font, same size, same corner as
            # the figure on a pick up at the top of the window, so the two
            # are read the same way rather than as two conventions. The
            # header rows carry one too — that hero's synergy with its own
            # four — in the same corner, so a total is read exactly where
            # the pairs that made it are.
            # An AXIS row's figure is that hero's whole triangle, so it
            # takes the sigma; a body cell is one pair and does not.
            text = (sigma(value) if index.data(PAIR_HEADER)
                    else f"{float(value) * 100:+.2f}")
            tilekit.paint_badge(painter, box, text,
                                theme.GOOD if float(value) > 0 else theme.BAD,
                                option.font)
        painter.restore()


class MatrixTable(QWidget):
    """A drafted-hero grid: allies against enemies, or allies with allies.

    Reading a total tells you the draft is fine; reading the grid tells you
    which lane is not. Cells are coloured by sign and blank where a pair has
    no meaning (the diagonal, and the half a symmetric matrix would repeat).
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)
        self.caption = QLabel("")
        self.caption.setWordWrap(True)
        self.caption.setProperty("dim", True)
        layout.addWidget(self.caption)
        self.table = PairGrid(0, 0)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setSelectionMode(QTableWidget.SelectionMode.NoSelection)
        self.table.setHorizontalHeader(
            PortraitHeader(Qt.Orientation.Horizontal, self.table))
        self.table.setVerticalHeader(
            PortraitHeader(Qt.Orientation.Vertical, self.table))
        # NEITHER BAR, EVER. The grid is five rows and it is sized to fit
        # them, so a scrollbar can only mean the fit was wrong — and it
        # hides part of the answer while making the widget look correct.
        # Off, so getting it wrong shows up as a squashed grid instead of
        # as a grid that quietly stopped showing a row.
        self.table.setVerticalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.table.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        # TOP LEFT, not centred. `_fit_height` and `_fit_width` give the
        # table a fixed size, so a layout puts the slack ABOVE it as well as
        # below and either side of it — and the moment the two grids stopped
        # being the same height (the synergy one grew a bottom header row)
        # the shorter one floated down the middle of its card and the two
        # stopped lining up. Left for the same reason: the grid begins under
        # the heading above it, and the room the columns no longer take is
        # plain background on the right.
        layout.addWidget(self.table, 1, Qt.AlignmentFlag.AlignTop
                         | Qt.AlignmentFlag.AlignLeft)
        self.empty_note = QLabel("")
        self.empty_note.setWordWrap(True)
        self.empty_note.setProperty("dim", True)
        layout.addWidget(self.empty_note)

    def _fit_width(self) -> None:
        """As wide as its columns, and no wider.

        `_fit_height` has always done this for the other axis. Left to
        stretch, the columns take whatever the card is given and the
        portraits sit in gaps that the rows do not have; fixed to the
        picture, the table has a width of its own and the layout aligns it
        left, so the grid still begins under the heading above it and the
        leftover is plain background rather than five wide columns.
        """
        head = self.table.horizontalHeader()
        down = self.table.verticalHeader()
        edge = 0 if down.isHidden() else down.width()
        self.table.setFixedWidth(
            edge + head.length() + 2 * self.table.frameWidth() + 2)

    def _fit_height(self) -> None:
        """Size the table to its rows — EVERYWHERE, not just the callout.

        A five-row grid left to stretch fills whatever height the layout
        gives it, and the leftover is dead space inside the widget: half
        the window was blank and the window could not be made shorter,
        because a stretching table has no smaller size to offer. There are
        never more than six rows, so the exact height is cheap to compute
        and it is always the right one.
        """
        # `verticalHeader().length()` is the sum of the sections Qt has
        # actually laid out, which is not the same as adding up rowHeight
        # before the layout has run — and being short by a few pixels puts
        # a scrollbar on a five-row grid, which is a grid you cannot read
        # without moving it. The header is measured the same way: its
        # `height()` is stale until it has been shown, so the larger of
        # that and its size hint is the honest number.
        head = self.table.horizontalHeader()
        header_h = max(head.height(), head.sizeHint().height())
        rows = self.table.verticalHeader().length()
        self.table.setFixedHeight(
            header_h + rows + 2 * self.table.frameWidth() + 2)

    def set_compact(self, compact: bool = True,
                    short_names: bool = True) -> None:
        """Drop the explanatory caption, and optionally the full names.

        The caption goes everywhere: the card heading says which grid this
        is and the headers say what the axes are, so a paragraph repeating
        both only stands between the reader and the numbers. Short names
        are for the in-game callout alone, where width is scarce and the
        reader is looking at the same five portraits anyway.
        """
        self._compact = compact
        self._short_names = compact and short_names
        self.caption.setVisible(not compact)

    def set_icon_headers(self, on: bool = True,
                         size: int = HEADER_ICON) -> None:
        """Head the rows and columns with the heroes' own portraits.

        The grid sits directly under the tiles it describes, so a column
        headed by the same picture as the tile above it reads straight
        down; a name repeated in a narrow header does not. Falls back to
        the name for any hero whose portrait has not been downloaded.
        """
        self._icon_headers = on
        self._icon_size = size

    def set_team_colours(self, ally: str, enemy: str) -> None:
        """Which colour each team is outlined in, this match.

        Radiant is green and Dire is red — Dota's own two colours, and the
        ones the user asked for — so which of ALLY and ENEMY gets which
        depends on the side the player is on. It is set from outside for
        exactly that reason: nothing below the UI knows.
        """
        self._team_colours = (ally, enemy)
        self._pair_delegate().colours = {"ally": ally, "enemy": enemy}
        self._apply_team_boxes()
        self.table.viewport().update()

    def _apply_team_boxes(self) -> None:
        """Box each header strip in its own team's colour.

        Both grids put the enemies ACROSS the top and the allies DOWN the
        side — counters because the columns read against their five, the
        pair grid because its upper triangle is theirs — so one rule does
        both. An empty grid gets neither: an outline round five blank
        sections is a claim about heroes nobody has picked.
        """
        ally, enemy = getattr(self, "_team_colours", (theme.GOOD, theme.BAD))
        across = self.table.horizontalHeader()
        down = self.table.verticalHeader()
        heroes = bool(getattr(across, "heroes", {}) or
                      getattr(down, "heroes", {}))
        # In the PAIR grid the top strip and the triangle under it are the
        # same team wherever the first body row is theirs, so the header's
        # bottom edge is opened there and the two read as one region. In
        # counters the header is an axis and the cells below are a
        # different thing entirely, so it keeps its whole box.
        open_edges = self._pair_open_edges() if heroes else ()
        if isinstance(across, PortraitHeader):
            across.set_outline(enemy if heroes else "", open_edges, "enemy")
        if isinstance(down, PortraitHeader):
            down.set_outline(ally if heroes and not down.isHidden() else "")

    def _pair_open_edges(self) -> set:
        """Columns whose first body cell belongs to the top strip's team."""
        return {col for col in range(self.table.columnCount())
                if (item := self.table.item(0, col)) is not None
                and item.data(PAIR_SIDE) == "enemy"}

    def set_margins(self, on: bool) -> None:
        """Draw the Sigma row and column, or leave them off.

        Off where each hero's own tile already carries its total: the same
        figure in two places, one of them in the corner of a grid, is one
        place too many.
        """
        self._margins = on

    def show_matrix(self, matrix, empty_text: str = "") -> None:
        self.caption.setText(matrix.caption)
        self.caption.setVisible(not getattr(self, "_compact", False))
        self.empty_note.setText("" if not matrix.empty else empty_text)
        self.empty_note.setVisible(bool(matrix.empty and empty_text))
        self.table.setVisible(True)
        if matrix.empty:
            # The grid stays on screen as an outline. A card that vanishes
            # until the draft fills in leaves the tab collapsing and
            # re-expanding under the reader; the shape of the answer is
            # itself information, and it is where the answer will appear.
            self._show_outline()
            return
        self.table.setStyleSheet("")            # back to the app's own
        self.table.setItemDelegate(self._delta_delegate())

        # The sections this was last applied to are about to be replaced,
        # so the cached figure no longer describes anything.
        self._icon_box = None
        margins = getattr(self, "_margins", True)
        extra = 1 if margins else 0
        self.table.setRowCount(len(matrix.rows) + extra)
        self.table.setColumnCount(len(matrix.cols) + extra)
        self._set_headers(matrix, margins)

        for row, line in enumerate(matrix.cells):
            for col, value in enumerate(line):
                if value is None:
                    item = QTableWidgetItem("")
                    item.setFlags(Qt.ItemFlag.NoItemFlags)
                else:
                    item = delta_item(value)
                self.table.setItem(row, col, item)
        if margins:
            last_col, last_row = len(matrix.cols), len(matrix.rows)
            for row, value in enumerate(matrix.row_totals):
                self.table.setItem(row, last_col, _total_item(value))
            for col, value in enumerate(matrix.col_totals):
                self.table.setItem(last_row, col, _total_item(value))
            self.table.setItem(last_row, last_col, _total_item(matrix.total))

        header = self.table.horizontalHeader()
        header.setStretchLastSection(False)
        # Fixed narrow columns and a height fitted to the rows are the
        # CALLOUT's layout, not every compact one: in the main window the
        # grid should fill its card and the names should stay readable.
        cramped = getattr(self, "_short_names", False)
        for col in range(self.table.columnCount()):
            if cramped:
                header.setSectionResizeMode(col, QHeaderView.ResizeMode.Fixed)
                self.table.setColumnWidth(col, COMPACT_COLUMN)
            else:
                # Stretch, not fit-to-contents: a column pushed off the
                # right edge costs more than a name elided by a few pixels.
                header.setSectionResizeMode(col, QHeaderView.ResizeMode.Stretch)
        if not getattr(self, "_icon_headers", False):
            # With portrait headers the row height is set by _set_headers,
            # to the same square the columns use; resizing to contents here
            # would shrink it back to the height of a line of digits.
            self.table.verticalHeader().setSectionResizeMode(
                QHeaderView.ResizeMode.ResizeToContents)
        # LAST WORD ON THE COLUMNS. The stretch above is for a grid of
        # names; with portraits the columns are cut to the picture, and
        # this has to run after that loop rather than before it inside
        # `_set_headers`, or the stretch puts the gaps straight back.
        self._apply_icon_box()
        self._fit_height()

    def show_pairs(self, grid, empty_text: str = "") -> None:
        """Both teams' synergies, as the two triangles of one square.

        DIRE above the diagonal, read against the enemy portraits along
        the TOP; RADIANT below it, read against the ally portraits along
        the BOTTOM, which is an ordinary last ROW of the table rather than
        a second header — Qt has no bottom header and a separate widget
        under the table would not keep its columns in step with it.
        Radiant takes the lower LEFT because that is the half of the square
        reaching the same edge its panel sits at.

        There is no left-hand header at all: every cell carries its own row
        hero's portrait, so the pair names itself.

        THE BODY IS ONE ROW SHORTER THAN IT IS WIDE, because the triangles
        touch: n heroes a side is n(n-1) pairs across both teams, which is
        exactly (n-1) rows of n. With the bottom axis row added back the
        table is n by n — the same five rows the counters grid has, which
        is what makes the two cards line up without either being told
        about the other.
        """
        self.caption.setVisible(False)
        self.empty_note.setText("" if not grid.empty else empty_text)
        self.empty_note.setVisible(bool(grid.empty and empty_text))
        self.table.setVisible(True)
        self.table.setStyleSheet("")
        self._icon_box = None
        # Before the empty check too: an empty synergy grid is the same
        # grid waiting to fill, so it should not sprout a header column
        # that the filled one does not have.
        self.table.verticalHeader().setVisible(False)
        if grid.empty:
            self._show_outline()
            return
        columns = grid.columns
        rows = len(grid.cells)
        self.table.setColumnCount(columns)
        # One extra row: the enemy portraits, which are this grid's second
        # header and the axis its lower triangle is read against.
        self.table.setRowCount(rows + 1)
        self.table.setItemDelegate(self._pair_delegate())

        for row in range(rows):
            for col in range(columns):
                cell = grid.cells[row][col]
                item = QTableWidgetItem()
                item.setFlags(Qt.ItemFlag.NoItemFlags)
                if cell is not None:
                    item.setData(PAIR_HERO, cell.hero_id)
                    item.setData(PAIR_VALUE, cell.delta)
                    item.setData(PAIR_SIDE, cell.side)
                    item.setData(SORT_ROLE, cell.delta)
                self.table.setItem(row, col, item)
        for col, (hero_id, name) in enumerate(grid.allies):
            item = QTableWidgetItem()
            item.setFlags(Qt.ItemFlag.NoItemFlags)
            item.setData(PAIR_HERO, hero_id)
            item.setData(PAIR_HEADER, True)
            # IN the triangle, not beside it: the bottom row is Radiant's
            # own axis and it sits against Radiant's triangle, so giving it
            # the same side makes the green outline enclose the faces and
            # the pairs as one region instead of drawing a line between a
            # team and its own portraits.
            item.setData(PAIR_SIDE, "ally")
            total = grid.ally_totals.get(hero_id)
            if total is not None:
                item.setData(PAIR_VALUE, total)
            item.setToolTip(name)
            self.table.setItem(rows, col, item)

        self._set_pair_columns(grid)
        header = self.table.horizontalHeader()
        header.setStretchLastSection(False)
        for col in range(columns):
            header.setSectionResizeMode(col, QHeaderView.ResizeMode.Stretch)
        self._apply_icon_box()
        self._fit_height()

    def _delta_delegate(self):
        if getattr(self, "_deltas", None) is None:
            # Kept on the widget for the same reason the pair one is: a
            # delegate the table does not own is collected the moment this
            # returns, and the cells fall back to Qt's own with no halo.
            self._deltas = DeltaCellDelegate(self.table)
        return self._deltas

    def _pair_delegate(self):
        if getattr(self, "_pairs", None) is None:
            # Kept on the widget: a delegate the table does not own is
            # garbage-collected the moment this method returns, and the
            # cells then draw with Qt's default one and no portraits.
            self._pairs = PairCellDelegate(self.table)
        return self._pairs

    def _set_pair_columns(self, grid) -> None:
        """The TOP header is the ENEMIES, whose triangle it sits on; there
        is no left header at all."""
        from .portraits import portrait
        by_index, totals = {}, {}
        for index, (hero_id, name) in enumerate(grid.enemies):
            item = QTableWidgetItem()
            total = grid.enemy_totals.get(hero_id)
            if portrait(hero_id) is None:
                # No art to print a badge on, so the total goes in the
                # text beside the name rather than being dropped.
                item.setText(name if total is None
                             else f"{name} {total * 100:+.2f}")
            else:
                by_index[index] = hero_id
                if total is not None:
                    totals[index] = total
                item.setToolTip(name)
            self.table.setHorizontalHeaderItem(index, item)
        # BLANK THE REST. The grid is as wide as the LONGER team, so a
        # 5v4 leaves a column with no hero to head it — and a header
        # section with no item of its own draws Qt's default label, which
        # came out as a white box with "5" in it in the corner of the card.
        for index in range(len(grid.enemies), self.table.columnCount()):
            self.table.setHorizontalHeaderItem(index, QTableWidgetItem(""))
        head = self.table.horizontalHeader()
        if isinstance(head, PortraitHeader):
            head.set_heroes(by_index)
            head.set_values(totals)

    def _show_outline(self) -> None:
        """Five by five of nothing — the shape the grid will have."""
        self.table.setRowCount(BLANK_SIDE)
        self.table.setColumnCount(BLANK_SIDE)
        for header, setter in ((self.table.horizontalHeader(),
                                self.table.setHorizontalHeaderItem),
                               (self.table.verticalHeader(),
                                self.table.setVerticalHeaderItem)):
            if isinstance(header, PortraitHeader):
                header.set_heroes({})
                header.set_values({})
            for index in range(BLANK_SIDE):
                setter(index, QTableWidgetItem(""))
        self._apply_team_boxes()
        for row in range(BLANK_SIDE):
            for col in range(BLANK_SIDE):
                cell = QTableWidgetItem("")
                cell.setFlags(Qt.ItemFlag.NoItemFlags)
                self.table.setItem(row, col, cell)
        # Grid lines are on everywhere now (the numbers alone were not
        # enough structure to keep a column straight across five), so
        # nothing extra is needed here — an empty grid draws as a grid.
        head = self.table.horizontalHeader()
        head.setStretchLastSection(False)
        width, height = self._blank_metrics()
        for col in range(BLANK_SIDE):
            if width is None:
                head.setSectionResizeMode(col, QHeaderView.ResizeMode.Stretch)
            else:
                head.setSectionResizeMode(col, QHeaderView.ResizeMode.Fixed)
                self.table.setColumnWidth(col, width)
        # Fixed rows, not ResizeToContents: empty cells have no contents,
        # so the outline would collapse to five hairlines.
        side = self.table.verticalHeader()
        side.setSectionResizeMode(QHeaderView.ResizeMode.Fixed)
        side.setDefaultSectionSize(height)
        for row in range(BLANK_SIDE):
            self.table.setRowHeight(row, height)
        if width is not None:
            if isinstance(side, PortraitHeader) and not side.isHidden():
                side.setFixedWidth(width)
            self._fit_width()
        self._fit_height()

    def _blank_metrics(self) -> tuple[int | None, int]:
        """The cell the empty outline draws, before there is a hero in it.

        The whole point of drawing an empty grid is that it is the SHAPE
        the answer will have, so it has to be worked out the same way a
        filled one is: as wide as the widest number, and as tall as the
        16:9 portrait that width implies. A constant cannot do it — the
        body size has been raised twice since one was written down here,
        and the outline quietly stopped matching the grid it stands in for.
        None means "stretch", which is right where the headers are names
        rather than pictures and nothing sets a natural width.
        """
        if not getattr(self, "_icon_headers", False):
            return None, BLANK_ROW
        digits = self.table.fontMetrics().horizontalAdvance(WIDEST_TOTAL) + 10
        size = max(min(self._portrait_want(), self._portrait_room()),
                   digits - 2 * CELL_PAD)
        return size + 2 * CELL_PAD, round(size * 9 / 16) + 2 * CELL_PAD

    def set_tile_width(self, width: int) -> None:
        """The pick tile's width — the box every portrait in the app takes.

        A grid portrait used to have a size of its own, so the same hero
        was one size at the top of the window and another in the grid
        below it. The draft panel decides the box for the whole app (see
        `TeamPanel._resize_tiles`) and hands it down; this grid can only
        make it SMALLER, when six of them will not fit across half the
        window.
        """
        self._tile_w = max(1, int(width))

    def _portrait_want(self) -> int:
        return getattr(self, "_tile_w", None) or HEADER_ICON_MAX

    def sections(self) -> int:
        """How many portraits wide this grid is — its columns, plus the
        row header when it has one, or 0 before it holds anything.

        ZERO IS THE IMPORTANT ANSWER. An empty grid used to report one
        section, and one section divides the whole card into a single
        enormous portrait — so the cap computed at startup, BEFORE the
        first refresh fills the grids, was 304 and was then latched. The
        two never re-agreed: the picks kept their own size and the grids
        settled on theirs, which is the "weird shit happening to the top
        portraits" in the screenshot. A grid with nothing in it has no
        opinion about how big a portrait should be, and has to say so.
        """
        cols = self.table.columnCount()
        if cols < 1:
            return 0
        down = self.table.verticalHeader()
        return cols + (0 if down.isHidden() else 1)

    def _portrait_room(self) -> int:
        """What this card fits, ITS OWN sections across.

        It used to divide by a hard-coded SIX — what the busier of the two
        grids needs — so that the pair of them agreed with each other. They
        did, and both disagreed with the pick tiles above them, which is
        what "the matrix portraits are smaller than the other portraits"
        was. The two are made to agree a better way now: each asks for what
        it can honestly fit, the SMALLEST answer becomes the app's one box
        (`teams.set_grid_cap`), and the picks come down to meet it. So this
        can go back to telling the truth about its own width.

        Measured on THIS WIDGET rather than on the inner table, and that
        distinction is the whole reason this is safe: the table is fixed
        to whatever this chooses, so measuring inside it would be
        measuring the last answer and the portraits would lose a few
        pixels on every layout pass. The wrapper expands to its card
        regardless. Before the first layout there is no width to read, so
        it falls back to half the window, which is what a card gets.
        """
        room = self.width() or (self.window().width() // 2)
        n = self.sections()
        if n < 1:
            return 0            # nothing to measure; see `sections`
        return max(HEADER_ICON,
                   (room - 2 * CARD_MARGIN) // n - 2 * CELL_PAD)

    def portrait_ceiling(self) -> int:
        """The biggest portrait this card can draw. Read by the window,
        which takes the smaller of the two grids' answers and makes it the
        box every portrait in the app uses."""
        return self._portrait_room()

    def _apply_icon_box(self) -> None:
        """Give both headers the SAME portrait, sized to the window.

        Without one number for both, the two headers scale from different
        measurements and nothing on screen says why: a column header's
        section is (stretched column width) x (fixed header height) and a
        row header's is (fixed header width) x (row height), so each
        portrait is limited by a different one — which is how a wide window
        ended up with big portraits along one axis and small ones along the
        other.

        So one WIDTH is chosen for both, and the sections are then cut to
        what that actually draws. A portrait is 256x144, so a square
        section would be 40% empty space; the height comes from measuring
        the scaled pixmap rather than assuming the picture is square.
        """
        if not getattr(self, "_icon_headers", False):
            return
        columns = self.table.columnCount()
        if columns < 1:
            return
        across = self.table.horizontalHeader()
        down = self.table.verticalHeader()
        floor = getattr(self, "_icon_size", HEADER_ICON)
        # Only grow for PICTURES. With no portraits downloaded the headers
        # fall back to names, and a 68px row header elides "Tidehunter"
        # while making every row 68px tall for nothing.
        heroes = list(getattr(across, "heroes", {}).values()) or \
            list(getattr(down, "heroes", {}).values())
        self._apply_team_boxes()
        if not heroes:
            self._icon_box = None
            across.setFixedHeight(floor + 4)
            down.setFixedWidth(ROW_HEADER)
            down.setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
            return

        # From the WINDOW, never from our own viewport. The columns are
        # fixed to what this chooses, so measuring the room inside the
        # table would be measuring the last answer: each pass would take a
        # few pixels off the one before and the portraits would shrink away
        # over a handful of layout passes. The window's width cannot depend
        # on our choice — the floor comes from `minimum_grid_width` and a
        # snug grid is well inside it.
        # WIDE ENOUGH FOR THE NUMBER, measured against the real font. A
        # snug column is cut to its portrait, and a portrait is narrower
        # than "+12.34" at the app's body size — so cutting to the picture
        # alone put "..." where the numbers were, which is a grid that has
        # stopped being a grid. Measured rather than guessed at, because
        # the body size has been raised twice and a constant does not
        # follow it.
        digits = self.table.fontMetrics().horizontalAdvance(WIDEST_TOTAL) + 10
        size = max(floor, min(self._portrait_want(), self._portrait_room()),
                   digits - 2 * CELL_PAD)
        cells = self.table.itemDelegate()
        if isinstance(cells, PairCellDelegate):
            cells.box = size
        if size != getattr(self, "_icon_box", None):
            self._icon_box = size
            from .portraits import scaled
            art = scaled(heroes[0], size, size)
            self._icon_drawn = ((art.width(), art.height()) if art is not None
                                else (size, size))
            for header in (across, down):
                if isinstance(header, PortraitHeader):
                    header.set_box(size)
        width, height = self._icon_drawn
        pad = 2 * CELL_PAD
        across.setFixedHeight(height + pad)
        down.setFixedWidth(width + pad)
        down.setSectionResizeMode(QHeaderView.ResizeMode.Fixed)
        down.setDefaultSectionSize(height + pad)
        for row in range(self.table.rowCount()):
            self.table.setRowHeight(row, height + pad)
        # Every column is CUT TO ITS PORTRAIT, not stretched to the card.
        # The rows were already snug — a row is the height of the picture
        # in it — and stretching the other axis meant a gap between every
        # pair of columns and none between any pair of rows, which reads as
        # the grid having come apart horizontally. The slack goes to the
        # RIGHT of the table (see `_fit_width`), so the grid still starts
        # under the heading above it.
        column = max(width + 2 * CELL_PAD, digits)
        for col in range(columns):
            across.setSectionResizeMode(col, QHeaderView.ResizeMode.Fixed)
            self.table.setColumnWidth(col, column)
        self._fit_width()
        self._fit_height()

    def resizeEvent(self, event) -> None:       # noqa: N802 - Qt naming
        super().resizeEvent(event)
        self._apply_icon_box()

    def _set_headers(self, matrix, margins: bool) -> None:
        icons = getattr(self, "_icon_headers", False)
        label = (short_name if getattr(self, "_short_names", False)
                 else (lambda n: n))
        cols = [n for _i, n in matrix.cols] + ([TOTAL_LABEL] if margins else [])
        rows = [n for _i, n in matrix.rows] + ([TOTAL_LABEL] if margins else [])
        if not icons:
            self.table.setHorizontalHeaderLabels([label(n) for n in cols])
            self.table.setVerticalHeaderLabels([label(n) for n in rows])
            return

        from .portraits import portrait
        size = getattr(self, "_icon_size", HEADER_ICON)
        for ids, names, header, setter in (
                ([i for i, _n in matrix.cols], cols,
                 self.table.horizontalHeader(),
                 self.table.setHorizontalHeaderItem),
                ([i for i, _n in matrix.rows], rows,
                 self.table.verticalHeader(),
                 self.table.setVerticalHeaderItem)):
            by_index = {}
            for index, name in enumerate(names):
                item = QTableWidgetItem()
                art = portrait(ids[index]) if index < len(ids) else None
                if art is None:
                    # No portrait downloaded, or the margin column: the
                    # name still has to say which hero this is.
                    item.setText(label(name))
                else:
                    by_index[index] = ids[index]
                    item.setToolTip(name)
                setter(index, item)
            if isinstance(header, PortraitHeader):
                header.set_heroes(by_index)
                # EACH HERO'S TOTAL, ON ITS OWN FACE, at the user's
                # request — a column header carries that enemy's whole
                # column and a row header that ally's whole row, with a
                # sigma to say it is a sum. This is the same rule the
                # synergy axis rows follow, so the two cards agree, and it
                # is why the Sigma row and column stay OFF: a total drawn
                # on the portrait it belongs to costs no grid at all,
                # where a margin row and column would have cost a section
                # of width each and made every portrait smaller.
                totals = (matrix.col_totals if header is
                          self.table.horizontalHeader() else matrix.row_totals)
                header.set_values({i: v for i, v in enumerate(totals)
                                   if i < len(ids)})
        self._apply_icon_box()
