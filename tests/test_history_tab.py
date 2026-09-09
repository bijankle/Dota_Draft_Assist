"""The Analysis tab, which is now the match history report.

Rendering is checked against a report built from synthetic matches, so
nothing here touches OpenDota. The point of most of these is what the tab
must NOT do: run by itself, reach the network from the refresh loop, or
leave a thread running when the window closes.
"""

import os
import time

import pytest

pytest.importorskip("PyQt6")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication          # noqa: E402

from draft_assist.history import analyse, shape    # noqa: E402
from draft_assist.history.report import Options, Report  # noqa: E402
from draft_assist.ui.history_tab import BucketTable, HistoryTab  # noqa: E402

HEROES = {1: "Anti-Mage", 2: "Axe", 3: "Bane"}


@pytest.fixture(scope="module")
def qapp():
    yield QApplication.instance() or QApplication([])


@pytest.fixture()
def window(qapp):
    """The real main window, the same way the smoke tests build one."""
    from draft_assist.config import RULES_FILE
    from draft_assist.model import items as items_mod
    from draft_assist.ui.app import MainWindow
    from draft_assist.ui.demo import demo_dataset
    from draft_assist.ui.providers import DemoProvider
    dataset = demo_dataset()
    rules, meta = items_mod.load_rules(RULES_FILE)
    win = MainWindow(dataset, DemoProvider(dataset), rules, meta)
    win.timer.stop()
    yield win
    win.close()


def a_report(count=60):
    start = time.time() - count * 1500 - 86400
    rows = []
    for index in range(count):
        won = index % 3 != 0
        slot = 0 if index % 2 else 128
        rows.append(dict(match_id=500 + index, player_slot=slot,
                         radiant_win=(slot < 128) == won, duration=1800,
                         start_time=int(start + index * 1500),
                         hero_id=1 + index % 3, kills=5, deaths=4, assists=9,
                         hero_damage=12000 + 400 * (index % 3), party_size=1,
                         lobby_type=7, game_mode=22, item_0=29))
    shaped = shape.shape(rows, HEROES)
    blocks = analyse.build_blocks(shaped.matches, shaped.baseline,
                                  dict(analyse.DEFAULT_ON), {29: "Boots"})
    return Report(options=Options(account_id=195286385),
                  how="read as a 32 bit friend ID", name="Bijson",
                  matches=shaped.matches, blocks=blocks,
                  dropped=shaped.dropped, sessions=shaped.sessions,
                  returned=count)


def test_the_tab_draws_a_card_for_every_block(qapp):
    from PyQt6.QtWidgets import QFrame
    tab = HistoryTab()
    report = a_report()
    tab.render(report)
    from PyQt6.QtWidgets import QLabel
    for index in range(tab.results.count()):
        assert isinstance(tab.results.itemAt(index).widget(), QFrame)
    # The block cards, plus "This run" and the findings card.
    assert tab.results.count() >= len(report.blocks) + 2
    headings = {label.text() for label in tab.findChildren(QLabel)}
    for block in report.blocks:
        assert block.name in headings, block.name
    tab.deleteLater()


def test_it_says_what_it_measures_before_anything_has_been_run(qapp):
    """An empty tab that says nothing reads as a broken tab."""
    from PyQt6.QtWidgets import QLabel
    tab = HistoryTab()
    text = " ".join(label.text() for label in tab.findChildren(QLabel))
    assert "datum" in text
    assert "hypothesis" in text, "the multiple-comparisons caveat"
    assert "Expose Public Match Data" in text
    tab.deleteLater()


def test_nothing_runs_until_the_button_is_pressed(qapp):
    """The app's live loop never makes network calls, and this is the only
    feature in it that would."""
    tab = HistoryTab()
    assert tab.worker is None
    assert tab.report is None
    assert not tab.export_button.isEnabled()
    tab.deleteLater()


def test_a_bad_account_is_refused_without_a_request(qapp, monkeypatch):
    from draft_assist.history import opendota
    called = []
    monkeypatch.setattr(opendota, "_get",
                        lambda *a, **k: called.append(a) or {})
    tab = HistoryTab()
    tab.account_box.setText("not an id at all")
    tab.start()
    assert tab.worker is None, "it must not start a run it cannot make"
    assert not called
    assert "display name" in tab.status.text()
    tab.deleteLater()


def test_the_options_are_read_off_the_controls(qapp):
    tab = HistoryTab()
    tab.window_box.setCurrentIndex(1)          # last 3 months
    tab.ranked_tick.setChecked(True)
    tab.analysis_ticks["lane"].setChecked(True)
    options = tab.options()
    assert options.window == "3m" and options.days == 91
    assert options.ranked_only and options.picked["lane"]
    assert options.window_label == "Last 3 months"
    tab.deleteLater()


def test_a_finished_run_is_remembered_and_headlined(qapp, tmp_path,
                                                    monkeypatch):
    """The date of the last run stays at the top for that account, which is
    what makes running it again a one-press job."""
    from draft_assist.history import account, store
    monkeypatch.setattr(store, "STORE_FILE", tmp_path / "accounts.json")
    tab = HistoryTab()
    tab._account = account.parse("195286385")
    report = a_report()
    report.options.account_id = 195286385
    tab._done(report)
    assert tab.report is report
    assert tab.export_button.isEnabled()
    assert "Last run" in tab.last_run.text()
    assert "195286385" in tab.last_run.text()
    saved = store.load(tmp_path / "accounts.json")
    assert saved and saved[0]["account_id"] == 195286385
    assert saved[0]["matches"] == report.n
    tab.deleteLater()


def test_the_bar_column_is_scaled_to_the_block_it_is_in(qapp):
    """A block of small differences still has to be readable, so the bar is
    scaled against that block's own biggest eligible deviation rather than
    against some absolute idea of a big number."""
    from PyQt6.QtCore import Qt
    table = BucketTable(["Bucket", "Games", "Win rate", "Against"])
    rows = analyse.categorical(a_report().matches, 0.6, lambda m: m.hero,
                               "count")
    table.fill(rows, lambda row: f"{row.rate * 100:.0f}%", 0.2)
    assert table.rowCount() == len(rows)
    for index in range(table.rowCount()):
        data = table.item(index, 3).data(Qt.ItemDataRole.UserRole)
        assert data and data[1] == 0.2
    table.deleteLater()


def test_the_ranked_list_of_every_hero_is_gone(window):
    """It answered "what should I pick", which the Draft tab answers under
    the picks. The tab is the match history now."""
    assert not hasattr(window, "table")
    assert not hasattr(window, "search_box")
    assert not hasattr(window, "detail")
    assert not hasattr(window, "counters")
    titles = [window.tabs.tabText(i) for i in range(window.tabs.count())]
    assert titles == ["Draft", "Analysis", "Debug"]
    assert window.history_tab is window.tabs.widget(1)


def test_the_refresh_loop_never_reaches_the_analyser(window, monkeypatch):
    """Four times a second, and a network call in it costs a draft."""
    from draft_assist.history import opendota
    monkeypatch.setattr(opendota, "_get", lambda *a, **k: pytest.fail(
        "the refresh loop asked OpenDota for something"))
    window.refresh()
    window.refresh()


def test_closing_the_window_does_not_leave_a_thread_running(window):
    """A QThread destroyed while it is still running takes the process with
    it, and closing mid-fetch is exactly when that happens."""
    window.history_tab.shutdown()
    window.close()
    assert window.history_tab.worker is None
