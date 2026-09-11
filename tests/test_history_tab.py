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

from PyQt6.QtWidgets import QApplication, QLabel  # noqa: E402

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


def row_says(tab) -> str:
    """Everything the account row at the top of the tab is saying.

    It REPLACED a dim one-line label, at the user's request, so the
    assertions that used to read `.text()` read the row's parts instead:
    the name, the range, and the tooltip that took over the match count
    and win rate the old line printed inline.
    """
    row = tab.last_run
    return " | ".join((row.who.text(), row.when.text(), row.toolTip()))


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
    # COUNTED, NEVER SPELLED. It read "Eleven analyses run at once" after
    # the list had grown past eleven — a front page understating the very
    # multiple-comparisons risk that sentence exists to raise.
    from draft_assist.history import analyse
    assert f"{len(analyse.ANALYSES)} analyses run at once" in text
    assert "Eleven analyses" not in text
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
    # Whichever analysis happens to be first — the point is that the tick
    # reaches the options, not which one it is. Naming one meant this
    # broke when Lane role was removed, which is a fact about the list
    # rather than about reading the controls.
    key = next(iter(tab.analysis_ticks))
    tab.analysis_ticks[key].setChecked(True)
    options = tab.options()
    assert options.window == "3m" and options.days == 91
    assert options.ranked_only and options.picked[key]
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
    # After a run the row shows the RANGE, the same way the Draft tab's
    # does — it is the same widget, so the two cannot describe one run
    # two different ways.
    # The run's own name, not its number: the lookup resolved it, and
    # the number is what you TYPE while the name is what you recognise.
    assert tab.last_run.who.text() == "Bijson"
    assert "\u2192" in tab.last_run.when.text(), "a from-to range"
    assert "60 matches" in tab.last_run.toolTip()
    # And no offer to click through to the tab you are already on.
    assert "Click to open" not in tab.last_run.toolTip()
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


def test_the_dropdown_names_the_account_it_cannot_be_recognised_by(
        qapp, tmp_path, monkeypatch):
    """Nobody recognises their own friend ID a fortnight later, so the
    name the run resolved goes in brackets after the number — in the
    dropdown and in the line above it, spelled the same way in both."""
    from draft_assist.history import store
    path = tmp_path / "accounts.json"
    monkeypatch.setattr(store, "STORE_FILE", path)
    store.remember(195286385, "Bijson", when="2026-09-09 10:00",
                   matches=412, wins=211, path=path)
    store.remember(42, "", when="2026-09-01 09:00", matches=88, wins=40,
                   path=path)

    tab = HistoryTab()
    shown = [tab.remembered.itemText(i)
             for i in range(1, tab.remembered.count())]
    assert shown == ["42", "195286385 (Bijson)"]
    # An account with no resolved name is its number alone: empty brackets
    # would be the app reporting a failed lookup at the user.
    assert "()" not in " ".join(shown)
    assert "195286385 (Bijson)" not in row_says(tab)   # 42 is newest
    tab._apply_remembered(store.load(path)[1])
    assert "195286385 (Bijson)" in row_says(tab)
    tab.deleteLater()


def test_a_private_match_history_is_flagged_under_the_search(qapp):
    """It is a Dota setting the user can change in ten seconds, so it must
    read as something to act on rather than as the app having failed."""
    from draft_assist.history import runner
    tab = HistoryTab()
    tab._fault(runner.PRIVATE)
    # `isHidden`, not `isVisible`: the tab has never been shown, so
    # isVisible answers "is this on screen" rather than "did we hide it".
    assert not tab.status.isHidden()
    assert tab.status.text() == runner.PRIVATE
    assert tab.status.property("warn") is True
    # And it goes back to an ordinary note when the next run starts.
    tab._progress("Looking up the account…", 0, 0)
    assert tab.status.property("warn") is False
    tab.deleteLater()


