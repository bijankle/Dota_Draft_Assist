"""THE SAME DRAFT AS TEXT (View - Simplified view).

At the user's request: a toggle between the app as it is and "a
spreadsheet view where it's just like simple data tables... it's got
what's been drafted, what the recommended hero selection is, what the
synergies are", with "hero names in text instead of any portraits",
"off by default" and "once you toggle to it it should be remembered".

Every one of those five clauses is a test here, and so is the property
that holds the whole thing up: the two views never compute a figure
twice, so they cannot disagree about one. A simplified view that
quietly ranked heroes in a different order from the strip above it
would be worse than no simplified view at all - the surface nobody is
looking at is the one that goes wrong.
"""

import os

import pytest

pytest.importorskip("PyQt6")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from pathlib import Path  # noqa: E402

from PyQt6.QtCore import QPoint, QPointF, Qt  # noqa: E402
from PyQt6.QtGui import QWheelEvent  # noqa: E402
from PyQt6.QtWidgets import (QAbstractItemView, QApplication,  # noqa: E402
                             QHeaderView)

from draft_assist.config import RULES_FILE  # noqa: E402
from draft_assist.model import items as items_mod  # noqa: E402
from draft_assist.model import scoring  # noqa: E402
from draft_assist.ui import settings as ui_settings  # noqa: E402
from draft_assist.ui import simpleview, theme  # noqa: E402
from draft_assist.ui.app import MainWindow  # noqa: E402
from draft_assist.ui.demo import demo_dataset  # noqa: E402
from draft_assist.ui.providers import DemoProvider  # noqa: E402

SOURCE = Path(simpleview.__file__)


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


def _build(qapp):
    ds = demo_dataset()
    provider = DemoProvider(ds)
    # Fast-forward the scripted draft to fully drafted, short of the
    # 60-second auto-restart.
    provider.draft.started -= 45
    rules, meta = items_mod.load_rules(RULES_FILE)
    win = MainWindow(ds, provider, rules, meta)
    win.timer.stop()
    return win


@pytest.fixture()
def window(qapp):
    win = _build(qapp)
    yield win
    win.close()


@pytest.fixture()
def simple(window):
    """A window already switched to the simplified view, with the board
    drawn."""
    window.refresh()
    window._set_simple_view(True)
    window.refresh()
    return window


def _column(table, index):
    return [table.item(r, index).text() if table.item(r, index) else ""
            for r in range(table.rowCount())]


def _headers(table):
    return [table.horizontalHeaderItem(c).text()
            for c in range(table.columnCount())]


# ---- the five clauses of the request --------------------------------

def test_it_is_off_by_default(window):
    """"I want this to be off by default so that by default it looks
    like how it is right now"."""
    assert ui_settings.DEFAULTS["simple_view"] is False
    assert window.draft_pages.currentWidget() is window.draft_scroll
    assert not window.simple_action.isChecked()


def test_toggling_switches_the_page_and_back(window):
    window.refresh()
    window._set_simple_view(True)
    assert window.draft_pages.currentWidget() is window.simple_scroll
    window._set_simple_view(False)
    assert window.draft_pages.currentWidget() is window.draft_scroll
    # BOTH WAYS, and the rich page is intact after the round trip: the
    # two are pages of one stack, not a rebuild.
    assert window.suggest_row.hero_ids


def test_the_choice_survives_a_restart(qapp, window):
    """"If I toggle to this simplified view and then restart the app or
    update it, whatever, it should stay in that simplified view."

    The restart is a second MainWindow, which is what one is from the
    settings file's point of view. It is the write filter that makes
    this work - a key `DEFAULTS` does not name is kept for the session
    and dropped on the way to disk, which is the fault that lost the
    transparency setting.
    """
    window.refresh()
    window._set_simple_view(True)
    assert ui_settings.load()["simple_view"] is True
    again = _build(qapp)
    try:
        assert again.draft_pages.currentWidget() is again.simple_scroll
        assert again.simple_action.isChecked()
    finally:
        again.close()


def test_the_board_is_hero_names_in_text(simple):
    """"Hero names are in text instead of any portraits"."""
    view = simple.simple_view
    drawn = _column(view.board, 2)
    for side in ("ally", "enemy"):
        for tile in simple.team_buttons[side]:
            hid = tile.property("hero_id")
            if hid is not None:
                assert any(simple.ds.name(hid) in cell for cell in drawn)
    assert view.board.rowCount() == 10      # every SLOT, picked or not


