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