def test_opening_the_tab_draws_the_last_run_with_no_network(qapp, tmp_path,
                                                           monkeypatch):
    """The tab used to cost a fetch every time it was looked at, and it
    opened blank until that fetch finished."""
    from draft_assist.history import cache, opendota, store

    report = a_report()
    report.options.account_id = 195286385
    store.remember(195286385, "Bijson", when="2026-09-09 10:00",
                   matches=report.n, wins=report.wins)
    assert cache.save(report)

    monkeypatch.setattr(opendota, "_get", lambda *a, **k: pytest.fail(
        "opening the tab asked OpenDota for something"))
    tab = HistoryTab()
    assert tab.report is not None
    assert tab.report.n == report.n
    assert tab.export_button.isEnabled(), "export must work with no network"
    # And the button says what pressing it would now do.
    assert tab.run_button.text() == "Update"
    tab.deleteLater()


def test_a_listener_connected_after_the_tab_must_be_told_what_it_holds(
        qapp, tmp_path, monkeypatch):
    """Closing the app and reopening it showed "No account measured yet"
    with last night's run sitting on disk the whole time.

    `HistoryTab.__init__` loads the cached run and ASSIGNS `report`,
    which emits `report_changed` - before `MainWindow` has connected
    anything to it. A signal announces CHANGES; whatever the object
    already holds has to be read once, explicitly, or every listener
    built after it starts life out of date.
    """
    from draft_assist.history import cache, store
    monkeypatch.setattr(cache, "CACHE_DIR", tmp_path)
    monkeypatch.setattr(store, "STORE_FILE", tmp_path / "accounts.json")

    report = a_report()
    report.options.account_id = 195286385
    report.name = "Bijson"
    cache.save(report)
    store.remember(195286385, "Bijson",
                   when=report.ran_at.strftime("%Y-%m-%d %H:%M"),
                   matches=report.n, wins=report.wins,
                   options=report.options.as_dict())

    tab = HistoryTab()                       # as if the app just opened
    assert tab.report is not None, "the cached run is loaded on construction"

    heard = []
    tab.report_changed.connect(heard.append)
    assert heard == [], "the emit already happened - this is the trap"

    # So the window reads it once, and only then is the row right.
    tab.report_changed.emit(tab.report)
    assert heard and heard[0] is tab.report
    assert tab.last_run.who.text() == "Bijson"
    assert "\u2192" in tab.last_run.when.text()
    tab.deleteLater()


def test_with_nothing_cached_the_button_still_says_run(qapp):
    tab = HistoryTab()
    assert tab.report is None
    assert tab.run_button.text() == "Run"
    tab.deleteLater()


def test_the_ranked_list_of_every_hero_is_gone(window):
    """It answered "what should I pick", which the Draft tab answers under
    the picks. The tab is the match history now."""
    assert not hasattr(window, "table")
    assert not hasattr(window, "search_box")
    assert not hasattr(window, "detail")
    assert not hasattr(window, "counters")
    titles = [window.tabs.tabText(i) for i in range(window.tabs.count())]
    assert titles == ["Draft", "History"]
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


def test_lane_role_is_gone_entirely(qapp):
    """Removed at the user's request — "dont even want it there as an
    unticked item". It was off by default because OpenDota parses a
    minority of matches, so the bucket was mostly "Unparsed": an analysis
    that mostly reports it could not tell."""
    from draft_assist.history import analyse

    assert "lane" not in dict((k, t) for k, t, _d, _b in analyse.ANALYSES)
    assert "lane" not in analyse.SPLITS
    tab = HistoryTab()
    assert "lane" not in tab.analysis_ticks
    assert not any("lane" in t.text().lower()
                   for t in tab.analysis_ticks.values())
    tab.deleteLater()


def test_ranked_only_starts_ticked(qapp):
    """At the user's request. The question the tab asks is what goes with
    winning RANKED games; turbo and unranked answer a different one."""
    from draft_assist.history.report import Options

    assert Options(account_id=1).ranked_only is True
    assert Options.from_dict({}, 1).ranked_only is True
    tab = HistoryTab()
    assert tab.ranked_tick.isChecked()
    tab.deleteLater()


