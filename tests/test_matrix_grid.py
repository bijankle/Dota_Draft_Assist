"""The two grids: their portrait headers, and what they draw when empty.

Both faults here were invisible to every test that only asked what the
numbers were. The headers scale from different measurements — a column
section is (stretched width) x (fixed header height), a row section is
(fixed header width) x (row height) — so without one shared box a wide
window grows one axis' portraits and not the other's. And an empty grid
used to hide itself, which moved everything below it.
"""

import os

import pytest

pytest.importorskip("PyQt6")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtGui import QColor, QPixmap                     # noqa: E402
from PyQt6.QtWidgets import QApplication                    # noqa: E402

from draft_assist.model.scoring import Matrix               # noqa: E402
from draft_assist.ui import portraits                       # noqa: E402
from draft_assist.ui.tables import (HEADER_ICON,            # noqa: E402
                                    HEADER_ICON_MAX, BLANK_SIDE,
                                    MatrixTable, PortraitHeader)

HEROES = [(1, "Anti-Mage"), (2, "Axe"), (3, "Bane"), (4, "Bloodseeker"),
          (5, "Crystal Maiden")]


@pytest.fixture(scope="module")
def qapp():
    yield QApplication.instance() or QApplication([])


@pytest.fixture()
def art(tmp_path, monkeypatch):
    """Portraits on disk, at the shape Dota publishes them: 256x144."""
    for hero_id, name in HEROES:
        pixmap = QPixmap(256, 144)
        pixmap.fill(QColor("#3050a0"))
        pixmap.save(str(tmp_path / f"{hero_id}_{name.lower()}.png"))
    monkeypatch.setattr(portraits, "BASE_DIR", tmp_path)
    portraits.forget()
    yield tmp_path
    portraits.forget()


def grid() -> Matrix:
    return Matrix(rows=list(HEROES), cols=list(HEROES),
                  cells=[[0.01 * (r + c) for c in range(5)] for r in range(5)])


def built(qapp, width=700) -> MatrixTable:
    table = MatrixTable()
    table.set_compact(True, short_names=False)
    table.set_icon_headers(True)
    table.set_margins(False)
    table.resize(width, 400)
    table.show()                    # geometry is not applied until shown
    QApplication.processEvents()
    table.show_matrix(grid())
    QApplication.processEvents()
    return table


def boxes(table: MatrixTable) -> tuple[int, int]:
    return (table.table.horizontalHeader().box,
            table.table.verticalHeader().box)


def drawn(table: MatrixTable) -> tuple[tuple, tuple]:
    """The size of the portrait each header actually puts on screen.

    Computed the way `paintSection` does, from the section it is handed —
    which is the whole point: the two sections are shaped differently and
    the pictures still have to come out the same.
    """
    from draft_assist.ui.portraits import scaled
    inner = table.table
    hero = next(iter(inner.horizontalHeader().heroes.values()))
    column = scaled(hero, min(inner.horizontalHeader().box,
                              inner.columnWidth(0)),
                    inner.horizontalHeader().height())
    row = scaled(hero, min(inner.verticalHeader().box,
                           inner.verticalHeader().width()),
                 inner.rowHeight(0))
    return ((column.width(), column.height()), (row.width(), row.height()))


def test_both_headers_draw_the_same_portrait(art, qapp):
    """The complaint was that widening the window grew one axis' portraits
    and left the other alone."""
    table = built(qapp)
    across, down = boxes(table)
    assert across == down
    assert drawn(table)[0] == drawn(table)[1]


def test_the_sections_are_cut_to_what_they_draw(art, qapp):
    """A portrait is 256x144, so a square header section would be 40%
    empty space and every row 40% too tall."""
    # The padding is a CONSTANT, read here rather than repeated: it is the
    # slack the team outline sits in, so it moves when that does, and a
    # literal 4 would leave this measuring a layout the app stopped
    # drawing — which is exactly what it did.
    from draft_assist.ui.tables import CELL_PAD
    pad = 2 * CELL_PAD
    table = built(qapp)
    width, height = drawn(table)[0]
    assert table.table.horizontalHeader().height() == height + pad
    assert table.table.verticalHeader().width() == width + pad
    assert table.table.rowHeight(0) == height + pad


