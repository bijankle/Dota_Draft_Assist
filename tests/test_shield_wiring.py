"""The gold shield, from the dataset all the way onto a tile.

`tests/test_hero_counters.py` tests `analyse.shielded` on its own, and
every one of those passed while the mark never once appeared on screen:
`_recompute_shields` was called from `reload_backend` and NOWHERE ELSE,
so on an ordinary start it never ran and `self.shields` stayed the empty
dict it is built with - for the whole session, on every tile, for ever.

A tested function and untested wiring is how a feature ships broken, so
these start at the window and finish at the widget.
"""

import os

import pytest

pytest.importorskip("PyQt6")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication  # noqa: E402


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture()
def window(qapp):
    from draft_assist.config import RULES_FILE
    from draft_assist.model import items as items_mod
    from draft_assist.ui.app import MainWindow
    from draft_assist.ui.demo import demo_dataset
    from draft_assist.ui.providers import DemoProvider
    ds = demo_dataset()
    provider = DemoProvider(ds)
    provider.draft.started -= 45          # a board with heroes on it
    rules, meta = items_mod.load_rules(RULES_FILE)
    win = MainWindow(ds, provider, rules, meta)
    win.timer.stop()
    yield win
    win.close()


def test_the_shields_are_worked_out_when_the_APP_STARTS(window):
    """THE BUG. It needs no history and no account, only the matrix, so
    there is nothing to wait for - and waiting for a statistics download
    is not something anybody does to make a mark show up."""
    assert window.shields, "no shields were computed at startup"


def test_the_mark_actually_reaches_the_tiles(window, qapp):
    """One step further out than the dict: `set_shields` runs AFTER
    `show_heroes`, which destroys every tile, so a mark applied before it
    is a mark on a widget that no longer exists."""
    for _ in range(6):
        window.refresh()
        qapp.processEvents()
    tiles = window.suggest_row._tiles
    assert tiles, "the strip has suggestions to mark"
    assert any(t.shielded for t in tiles), "no tile wears the shield"
    worn = next(t for t in tiles if t.shielded)
    assert worn.hero_id in window.shields
    assert worn._why_shield, "and it says why, in the tooltip"


def test_moving_the_count_REDRAWS_THE_MARKS(window):
    """The setting is a COUNT over the strip now, so it is a cut over a
    ranking that has not changed - and the marks are simply drawn again.

    It still has to happen on the settings change. The strip is redrawn
    when a PICK changes, so without this the control moves a number in a
    file and nothing on screen until the next hero is picked, which is
    indistinguishable from a broken setting and is the state the old
    shield bar actually shipped in.
    """
    marked = []
    window.suggest_row.set_shields = lambda rows, count=0: marked.append(
        count)
    window.suggest_row.set_stars = lambda stars, count=0: None
    # NOT THE DEFAULT. `_apply_settings` is idempotent by design - it
    # compares against what is already in `self.settings` - so handing it
    # the value that is already there is correctly a no-op, and this
    # asserted a redraw for a change that never happened. It passed only
    # while 5 differed from the shipped count, which it no longer does.
    from draft_assist.ui import settings as ui_settings
    want = ui_settings.DEFAULTS["shield_count"] + 2
    window._apply_settings({"shield_count": want})
    assert marked and marked[-1] == want, (
        "the strip was not told the new count")


def test_every_hero_measured_comes_back_with_its_standing(window):
    """The report is no longer cut at a bar: the strip needs a FIGURE for
    every hero it might be showing, because the ranking happens there."""
    assert window.shields
    for hero_id, row in window.shields.items():
        share, why = row
        assert 0.0 <= share <= 100.0
        assert why, f"hero {hero_id} has a standing but no sentence"


# ---- no shields must say WHICH cause ------------------------------------

def test_the_reason_is_reported_beside_the_answer(window):
    """NO SHIELDS HAS FOUR CAUSES AND ONE APPEARANCE, which is this app's
    most repeated bug and was this mark's own: it was computed nowhere
    for weeks and looked exactly like "no hero clears the bar"."""
    assert window.shields_note, "the recompute said nothing about itself"
    assert str(len(window.shields)) in window.shields_note