def _report(blocks):
    """A Report carrying just these blocks. `findings` is a PROPERTY read
    off them, so the blocks are what a test has to build."""
    from draft_assist.history.report import Options, Report
    return Report(options=Options(account_id=1), how="", name="",
                  matches=[], blocks=blocks, dropped={}, sessions=0,
                  returned=0)


def _block(kind, sigmas, ident="b"):
    """A block with real BUCKETS behind its findings.

    The summary draws a bar showing where each finding sits in its
    block's range, and a block with no rows has no range — so a fixture
    without them silently exercises the "nothing to draw" path instead of
    the one under test.
    """
    from draft_assist.history.analyse import Block, Bucket, Finding
    rows = [Bucket(key=f"{ident}{i}", n=40, rate=rate, mean=rate * 100,
                   sigma=0.0, eligible=True)
            for i, rate in enumerate((0.40, 0.50, 0.60, 0.70))]
    findings = []
    for i, s in enumerate(sigmas):
        rate = 0.70 if s > 0 else 0.40
        findings.append(Finding(sigma=s, key=f"{ident}{i}", text="",
                                short=f"{ident}{i} win rate",
                                value=rate if kind == "cat" else rate * 100,
                                n=40))
    return Block(id=ident, name=ident, desc="", kind=kind, rows=rows,
                 datum=50.0, findings=findings)


def test_item_findings_stay_out_of_the_summary(qapp):
    """At the user's request — "do not show item recommendations /
    findings in the what goes with winning summary ... its just too much
    spam". The block itself is untouched further down the tab; what comes
    out is the HEADLINE, and items crowded it: three heroes' worth, and
    they separate easily because an expensive item is partly a consequence
    of the game going well rather than a cause of it."""
    report = _report([_block("cat", [3.0, 2.0], "split"),
                      _block("items", [9.0, 8.0], "items")])
    rates, _ = report.split_findings()
    assert [pair[0].kind for pair in rates] == ["cat", "cat"]
    assert not any(pair[0].kind == "items" for pair in rates)
    # And the block is still THERE to be drawn in full further down.
    assert any(b.kind == "items" for b in report.blocks)


def test_the_per_hero_summary_keeps_three_of_each_metric(qapp):
    """"I only want the top 3 hero damage, and top 3 weighted KDA."

    It was three at each END of the two metrics POOLED, which is a
    different cut and a worse one to read: damage and KDA separate by
    different amounts, so the pooled ends came out all damage with the
    KDA ranking crowded out of its own summary. Per metric, both get
    their three whatever the other is doing — and it is still the biggest
    deviation EITHER WAY, because where you are worst on a hero is as
    much the point as where you are best.
    """
    from draft_assist.history.report import Report

    report = _report([_block("metric", [9.0, -8.0, 7.0, -6.0, 5.0], "dmg"),
                      _block("metric", [4.0, -3.5, 3.0, -2.5, 2.0], "kda")])
    _, contributions = report.split_findings()
    per_block = {}
    for block, finding in contributions:
        per_block.setdefault(block.id, []).append(finding.sigma)
    assert set(per_block) == {"dmg", "kda"}, \
        "a metric was crowded out of its own summary"
    for ident, kept in per_block.items():
        assert len(kept) == Report.SUMMARY_PER_METRIC, ident
    # Strongest first, either direction — not the flattering end alone.
    assert per_block["dmg"] == [9.0, -8.0, 7.0]
    assert per_block["kda"] == [4.0, -3.5, 3.0]

    # Fewer than three: everything is kept rather than padded or dropped.
    _, few = _report([_block("metric", [1.0, -1.0], "m")]).split_findings()
    assert len(few) == 2


