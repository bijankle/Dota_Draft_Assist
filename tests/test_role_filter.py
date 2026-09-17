"""Cutting the suggestion strip to the roles the draft is short of.

"the user looks at the team attributes, figures out what lacking and
ticks the suggested hero filters (its also helpful as if you are always
support you dont want to see anythign that has 0 support attribution)".

So this is the other half of the Roles card: that one says what the draft
has, these eight controls cut the strip to heroes that answer it.

They are NUMBERS rather than ticks, at the user's request — "instead of a
tick box it would be nice to have a number input (up / down arrow) for
each allowing 1, 2, 3 only... that way if you need a really strong
support example you can filter the suggested heroes well" — so the value
is the LOWEST rating that passes on Valve's 0-to-3 scale, and nought is
off.
"""

import os
import sys
from pathlib import Path

import pytest
from PyQt6.QtWidgets import QApplication

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from draft_assist.config import RULES_FILE                    # noqa: E402
from draft_assist.model import items as items_mod             # noqa: E402
from draft_assist.model import roles as roles_mod             # noqa: E402
from draft_assist.ui import settings as ui_settings           # noqa: E402
from draft_assist.ui import rolebar                          # noqa: E402
from draft_assist.ui.app import MainWindow                    # noqa: E402
from draft_assist.ui.demo import demo_dataset                 # noqa: E402
from draft_assist.ui.providers import DemoProvider            # noqa: E402


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


def build(qapp):
    ds = demo_dataset()
    provider = DemoProvider(ds)
    provider.draft.started -= 45
    rules, meta = items_mod.load_rules(RULES_FILE)
    win = MainWindow(ds, provider, rules, meta)
    win.timer.stop()
    win.refresh()
    qapp.processEvents()
    return win


@pytest.fixture()
def win(qapp):
    window = build(qapp)
    yield window
    window.close()


# ---- the control -------------------------------------------------------

def test_there_is_one_box_per_role_valve_actually_scores(win):
    assert list(win.role_boxes) == list(roles_mod.ROLES)
    assert len(win.role_boxes) == 8


def test_each_box_takes_nought_to_three_and_nothing_else(win):
    for role, box in win.role_boxes.items():
        assert box.minimum() == 0, role
        assert box.maximum() == roles_mod.MAX_LEVEL == 3, role


def _cells(win):
    """Every (row, column) the filter's grid is using."""
    grid = win.role_boxes["Carry"].parent().layout()
    return {grid.getItemPosition(index)[:2] for index in range(grid.count())}


def test_they_are_laid_out_two_rows_by_four_columns(win):
    """As asked — and eight is only a clean 2x4 because Valve scores
    eight roles. A ninth (Jungler, which has no hero data at all) would
    have made it a 3x3 with a dead corner.

    A QGridLayout is how Qt is told "two rows of four"; NOTHING DRAWS A
    GRID, at the user's request: "when you say grid i dont want it to
    look like a grid, just said it in terms of row / column so that they
    fit nicely".

    THIS IS THE NARROW SHAPE NOW, and it is still the one the window
    opens at: the filter took the whole row when the two rank counts
    moved up to the heading, so it reflows to eight across when there is
    room for them (see below) and comes back to this at anything near the
    window's own floor.
    """
    win.role_filter._relayout(4)
    cells = _cells(win)
    assert max(r for r, _c in cells) == 1, "more than two rows"
    # Each role takes THREE grid columns — its name, its box, and the
    # fixed gap to the next cell. The gap column is what keeps the two
    # rows of four snug at any width now that the filter REFLOWS: at
    # four columns it asked for 644px, which made the Suggested picks
    # card 1030px wide at its narrowest, over the window's own 940 floor,
    # so the Draft page stopped shrinking and the portraits with it.
    # COLUMN 0 IS THE FIRST CELL now: the leading slack column that
    # pushed the block flush right is gone, since the slack goes between
    # the cells — "spread it out to fit the margins on both left and
    # right side, equal spacing".
    assert rolebar.RoleFilter.FIRST == 0
    assert min(c for _r, c in cells) == rolebar.RoleFilter.FIRST
    assert max(c for _r, c in cells) == 10 + rolebar.RoleFilter.FIRST
    assert len(cells) == 16, "a label and a box for each of eight roles"


