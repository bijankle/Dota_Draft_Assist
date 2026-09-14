"""Cutting the suggestion strip to the roles the draft is short of.

"the user looks at the team attributes, figures out what lacking and
ticks the suggested hero filters (its also helpful as if you are always
support you dont want to see anythign that has 0 support attribution)".

So this is the other half of the Roles card: that one says what the draft
has, these eight ticks cut the strip to heroes that answer it.
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

def test_there_is_one_tick_per_role_valve_actually_scores(win):
    assert list(win.role_ticks) == list(roles_mod.ROLES)
    assert len(win.role_ticks) == 8


def test_they_are_laid_out_two_rows_by_four_columns(win):
    """As asked — and eight is only a clean 2x4 because Valve scores
    eight roles. A ninth (Jungler, which has no hero data at all) would
    have made it a 3x3 with a dead corner."""
    grid = win.role_ticks["Carry"].parent().layout()
    seen = {}
    for index in range(grid.count()):
        item = grid.itemAt(index)
        row, column, _rs, _cs = grid.getItemPosition(index)
        seen[item.widget().text()] = (row, column)
    assert max(r for r, _c in seen.values()) == 1, "more than two rows"
    assert max(c for _r, c in seen.values()) == 3, "more than four columns"
    assert len(set(seen.values())) == 8, "two ticks share a cell"


def test_nothing_is_ticked_to_start_with(win):
    assert win._picked_roles() == []
    assert ui_settings.DEFAULTS["pick_roles"] == []


# ---- what it does ------------------------------------------------------

def test_ticking_a_role_drops_the_heroes_with_none_of_it(win, qapp):
    before = list(win.suggest_row.hero_ids)
    win.role_ticks["Support"].setChecked(True)
    qapp.processEvents()
    after = list(win.suggest_row.hero_ids)
    assert after != before or len(before) == 0
    for hero_id in after:
        assert roles_mod.levels_for(hero_id)["Support"] > 0


def test_two_ticks_means_BOTH_rather_than_either(win, qapp):
    """"heroes that contain non-zero attributes in the ticked
    departments" — the narrower reading, and the one that makes this a
    tool: ticking Durable and Initiator to find the hero who is both."""
    win.role_ticks["Support"].setChecked(True)
    win.role_ticks["Durable"].setChecked(True)
    qapp.processEvents()
    for hero_id in win.suggest_row.hero_ids:
        levels = roles_mod.levels_for(hero_id)
        assert levels["Support"] > 0 and levels["Durable"] > 0


def test_the_filter_runs_BEFORE_the_count_is_cut(win, qapp):
    """Cutting to twenty first and then dropping the misses would show
    however many of the top twenty happened to qualify — a different
    answer, and a worse one."""
    win.settings["suggested_picks"] = 5
    win.role_ticks["Durable"].setChecked(True)
    qapp.processEvents()
    win._refresh_views()
    qapp.processEvents()
    shown = win.suggest_row.hero_ids
    assert len(shown) == 5 or len(shown) == len(
        [s for s in win.scored
         if roles_mod.levels_for(s.hero_id).get("Durable", 0) > 0])
    for hero_id in shown:
        assert roles_mod.levels_for(hero_id)["Durable"] > 0


def test_a_filter_that_matches_nothing_says_so(win, qapp):
    """An empty strip is indistinguishable from the app having stopped
    working — the hero picker's refused rows carry the same lesson."""
    for role in roles_mod.ROLES:
        win.role_ticks[role].setChecked(True)
    qapp.processEvents()
    assert not win.suggest_row.hero_ids, "no hero has all eight roles"
    assert "untick one" in win.suggest_row.message.text()
    # `isHidden`, not `isVisible`: nothing here shows the window, and a
    # widget on an unshown window is not "visible" whatever it was told.
    # The app's own note about the tab widget says the same.
    assert not win.suggest_row.message.isHidden()


def test_an_unrated_hero_fails_a_filter_but_passes_no_filter():
    """The strip is being cut to heroes that ANSWER something, and "we
    have no figures for this one" is not an answer. With nothing ticked
    there is no filter, so a hero added in a patch is only ever missing
    from a FILTERED strip."""
    assert MainWindow._has_roles(10_000_000, []) is True
    assert MainWindow._has_roles(10_000_000, ["Carry"]) is False
    assert MainWindow._has_roles(1, ["Carry"]) is True      # Anti-Mage
    assert MainWindow._has_roles(1, ["Support"]) is False


# ---- remembered --------------------------------------------------------

def test_the_ticks_are_remembered_like_the_mark_count(qapp, tmp_path,
                                                      monkeypatch):
    """"i want the suggest hero tick boxes to be remembered from previous
    state just like for shield / heart count"."""
    monkeypatch.setattr(ui_settings, "SETTINGS_FILE", tmp_path / "s.json")
    first = build(qapp)
    try:
        first.role_ticks["Nuker"].setChecked(True)
        first.role_ticks["Escape"].setChecked(True)
        qapp.processEvents()
        assert first.settings["pick_roles"] == ["Nuker", "Escape"]
    finally:
        first.close()

    second = build(qapp)
    try:
        assert second._picked_roles() == ["Nuker", "Escape"]
        assert second.role_ticks["Nuker"].isChecked()
        assert not second.role_ticks["Carry"].isChecked()
    finally:
        second.close()


def test_they_are_stored_in_valves_order_however_they_were_ticked(qapp,
                                                                  tmp_path,
                                                                  monkeypatch):
    """So the ticks read in the same order as the Roles card above them."""
    monkeypatch.setattr(ui_settings, "SETTINGS_FILE", tmp_path / "s.json")
    win = build(qapp)
    try:
        win.role_ticks["Initiator"].setChecked(True)
        win.role_ticks["Carry"].setChecked(True)
        qapp.processEvents()
        assert win.settings["pick_roles"] == ["Carry", "Initiator"]
    finally:
        win.close()


def test_a_file_naming_a_role_the_game_no_longer_scores_is_cleaned():
    """A hand-edited file must not be able to cut the strip to nothing
    with a name nothing can ever satisfy."""
    assert ui_settings.clean_roles(["Jungler"]) == []
    assert ui_settings.clean_roles(["Nuker", "Jungler"]) == ["Nuker"]
    assert ui_settings.clean_roles(None) == []
    assert ui_settings.clean_roles("Carry") == []


def test_the_default_list_is_not_shared_with_DEFAULTS(tmp_path, monkeypatch):
    """`dict(DEFAULTS)` is shallow, so one shared list would let a tick
    edit the defaults themselves — the trap the two dict preferences
    already carry a note about."""
    monkeypatch.setattr(ui_settings, "SETTINGS_FILE", tmp_path / "s.json")
    one = ui_settings.load()
    one["pick_roles"].append("Carry")
    assert ui_settings.DEFAULTS["pick_roles"] == []
    assert ui_settings.load()["pick_roles"] == []