def test_the_sigma_figure_is_never_drawn(qapp):
    """"You can drive by the sigma, but don't show the sigma value — it
    means nothing to people."

    A count of standard errors is what decided which findings appeared
    and in what order, and as a figure beside a sentence it is a number
    the reader cannot act on sitting in the column their eye lands on
    first. The summary no longer consults it at all — every section gets
    a row whether or not anything cleared the floor — but it still must
    never be PRINTED, and the direction it used to carry is on the bar,
    as a green mark for the section's best and a red one for its worst.
    """
    from draft_assist.ui import theme
    from draft_assist.ui.spread_bar import SpreadBar

    tab = HistoryTab()
    # A real section id: `summary_rows` walks `BLOCK_ORDER`, which is the
    # authority on what a section is and what order they come in.
    report = _report([_block("cat", [4.0, -3.0], "dow")])
    tab.render(report)
    labels = [w.text() for w in tab.results.parentWidget().findChildren(QLabel)]
    assert not any("\u03c3" in text for text in labels), \
        [t for t in labels if "\u03c3" in t]

    bars = tab.results.parentWidget().findChildren(SpreadBar)
    assert len(bars) == 1, "one bar per section"
    # CHECKED AGAINST THE PIXELS, because the marks are painted: a value
    # that never reaches the screen would pass a test about the value and
    # show the reader nothing.
    bar = bars[0]
    bar.resize(240, bar.height())
    image = bar.grab().toImage()
    found = {image.pixelColor(x, y).name()
             for x in range(image.width()) for y in range(image.height())}
    assert theme.GOOD in found, "the best never drew"
    assert theme.BAD in found, "the worst never drew"
    tab.deleteLater()


def test_the_export_button_is_the_same_button_as_run(qapp):
    """"export workbook needs to look like the other buttons e.g. run...
    greyed out when the analysis hasnt been run yet, but once it runs it
    should turn into the typical red button"."""
    from draft_assist.ui import theme

    tab = HistoryTab()
    assert tab.export_button.property("accent") is True
    assert tab.run_button.property("accent") is True
    assert not tab.export_button.isEnabled(), "nothing to export yet"
    # And the DISABLED rule has to come after the accent one, or a button
    # carrying [accent="true"] stays fully red while unclickable.
    css = theme.STYLESHEET
    assert 'QPushButton[accent="true"]:disabled' in css
    assert (css.index('QPushButton[accent="true"] {')
            < css.index('QPushButton[accent="true"]:disabled'))
    tab.deleteLater()


# ---- the tables: a cut, and a sort, and they are not the same thing ----

def _buckets(spec):
    """(name, games, rate) -> the rows a block hands its table."""
    from draft_assist.history.analyse import Bucket
    return [Bucket(key=name, n=games, rate=rate, delta=rate - 0.5,
                   eligible=games >= 8) for name, games, rate in spec]


ROWS = _buckets([("Lion", 42, 0.55), ("Axe", 30, 0.70), ("Pudge", 20, 0.40),
                 ("Sniper", 12, 0.65), ("Bane", 4, 0.90)])


def _table(rows=None):
    from draft_assist.ui.history_tab import BucketTable
    table = BucketTable(["Bucket", "Games", "Win rate", "Against 50%"])
    table.show_rows(rows if rows is not None else ROWS,
                    lambda r: f"{r.rate * 100:.0f}%", 0.2, (),
                    lambda r: r.rate)
    return table


def _column(table, column=0):
    return [table.item(i, column).text() for i in range(table.rowCount())]


def test_a_table_opens_on_games_descending_with_every_row(qapp):
    """"By default the sort should be number of games, as is right now.\""""
    table = _table()
    assert _column(table) == ["Lion", "Axe", "Pudge", "Sniper", "Bane"]
    assert table.view() == {"top": 0, "by": "games", "sort": "games",
                            "desc": True}
    table.deleteLater()


def test_clicking_a_heading_sorts_and_clicking_it_again_flips(qapp):
    """And it sorts on the VALUE, not on the text. Qt's own sortItems
    compares the item's string, so "10" lands before "9" and "62%" before
    "9%" — every column here is a number wearing a suffix."""
    from draft_assist.ui.history_tab import VALUE_COL, GAMES_COL
    table = _table()
    # Bane is the four-game bucket, so it is muted and sinks either way
    # (see the test below); the other four are what the sort orders.
    table._clicked(VALUE_COL)
    assert _column(table) == ["Axe", "Sniper", "Lion", "Pudge", "Bane"]
    table._clicked(VALUE_COL)
    assert _column(table) == ["Pudge", "Lion", "Sniper", "Axe", "Bane"]
    # A NEW column starts descending — "most" is what anybody wants first.
    table._clicked(GAMES_COL)
    assert _column(table, GAMES_COL) == ["42", "30", "20", "12", "4"]
    table.deleteLater()