def test_nothing_in_the_simplified_view_draws_a_portrait(simple):
    """Not one cell carries an icon, and the module reaches for no
    artwork at all.

    The source scan is the half that matters: a test of the cells can
    only speak for the draft it was handed, where the premise of the
    whole view is that it never asks for a picture. `portraits` and
    `item_icons` are where every picture in this app comes from.

    IT PARSES RATHER THAN SEARCHING THE TEXT, the trap `single.py`'s
    own guard already carries: this module's docstring has to quote the
    request - "hero names are in text instead of any PORTRAITS" - to
    explain why it exists, and a scan over raw characters would fail on
    the sentence stating the rule it is enforcing.
    """
    import ast
    used = set()
    for node in ast.walk(ast.parse(SOURCE.read_text())):
        if isinstance(node, ast.Name):
            used.add(node.id)
        elif isinstance(node, ast.Attribute):
            used.add(node.attr)
        elif isinstance(node, ast.alias):
            used.add(node.name.rsplit(".", 1)[-1])
            used.add(node.asname or "")
        elif isinstance(node, ast.ImportFrom) and node.module:
            used.update(node.module.split("."))
    for forbidden in ("portraits", "item_icons", "QPixmap", "QIcon"):
        assert forbidden not in used, forbidden
    view = simple.simple_view
    for table in (view.board, view.roles, view.picks, view.items,
                  view.synergy, view.counters):
        for r in range(table.rowCount()):
            for c in range(table.columnCount()):
                item = table.item(r, c)
                if item is not None:
                    assert item.icon().isNull()


def test_it_shows_the_draft_the_picks_and_the_synergies(simple):
    """The three things the request named, each with rows in it."""
    view = simple.simple_view
    assert view.board.rowCount() == 10
    assert view.picks.rowCount() > 0
    assert view.synergy.rowCount() > 0


# ---- the two views never disagree -----------------------------------

def test_the_hero_table_is_the_strip_in_the_strips_own_order(simple):
    """Same list, same order, same figures - because it IS that list.

    The cut is a count the user sets, the filter is eight role boxes and
    the ordering changes with whether anything is drafted at all, so a
    second place working it out is a second place to get one of those
    wrong.
    """
    view = simple.simple_view
    names = _column(view.picks, 1)
    assert names == [simple.ds.name(h) for h in simple.suggest_row.hero_ids]


def test_every_figure_is_the_one_the_other_view_draws(simple):
    """The board's values are `net_contributions`, spelled by the same
    function that writes the badge on a tile."""
    from draft_assist.ui import tilekit
    draft = simple._current_draft()
    net = scoring.net_contributions(simple.ds, draft)
    view = simple.simple_view
    heroes, values = _column(view.board, 2), _column(view.board, 3)
    for hid, figure in net.items():
        name = simple.ds.name(hid)
        row = next(i for i, cell in enumerate(heroes) if name in cell)
        assert values[row] == tilekit.delta_text(figure)


def test_the_synergy_table_is_every_pair_once(simple):
    """Read off the very grid the painted triangles are drawn from, so
    the two cannot disagree about a figure - and complete, because the
    two triangles between them hold each team's pairs exactly once."""
    from draft_assist.ui import tilekit
    draft = simple._current_draft()
    grid = scoring.team_synergy_grid(simple.ds, draft)
    pairs = grid.pairs
    view = simple.simple_view
    assert view.synergy.rowCount() == len(pairs)
    drawn = set(_column(view.synergy, 3))
    assert drawn == {tilekit.delta_text(c.delta) for c in pairs}
    # STRONGEST FIRST WITHIN A TEAM, never across both: a green number
    # on their rows is a pair that works for THEM.
    for team in set(_column(view.synergy, 0)):
        block = [float(v) for t, v in
                 zip(_column(view.synergy, 0), _column(view.synergy, 3))
                 if t == team]
        assert block == sorted(block, reverse=True)


def test_the_counters_table_is_the_matrix_the_grid_is_handed(simple):
    from draft_assist.ui import tilekit
    draft = simple._current_draft()
    matrix = scoring.matchup_matrix(simple.ds, draft)
    view = simple.simple_view
    assert _headers(view.counters)[1:] == [n for _h, n in matrix.cols]
    assert _column(view.counters, 0) == [n for _h, n in matrix.rows]
    for r, line in enumerate(matrix.cells):
        for c, value in enumerate(line):
            assert view.counters.item(r, c + 1).text() == \
                tilekit.delta_text(value)


def test_the_counters_axes_say_which_team_is_which(simple):
    """Ten heroes with nothing saying which five are yours is the one
    way this table can be read backwards. The painted card says it with
    a green box and a red one; a table has to say it in words."""
    view = simple.simple_view
    mine, theirs = simple._side_names
    assert mine in view.counters_axes.text()
    assert theirs in view.counters_axes.text()
    assert _headers(view.counters)[0] == mine


# ---- the shape of the page -------------------------------------------

def test_the_view_ticks_hide_the_same_blocks_here(simple):
    view = simple.simple_view
    for key, card_name in (("show_roles", "roles"),
                           ("show_suggestions", "picks"),
                           ("show_items", "items")):
        # `isHidden`, never `isVisible`: this window was never shown,
        # so `isVisible` answers "is anybody looking at it" rather than
        # "did the app hide it" - the note the Draft tab's own tests
        # already carry.
        simple._set_section(key, False)
        assert view.cards[card_name].isHidden()
        simple._set_section(key, True)
        assert not view.cards[card_name].isHidden()