def test_the_two_headers_agree_at_every_width(art, qapp):
    """Both or neither, always. The complaint that started this was a wide
    window growing one axis' portraits and leaving the other alone.

    The columns are SNUG now — cut to the picture rather than stretched to
    the card — so the portrait settles at a size of its own instead of
    following the window up. What has to hold at every width is that the
    two axes land on the same one."""
    for width in (200, 340, 700, 1400):
        table = built(qapp, width=width)
        across, down = boxes(table)
        assert across == down, f"at {width}: {across} vs {down}"
    # THE NUMBER SETS THE FLOOR, not HEADER_ICON_MAX: a column has to print
    # the widest figure it can be asked for whatever the portrait would
    # have liked to be, so the picture is whichever of the two is bigger.
    # Above the width where the room runs out, that is the whole answer and
    # more window does not move it.
    # The widest figure is a TOTAL — the sigma sits ahead of the digits —
    # and this reads the module's own constant rather than repeating the
    # string, so a change to what a cell can hold cannot leave the check
    # measuring something the app stopped drawing.
    from draft_assist.ui.tables import WIDEST_TOTAL
    roomy = [built(qapp, width=w) for w in (700, 1400)]
    digits = roomy[0].table.fontMetrics().horizontalAdvance(WIDEST_TOTAL) + 10
    want = max(HEADER_ICON_MAX, digits - 4)
    assert [boxes(t)[0] for t in roomy] == [want, want], \
        "with room to spare the size should stop chasing the window"


def test_the_portraits_are_never_smaller_than_the_floor(art, qapp):
    """Squeezed, they shrink; there is a size below which a portrait is not
    worth drawing at all and the headers stop there."""
    table = built(qapp, width=200)
    across, down = boxes(table)
    assert across == down
    assert across >= HEADER_ICON


def test_the_columns_are_snug_and_the_slack_is_on_the_right(art, qapp):
    """The rows were already the height of the picture in them; the columns
    stretched to the card, so there was a gap between every pair of columns
    and none between any pair of rows. Fixed to the portrait, the table has
    a width of its own — and it is aligned LEFT, so the grid still begins
    under the heading above it."""
    from PyQt6.QtCore import Qt
    table = built(qapp, width=1400)
    inner = table.table
    from draft_assist.ui.tables import CELL_PAD
    drawn_w = drawn(table)[0][0]
    for col in range(5):
        assert inner.columnWidth(col) == drawn_w + 2 * CELL_PAD
    assert inner.width() < table.width(), "the table still fills the card"
    assert inner.x() < 20, "the slack should all be on the right"
    align = table.layout().itemAt(table.layout().indexOf(inner)).alignment()
    assert align & Qt.AlignmentFlag.AlignLeft


def test_with_no_portraits_the_headers_stay_at_the_floor(qapp, monkeypatch,
                                                          tmp_path):
    """Names, not pictures — and a 68px row header elides "Tidehunter"
    while making every row 68px tall for nothing."""
    monkeypatch.setattr(portraits, "BASE_DIR", tmp_path)
    portraits.forget()
    table = built(qapp, width=1400)
    assert boxes(table) == (HEADER_ICON, HEADER_ICON)
    portraits.forget()


def test_the_header_paints_the_portrait_itself(art, qapp):
    """Qt will not: a QHeaderView under a stylesheet ignores iconSize."""
    table = built(qapp)
    header = table.table.horizontalHeader()
    assert isinstance(header, PortraitHeader)
    assert header.heroes, "no hero ids reached the header"
    assert not table.table.grab().isNull()