def test_the_muted_rows_sink_whichever_way_the_sort_runs(qapp):
    """"The sort should keep the grey rows at the bottom."

    A muted row is one there is not enough behind to act on, and sorting
    by a figure floated them: three heroes with two, three and four games
    stood above every hero with a real sample, so the numbers at the top
    of the table were the ones least worth reading. Folding "muted" into
    the sort key would only move the problem — it would flip with the
    direction and put them back on top the other way round — so it is a
    partition applied after the sort, in both directions.
    """
    from draft_assist.ui.history_tab import VALUE_COL, GAMES_COL, NAME_COL
    table = _table()
    # DERIVED, not written down: `_buckets` decides eligibility from the
    # sample, and a set typed out here goes stale the moment that does.
    grey = {r.key for r in ROWS if not r.eligible}
    assert grey, "the sample has no muted row to sink"
    table.set_view(top=0)
    for column in (VALUE_COL, GAMES_COL, NAME_COL):
        for _ in range(2):               # descending, then ascending
            table._clicked(column)
            shown = _column(table)
            muted = [name for name in shown if name in grey]
            assert shown[-len(muted):] == muted, (column, shown)
    table.deleteLater()


def test_the_cut_is_by_the_filter_field_and_the_sort_only_reorders(qapp):
    """"Filter the top 10 heroes by number of games played, and then sort
    by win rate."

    Two inputs, because the cut and the reading are different questions.
    One control doing both would make them the same answer: the rows
    shown would always be the rows the sort puts first, so asking for the
    best win rates would quietly reduce the table to whichever four-game
    buckets got lucky — which is exactly the row this sample has in it.
    """
    from draft_assist.ui.history_tab import VALUE_COL
    table = _table()
    table.set_view(top=3, by="games")
    table._clicked(VALUE_COL)               # now read by win rate
    # The three MOST PLAYED, in win-rate order. Bane's 90% off four games
    # never had a chance to make it in.
    assert _column(table) == ["Axe", "Lion", "Pudge"]
    assert "Bane" not in _column(table)
    # And the cut does not follow the sort direction: flipping the
    # reading must not change WHICH rows exist.
    table._clicked(VALUE_COL)
    assert sorted(_column(table)) == ["Axe", "Lion", "Pudge"]
    table.deleteLater()


def test_a_cut_rescales_the_bars_it_left_behind(qapp):
    """The fade is relative to the biggest sample IN THE TABLE, so a cut
    that removes the biggest bucket has to re-scale the survivors or
    every remaining bar reads too faint for what it is."""
    from PyQt6.QtCore import Qt
    from draft_assist.ui.history_tab import BAR_COLUMN

    def weight_of(table, name):
        row = _column(table).index(name)
        return table.item(row, BAR_COLUMN).data(Qt.ItemDataRole.UserRole)[3]

    table = _table()
    with_lion = weight_of(table, "Axe")
    table.set_view(top=2, by="value")        # Bane and Axe survive
    assert weight_of(table, "Axe") > with_lion
    table.deleteLater()


def test_the_sorted_column_wears_the_caret(qapp):
    """Drawn INTO the heading text. Qt's own sort indicator is a
    sub-control this stylesheet does not name, and the parts a stylesheet
    does not name are handed to the native style — the lesson the
    scrollbars taught."""
    from draft_assist.ui.history_tab import VALUE_COL
    table = _table()
    heads = lambda: [table.horizontalHeaderItem(c).text() for c in range(3)]
    assert heads()[1].endswith("▼") and "▼" not in heads()[2]
    table._clicked(VALUE_COL)
    assert heads()[2].endswith("▼") and "▼" not in heads()[1]
    table._clicked(VALUE_COL)
    assert heads()[2].endswith("▲")
    table.deleteLater()