def test_it_goes_eight_across_when_the_row_is_its_own(win):
    """"spread the carr / support / etc filytters to fill the space
    left" — the space the two rank counts left when they moved up to the
    heading row.

    Eight is still a divisor of eight, so the last column is never
    short — and the CELLS are what fill the row where there is room for
    all eight, with the gaps spreading whatever is left over (see
    `test_the_cells_span_the_row_with_the_slack_shared_between_them`).
    """
    assert rolebar.RoleFilter.COLUMNS[0] == 8
    assert len(roles_mod.ROLES) % 8 == 0, "the last column would be short"
    win.role_filter._relayout(8)
    cells = _cells(win)
    assert max(r for r, _c in cells) == 0, "eight across is ONE row"
    assert max(c for _r, c in cells) == 22 + rolebar.RoleFilter.FIRST
    assert len(cells) == 16, "a label and a box for each of eight roles"


def test_the_cells_span_the_row_with_the_slack_shared_between_them(win,
                                                                   qapp):
    """"dotn liek that this is all on the right.... spread it out to fit
    the margins on both left and right side, equal spacing".

    THIS REVERSES "SNUG, WITH THE SLACK ON THE LEFT", which put the
    whole block flush right with an empty half beside it — the shape the
    user was looking at when they asked for this. The objection that
    rule carried (a hand's width of nothing between two controls) is
    real and is the trade they have now chosen, having seen both.

    BOTH EDGES AND EQUAL GAPS ARE ONE MECHANISM: the stretch is on the
    SEPARATOR columns only, so with nothing stretching before the first
    cell or after the last the block is pinned to both ends, and the
    separators being equally weighted shares what is left between them.

    **THE EXACT COMPARISON IS AGAINST ITS OWN ROW, AND THE STRIP GETS A
    TOLERANCE.** Both are "the margins" and only one of them is
    deterministic: the strip's width is ELEVEN TILES AND TEN GAPS
    (`_suggestion_box`), and `TeamPanel.STEADY` only takes a tile size
    at least three pixels BIGGER than the one it has — so the strip's
    right edge depends on the sequence of widths the window has already
    been through, and lands a pixel off the card in a long run where it
    is exact in a short one. That is the damping working, not a fault in
    this block, and asserting the strip to the pixel made this test pass
    alone and fail in the full suite.
    """
    from PyQt6.QtWidgets import QApplication

    # SHOWN, because this is a test about GEOMETRY: the fixture does not
    # show its window, and Qt does not lay out or deliver a resize to a
    # hidden one — every edge would be measured off a layout that never
    # ran. The same reason `ReflowGrid` re-fits on `showEvent`.
    win.show()
    for _ in range(4):
        QApplication.processEvents()

    filt = win.role_filter
    names, boxes = list(filt._labels.values()), list(filt.boxes.values())

    def left(widget):
        return widget.mapTo(win, widget.rect().topLeft()).x()

    def right(widget):
        return widget.mapTo(win, widget.rect().topRight()).x()

    for width in (1500, 1180, 960):
        win.resize(width, 950)
        win.refresh()
        for _ in range(8):
            QApplication.processEvents()
        per = len(roles_mod.ROLES) // filt.columns
        row, strip = win._picks_row, win.suggest_row
        first, last = names[0], boxes[(filt.columns - 1) * per]
        # Pinned to both ends of its own row, exactly. This is what the
        # spread IS: no slack column before the first cell or after the
        # last.
        assert left(first) == left(row), (
            f"at {width} the filter does not start at the row's left edge")
        assert right(last) == right(row), (
            f"at {width} the filter does not reach the row's right edge")
        # And that row is the strip's own span, to within the pixel
        # `STEADY` can leave on the tiles — see the docstring.
        assert abs(left(first) - left(strip)) <= 2, (
            f"at {width} the filter does not start where the portraits do")
        assert abs(right(last) - right(strip)) <= 2, (
            f"at {width} the filter does not end where the portraits do")

        # And the gaps between the cells on the top row are equal —
        # within a pixel, since the leftover rarely divides exactly.
        row = [(names[i * per], boxes[i * per]) for i in range(filt.columns)]
        gaps = [left(row[i + 1][0]) - right(row[i][1])
                for i in range(len(row) - 1)]
        assert max(gaps) - min(gaps) <= 1, f"uneven at {width}: {gaps}"
        # Never CLOSER than the minimum, whatever the width does.
        assert min(gaps) >= rolebar.ReflowGrid.GAP, gaps