def test_an_empty_grid_is_an_outline_not_a_hole(qapp):
    """A card that vanishes until the draft fills in moves everything under
    it; the shape of the answer is itself information."""
    table = MatrixTable()
    table.set_icon_headers(True)
    table.show_matrix(Matrix(rows=[], cols=[], cells=[]), "Fill in both teams.")
    assert not table.table.isHidden()
    assert table.table.rowCount() == BLANK_SIDE
    assert table.table.columnCount() == BLANK_SIDE
    assert table.empty_note.text() == "Fill in both teams."


def test_every_cell_has_a_border(art, qapp):
    """The numbers were meant to be the structure, and across five columns
    of signed deltas they are not — the eye loses which column it is in.
    The lines are on for the filled grid and the empty outline alike, so
    there is no per-state stylesheet to keep in step."""
    from draft_assist.ui import theme
    assert f"gridline-color: {theme.BORDER}" in theme.STYLESHEET
    table = built(qapp)
    assert "gridline-color" not in table.table.styleSheet(), \
        "no local override: the app-wide rule is the only one"
    assert table.table.showGrid()


# --------------------------------------------------------------------------
# The synergy grid: both teams, as the two triangles of one square.
# --------------------------------------------------------------------------

def test_a_pair_cell_actually_draws_its_portrait_and_number(qapp, tmp_path,
                                                            monkeypatch):
    """RENDER the portrait branch, don't just assert about the data.

    This grid's whole point is a picture behind a figure, and the portrait
    branch of a painter is exactly the kind of code that ships with a
    mistyped enum and no test to catch it — there is no portrait on disk in
    a dev checkout, so nothing takes that branch by accident.
    """
    from PyQt6.QtCore import QRect, Qt
    from PyQt6.QtGui import QColor, QImage, QPainter, QPixmap
    from PyQt6.QtWidgets import QStyleOptionViewItem, QTableWidget, \
        QTableWidgetItem
    from draft_assist.ui import portraits, theme
    from draft_assist.ui.tables import PAIR_HERO, PAIR_VALUE, PairCellDelegate

    blue = QPixmap(256, 144)
    blue.fill(QColor("#3050a0"))
    blue.save(str(tmp_path / "1_anti-mage.png"))
    monkeypatch.setattr(portraits, "BASE_DIR", tmp_path)
    portraits.forget()
    try:
        table = QTableWidget(1, 1)
        item = QTableWidgetItem()
        item.setData(PAIR_HERO, 1)
        item.setData(PAIR_VALUE, 0.0421)
        table.setItem(0, 0, item)

        picture = QImage(90, 40, QImage.Format.Format_ARGB32)
        picture.fill(0)
        painter = QPainter(picture)
        option = QStyleOptionViewItem()
        option.rect = QRect(0, 0, 90, 40)
        PairCellDelegate(table).paint(painter, option,
                                      table.model().index(0, 0))
        painter.end()

        colours = {picture.pixelColor(x, y).name()
                   for y in range(picture.height())
                   for x in range(picture.width())}
        # Drawn, and knocked back rather than at full strength.
        assert "#3050a0" not in colours, "the veil never went on"
        assert any(c.startswith("#1") or c.startswith("#2") for c in colours)
        assert theme.GOOD in colours, "the number is not on top of it"
        assert "#000000" in colours, "no outline round the digits"
        assert picture.pixelColor(2, 2).alpha() == 255, "unpainted cell"
    finally:
        portraits.forget()


def test_the_cell_portrait_is_the_same_shape_as_the_header_above_it(qapp,
                                                                    tmp_path,
                                                                    monkeypatch):
    """Fitted, never filled. Covering the cell instead threw away the top
    and bottom of a 16:9 head shot — a cell is wider than it is tall — and
    left a wide slice of the middle that read as stretched."""
    from PyQt6.QtGui import QColor, QPixmap
    from draft_assist.ui import portraits

    wide = QPixmap(256, 144)
    wide.fill(QColor("#3050a0"))
    wide.save(str(tmp_path / "1_anti-mage.png"))
    monkeypatch.setattr(portraits, "BASE_DIR", tmp_path)
    portraits.forget()
    try:
        art = portraits.scaled(1, 120, 40)
        assert art is not None
        # The portrait's own 16:9, not the cell's shape.
        assert abs(art.width() / art.height() - 256 / 144) < 0.05
        assert art.height() <= 40 and art.width() <= 120
    finally:
        portraits.forget()