def test_the_table_view_is_remembered_across_accounts(qapp, tmp_path,
                                                      monkeypatch):
    """"If I look up someone else's account, the sorts and filters should
    be the same as I had on the previous analysis." So it is keyed by the
    BLOCK and kept in the app's own settings, not beside the remembered
    accounts where it would be one player's answer restored over
    another's."""
    from draft_assist.ui import settings as ui_settings
    from draft_assist.ui.history_tab import VALUE_COL

    monkeypatch.setattr(ui_settings, "SETTINGS_FILE", tmp_path / "s.json")
    settings = dict(ui_settings.DEFAULTS)
    settings["history_tables"] = {}
    tab = HistoryTab(settings=settings)
    report = _report([_block("cat", [3.0], "hero")])
    report.blocks[0].shown = list(ROWS)
    report.blocks[0].rows = list(ROWS)
    tab.render(report)
    table = tab._tables["hero"][0]
    table.controls.count.setValue(3)
    table._clicked(VALUE_COL)
    assert settings["history_tables"]["hero"] == {
        "top": 3, "by": "games", "sort": "value", "desc": True}
    # It reached DISK, so the next launch opens the same way.
    assert ui_settings.load(tmp_path / "s.json")["history_tables"]["hero"] \
        == settings["history_tables"]["hero"]

    # A second tab — which is what looking up another account amounts to
    # — opens wearing it.
    again = HistoryTab(settings=dict(settings))
    again.render(report)
    assert again._tables["hero"][0].view()["top"] == 3
    assert again._tables["hero"][0].view()["sort"] == "value"
    assert _column(again._tables["hero"][0]) == ["Axe", "Lion", "Pudge"]
    tab.deleteLater()
    again.deleteLater()


def test_a_dict_preference_is_not_shared_with_DEFAULTS(qapp, tmp_path):
    """`dict(DEFAULTS)` is SHALLOW, so the two dict-valued preferences
    would be the same object every caller shares — writing a table's sort
    order would edit DEFAULTS itself and the next fresh load would come
    back carrying it as though it had always been the default."""
    from draft_assist.ui import settings as ui_settings
    shipped = dict(ui_settings.DEFAULTS["history_tables"])
    first = ui_settings.load(tmp_path / "missing.json")
    first["history_tables"]["hero"] = {"top": 5, "mutated": True}
    assert ui_settings.DEFAULTS["history_tables"] == shipped, \
        "writing a table's view edited the defaults themselves"
    assert ui_settings.load(tmp_path / "missing.json")["history_tables"] \
        == shipped


# ---- the item block: one hero at a time --------------------------------

def _item_report(spec=(("Lion", 42), ("Axe", 30), ("Pudge", 9))):
    """A report whose item block carries one group per named hero."""
    from draft_assist.history.analyse import Block, ItemGroup
    groups = [ItemGroup(hero=name, games=games, measured=games,
                        baseline=0.5, rows=list(ROWS), shown=list(ROWS),
                        hidden=0)
              for name, games in spec]
    block = Block(id="items", name="Items and win rate by hero", desc="d",
                  kind="items", groups=groups, covered=len(spec), total=9)
    return _report([block])