def test_a_missing_dataset_says_so_rather_than_marking_nothing(qapp):
    from draft_assist.data.store import empty_dataset
    from draft_assist.history import analyse

    marked, why = analyse.shield_report(empty_dataset(), 70)
    assert marked == {}
    assert "downloaded" in why.lower(), why


def test_the_sentence_counts_what_it_measured(qapp):
    """The report no longer cuts anything, so the sentence has to say how
    MANY were measured rather than how many survived a bar - "no shields"
    still needs to be distinguishable from "no statistics", which is the
    whole reason this sentence exists.
    """
    from test_hero_counters import a_dataset
    ds = a_dataset([1, 2, 3], [[0, 1, 2], [-1, 0, 1], [-2, -1, 0]])
    from draft_assist.history import analyse
    marked, why = analyse.shield_report(ds)
    assert len(marked) == 3, "every hero measured comes back"
    assert "3 heroes measured" in why, why


def test_the_floor_form_still_cuts_at_a_bar(qapp):
    """`shielded` is kept because "which heroes clear a given bar" is
    still a real question - it is just no longer the one the strip
    asks."""
    from test_hero_counters import a_dataset
    ds = a_dataset([1, 2, 3], [[0, 1, 2], [-1, 0, 1], [-2, -1, 0]])
    from draft_assist.history import analyse
    assert analyse.shielded(ds, 100) == {}
    assert analyse.shielded(ds, 0)



def test_the_settings_page_prints_it_under_the_bar(window, qapp):
    """A count beside the control tells a working feature from a broken
    one at a glance, which is the whole complaint this answers."""
    window._open_settings("General")
    qapp.processEvents()
    label = window.settings_window.general.shield_note
    assert label.text() == window.shields_note
    assert label.text(), "opened blank"


def test_the_strip_is_ordered_by_how_hard_a_hero_is_to_counter(window, qapp):
    """AT THE USER'S REQUEST, and it reverses what this list answered.

    "i want them to show based on the counterability rank with the
    hardest to counter showing first". `counter_standings` measures
    every hero against the WHOLE FIELD out of the matchup matrix and
    never looks at the board, so this strip now shows the same heroes in
    the same order every game, minus whoever is already picked. That was
    put to them in those words and taken: "yes it would be the same
    heroes, but you have the abiltiy to change things like support
    score, etc, so it can be tweaked".
    """
    # ON AN EMPTY BOARD, which is the mode this ordering belongs to.
    # With a pick down the strip goes back to ranking by draft fit — see
    # `_update_suggestions`.
    window.manual.clear()
    window._cleared = None
    window._refresh_views()
    qapp.processEvents()
    draft = window._current_draft()
    if draft.allies or draft.enemies:
        import pytest as _pytest
        _pytest.skip("this fixture's board cannot be emptied")
    shown = list(window.suggest_row.hero_ids)
    assert shown, "the strip is empty"
    ranks = window.shields or {}
    got = [ranks[h][0] for h in shown if h in ranks]
    assert len(got) > 1, "not enough ranked heroes to tell an order"
    assert got == sorted(got, reverse=True), (
        "the strip is not hardest-to-counter first")


def test_a_hero_the_dataset_cannot_rank_goes_last_and_keeps_its_place(window):
    """Stable, so unranked heroes stay in the order they arrived in
    rather than being shuffled into an arbitrary one — and with NO
    statistics at all every hero sorts equal and the strip falls back to
    exactly the fit order it had before, which is the right answer when
    there is nothing to rank by and is never an empty strip."""
    class Fake:
        def __init__(self, hero_id):
            self.hero_id = hero_id

    window.shields = {1: (0.9, "why"), 2: (0.1, "why")}
    out = [s.hero_id for s in window._by_counter_rank(
        [Fake(3), Fake(2), Fake(1), Fake(4)])]
    assert out == [1, 2, 3, 4], out
    window.shields = {}
    same = [s.hero_id for s in window._by_counter_rank(
        [Fake(3), Fake(2), Fake(1)])]
    assert same == [3, 2, 1], "no statistics must not reorder anything"