def test_it_falls_back_to_four_before_the_window_reaches_its_floor(win):
    """A block that reflows has to come back, or the card sets a floor
    the window cannot honour — the fault this whole class was written
    for. Eight across is 1230px; four is 606, which is inside the card
    even at the narrowest window this app will open at.
    """
    filt = win.role_filter
    assert filt.columns_for(2000) == 8
    assert filt.columns_for(700) == 4
    # And the minimum it REPORTS is still one cell, whatever it is
    # currently laid out as: a widget's minimum is the window's.
    assert filt.minimumSizeHint().width() <= filt._cell_width()


def test_nothing_is_filtered_to_start_with(win):
    assert win._picked_roles() == {}
    assert ui_settings.DEFAULTS["pick_roles"] == {}


# ---- what it does ------------------------------------------------------

def test_a_figure_keeps_only_heroes_that_clear_it(win, qapp):
    for least in (1, 2, 3):
        win.role_boxes["Support"].setValue(least)
        qapp.processEvents()
        shown = win.suggest_row.hero_ids
        assert shown, f"Support >= {least} left nothing at all"
        for hero_id in shown:
            assert roles_mod.levels_for(hero_id)["Support"] >= least


def test_turning_it_up_narrows_and_never_widens(win, qapp):
    """"if you need a really strong support example you can filter the
    suggested heroes well"."""
    counts = []
    for least in (1, 2, 3):
        win.role_boxes["Support"].setValue(least)
        qapp.processEvents()
        counts.append(len(win.suggest_row.hero_ids))
    assert counts == sorted(counts, reverse=True), counts


def test_nought_is_the_filter_being_off(win, qapp):
    win.role_boxes["Support"].setValue(3)
    qapp.processEvents()
    narrowed = len(win.suggest_row.hero_ids)
    win.role_boxes["Support"].setValue(0)
    qapp.processEvents()
    assert len(win.suggest_row.hero_ids) >= narrowed
    assert win._picked_roles() == {}, "nought must not be stored"


def test_two_figures_means_BOTH_rather_than_either(win, qapp):
    win.role_boxes["Durable"].setValue(2)
    win.role_boxes["Initiator"].setValue(2)
    qapp.processEvents()
    shown = win.suggest_row.hero_ids
    assert shown
    for hero_id in shown:
        levels = roles_mod.levels_for(hero_id)
        assert levels["Durable"] >= 2 and levels["Initiator"] >= 2


def expected(win, role, least):
    """The heroes that clear the filter, in the order the app ranks them.

    IT ASKS THE APP FOR THE ORDER RATHER THAN RESTATING IT. These three
    tests are about the FILTER — that it runs over the whole pool, before
    the cut, and refills — and they used to spell the ranking out as
    "fit order" alongside it. A test that hard-codes the sort fails for a
    change to the sort while saying nothing about the filter it guards.

    AND THE SORT DEPENDS ON THE BOARD. With nothing drafted the strip
    ranks by how hard a hero is to counter; from the first pick it ranks
    by draft fit, which is the order `score_all` already returns. These
    fixtures have a drafted board, so this mirrors that rather than
    assuming either one.
    """
    pool = [s for s in win.scored
            if roles_mod.levels_for(s.hero_id).get(role, 0) >= least]
    draft = win._current_draft()
    if draft.allies or draft.enemies:
        return [s.hero_id for s in pool]
    return [s.hero_id for s in win._by_counter_rank(pool)]