def test_the_item_block_shows_one_hero_chosen_from_a_dropdown(qapp,
                                                              tmp_path,
                                                              monkeypatch):
    """"I don't need to see them simultaneously — the user should just
    select what they want to see the most effective items for, hero by
    hero."

    Stacking was the wrong shape for this block: each hero's items are
    read against THAT HERO's own win rate, so two tables side by side
    share nothing but a column heading.
    """
    from PyQt6.QtWidgets import QComboBox
    from draft_assist.ui import settings as ui_settings

    monkeypatch.setattr(ui_settings, "SETTINGS_FILE", tmp_path / "s.json")
    settings = dict(ui_settings.DEFAULTS)
    settings["history_tables"] = {}
    tab = HistoryTab(settings=settings)
    tab.render(_item_report())

    boxes = [b for b in tab.results.parentWidget().findChildren(QComboBox)
             if b.count() and " games)" in b.itemText(0)]
    assert len(boxes) == 1, "one chooser, not one per hero"
    chooser = boxes[0]
    # MOST PLAYED FIRST — the heroes worth reading are already at the top.
    assert [chooser.itemData(i) for i in range(chooser.count())] == \
        ["Lion", "Axe", "Pudge"]
    assert "42 games" in chooser.itemText(0)
    # And exactly ONE table on the card, whichever hero is picked.
    assert len(tab._tables.get("items", [])) == 1

    chooser.setCurrentIndex(1)
    assert len(tab._tables.get("items", [])) == 1
    # REMEMBERED BY NAME: the list is this account's own heroes in its own
    # order, so an index means a different hero the moment you look
    # somebody else up.
    assert settings["history_tables"]["item_hero"] == {"hero": "Axe"}

    again = HistoryTab(settings=dict(settings))
    again.render(_item_report())
    reopened = [b for b in again.results.parentWidget().findChildren(QComboBox)
                if b.count() and " games)" in b.itemText(0)][0]
    assert reopened.currentData() == "Axe"
    tab.deleteLater()
    again.deleteLater()


def test_a_block_card_is_its_heading_and_its_table(qapp):
    """"Remove this blurb on all the sections — it's just fluff", and
    "just the header is fine".

    Each card carried three paragraphs: what the split measures, how many
    single-game buckets were left out, and a caveat about reading the
    figures. Between them they pushed the table — the thing the card
    exists for — most of a screen down, so all three were cut.

    The user has since changed their mind about the FIRST of the three:
    "make it a slightly smaller text and italics, and make sure it's not
    super fluffy — still concise, but describes what the metric is." So
    one line comes back and the other two stay gone, and every `desc`
    was rewritten to earn the space: they say what is measured and stop.
    """
    from PyQt6.QtWidgets import QLabel
    from draft_assist.history.analyse import Block

    block = Block(id="hero", name="Hero win rates",
                  desc="Your win rate on each hero you played.", kind="cat",
                  rows=list(ROWS), shown=list(ROWS), hidden=4,
                  caveat="This ranks heroes, not your play.")
    tab = HistoryTab()
    tab.render(_report([block]))
    labels = tab.results.parentWidget().findChildren(QLabel)
    said = " ".join(w.text() for w in labels)
    assert "Hero win rates" in said, "the heading"
    assert block.desc in said, "the one line saying what is measured"
    for fluff in (block.caveat, "bucket(s)", "workbook"):
        assert fluff not in said, fluff

    # SMALLER AND ITALIC, as asked, and dim like every other aside.
    blurb = next(w for w in labels if w.text() == block.desc)
    assert "italic" in blurb.styleSheet()
    assert blurb.property("dim") is True
    tab.deleteLater()


def test_the_summary_cards_get_no_blurb(qapp):
    """"I don't want blurbs below Win rate and Game impact
    metrics." Those name a question rather than a measurement, and there
    is nothing to describe that the rows below do not already say."""
    from PyQt6.QtWidgets import QLabel
    from draft_assist.history.analyse import Block

    block = Block(id="hero", name="Hero win rates",
                  desc="Your win rate on each hero you played.", kind="cat",
                  rows=list(ROWS), shown=list(ROWS))
    tab = HistoryTab()
    tab.render(_report([block]))
    for ident in ("winning", "contrib"):
        card_widget = tab._anchors.get(ident)
        if card_widget is None:
            continue
        said = " ".join(w.text() for w in card_widget.findChildren(QLabel))
        assert block.desc not in said, ident
    tab.deleteLater()