def _render_pair_cell(table, row, col, size=(90, 40)):
    """One cell of a pair grid, painted into an image we can look at."""
    from PyQt6.QtCore import QRect
    from PyQt6.QtGui import QImage, QPainter
    from PyQt6.QtWidgets import QStyleOptionViewItem
    from draft_assist.ui.tables import PairCellDelegate

    picture = QImage(size[0], size[1], QImage.Format.Format_ARGB32)
    picture.fill(0)
    painter = QPainter(picture)
    option = QStyleOptionViewItem()
    option.rect = QRect(0, 0, size[0], size[1])
    PairCellDelegate(table).paint(painter, option,
                                  table.model().index(row, col))
    painter.end()
    return picture


def _pair_grid(allies=3, enemies=3):
    """A synergy grid of the shape the app builds: theirs upper right,
    yours lower left, lifted one row so the two triangles touch."""
    from draft_assist.model.scoring import PairCell, SynergyGrid
    ally = [(i + 1, name) for i, name in enumerate(
        [n for _, n in HEROES][:allies])]
    enemy = [(i + 1, name) for i, name in enumerate(
        [n for _, n in HEROES][:enemies])]
    side = max(allies, enemies)
    cells = []
    for row in range(side - 1):
        line = []
        for col in range(side):
            if col > row:
                line.append(PairCell(enemy[row][0], enemy[col][0], 0.01,
                                     "enemy"))
            else:
                line.append(PairCell(ally[row + 1][0], ally[col][0], -0.01,
                                     "ally"))
        cells.append(line)
    return SynergyGrid(allies=ally, enemies=enemy, cells=cells,
                       ally_totals={h: 0.02 for h, _ in ally},
                       enemy_totals={h: -0.02 for h, _ in enemy})


def _shot(art, qapp, width=700):
    """The whole pair grid rendered, headers included."""
    from draft_assist.ui import theme
    table = MatrixTable()
    table.set_compact(True, short_names=False)
    table.set_icon_headers(True)
    table.set_margins(False)
    table.set_team_colours(theme.GOOD, theme.BAD)
    table.resize(width, 400)
    table.show()
    QApplication.processEvents()
    table.show_pairs(_pair_grid())
    QApplication.processEvents()
    return table, table.table.grab().toImage()


def test_each_triangle_is_outlined_in_its_own_colour(art, qapp):
    """Two triangles that touch need a line saying which is which. The
    sides are ALLY and ENEMY, not Radiant and Dire: which team is which
    side is something only the UI knows, so the colours are set from
    outside."""
    from draft_assist.ui import theme
    _, picture = _shot(art, qapp)
    seen = {picture.pixelColor(x, y).name()
            for y in range(picture.height())
            for x in range(picture.width())}
    assert theme.GOOD in seen, "no green round your triangle"
    assert theme.BAD in seen, "no red round theirs"


def test_the_outline_is_one_continuous_line(art, qapp):
    """It was drawn per cell, each stroking the edges where its four
    neighbours disagreed — and between two cells there is the grid line,
    so every edge stopped a pixel short of the next and the border came
    out as a row of dashes with a break at each portrait."""
    from draft_assist.ui import theme
    _, picture = _shot(art, qapp)
    green = [(x, y) for y in range(picture.height())
             for x in range(picture.width())
             if picture.pixelColor(x, y).name() == theme.GOOD]
    assert green
    # The longest horizontal run of green anywhere, WHEREVER it sits.
    # It used to look at the lowest green pixel and scan that row, which
    # stopped being the bottom edge the moment the border was inset into
    # the cells to let both teams' colours be seen: the lowest green is
    # now the end cap of a vertical, and four pixels is not a line.
    # Measuring the longest unbroken run says the thing the test is
    # actually for, and says it wherever the border is drawn.
    rows: dict = {}
    for x, y in green:
        rows.setdefault(y, []).append(x)
    best, gaps = 0, None
    for y, xs in rows.items():
        xs = sorted(xs)
        run = longest = 1
        breaks = []
        for a, b in zip(xs, xs[1:]):
            if b - a <= 1:
                run += 1
                longest = max(longest, run)
            else:
                breaks.append(b - a)
                run = 1
        if longest > best:
            best, gaps = longest, breaks
    assert best > 100, f"no continuous edge: longest green run is {best}px"
    assert not gaps, f"the line breaks {len(gaps)} times: {gaps[:5]}"


