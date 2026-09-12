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


def test_moving_the_bar_in_settings_RE_MEASURES(window):
    """The second half of the same bug. The bar is an input to the
    RANKING, not a filter over its result, so re-applying the shields
    already computed changes nothing - the control moved a number in a
    file and nothing on screen, which is indistinguishable from the mark
    being broken.

    Settings shows "top 30%" and stores 70, so a HIGHER stored number is
    a STRICTER bar and must mark fewer heroes.
    """
    window._apply_settings({"shield_pct": 70})
    wide = dict(window.shields)
    window._apply_settings({"shield_pct": 90})
    narrow = dict(window.shields)
    assert wide and narrow
    assert len(narrow) < len(wide), (
        "top 10%% must mark fewer heroes than top 30%% (%d vs %d)"
        % (len(narrow), len(wide)))
    assert set(narrow) <= set(wide), "and they are the same heroes"


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


def test_a_bar_nothing_can_clear_says_that_instead(qapp):
    from test_hero_counters import a_dataset
    ds = a_dataset([1, 2, 3], [[0, 1, 2], [-1, 0, 1], [-2, -1, 0]])
    from draft_assist.history import analyse
    marked, why = analyse.shield_report(ds, 100)
    assert marked == {}
    assert "100%" in why and "Lower the bar" in why



def test_the_settings_page_prints_it_under_the_bar(window, qapp):
    """A count beside the control tells a working feature from a broken
    one at a glance, which is the whole complaint this answers."""
    window._open_settings("General")
    qapp.processEvents()
    label = window.settings_window.general.shield_note
    assert label.text() == window.shields_note
    assert label.text(), "opened blank"