def test_stepping_the_count_keeps_the_page_where_it_was(qapp):
    """"When I hit the up/down arrow the whole page shifts, so I can't
    spam the arrow — I have to track it."

    Removing a row shortens the table, which shortens the page, and the
    scroll area then re-clamps. The page genuinely has fewer rows in it;
    what has to stay put is the control the cursor is over.
    """
    tab = HistoryTab()
    tab.resize(700, 300)
    block = _block("cat", [3.0], "hero")
    block.rows = block.shown = list(ROWS)
    tab.render(_report([block]))
    tab.results.parentWidget().layout().activate()
    table = tab._tables["hero"][0]
    bar = tab.scroll.verticalScrollBar()
    bar.setValue(bar.maximum())
    qapp.processEvents()

    def where():
        from PyQt6.QtCore import QPoint
        return (table.controls.mapTo(tab.page, QPoint(0, 0)).y()
                - bar.value())

    before = where()
    tab._hold_still(table.controls,
                    lambda: table.set_view(top=2))
    assert where() == before, "the control moved under the cursor"
    tab.deleteLater()


# ---- the page scrolls, never a table inside it ---------------------------

def test_no_table_scrolls_inside_itself(qapp):
    """"There is the slightest little scroll happening" inside the section
    tables. Every one is sized to hold all of its rows, so anything left
    to scroll is the fit being a few pixels out — and with both scrollbars
    off that is invisible except as a page that will not move."""
    tab = HistoryTab()
    tab.resize(1200, 900)
    tab.show()
    tab.render(a_report())
    for _ in range(4):
        qapp.processEvents()
    tables = tab.findChildren(BucketTable)
    assert tables, "no tables were drawn at all"
    for table in tables:
        assert table.verticalScrollBar().maximum() == 0, \
            f"a table can still scroll by {table.verticalScrollBar().maximum()}"
    tab.close()


def test_the_wheel_over_a_table_belongs_to_the_page(qapp):
    """The half of that fix which cannot be a pixel out.

    A table as tall as every row it holds has nothing of its own to
    scroll, so an ignored wheel event goes to the scroll area under it.
    """
    from PyQt6.QtCore import QPoint, QPointF, Qt
    from PyQt6.QtGui import QWheelEvent
    tab = HistoryTab()
    tab.resize(1200, 900)
    tab.show()
    tab.render(a_report())
    for _ in range(4):
        qapp.processEvents()
    table = tab.findChildren(BucketTable)[0]
    event = QWheelEvent(
        QPointF(10, 10), QPointF(table.mapToGlobal(QPoint(10, 10))),
        QPoint(0, -40), QPoint(0, -120), Qt.MouseButton.NoButton,
        Qt.KeyboardModifier.NoModifier, Qt.ScrollPhase.NoScrollPhase, False)
    table.wheelEvent(event)
    assert not event.isAccepted(), "the table swallowed the wheel"
    tab.close()


def test_the_wheel_never_changes_a_control_it_rolls_over(qapp):
    """"I keep accidentally scrolling and changing them by accident."

    Qt steps a dropdown and a spin box on every wheel notch, which makes
    each one a trap in a page that scrolls. Click, scroll, click: the
    wheel is the page's.
    """
    from PyQt6.QtCore import QPoint, QPointF, Qt
    from PyQt6.QtGui import QWheelEvent
    from draft_assist.ui.chrome import CountBox, Dropdown

    tab = HistoryTab()
    tab.resize(1200, 900)
    tab.show()
    tab.render(a_report())
    for _ in range(4):
        qapp.processEvents()

    controls = tab.findChildren(Dropdown) + tab.findChildren(CountBox)
    assert controls, "no dropdowns or count boxes were built"
    for control in controls:
        was = (control.currentIndex() if isinstance(control, Dropdown)
               else control.value())
        event = QWheelEvent(
            QPointF(4, 4), QPointF(control.mapToGlobal(QPoint(4, 4))),
            QPoint(0, -40), QPoint(0, -120), Qt.MouseButton.NoButton,
            Qt.KeyboardModifier.NoModifier, Qt.ScrollPhase.NoScrollPhase,
            False)
        control.wheelEvent(event)
        now = (control.currentIndex() if isinstance(control, Dropdown)
               else control.value())
        assert now == was, f"{type(control).__name__} changed under the wheel"
        assert not event.isAccepted(), "the page never gets the wheel"
    tab.close()