def test_nothing_is_drawn_between_two_cells_of_the_same_team(art, qapp):
    """A union of rectangles was tried first and is not the answer:
    `QPainterPath.simplified` leaves rectangles that merely touch as
    separate subpaths, so every cell came out with a box round it — which
    says the boundary is between every portrait rather than between the
    two teams."""
    from draft_assist.ui import theme
    table, picture = _shot(art, qapp)
    inner = table.table
    # Row 1 of the body is yours at columns 0 and 1 (see `_pair_grid`).
    left = inner.visualRect(inner.model().index(1, 0))
    right = inner.visualRect(inner.model().index(1, 1))
    origin = inner.viewport().mapTo(inner, left.topLeft())
    band = origin.x() + left.width()
    strip = [picture.pixelColor(x, y).name()
             for x in range(band, band + (right.left() - left.right()) + 2)
             for y in range(origin.y() + 4, origin.y() + left.height() - 4)]
    assert theme.GOOD not in strip, "a line between two of your own cells"


def test_the_top_strip_is_not_boxed_off_from_its_own_triangle(art, qapp):
    """One of the two axis strips had a box round it while the other was
    part of its triangle. Where the cells below a header section are the
    same team, a line between them rules through the middle of one region
    — the user's words were "outer edge only, not a box around just the
    main high brightness row"."""
    from PyQt6.QtCore import QPoint
    from draft_assist.ui import theme
    table, picture = _shot(art, qapp)
    header = table.table.horizontalHeader()
    join = header.mapTo(table.table, QPoint(0, header.height() - 1)).y()
    red = [x for x in range(picture.width())
           for y in (join - 1, join, join + 1)
           if picture.pixelColor(x, y).name() == theme.BAD]
    # Column 0 IS yours below the strip, so the strip is closed over that
    # one column and open over the rest. A full-width line means the box
    # is back.
    assert len(set(red)) < picture.width() * 0.45, \
        "the top strip is boxed off from the triangle below it"


def test_the_counters_headers_are_boxed_by_team(art, qapp):
    """Your five DOWN the side against their five ACROSS the top, and
    nothing said which was which — the numbers read from your point of view
    either way, so the grid looked symmetrical while meaning two different
    things by its axes."""
    from draft_assist.ui import theme
    table = built(qapp)
    table.set_team_colours(theme.GOOD, theme.BAD)
    assert table.table.horizontalHeader().outline == theme.BAD
    assert table.table.verticalHeader().outline == theme.GOOD
    # An outline round five blank sections would be a claim about heroes
    # nobody has picked.
    table.show_matrix(Matrix(rows=[], cols=[], cells=[]))
    assert table.table.horizontalHeader().outline == ""


def test_a_cell_in_the_middle_of_a_triangle_has_no_outline(qapp):
    """Only the boundary is traced. Outlining every cell would be a grid
    of green and red boxes, which says nothing about where one team's
    half ends."""
    from PyQt6.QtWidgets import QTableWidget, QTableWidgetItem
    from draft_assist.ui import theme
    from draft_assist.ui.tables import PAIR_SIDE

    table = QTableWidget(3, 3)
    for row in range(3):
        for col in range(3):
            item = QTableWidgetItem()
            item.setData(PAIR_SIDE, "radiant")
            table.setItem(row, col, item)
    picture = _render_pair_cell(table, 1, 1)
    colours = {picture.pixelColor(x, y).name()
               for y in range(picture.height())
               for x in range(picture.width())}
    assert theme.GOOD not in colours