def test_the_synergy_tables_are_drawn_whatever_the_matrices_tick_says(simple):
    """The one deliberate exception, and the reason is the painted
    cards' SIZE: "Synergies and counters" starts off because a 5x5 of
    portraits is most of a screen, and a pair list is twenty short rows.
    The user named synergies as content of this view in the breath that
    asked for it."""
    view = simple.simple_view
    simple._set_section("show_matrices", False)
    assert not view.cards["synergy"].isHidden()
    assert not view.cards["counters"].isHidden()


def test_no_table_ever_scrolls_inside_itself(simple):
    """A table sized to its rows has nothing of its own to scroll, so a
    scrollbar on one can only mean the fit was wrong - and it hides part
    of the answer while making the widget look correct."""
    view = simple.simple_view
    for table in (view.board, view.roles, view.picks, view.items,
                  view.synergy, view.counters):
        assert (table.verticalScrollBarPolicy()
                == Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        assert (table.horizontalScrollBarPolicy()
                == Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        if table.rowCount():
            wanted = (table.horizontalHeader().sizeHint().height()
                      + table.verticalHeader().length()
                      + 2 * table.frameWidth() + 2)
            assert table.height() >= wanted - 2


def test_a_table_lets_the_page_take_the_wheel(simple):
    """A control that answers the wheel while the reader is scrolling
    past it is the History tab's own fault one card over."""
    table = simple.simple_view.board
    event = QWheelEvent(
        QPointF(5, 5), QPointF(table.mapToGlobal(QPoint(5, 5))),
        QPoint(0, -40), QPoint(0, -120), Qt.MouseButton.NoButton,
        Qt.KeyboardModifier.NoModifier, Qt.ScrollPhase.NoScrollPhase, False)
    table.wheelEvent(event)
    assert not event.isAccepted()


def test_nothing_in_the_table_can_be_sorted_or_edited(simple):
    """Qt sorts by TEXT, so "10" lands before "9" and "+6.4" before
    "+62.1" - and every column here is a number wearing a sign. The
    order is the one the app already decided."""
    view = simple.simple_view
    for table in (view.board, view.picks, view.synergy):
        assert not table.isSortingEnabled()
        assert not table.horizontalHeader().sectionsClickable()
        assert (table.editTriggers()
                == QAbstractItemView.EditTrigger.NoEditTriggers)


def test_the_cells_can_still_be_copied_out(simple):
    """A table nobody can select out of is a picture of a table."""
    table = simple.simple_view.board
    assert table.selectionMode() != QAbstractItemView.SelectionMode.NoSelection
    item = table.item(0, 2)
    assert item.flags() & Qt.ItemFlag.ItemIsSelectable


def test_the_simplified_page_does_not_set_the_windows_floor(qapp):
    """A stack's minimum is its TALLEST page whether or not anybody is
    looking at it, exactly like a tab widget's - and this one is six
    tables. Both pages are scroll areas for that reason."""
    win = _build(qapp)
    try:
        win.refresh()
        rich = win.minimumSizeHint().height()
        win._set_simple_view(True)
        win.refresh()
        assert win.minimumSizeHint().height() <= rich
    finally:
        win.close()


def test_it_is_not_filled_while_it_is_hidden(window):
    """Six tables rebuilt for nobody is the smooth-scaled hidden widget
    all over again - and turning the page on fills it, so there is
    nothing to gain by doing it in the dark."""
    window.refresh()
    assert window.simple_view.board.rowCount() == 0
    window._set_simple_view(True)
    assert window.simple_view.board.rowCount() == 10


def test_a_signed_number_wears_the_apps_own_two_colours(simple):
    """Green good, red bad, read from your own side - and looked up at
    paint time, so View - Greyscale reaches them."""
    view = simple.simple_view
    seen = set()
    for r in range(view.board.rowCount()):
        item = view.board.item(r, 3)
        text = item.text()
        if text.startswith("+") and float(text) > 0:
            seen.add(("good", item.foreground().color().name()))
        elif text.startswith("-") and float(text) < 0:
            seen.add(("bad", item.foreground().color().name()))
    assert ("good", theme.GOOD) in seen or ("bad", theme.BAD) in seen
    for kind, colour in seen:
        assert colour == (theme.GOOD if kind == "good" else theme.BAD)


def test_the_stretched_column_is_the_one_that_holds_text(simple):
    """The numbers end up hard against the card's right edge and the
    names against its left, which is what makes a column of figures
    readable as a column."""
    head = simple.simple_view.board.horizontalHeader()
    assert head.sectionResizeMode(2) == QHeaderView.ResizeMode.Stretch
    assert head.sectionResizeMode(3) != QHeaderView.ResizeMode.Stretch


def test_a_heading_is_aligned_like_the_column_under_it(simple):
    """Qt centres header text whatever the cells do, which reads as two
    columns rather than one."""
    table = simple.simple_view.board
    right = Qt.AlignmentFlag.AlignRight.value
    assert table.horizontalHeaderItem(3).textAlignment() & right
    assert not table.horizontalHeaderItem(2).textAlignment() & right