def test_the_strip_refills_and_keeps_the_apps_own_order(win, qapp):
    """"the suggested hero pool fills with more suggestions that are
    support strength 3 and its all still in order of synergy / counter
    score - with no more than the max suggest hero count"."""
    win.settings["suggested_picks"] = 6
    win.role_boxes["Support"].setValue(1)
    qapp.processEvents()
    win._refresh_views()
    qapp.processEvents()
    shown = list(win.suggest_row.hero_ids)
    assert len(shown) <= 6, "it went past the cap"
    # Still the ranked order, just with the misses taken out of it.
    ranked = expected(win, "Support", 1)
    assert shown == ranked[:len(shown)]
    if len(ranked) >= 6:
        assert len(shown) == 6, "the strip did not refill to the cap"


def test_the_filter_runs_BEFORE_the_count_is_cut(win, qapp):
    """Cutting to six first and then dropping the misses would show
    however many of the top six happened to qualify — a different
    answer, and a worse one."""
    win.settings["suggested_picks"] = 6
    win.role_boxes["Durable"].setValue(3)
    qapp.processEvents()
    win._refresh_views()
    qapp.processEvents()
    eligible = expected(win, "Durable", 3)
    assert list(win.suggest_row.hero_ids) == eligible[:6]


def test_a_filter_that_matches_nothing_says_so(win, qapp):
    """An empty strip is indistinguishable from the app having stopped
    working — the hero picker's refused rows carry the same lesson."""
    for role in roles_mod.ROLES:
        win.role_boxes[role].setValue(3)
    qapp.processEvents()
    assert not win.suggest_row.hero_ids, "no hero is a 3 in all eight"
    said = win.suggest_row.message.text()
    assert "turn one down" in said, said
    assert "Carry 3" in said, "it does not say what it was asked for"
    # `isHidden`, not `isVisible`: nothing here shows the window, and a
    # widget on an unshown window is not "visible" whatever it was told.
    assert not win.suggest_row.message.isHidden()


def test_an_unrated_hero_fails_a_filter_but_passes_no_filter():
    """The strip is being cut to heroes that ANSWER something, and "we
    have no figures for this one" is not an answer. With nothing set
    there is no filter, so a hero added in a patch is only ever missing
    from a FILTERED strip."""
    assert MainWindow._has_roles(10_000_000, {}) is True
    assert MainWindow._has_roles(10_000_000, {"Carry": 1}) is False
    assert MainWindow._has_roles(1, {"Carry": 3}) is True     # Anti-Mage
    assert MainWindow._has_roles(1, {"Carry": 1}) is True
    assert MainWindow._has_roles(1, {"Support": 1}) is False
    # Lion is Nuker 3, Support 2 — so 3 is too much to ask of his support.
    assert MainWindow._has_roles(26, {"Support": 2}) is True
    assert MainWindow._has_roles(26, {"Support": 3}) is False


# ---- remembered --------------------------------------------------------

def test_the_figures_are_remembered_like_the_mark_count(qapp, tmp_path,
                                                        monkeypatch):
    """"i want the suggest hero tick boxes to be remembered from previous
    state just like for shield / heart count"."""
    monkeypatch.setattr(ui_settings, "SETTINGS_FILE", tmp_path / "s.json")
    first = build(qapp)
    try:
        first.role_boxes["Nuker"].setValue(3)
        first.role_boxes["Escape"].setValue(1)
        qapp.processEvents()
        assert first.settings["pick_roles"] == {"Nuker": 3, "Escape": 1}
    finally:
        first.close()

    second = build(qapp)
    try:
        assert second._picked_roles() == {"Nuker": 3, "Escape": 1}
        assert second.role_boxes["Nuker"].value() == 3
        assert second.role_boxes["Carry"].value() == 0
    finally:
        second.close()


def test_a_filter_saved_when_it_was_a_TICK_still_works(qapp, tmp_path,
                                                       monkeypatch):
    """The preference was a list of names while the control was a tick
    box. A tick meant "any rating above zero", which is 1."""
    import json
    path = tmp_path / "s.json"
    path.write_text(json.dumps({"pick_roles": ["Support", "Durable"]}),
                    encoding="utf-8")
    monkeypatch.setattr(ui_settings, "SETTINGS_FILE", path)
    win = build(qapp)
    try:
        assert win._picked_roles() == {"Support": 1, "Durable": 1}
    finally:
        win.close()