def test_the_axis_rows_are_full_brightness_and_carry_a_total(qapp, tmp_path,
                                                             monkeypatch):
    """The two header rows ARE the subject — they name the ten heroes the
    card is about — so they are not knocked back the way a cell behind a
    number is. Each carries that hero's synergy with its own four."""
    from PyQt6.QtGui import QColor, QPixmap
    from PyQt6.QtWidgets import QTableWidget, QTableWidgetItem
    from draft_assist.ui import portraits, theme
    from draft_assist.ui.tables import PAIR_HEADER, PAIR_HERO, PAIR_VALUE

    blue = QPixmap(256, 144)
    blue.fill(QColor("#3050a0"))
    blue.save(str(tmp_path / "1_anti-mage.png"))
    monkeypatch.setattr(portraits, "BASE_DIR", tmp_path)
    portraits.forget()
    try:
        table = QTableWidget(1, 2)
        for col, header in ((0, False), (1, True)):
            item = QTableWidgetItem()
            item.setData(PAIR_HERO, 1)
            item.setData(PAIR_VALUE, 0.0421)
            if header:
                item.setData(PAIR_HEADER, True)
            table.setItem(0, col, item)

        def colours(col):
            picture = _render_pair_cell(table, 0, col)
            return {picture.pixelColor(x, y).name()
                    for y in range(picture.height())
                    for x in range(picture.width())}

        body, axis = colours(0), colours(1)
        assert "#3050a0" not in body, "a cell behind a number is veiled"
        assert "#3050a0" in axis, "the axis row was knocked back too"
        # And the total is printed on it, in the same badge as everything.
        assert theme.GOOD in axis
        assert "#000000" in axis, "no outline round the digits"
    finally:
        portraits.forget()


def test_a_heros_total_is_its_four_pairs_not_a_row_of_the_grid(qapp):
    """A hero's pairs are split between a row and a column of its own
    triangle, so summing what is DRAWN in either direction alone gives a
    partial answer. The header number adds the four pairs it is in."""
    from draft_assist.model import scoring
    from draft_assist.ui.demo import demo_dataset

    ds = demo_dataset()
    allies, enemies = ds.hero_ids[:5], ds.hero_ids[5:10]
    grid = scoring.team_synergy_grid(
        ds, scoring.DraftState(allies=allies, enemies=enemies))
    for team, totals in ((allies, grid.ally_totals),
                         (enemies, grid.enemy_totals)):
        for hero in team:
            expected = sum(float(ds.delta_with[ds.index[hero], ds.index[other]])
                           for other in team if other != hero)
            assert totals[hero] == pytest.approx(expected)


def test_a_counters_cell_has_the_same_halo_as_a_tiles_number(qapp):
    """The grids printed their deltas as plain table text, which made them
    the one place in the app where a signed number had no outline round
    it. The halo is what separates a figure from whatever is behind it and
    what makes a number in a cell and a number on a portrait read as the
    same kind of object."""
    from PyQt6.QtCore import QRect
    from PyQt6.QtGui import QImage, QPainter
    from PyQt6.QtWidgets import QStyleOptionViewItem, QTableWidget
    from draft_assist.ui import theme
    from draft_assist.ui.tables import DeltaCellDelegate, delta_item

    table = QTableWidget(1, 1)
    table.setItem(0, 0, delta_item(0.0234))
    picture = QImage(90, 30, QImage.Format.Format_ARGB32)
    picture.fill(0)
    painter = QPainter(picture)
    option = QStyleOptionViewItem()
    option.rect = QRect(0, 0, 90, 30)
    DeltaCellDelegate(table).paint(painter, option, table.model().index(0, 0))
    painter.end()
    colours = {picture.pixelColor(x, y).name()
               for y in range(picture.height())
               for x in range(picture.width())
               if picture.pixelColor(x, y).alpha() > 0}
    assert theme.GOOD in colours, "the number itself"
    assert "#000000" in colours, "no halo round it"