def test_a_file_asking_for_the_impossible_is_cleaned():
    """A hand-edited file must not be able to cut the strip to nothing
    with a name or a figure nothing can ever satisfy."""
    assert ui_settings.clean_roles({"Jungler": 3}) == {}
    assert ui_settings.clean_roles({"Nuker": 9}) == {}
    assert ui_settings.clean_roles({"Nuker": 0}) == {}
    assert ui_settings.clean_roles({"Nuker": "x"}) == {}
    assert ui_settings.clean_roles({"Nuker": 2, "Jungler": 1}) == {"Nuker": 2}
    assert ui_settings.clean_roles(None) == {}
    assert ui_settings.clean_roles("Carry") == {}


def test_it_comes_back_in_valves_own_order(qapp, tmp_path, monkeypatch):
    """So the boxes read in the same order as the Roles card above."""
    order = ui_settings.clean_roles({"Initiator": 1, "Carry": 2})
    assert list(order) == ["Carry", "Initiator"]


def test_the_default_is_not_shared_with_DEFAULTS(tmp_path, monkeypatch):
    """`dict(DEFAULTS)` is shallow, so one shared object would let a
    filter edit the defaults themselves."""
    monkeypatch.setattr(ui_settings, "SETTINGS_FILE", tmp_path / "s.json")
    one = ui_settings.load()
    one["pick_roles"]["Carry"] = 3
    assert ui_settings.DEFAULTS["pick_roles"] == {}
    assert ui_settings.load()["pick_roles"] == {}


def test_the_filter_searches_the_WHOLE_pool_not_a_window(win, qapp):
    """"im concerned if you just populate a single row below, that what
    if i filter support level 3 and there are hardly any in the list of
    20 as well as the reserve list of 10 below".

    There is no window and no reserve list: `score_all` returns EVERY
    undrafted hero and the filter runs over all of them, so the strip
    shows the best N of everything that qualifies. When it shows fewer
    than the cap it is because fewer than the cap exist.
    """
    assert len(win.scored) > 100, "the pool is the whole roster"
    drafted = set(win._current_draft().allies) | set(
        win._current_draft().enemies)
    assert not (drafted & {s.hero_id for s in win.scored})

    win.settings["suggested_picks"] = 20
    win.role_boxes["Support"].setValue(3)
    qapp.processEvents()
    win._refresh_views()
    qapp.processEvents()
    eligible = expected(win, "Support", 3)
    shown = list(win.suggest_row.hero_ids)
    assert shown == eligible[:20]
    # Short of the cap ONLY because the roster is short of them.
    if len(shown) < 20:
        assert len(shown) == len(eligible)


def test_no_tile_is_ever_laid_out_below_the_strips_own_edge(win, qapp):
    """"i dont want you to layout suggestions below what is visible".

    That was a real fault and it is fixed at the root: `FlowLayout`
    always answered `heightForWidth`, but the strip's SIZE POLICY did
    not declare it had one, so Qt never asked and a parent short of room
    compressed the strip over its own tiles. The strip now takes the
    height its wrap needs, at any filter.
    """
    win.resize(940, 1000)
    win.show()
    qapp.processEvents()
    for setting in ({}, {"Support": 1}, {"Support": 3}, {"Carry": 2}):
        for role in roles_mod.ROLES:
            win.role_boxes[role].setValue(setting.get(role, 0))
        # SEVERAL PASSES. Qt defers layout, and a strip that has just been
        # refilled is measured on the NEXT pass — reading its geometry
        # after one `processEvents` reads the previous answer.
        for _ in range(8):
            qapp.processEvents()
        strip = win.suggest_row
        room = strip.rect()
        tiles = strip._tiles or strip._blanks
        outside = [t for t in tiles if not room.contains(t.geometry())]
        assert not outside, (
            f"{len(outside)} of {len(tiles)} tiles fall outside "
            f"{room.width()}x{room.height()} with {setting}")