def test_the_outline_colour_follows_the_side_the_player_is_on(qapp):
    """Radiant is green and Dire is red — Dota's own colours — so which of
    ally and enemy gets which changes with the match. Nothing below the UI
    knows the answer, so it is set from outside."""
    from draft_assist.ui import theme
    grid = MatrixTable()
    grid.set_icon_headers(True)
    grid.set_team_colours(theme.BAD, theme.GOOD)      # the player is Dire
    assert grid._pair_delegate().colours == {"ally": theme.BAD,
                                             "enemy": theme.GOOD}


def test_the_grid_portrait_is_the_pick_tiles_box(art, qapp):
    """A grid portrait had a size of its own, so the same hero was one
    size at the top of the window and another in the grid under it. One
    box for the whole app — and the grid gets a VOTE in it now rather than
    only a veto: it reports what it can fit (`portrait_ceiling`) and the
    window takes the smaller of the two cards' answers, because counters
    fits its row header plus five columns where a panel fits five tiles
    and no amount of margin-matching closes six against five."""
    from draft_assist.ui.tables import WIDEST_TOTAL
    table = built(qapp, width=1400)
    table.set_tile_width(132)
    table.show_matrix(grid())
    QApplication.processEvents()
    assert table._icon_box == min(132, table._portrait_room())
    assert table.portrait_ceiling() == table._portrait_room()
    # Squeezed, it gives way rather than pushing the columns off the card.
    narrow = built(qapp, width=520)
    narrow.set_tile_width(132)
    narrow.show_matrix(grid())
    QApplication.processEvents()
    assert narrow._icon_box < 132
    assert narrow._icon_box == max(narrow._portrait_room(),
                                   narrow.table.fontMetrics()
                                   .horizontalAdvance(WIDEST_TOTAL) + 6)


def test_the_grid_divides_by_its_own_sections(art, qapp):
    """It used to divide by a hard-coded SIX — what the busier of the two
    grids needs — so the pair of them agreed with each other and both
    disagreed with the picks above. Each asks about its own width now, and
    the window reconciles them."""
    table = built(qapp, width=1400)
    table.show_matrix(grid())
    QApplication.processEvents()
    down = table.table.verticalHeader()
    expected = table.table.columnCount() + (0 if down.isHidden() else 1)
    assert table.sections() == expected


def test_an_empty_grid_has_no_opinion_about_portrait_size(art, qapp):
    """**THIS SHIPPED AS A VISIBLE REGRESSION.** An empty grid reported ONE
    section, and one section divides the whole card into a single enormous
    portrait — so the cap taken at startup, before the first refresh fills
    the grids, was 304, and it was then latched. The picks and the grids
    settled on two different sizes with nothing left to reconcile them.

    A grid holding nothing has nothing to say about how big a portrait
    should be, and has to say so rather than guessing."""
    from draft_assist.ui.tables import MatrixTable
    # A BARE one: `built` already draws the empty 5x5 outline, which is a
    # grid holding a shape rather than a grid holding nothing.
    bare = MatrixTable()
    assert bare.table.columnCount() == 0
    assert bare.sections() == 0
    assert bare.portrait_ceiling() == 0
    bare.deleteLater()

    table = built(qapp, width=1400)
    table.show_matrix(grid())
    QApplication.processEvents()
    assert table.sections() > 1
    assert table.portrait_ceiling() > 0


def test_the_cap_is_taken_again_once_the_grids_are_filled(qapp):
    """It was only recomputed on a window RESIZE, and nothing resizes the
    window between building it and the first refresh — so the one
    measurement that mattered was the one taken from empty grids."""
    import inspect
    from draft_assist.ui import app as app_mod

    source = inspect.getsource(app_mod.MainWindow._refresh_views)
    assert "_match_grid_portraits" in source, (
        "the cap has to be retaken after the grids are populated, not only "
        "when the window is resized")
    assert (source.index("_update_matrices")
            < source.index("_match_grid_portraits"))
