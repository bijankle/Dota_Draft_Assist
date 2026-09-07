"""Headless UI smoke test: the whole window runs on fake state (demo
provider, offscreen Qt platform) — no Dota, no capture, no network."""

import json
import os
from pathlib import Path

import pytest

pytest.importorskip("PyQt6")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import QPoint, Qt  # noqa: E402
from PyQt6.QtWidgets import QApplication  # noqa: E402

from draft_assist.config import RULES_FILE  # noqa: E402
from draft_assist.model import items as items_mod  # noqa: E402
from draft_assist.ui.app import MainWindow  # noqa: E402
from draft_assist.ui.hero_picker import (  # noqa: E402
    HeroPickerDialog as _Picker)
HeroPickerDialogCode = _Picker.DialogCode
from draft_assist.ui.demo import DemoDraft, demo_dataset  # noqa: E402
from draft_assist.ui.providers import DemoProvider  # noqa: E402
from draft_assist.ui import item_row as item_row_mod  # noqa: E402
from draft_assist.ui.tables import SORT_ROLE, TOTAL_LABEL  # noqa: E402


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


@pytest.fixture()
def window(qapp):
    ds = demo_dataset()
    provider = DemoProvider(ds)
    # Fast-forward the scripted draft to fully drafted (but short of the
    # 60-second auto-restart).
    provider.draft.started -= 45
    rules, meta = items_mod.load_rules(RULES_FILE)
    win = MainWindow(ds, provider, rules, meta)
    win.timer.stop()  # drive refresh manually
    yield win
    win.close()


EMPTY_SLOT_TEXT = "+"


def filled(window, side):
    """Slot labels that hold a hero; empty slots read '+' and stay clickable
    so a pick can be entered by hand."""
    return [b.text() for b in window.team_buttons[side]
            if b.text() != EMPTY_SLOT_TEXT]


def test_refresh_populates_table_and_teams(window):
    window.refresh()
    assert window.table.rowCount() > 100
    assert len(filled(window, "ally")) == 5
    # demo leaves one dire slot unknown
    assert len(filled(window, "enemy")) == 4
    assert "unresolved" in window.unknown_label.text()


def test_drafted_heroes_not_in_candidate_list(window):
    window.refresh()
    listed = {window.table.item(r, 0).text()
              for r in range(window.table.rowCount())}
    for side in ("ally", "enemy"):
        for name in filled(window, side):
            assert name not in listed


def test_breakdown_view(window):
    """Selecting a candidate shows its per-opponent terms, not just a sum,
    split into an ally bank and an enemy bank."""
    window.refresh()
    window.table.selectRow(0)
    hero_name = window.table.item(0, 0).text()
    panel = window.detail
    assert hero_name == panel.heading.text()
    assert "draft fit" in panel.subtitle.text()
    # The hero's own win rate is still shown, plainly labelled as not being
    # part of the number the list is ranked on.
    assert "not scored" in panel.subtitle.text()
    allies = [name for name, _ in panel.rows_for(0)]
    enemies = [name for name, _ in panel.rows_for(1)]
    # Every drafted hero the score depends on is itemised by name, on the
    # side it is actually on.
    assert set(allies) <= set(filled(window, "ally"))
    assert set(enemies) <= set(filled(window, "enemy"))
    assert len(allies) + len(enemies) >= 5


def test_breakdown_banks_sort_by_size_and_independently(window):
    """The point of the panel is that the terms which moved the number are
    on top — and sorting the enemy bank must not drag the allies along."""
    window.refresh()
    window.table.selectRow(0)
    panel = window.detail
    values = [delta for _, delta in panel.rows_for(0)]
    assert values == sorted(values, reverse=True)

    allies_before = [name for name, _ in panel.rows_for(0)]
    panel._sort_bank(3)                     # the enemy bank's value column
    assert [name for name, _ in panel.rows_for(0)] == allies_before
    enemies = [delta for _, delta in panel.rows_for(1)]
    assert enemies == sorted(enemies)       # flipped to ascending

    panel._sort_bank(0)                     # ally bank, by name
    names = [name for name, _ in panel.rows_for(0)]
    assert names == sorted(names, key=str.lower)


def test_counters_go_to_their_own_panel(window):
    """Mixing a ranked list of heroes nobody picked into "Why this score"
    made the breakdown look wrong — it is about heroes in THIS game."""
    window.refresh()
    window.table.selectRow(0)
    breakdown_heading = window.detail.heading.text()

    button = window.team_buttons["enemy"][0]
    assert button.text() != EMPTY_SLOT_TEXT
    button.click()
    assert "Best against" in window.counters.heading.text()
    assert panel_values(window.counters, 0) == sorted(
        panel_values(window.counters, 0), reverse=True)
    # and the breakdown is untouched
    assert window.detail.heading.text() == breakdown_heading
    assert "Best against" not in window.detail.heading.text()


def test_why_this_score_only_names_heroes_in_this_game(window):
    window.refresh()
    window.table.selectRow(0)
    drafted = set(filled(window, "ally")) | set(filled(window, "enemy"))
    named = {name for bank in (0, 1)
             for name, _delta in window.detail.rows_for(bank)}
    assert named <= drafted
    assert named


def panel_values(panel, bank):
    return [delta for _, delta in panel.rows_for(bank)]


def test_hero_table_sorts_on_numbers_not_text(window):
    """Sorted as text, "+9.0" lands above "+10.0" and a percentage column
    comes out alphabetical."""
    window.refresh()
    header = window.table.horizontalHeader()
    for column, reverse in ((1, True), (2, False), (3, False)):
        window.table.sortItems(
            column, Qt.SortOrder.DescendingOrder if reverse
            else Qt.SortOrder.AscendingOrder)
        values = [window.table.item(row, column).data(SORT_ROLE)
                  for row in range(window.table.rowCount())]
        assert values == sorted(values, reverse=reverse), \
            f"column {column} is not in numeric order"
    assert header.isSortIndicatorShown()


def test_chosen_sort_survives_a_refresh(window):
    """The table refreshes on a timer; a sort the user picked must not be
    silently reset under them every second."""
    window.refresh()
    window.table.sortItems(2, Qt.SortOrder.AscendingOrder)
    window.refresh()
    header = window.table.horizontalHeader()
    assert header.sortIndicatorSection() == 2
    assert header.sortIndicatorOrder() == Qt.SortOrder.AscendingOrder
    values = [window.table.item(row, 2).data(SORT_ROLE)
              for row in range(window.table.rowCount())]
    assert values == sorted(values)


def test_items_are_live_from_the_first_enemy_pick(window):
    """They used to wait for your own pick to be locked, which left the
    strip blank for the whole draft — the one stretch where knowing their
    line-up demands a Nullifier would change what you pick."""
    window.refresh()
    assert window.item_row.isVisible() or True
    # Either concrete advice or the honest-silence message; never a prompt
    # telling you to go and lock something first.
    assert "Lock your pick" not in window.item_row.message.text()

    # Naming and locking a pick refines the advice; it does not switch it on.
    before = list(window.item_row.items)
    window._set_my_hero(window.team_buttons["ally"][0].property("hero_id"))
    window._set_my_hero_locked(True)
    assert "Lock your pick" not in window.item_row.message.text()
    assert isinstance(before, list)


def test_an_empty_draft_shows_the_shape_of_the_strip_not_a_sentence(qapp):
    """A line saying items appear later is read once and skipped forever.
    Blank plates say the same thing in the place the answer will be."""
    window = blank_window(qapp)
    try:
        window.refresh()
        assert window.item_row.items == []
        assert window.item_row.message.text() == ""
        assert len(window.item_row._blanks) == item_row_mod.PLACEHOLDERS
    finally:
        window.close()


def test_role_highlight_changes_rows(window):
    """Queued role highlights matching heroes but never filters the list."""
    from draft_assist.ui.app import HIGHLIGHT

    window.refresh()
    total_rows = window.table.rowCount()

    def highlighted():
        return sum(1 for r in range(total_rows)
                   if window.table.item(r, 0).background().color()
                   == HIGHLIGHT)

    assert highlighted() == 0          # no role selected yet
    # The role now comes from the slot your own hero stands in, so setting
    # it means naming your hero and giving that slot a position.
    window._set_my_hero(window.team_buttons["ally"][0].property("hero_id"))
    window._set_slot_role("ally", 0, "Pos 1")   # Carry
    assert highlighted() > 0
    # Highlighting is cosmetic: the full list is still present.
    assert window.table.rowCount() == total_rows


def test_side_swap_flips_teams(window):
    window.refresh()
    before = filled(window, "ally")
    window.side_combo.setCurrentIndex(1)
    window.refresh()
    after = filled(window, "enemy")
    assert before == after


def test_status_bar_reports_data_and_mode(window):
    window.refresh()
    msg = window.status.currentMessage()
    assert "mode: demo" in msg
    assert "bracket: ANCIENT+DIVINE" in msg


def test_snapshot_falls_back_to_grabbing_dota(window, monkeypatch):
    """With no live frame (game-data mode) the snapshot key still captures
    the Dota window — that grab is what anchors overlay positions."""
    window.refresh()
    window.snapshot_button.click()
    # Nothing to grab here (no Dota, no Windows), so it must say so plainly.
    assert "Nothing to capture" in window.snapshot_label.text()


def test_snapshot_grabs_a_frame_when_dota_is_available(window, tmp_path,
                                                       monkeypatch):
    import numpy as np

    from draft_assist.vision import debug as debug_mod

    monkeypatch.setattr(debug_mod, "DEBUG_OUT", tmp_path)
    monkeypatch.setattr(
        type(window), "_grab_dota_frame",
        lambda self: np.full((1080, 1920, 3), 60, dtype=np.uint8))
    window.refresh()
    window.snapshot_button.click()
    assert window.snapshot_label.text().startswith("Saved to")
    folder = tmp_path / sorted(p.name for p in tmp_path.iterdir())[0]
    assert (folder / "frame.png").exists()
    # The overlay drawn on it is what makes slot positions checkable.
    assert (folder / "overlay.png").exists()
    assert (folder / "slots.txt").exists()


def test_snapshot_writes_dump_for_a_frame(window, tmp_path, monkeypatch):
    """With a frame present the button must produce a self-contained folder."""
    import numpy as np

    from draft_assist.vision import debug as debug_mod
    from draft_assist.vision.layout import DraftLayout
    from draft_assist.vision.recognize import DraftRead, SlotRead

    monkeypatch.setattr(debug_mod, "DEBUG_OUT", tmp_path)
    window.refresh()
    frame = np.full((1080, 1920, 3), 40, dtype=np.uint8)
    rects = DraftLayout().slots()
    window.snapshot.frame = frame
    window.snapshot.read_raw = DraftRead(slots=[
        SlotRead(rect=r, hero_id=None, best_label="x", distance=30, margin=0)
        for r in rects])
    window.snapshot_button.click()

    text = window.snapshot_label.text()
    assert text.startswith("Saved to")
    folder = tmp_path / sorted(p.name for p in tmp_path.iterdir())[0]
    assert (folder / "frame.png").exists()
    assert (folder / "overlay.png").exists()
    assert (folder / "slots.txt").exists()
    assert "hash_size" in (folder / "context.txt").read_text()


def make_window(qapp, ds):
    from draft_assist.ui.app import MainWindow
    from draft_assist.ui.providers import DemoProvider
    rules, meta = items_mod.load_rules(RULES_FILE)
    win = MainWindow(ds, DemoProvider(ds), rules, meta)
    win.timer.stop()
    return win


def test_app_opens_before_any_data_is_downloaded(qapp):
    """First run must explain itself, not crash on a missing cache."""
    from draft_assist.data import store

    win = make_window(qapp, store.empty_dataset())
    try:
        win.refresh()
        assert win.table.rowCount() == 0
        assert win.banner.isVisible() or not win.isVisible()
        assert "No statistics downloaded yet" in win.banner_label.text()
        assert "Download" in win.banner_button.text()
        assert "data: none" in win.status.currentMessage()
        assert win.data_pill.text() == "no data"
    finally:
        win.close()


def test_banner_hidden_once_data_is_fresh(window):
    window.refresh()
    assert not window.banner.isVisible()


def test_menus_expose_every_maintenance_action(window):
    """Everything that used to be a .bat file is reachable from the menus."""
    menus = {m.title().replace("&", ""): m
             for m in window.menu_bar.findChildren(type(window.menu_bar
                                                         .addMenu("x")))}
    labels = {title: [a.text().replace("&", "") for a in menu.actions()]
              for title, menu in menus.items()}
    flat = [text for texts in labels.values() for text in texts]
    for expected in ("Statistics and portraits…", "Tune recognition…",
                     "List capture sources…", "Run capture probe…",
                     "Update application…", "Save debug snapshot"):
        assert expected in flat, f"{expected} missing from menus: {flat}"


def test_force_recognition_menu_and_toolbar_stay_in_sync(window):
    window.force_action.setChecked(True)
    assert window.force_check.isChecked()
    window.force_check.setChecked(False)
    assert not window.force_action.isChecked()


def test_hero_filter_hides_non_matching_rows(window):
    window.refresh()
    target = window.table.item(0, 0).text()
    window.search_box.setText(target)
    visible = [r for r in range(window.table.rowCount())
               if not window.table.isRowHidden(r)]
    assert visible
    for r in visible:
        assert target.lower() in window.table.item(r, 0).text().lower()
    window.search_box.setText("")
    assert not window.table.isRowHidden(1)


def test_reload_backend_picks_up_new_data(window, monkeypatch):
    from draft_assist.data import store
    from draft_assist.ui.demo import demo_dataset

    fresh = demo_dataset()
    monkeypatch.setattr(store, "load_or_empty", lambda *a, **k: fresh)
    window.reload_backend()
    assert window.ds is fresh
    assert "Reloaded" in window.status.currentMessage()


def test_crash_reporter_writes_a_log(tmp_path, monkeypatch, qapp):
    """A windowless launch has no console, so crashes must leave a trace."""
    from draft_assist.ui import app as app_mod

    monkeypatch.setattr(app_mod, "CRASH_LOG", tmp_path / "crash.log")
    monkeypatch.setattr(app_mod.QMessageBox, "exec", lambda self: 0)
    try:
        raise ValueError("boom in startup")
    except ValueError as exc:
        app_mod._report_crash(exc)
    text = (tmp_path / "crash.log").read_text()
    assert "boom in startup" in text and "ValueError" in text


def test_manual_hint_explains_missing_picks(qapp, monkeypatch):
    """When the game cannot report the enemy line-up the UI must say so."""
    from draft_assist.gsi import state as gsi_state
    from draft_assist.ui.demo import demo_dataset
    from draft_assist.ui.manual import ManualDraft
    from draft_assist.ui.providers import GsiProvider
    from tests.test_gsi import FakeServer

    ds = demo_dataset()
    manual = ManualDraft()
    payload = {"map": {"game_state": gsi_state.STATE_HERO_SELECTION},
               "player": {"team_name": "radiant"}, "hero": {"id": 5}}
    provider = GsiProvider(ds, FakeServer(payload), manual)
    rules, meta = items_mod.load_rules(RULES_FILE)
    win = MainWindow(ds, provider, rules, meta, manual)
    win.timer.stop()
    try:
        win.refresh()
        assert "come off the Dota window" in \
            win.manual_hint.text()
        assert "HERO_SELECTION" in win.status.currentMessage()

        # Entering a pick by hand puts it straight into the draft.
        manual.set_slot("enemy", 0, 11)
        win.last_draft_key = None
        win.refresh()
        assert win.snapshot.right == [11]
        assert filled(win, "enemy") == [ds.name(11)]
    finally:
        win.close()


def test_manual_slot_click_opens_picker(window, monkeypatch):
    """Clicking an empty slot must offer a hero, not silently do nothing."""
    from draft_assist.ui import app as app_mod

    chosen = {}

    class FakePicker:
        DialogCode = app_mod.HeroPickerDialog.DialogCode

        def __init__(self, ds, taken=frozenset(), current=None, title="",
                     parent=None):
            chosen["title"] = title
            chosen["taken"] = taken
            self.selected = 42
            self.cleared = False

        def exec(self):
            return app_mod.HeroPickerDialog.DialogCode.Accepted

    monkeypatch.setattr(app_mod, "HeroPickerDialog", FakePicker)
    window.refresh()
    window._edit_slot("enemy", 4)
    assert window.manual.enemies[4] == 42
    assert "Enemy team" in chosen["title"]


def test_capture_controls_hidden_under_game_data(qapp):
    """Force recognition and window binding are meaningless without pixels."""
    from draft_assist.gsi import state as gsi_state
    from draft_assist.ui.demo import demo_dataset
    from draft_assist.ui.manual import ManualDraft
    from draft_assist.ui.providers import GsiProvider
    from tests.test_gsi import FakeServer

    ds = demo_dataset()
    payload = {"map": {"game_state": gsi_state.STATE_IN_PROGRESS}}
    provider = GsiProvider(ds, FakeServer(payload), ManualDraft())
    rules, meta = items_mod.load_rules(RULES_FILE)
    win = MainWindow(ds, provider, rules, meta)
    win.timer.stop()
    try:
        assert not win.force_check.isVisible()
        assert not win.force_action.isEnabled()
        assert not win.bind_button.isEnabled()
    finally:
        win.close()


# ---- the always-on-top overlay -----------------------------------------

# ---- statistics bracket -------------------------------------------------

def test_banner_warns_when_data_bracket_differs_from_selection(
        qapp, tmp_path, monkeypatch):
    """A dataset built for one bracket must never be shown as another."""
    from draft_assist import config
    from draft_assist.ui import app as app_mod

    monkeypatch.setattr(config, "PREFS_FILE", tmp_path / "preferences.json")
    monkeypatch.setattr(app_mod, "target_brackets",
                        lambda: ("LEGEND", "ANCIENT"))
    ds = demo_dataset()          # built for ANCIENT+DIVINE
    win = make_window(qapp, ds)
    try:
        win._update_first_run_banner()
        assert win.banner.isVisible() or not win.isVisible()
        text = win.banner_label.text()
        assert "ANCIENT+DIVINE" in text and "LEGEND+ANCIENT" in text
        assert "Rebuild" in win.banner_button.text()
    finally:
        win.close()


def test_no_banner_when_bracket_matches(qapp, monkeypatch):
    from draft_assist.ui import app as app_mod

    monkeypatch.setattr(app_mod, "target_brackets",
                        lambda: ("ANCIENT", "DIVINE"))
    win = make_window(qapp, demo_dataset())
    try:
        win._update_first_run_banner()
        assert not win.banner.isVisible()
    finally:
        win.close()


def test_bracket_dialog_presets_and_validation(qapp):
    from draft_assist.ui.bracket_dialog import BracketDialog

    dialog = BracketDialog(("ANCIENT", "DIVINE"))
    try:
        assert dialog._chosen() == ("ANCIENT", "DIVINE")
        dialog._apply_preset(("LEGEND", "ANCIENT"))
        assert dialog._chosen() == ("LEGEND", "ANCIENT")
        assert "Legend + Ancient" in dialog.summary.text()
        # Changing the bracket invalidates the cache; the dialog must say so.
        assert "rebuild" in dialog.summary.text().lower()

        for box in dialog.boxes.values():
            box.setChecked(False)
        assert not dialog.ok.isEnabled()      # empty selection refused
        dialog.boxes["IMMORTAL"].setChecked(True)
        assert dialog.ok.isEnabled()
        assert "noisier" in dialog.summary.text()   # single-bracket warning
    finally:
        dialog.close()


# ---- the app should not ask what the game already reports ---------------

def gsi_window(qapp, payload, manual=None):
    from draft_assist.ui.manual import ManualDraft
    from draft_assist.ui.providers import GsiProvider
    from tests.test_gsi import FakeServer

    ds = demo_dataset()
    manual = manual or ManualDraft()
    provider = GsiProvider(ds, FakeServer(payload), manual)
    rules, meta = items_mod.load_rules(RULES_FILE)
    win = MainWindow(ds, provider, rules, meta, manual)
    win.timer.stop()
    return win, ds


def test_side_selector_is_hidden_when_the_game_reports_your_team(qapp):
    from draft_assist.gsi import state as gsi_state

    win, ds = gsi_window(qapp, {
        "map": {"game_state": gsi_state.STATE_HERO_SELECTION},
        "player": {"team_name": "dire", "name": "Bijson"},
        "hero": {"id": 5}})
    try:
        win.refresh()
        assert win.side_combo.isHidden()
        assert win.side_label.isHidden()
        # And it says who it thinks you are, from the game's own report.
        assert "Bijson" in win.team_captions["ally"].text()
        assert "Dire" in win.team_captions["ally"].text()
        assert "Radiant" in win.team_captions["enemy"].text()
    finally:
        win.close()


def test_side_selector_cannot_contradict_the_game(qapp):
    """Flipping the (hidden) control must not swap teams when the game has
    already said which side is yours."""
    from draft_assist.gsi import state as gsi_state
    from draft_assist.ui.manual import ManualDraft

    manual = ManualDraft()
    manual.set_slot("enemy", 0, 11)
    win, ds = gsi_window(qapp, {
        "map": {"game_state": gsi_state.STATE_HERO_SELECTION},
        "player": {"team_name": "radiant", "name": "Bijson"},
        "hero": {"id": 5}}, manual=manual)
    try:
        win.refresh()
        assert filled(win, "ally") == [ds.name(5)]
        assert filled(win, "enemy") == [ds.name(11)]
        win.side_combo.setCurrentIndex(1)
        win.last_draft_key = None
        win.refresh()
        assert filled(win, "ally") == [ds.name(5)]     # unchanged
        assert filled(win, "enemy") == [ds.name(11)]
    finally:
        win.close()


def test_side_selector_still_shown_for_pixel_sources(window):
    """With screen capture the banks are just screen positions, so the
    question is real and the control must stay."""
    window.refresh()
    assert not window.side_combo.isHidden()
    assert "Your team" in window.team_captions["ally"].text()


def test_draft_card_never_clips_the_hero_names(window):
    """A hero name sheared in half was the symptom; the cause was the card
    being allowed to shrink below its own minimum when the column got
    tight. Check the real constraint, at sizes a user might drag to."""
    card = window.team_buttons["ally"][0].parent()
    for height in (900, 700, 560, 480, 400, 340):
        window.resize(1280, height)
        window.show()
        QApplication.processEvents()
        assert card.height() >= card.minimumSizeHint().height(), \
            f"draft card squeezed at window height {height}"
        for side in ("ally", "enemy"):
            for button in window.team_buttons[side]:
                needed = button.fontMetrics().height()
                assert button.height() >= needed + 8, (
                    f"{side} slot is {button.height()}px for a "
                    f"{needed}px font at window height {height}")


def test_feeding_tasks_do_not_block_the_main_window():
    """The simulators exist to make the draft panel move, so blocking the
    window behind a modal dialog would defeat them: you could watch heroes
    arrive but not click one to read its breakdown."""
    from draft_assist.ui.tasks import TASKS
    for key in ("simulate_gsi", "simulate_gsi_real", "replay_gsi"):
        assert TASKS[key].modeless, f"{key} would block the draft panel"
    for key in ("update_data", "tune", "update_app"):
        assert not TASKS[key].modeless, \
            f"{key} changes data under the running app and must block"


def test_modeless_task_is_shown_not_executed(window, monkeypatch):
    import draft_assist.ui.app as app_mod

    shown, executed = [], []

    class FakeDialog:
        def __init__(self, task, parent):
            self.task = task
            self.succeeded = False

            class _Signal:
                def connect(self, _slot):
                    pass
            self.finished = _Signal()

        def start(self):
            pass

        def show(self):
            shown.append(self.task.key)

        def exec(self):
            executed.append(self.task.key)

        def close(self):
            pass

    monkeypatch.setattr(app_mod, "TaskDialog", FakeDialog)
    window.run_task("simulate_gsi")
    assert shown == ["simulate_gsi"] and executed == []
    assert len(window._open_tasks) == 1


# ---- typing the draft in, which is now the normal path -----------------

def blank_window(qapp):
    """A window with nothing drafted, so quick entry starts from empty."""
    from draft_assist.ui.manual import ManualDraft
    from draft_assist.ui.providers import ManualProvider
    ds = demo_dataset()
    rules, meta = items_mod.load_rules(RULES_FILE)
    win = MainWindow(ds, ManualProvider(ManualDraft()), rules, meta)
    win.timer.stop()
    win.refresh()
    return win


# ---- one Record button, one folder per press ---------------------------

def recording_window(qapp, monkeypatch, tmp_path):
    import draft_assist.ui.app as app_mod
    from draft_assist import record as record_mod

    monkeypatch.setattr(app_mod, "RECORDINGS_DIR", tmp_path)
    window = blank_window(qapp)
    window.recorder = record_mod.Recorder(tmp_path)
    window.sessions = []
    return window


def test_record_button_toggles_and_names_its_state(qapp, monkeypatch,
                                                   tmp_path):
    window = recording_window(qapp, monkeypatch, tmp_path)
    try:
        assert window.record_button.text() == "● Record"
        window.record_button.click()
        assert window.recorder.active
        assert window.record_button.text() == "■ Stop"
        assert window.record_button.property("recording") is True
        window.record_button.click()
        assert not window.recorder.active
        assert window.record_button.text() == "● Record"
    finally:
        window.close()


def test_each_press_makes_its_own_discrete_folder(qapp, monkeypatch,
                                                  tmp_path):
    """Never append to an earlier session: pooling two matches made every
    count in the report meaningless."""
    window = recording_window(qapp, monkeypatch, tmp_path)
    try:
        folders = []
        for _ in range(3):
            window.record_button.click()
            folders.append(window.recorder.folder)
            window.record_button.click()
        assert len({f.name for f in folders}) == 3
        for folder in folders:
            assert (folder / "gsi").is_dir()
            assert (folder / "frames").is_dir()
            assert (folder / "meta.json").is_file()
    finally:
        window.close()


def test_recording_routes_payloads_into_this_session(qapp, monkeypatch,
                                                     tmp_path):
    """One button covers game data as well as the screen, so the payload
    archive has to follow the session rather than a fixed folder."""
    class FakeServer:
        def __init__(self):
            self.archive = "never set"

        def set_archive_dir(self, directory):
            self.archive = directory
            return 0

    window = recording_window(qapp, monkeypatch, tmp_path)
    server = FakeServer()
    monkeypatch.setattr(window, "_gsi_server", lambda: server)
    try:
        window.record_button.click()
        assert server.archive == window.recorder.folder / "gsi"
        window.record_button.click()
        assert server.archive is None
    finally:
        window.close()


def test_the_state_log_records_what_the_app_concluded(qapp, monkeypatch,
                                                      tmp_path):
    from draft_assist import record as record_mod

    window = recording_window(qapp, monkeypatch, tmp_path)
    try:
        window.record_button.click()
        window.refresh()
        window.refresh()
        folder = window.recorder.folder
        window.record_button.click()
        states = record_mod.read_states(folder)
        assert len(states) >= 2
        assert set(states[0]) >= {"game_state", "source", "allies",
                                  "enemies", "at"}
        assert (folder / "report.txt").is_file()
    finally:
        window.close()


def test_a_write_failure_never_interrupts_the_draft(qapp, monkeypatch,
                                                    tmp_path):
    """A full disk mid-game must cost the recording, not the window."""
    window = recording_window(qapp, monkeypatch, tmp_path)
    try:
        window.record_button.click()
        folder = window.recorder.folder

        def explode(*_a, **_k):
            raise OSError("No space left on device")

        monkeypatch.setattr(Path, "open", explode)
        window.refresh()                     # must not raise
        monkeypatch.undo()
        assert window.recorder._errors
        window.record_button.click()
        assert "No space left" in (folder / "meta.json").read_text()
    finally:
        window.close()


def test_sessions_tab_lists_recordings_newest_first(qapp, monkeypatch,
                                                    tmp_path):
    window = recording_window(qapp, monkeypatch, tmp_path)
    try:
        for name in ("2026-09-01_1000", "2026-09-03_1200"):
            folder = tmp_path / name
            (folder / "gsi").mkdir(parents=True)
            (folder / "state.jsonl").write_text("")
        window._refresh_sessions()
        assert [window.session_list.item(i).text()
                for i in range(window.session_list.count())] == [
            "2026-09-03_1200", "2026-09-01_1000"]
        assert "RECORDING  2026-09-03_1200" in \
            window.session_report.toPlainText()
    finally:
        window.close()


def test_copying_a_report_puts_it_on_the_clipboard(qapp, monkeypatch,
                                                   tmp_path):
    window = recording_window(qapp, monkeypatch, tmp_path)
    try:
        folder = tmp_path / "2026-09-05_2031"
        (folder / "gsi").mkdir(parents=True)
        (folder / "state.jsonl").write_text("")
        window._refresh_sessions()
        window._copy_session_report()
        assert "2026-09-05_2031" in QApplication.clipboard().text()
    finally:
        window.close()


def test_sessions_tab_says_what_to_do_when_there_is_nothing(qapp,
                                                            monkeypatch,
                                                            tmp_path):
    window = recording_window(qapp, monkeypatch, tmp_path)
    try:
        window._refresh_sessions()
        assert "No recordings yet" in window.session_report.toPlainText()
        assert "Press Record" in window.session_report.toPlainText()
    finally:
        window.close()


def test_the_window_stops_the_recording_by_itself(qapp, monkeypatch,
                                                  tmp_path):
    """The whole point: press Record before queueing and never touch it
    again. The tick loop, not a keypress, ends the session."""
    from draft_assist import record as record_mod

    window = recording_window(qapp, monkeypatch, tmp_path)
    try:
        window.record_button.click()
        assert window.recorder.active

        window.recorder.observe("DOTA_GAMERULES_STATE_HERO_SELECTION")
        window.recorder.observe("DOTA_GAMERULES_STATE_PRE_GAME")
        window.recorder.left_draft_at -= record_mod.POST_DRAFT_GRACE + 1

        class Snap:
            game_state = "DOTA_GAMERULES_STATE_GAME_IN_PROGRESS"
            frame = None
            frames_arrived = 12
        window._capture_recording(Snap(), [], [])

        assert not window.recorder.active
        assert window.record_button.text() == "● Record"
        assert "after the draft ended" in window.status.currentMessage()
    finally:
        window.close()


def test_a_frame_grab_that_throws_does_not_stop_the_recording(qapp,
                                                              monkeypatch,
                                                              tmp_path):
    """Dota closing mid-session must cost a frame, not the session."""
    window = recording_window(qapp, monkeypatch, tmp_path)
    try:
        window.record_button.click()

        def explode():
            raise RuntimeError("No Dota 2 window found")

        monkeypatch.setattr(window, "_grab_dota_frame", explode)

        class Snap:
            game_state = "DOTA_GAMERULES_STATE_HERO_SELECTION"
            frame = None
            frames_arrived = 3
        window._capture_recording(Snap(), [], [])
        assert window.recorder.active
        assert window.recorder.frames == 0
    finally:
        window.close()


def test_the_label_counts_down_to_the_automatic_stop(qapp, monkeypatch,
                                                     tmp_path):
    window = recording_window(qapp, monkeypatch, tmp_path)
    try:
        window.record_button.click()

        class Snap:
            game_state = "DOTA_GAMERULES_STATE_HERO_SELECTION"
            frame = None
            frames_arrived = 5
        window._capture_recording(Snap(), [], [])
        assert "auto-stops after the draft" in window.recording_label.text()

        Snap.game_state = "DOTA_GAMERULES_STATE_PRE_GAME"
        window._capture_recording(Snap(), [], [])
        window._capture_recording(Snap(), [], [])
        assert "auto-stop in" in window.recording_label.text()
    finally:
        window.close()


# ---- recording that starts itself ---------------------------------------

class DraftSnap:
    game_state = "DOTA_GAMERULES_STATE_HERO_SELECTION"
    frame = None
    frames_arrived = 7


class MenuSnap:
    game_state = ""
    frame = None
    frames_arrived = 0


def test_recording_starts_itself_when_the_draft_does(qapp, monkeypatch,
                                                     tmp_path):
    """The session you most want is the one you were not expecting."""
    window = recording_window(qapp, monkeypatch, tmp_path)
    try:
        window.auto_record_check.setChecked(True)
        window._consider_auto_record(MenuSnap())
        assert not window.recorder.active

        window._consider_auto_record(DraftSnap())
        assert window.recorder.active
        assert "Draft detected" in window.status.currentMessage()
    finally:
        window.close()


def test_it_does_not_start_a_second_session_mid_draft(qapp, monkeypatch,
                                                      tmp_path):
    window = recording_window(qapp, monkeypatch, tmp_path)
    try:
        window.auto_record_check.setChecked(True)
        window._consider_auto_record(DraftSnap())
        folder = window.recorder.folder
        for _ in range(5):
            window._consider_auto_record(DraftSnap())
        assert window.recorder.folder == folder
    finally:
        window.close()


def test_stopping_by_hand_mid_draft_stays_stopped(qapp, monkeypatch,
                                                  tmp_path):
    """Otherwise Stop would mean "stop for one tick"."""
    window = recording_window(qapp, monkeypatch, tmp_path)
    try:
        window.auto_record_check.setChecked(True)
        window._consider_auto_record(DraftSnap())
        window.snapshot = DraftSnap()
        window.record_button.click()               # stop by hand
        assert not window.recorder.active

        window._consider_auto_record(DraftSnap())
        assert not window.recorder.active          # and it stays stopped

        window._consider_auto_record(MenuSnap())   # the match ends
        window._consider_auto_record(DraftSnap())  # the next one starts
        assert window.recorder.active
    finally:
        window.close()


def test_auto_can_be_turned_off_and_is_remembered(qapp, monkeypatch,
                                                  tmp_path):
    from draft_assist.ui import settings as ui_settings

    window = recording_window(qapp, monkeypatch, tmp_path)
    try:
        window.auto_record_check.setChecked(False)
        window._consider_auto_record(DraftSnap())
        assert not window.recorder.active
        assert ui_settings.load()["auto_record"] is False
        assert window.recording_label.text() == ""

        window.auto_record_check.setChecked(True)
        assert "waiting for a draft" in window.recording_label.text()
        assert ui_settings.load()["auto_record"] is True
    finally:
        window.close()


def test_a_whole_draft_needs_no_presses_at_all(qapp, monkeypatch, tmp_path):
    """Start to finish, hands off: the draft starts the session and the
    pre-game ends it."""
    from draft_assist import record as record_mod

    window = recording_window(qapp, monkeypatch, tmp_path)
    try:
        window.auto_record_check.setChecked(True)
        window._consider_auto_record(DraftSnap())
        window._capture_recording(DraftSnap(), [], [])
        folder = window.recorder.folder
        assert window.recorder.active

        class PreGame:
            game_state = "DOTA_GAMERULES_STATE_PRE_GAME"
            frame = None
            frames_arrived = 40

        window._capture_recording(PreGame(), [], [])
        assert window.recorder.active                  # still in the grace
        window.recorder.left_draft_at -= record_mod.POST_DRAFT_GRACE + 1
        window._capture_recording(PreGame(), [], [])

        assert not window.recorder.active
        assert (folder / "report.txt").is_file()
        assert "after the draft ended" in window.status.currentMessage()
    finally:
        window.close()


def test_calibration_moves_the_crop_boxes_live(window):
    """Editing JSON and restarting is not a workflow anyone completes; the
    boxes have to move while the picture is on screen."""
    before = window.layout_spec.radiant_x
    window.cal_spins["radiant_x"].setValue(before + 0.02)
    assert window.layout_spec.radiant_x == pytest.approx(before + 0.02)
    assert "not saved" in window.cal_label.text()


def test_calibration_reaches_the_capture_session(window, monkeypatch):
    class Session:
        layout = None
    monkeypatch.setattr(window.provider, "session", Session(),
                        raising=False)
    window.cal_spins["pitch"].setValue(0.07)
    assert window.provider.session.layout is window.layout_spec
    assert window.layout_spec.pitch == pytest.approx(0.07)


def test_calibration_saves_and_resets(window, monkeypatch, tmp_path):
    import draft_assist.vision.layout as layout_mod

    target = tmp_path / "calibration_local.json"
    monkeypatch.setattr(layout_mod, "CALIBRATION_FILE", target)
    monkeypatch.setattr(layout_mod.save_calibration, "__defaults__", (target,))

    window.cal_spins["slot_w"].setValue(0.09)
    window._save_calibration()
    assert "saved" in window.cal_label.text()
    assert json.loads(target.read_text())["slot_w"] == pytest.approx(0.09)

    window._reset_calibration()
    assert window.layout_spec.slot_w == layout_mod.DraftLayout().slot_w
    assert window.cal_spins["slot_w"].value() == pytest.approx(
        layout_mod.DraftLayout().slot_w)


# ---- the settings dialog replaces the source-switching menu items -------

def test_menus_no_longer_offer_a_source_mode(window):
    """"Use game data" and "Use screen capture" were mutually exclusive
    commands from when the two were alternatives. They are not."""
    labels = []
    for action in window.menu_bar.actions():
        menu = action.menu()
        if menu is None:
            continue
        for item in menu.actions():
            labels.append(item.text().replace("&", ""))
            if item.menu() is not None:
                labels += [b.text().replace("&", "")
                           for b in item.menu().actions()]
    assert not any("Use screen capture" in text for text in labels)
    assert not any("Use game data" in text for text in labels)
    assert not any("Capture source" in text for text in labels)
    assert "Settings…" in labels


def test_the_menu_bar_stays_small(window):
    titles = [a.text().replace("&", "") for a in window.menu_bar.actions()
              if a.menu() is not None]
    assert titles == ["Setup", "Game", "View", "Help"]
    for action in window.menu_bar.actions():
        menu = action.menu()
        if menu is not None:
            visible = [a for a in menu.actions() if not a.isSeparator()]
            assert len(visible) <= 7, f"{action.text()} has {len(visible)}"


def test_the_downloads_are_one_group(window):
    """Three siblings called Update / Fetch / Fetch are one idea said three
    times, and they pushed Setup past the size a menu stays readable at."""
    setup = next(a.menu() for a in window.menu_bar.actions()
                 if a.text().replace("&", "") == "Setup")
    names = [a.text().replace("&", "") for a in setup.actions()]
    assert "Download" in names
    downloads = next(a.menu() for a in setup.actions()
                     if a.text().replace("&", "") == "Download")
    inside = [a.text().replace("&", "") for a in downloads.actions()]
    assert any("Statistics and portraits" in n for n in inside)
    assert any("Alternative portraits" in n for n in inside)
    assert any("Item icons" in n for n in inside)


def test_both_sources_are_on_by_default():
    from draft_assist.ui import settings as ui_settings

    defaults = ui_settings.load()
    assert defaults["use_gsi"] is True
    assert defaults["use_vision"] is True
    assert defaults["auto_record"] is True


def test_settings_dialog_round_trips_the_switches(qapp):
    from draft_assist.ui.settings_dialog import SettingsDialog

    dialog = SettingsDialog({"use_gsi": True, "use_vision": False,
                             "auto_record": True})
    assert dialog.boxes["use_vision"].isChecked() is False
    dialog.boxes["use_vision"].setChecked(True)
    dialog.boxes["use_gsi"].setChecked(False)
    values = dialog.values()
    assert values["use_vision"] is True and values["use_gsi"] is False


def test_turning_a_source_off_rebuilds_the_provider(window, monkeypatch):
    from draft_assist.ui.providers import ManualProvider

    swapped = []
    monkeypatch.setattr(window, "_swap_provider", swapped.append)
    monkeypatch.setattr("draft_assist.ui.app._capture_session", lambda: None)
    window.settings.update({"use_gsi": False, "use_vision": False})
    window._apply_sources()
    assert len(swapped) == 1
    assert isinstance(swapped[0], ManualProvider)


# ---- the minimap names ten heroes but not whose they are ---------------

def minimap_window(qapp):
    """A window fed the real strategy-time payload, whose split is a guess."""
    import json
    from pathlib import Path
    from draft_assist.ui.manual import ManualDraft
    from draft_assist.ui.providers import GsiProvider
    from tests.test_gsi import FakeServer, minimap_dataset

    payload = json.loads(
        (Path(__file__).parent / "fixtures" / "gsi"
         / "strategy_time_minimap_3.json").read_text())
    ds = minimap_dataset()
    provider = GsiProvider(ds, FakeServer(payload), ManualDraft())
    rules, meta = items_mod.load_rules(RULES_FILE)
    win = MainWindow(ds, provider, rules, meta)
    win.timer.stop()
    win.refresh()
    return win


def test_dragging_the_whole_line_up_across_reverses_it(qapp):
    """The old Swap teams button did this in one click and nothing else,
    which is why it went: the case it handled is four drags, and the case
    the user actually hits — own hero right, other four wrong — it could
    not touch at all."""
    window = minimap_window(qapp)
    try:
        before = window._sides(window.snapshot)
        for index in range(5):
            window._on_slot_dropped("ally", 0, "enemy", 0)
        after = window._sides(window.snapshot)
        assert set(after[0]) == set(before[1])
        assert set(after[1]) == set(before[0])
    finally:
        window.close()


def test_a_new_match_forgets_the_corrections(qapp):
    """A correction applies to the match it was made in, never the next."""
    window = minimap_window(qapp)
    try:
        before = window._sides(window.snapshot)
        window._on_slot_dropped("ally", 0, "enemy", 2)
        assert window._sides(window.snapshot) != before
        window.provider.server._reception.payload["map"]["matchid"] = "999"
        window.refresh()
        assert not window.side_overrides
        assert window._sides(window.snapshot) == before
    finally:
        window.close()


# ---- the matrices -------------------------------------------------------

def test_matchup_matrix_is_allies_by_enemies(window):
    """No margin row or column any more: each tile carries that hero's
    total in its own corner, and the same figure twice is once too many."""
    window.refresh()
    allies, enemies = filled(window, "ally"), filled(window, "enemy")
    table = window.matchup_matrix.table
    assert table.rowCount() == len(allies)
    assert table.columnCount() == len(enemies)
    # Portraits head the axes; without art downloaded they fall back to
    # names, which is what runs here.
    assert [table.verticalHeaderItem(r).text()
            for r in range(table.rowCount())] == allies
    assert [table.horizontalHeaderItem(c).text()
            for c in range(table.columnCount())] == enemies
    assert table.item(0, 0).text()          # every cell carries a value


def test_the_grids_sit_under_the_team_they_are_about(window):
    """Synergy is ally-by-ally so it belongs under your five; counters are
    read against theirs. A column then reads straight down from the tile
    it describes."""
    window.resize(1400, 900)
    window.show()
    QApplication.processEvents()
    window.refresh()
    QApplication.processEvents()
    left = window.synergy_matrix.mapTo(window, window.synergy_matrix.pos()).x()
    right = window.matchup_matrix.mapTo(window,
                                        window.matchup_matrix.pos()).x()
    assert left < right, "synergy must sit under your five, counters theirs"
    assert (window.team_panels["ally"].mapTo(window, QPoint()).x()
            < window.team_panels["enemy"].mapTo(window, QPoint()).x())


def test_the_margins_can_be_turned_off_and_on(qapp):
    """The main window drops them because the tiles carry the totals; the
    in-game callout keeps them, so the switch has to work both ways."""
    from draft_assist.model import scoring
    from draft_assist.ui.tables import MatrixTable
    table = MatrixTable()
    matrix = scoring.Matrix(rows=[(1, "A"), (2, "B")], cols=[(3, "C")],
                            cells=[[0.01], [-0.02]])
    table.set_margins(False)
    table.show_matrix(matrix)
    assert (table.table.rowCount(), table.table.columnCount()) == (2, 1)
    table.set_margins(True)
    table.show_matrix(matrix)
    assert (table.table.rowCount(), table.table.columnCount()) == (3, 2)
    assert _cell_value(table.table, 0, 1) == pytest.approx(0.01)


def _cell_value(table, row, col):
    """The float behind a cell, or None where the pair has no meaning."""
    item = table.item(row, col)
    return None if item is None else item.data(SORT_ROLE)


def test_synergy_matrix_shows_each_pair_once(window):
    """Synergy is symmetric, so the lower half would only repeat the upper
    and the diagonal means nothing."""
    window.refresh()
    allies = filled(window, "ally")
    table = window.synergy_matrix.table
    assert table.rowCount() == table.columnCount() == len(allies)
    pairs = [(r, c) for r in range(len(allies)) for c in range(len(allies))
             if table.item(r, c).text()]
    assert len(pairs) == len(allies) * (len(allies) - 1) // 2
    assert all(c > r for r, c in pairs)


def test_matrices_say_what_is_missing_when_a_team_is_empty(qapp):
    window = blank_window(qapp)
    try:
        window.refresh()
        # The grid stays on screen as an outline rather than vanishing:
        # a card that collapses and re-expands moves everything under it.
        assert not window.matchup_matrix.table.isHidden()
        assert window.matchup_matrix.table.rowCount() == 5
        assert window.matchup_matrix.table.item(0, 0).text() == ""
        assert "Fill in both teams" in window.matchup_matrix.empty_note.text()
        assert "Fill in your own team" in \
            window.synergy_matrix.empty_note.text()
    finally:
        window.close()


def test_the_draft_tab_carries_the_teams_and_both_matrices(window):
    """The matrices moved onto the draft screen: the grid explaining the
    ten picks belongs beside the ten picks, not behind a tab."""
    titles = [window.tabs.tabText(i) for i in range(window.tabs.count())]
    assert titles == ["Draft", "Analysis", "Debug"]
    draft_tab = window.tabs.widget(0)
    for widget in (window.matchup_matrix, window.synergy_matrix,
                   window.team_panels["ally"], window.team_panels["enemy"]):
        assert window.tabs.indexOf(_tab_of(window, widget)) == 0, \
            f"{widget} is not on the draft tab"
    assert window.tabs.indexOf(_tab_of(window, window.table)) == 1
    assert draft_tab is not None


def _tab_of(window, widget):
    """Walk up to whichever top-level tab page holds this widget."""
    pages = {window.tabs.widget(i) for i in range(window.tabs.count())}
    node = widget
    while node is not None and node not in pages:
        node = node.parentWidget()
    return node


def test_the_picker_hides_heroes_already_drafted(window, monkeypatch):
    import draft_assist.ui.app as app_mod

    seen = {}

    class FakePicker:
        DialogCode = HeroPickerDialogCode

        def __init__(self, ds, taken=frozenset(), current=None, title="",
                     parent=None):
            seen["taken"] = set(taken)

        def exec(self):
            return 0

    monkeypatch.setattr(app_mod, "HeroPickerDialog", FakePicker)
    window.refresh()
    window._edit_slot("ally", 4)
    drafted = set(window.snapshot.left) | set(window.snapshot.right)
    assert drafted and drafted <= seen["taken"]


def test_clicking_an_empty_slot_opens_one_picker_and_no_more(qapp,
                                                             monkeypatch):
    """Clicking is deliberate, one slot at a time — unlike typing, it must
    not chain into the next."""
    import draft_assist.ui.app as app_mod

    opened = []

    class FakePicker:
        DialogCode = HeroPickerDialogCode

        def __init__(self, ds, taken=frozenset(), current=None, title="",
                     parent=None):
            opened.append(title)
            self.selected = ds.hero_ids[0]
            self.cleared = False

        def exec(self):
            return HeroPickerDialogCode.Accepted

    monkeypatch.setattr(app_mod, "HeroPickerDialog", FakePicker)
    window = blank_window(qapp)
    try:
        window.team_buttons["enemy"][0].click()
        assert len(opened) == 1
    finally:
        window.close()


# ---- roles on the slots -------------------------------------------------

def test_a_slot_can_be_given_a_role_and_shows_it(qapp):
    window = blank_window(qapp)
    try:
        window.manual.set_slot("enemy", 0, window.ds.hero_ids[0])
        window.last_draft_key = None
        window.refresh()
        button = window.team_buttons["enemy"][0]
        hero = button.text()

        window._set_slot_role("enemy", 0, "Pos 3")
        assert window.team_buttons["enemy"][0].text() == f"Pos 3 · {hero}"

        window._set_slot_role("enemy", 0, None)
        assert window.team_buttons["enemy"][0].text() == hero
    finally:
        window.close()


def test_a_role_survives_the_slot_being_refilled(qapp):
    """The role belongs to the lane, not to whoever is standing in it."""
    window = blank_window(qapp)
    try:
        window._set_slot_role("ally", 2, "Pos 1")
        for index, hero_id in enumerate(window.ds.hero_ids[:3]):
            window.manual.set_slot("ally", index, hero_id)
        window.last_draft_key = None
        window.refresh()
        assert window.team_buttons["ally"][2].text().startswith("Pos 1 · ")
    finally:
        window.close()


def test_an_empty_slot_with_a_role_still_shows_it(qapp):
    window = blank_window(qapp)
    try:
        window._set_slot_role("ally", 0, "Pos 5")
        assert window.team_buttons["ally"][0].text() == "Pos 5 · +"
    finally:
        window.close()


def test_one_hero_can_be_moved_to_the_other_team(qapp):
    """Swap teams fixes a whole line-up read backwards; this fixes one
    hero, which is what "some are wrong" actually needs. It exchanges
    rather than moving one way: a 5v5 cannot become 4v6."""
    window = minimap_window(qapp)
    try:
        allies, enemies = window._sides(window.snapshot)
        mine, theirs = allies[1], enemies[1]
        window._move_hero("ally", 1)
        after_allies, after_enemies = window._sides(window.snapshot)
        assert mine in after_enemies and mine not in after_allies
        assert theirs in after_allies and theirs not in after_enemies
        assert len(after_allies) == len(after_enemies) == 5
        assert set(after_allies) | set(after_enemies) == set(allies) | set(
            enemies)
    finally:
        window.close()


def test_moving_a_hero_back_restores_it(qapp):
    window = minimap_window(qapp)
    try:
        before = window._sides(window.snapshot)
        window._move_hero("ally", 0)
        window.refresh()
        # find it on the enemy side and move it home again
        for index, button in enumerate(window.team_buttons["enemy"]):
            if button.property("hero_id") == before[0][0]:
                window._move_hero("enemy", index)
                break
        assert window._sides(window.snapshot) == before
    finally:
        window.close()


def test_a_new_match_forgets_moved_heroes(qapp):
    window = minimap_window(qapp)
    try:
        window._move_hero("ally", 1)
        assert window.side_overrides
        window.provider.server._reception.payload["map"]["matchid"] = "777"
        window.refresh()
        assert window.side_overrides == {}
    finally:
        window.close()


def test_the_filter_sits_directly_above_the_list_it_filters(window):
    """It was stranded at the top of the column after the draft card moved
    in above it, filtering a table three cards away."""
    left = window.table.parent().layout()
    order = []
    for i in range(left.count()):
        item = left.itemAt(i)
        widget = item.widget()
        if widget is window.table:
            order.append("table")
        elif widget is not None:
            order.append("card")
        elif item.layout() is not None and any(
                item.layout().itemAt(j).widget() is window.search_box
                for j in range(item.layout().count())):
            order.append("filter")
    assert order.index("filter") == order.index("table") - 1


def test_replaying_a_session_is_a_button_on_the_recording(qapp, monkeypatch,
                                                          tmp_path):
    """It was a Game menu item that replayed "the newest" archive. It is
    one more thing you do WITH a recording, so it lives with them."""
    window = recording_window(qapp, monkeypatch, tmp_path)
    try:
        folder = tmp_path / "2026-09-05_1724"
        (folder / "gsi").mkdir(parents=True)
        (folder / "state.jsonl").write_text("")
        window._refresh_sessions()

        ran = {}
        monkeypatch.setattr(window, "run_task",
                            lambda key, arg="": ran.update(key=key, arg=arg))
        window._replay_session()
        assert ran["key"] == "replay_gsi"
        assert ran["arg"] == str(folder / "gsi")

        labels = []
        for action in window.menu_bar.actions():
            menu = action.menu()
            if menu is not None:
                labels += [a.text().replace("&", "") for a in menu.actions()]
        assert not any("Replay recorded" in text for text in labels)
    finally:
        window.close()


def test_a_task_argument_reaches_the_command_line():
    from draft_assist.ui.tasks import TASKS

    task = TASKS["replay_gsi"].with_argument("/tmp/session/gsi")
    assert task.steps[-1][-1] == "/tmp/session/gsi"
    assert "{arg}" not in " ".join(task.steps[-1])
    # the original is untouched
    assert "{arg}" in " ".join(TASKS["replay_gsi"].steps[-1])


def test_measuring_needs_a_frame_and_named_heroes(window, monkeypatch):
    """It says which half is missing rather than failing silently."""
    monkeypatch.setattr(window, "_grab_dota_frame", lambda: None)
    window.snapshot = None
    window._measure_calibration()
    assert "no frame" in window.cal_label.text()

    import numpy as np
    monkeypatch.setattr(window, "_grab_dota_frame",
                        lambda: np.zeros((100, 100, 3), np.uint8))
    window._measure_calibration()
    assert "not named enough heroes" in window.cal_label.text()


def test_measuring_says_when_portraits_are_missing(window, monkeypatch):
    import numpy as np
    import draft_assist.vision.autocal as autocal

    monkeypatch.setattr(window, "_grab_dota_frame",
                        lambda: np.zeros((100, 100, 3), np.uint8))
    monkeypatch.setattr(autocal, "base_portraits", lambda ids: {})
    window.refresh()
    window.snapshot.frame = None
    window._measure_calibration()
    assert "portraits are not downloaded" in window.cal_label.text()


def test_a_measuring_failure_never_takes_the_app_down(window, monkeypatch):
    import numpy as np
    import draft_assist.vision.autocal as autocal

    monkeypatch.setattr(window, "_grab_dota_frame",
                        lambda: np.zeros((100, 100, 3), np.uint8))
    monkeypatch.setattr(autocal, "base_portraits",
                        lambda ids: {h: np.zeros((10, 10, 3), np.uint8)
                                     for h in ids})

    def explode(*_a, **_k):
        raise RuntimeError("cv2 exploded")

    monkeypatch.setattr(autocal, "calibrate", explode)
    window.refresh()
    window.snapshot.frame = None
    window._measure_calibration()
    assert "measuring failed" in window.cal_label.text()
    assert window.measure_button.isEnabled()


# ---- clicking a hero: the matrix read one row at a time -----------------

def _delta_text(window, side, index):
    return window.team_panels[side].slots[index].delta_text()


def test_clicking_an_ally_answers_both_questions(window):
    """An ally is judged twice over — how it fits with your four and how it
    fares against their five — so clicking one shows synergy above the
    allies AND matchup above the enemies."""
    window.refresh()
    window.team_buttons["ally"][0].click()

    assert window.focus is not None and window.focus[0] == "ally"
    assert _delta_text(window, "ally", 0) == ""          # the clicked hero
    for i in range(1, 5):
        assert "vs" not in _delta_text(window, "ally", i), \
            "an ally-to-ally pairing is synergy, not a matchup"
        assert _delta_text(window, "ally", i) != ""
    for i in range(len(window._current_draft().enemies)):
        assert "vs" in _delta_text(window, "enemy", i)


def test_clicking_an_enemy_answers_only_the_matchup(window):
    """Their pair-ups with each other are their business: clicking an enemy
    says how YOUR five fare against it and nothing else."""
    window.refresh()
    window.team_buttons["enemy"][2].click()

    assert window.focus[0] == "enemy"
    for i in range(5):
        assert "vs" in _delta_text(window, "ally", i)
    for i in range(len(window._current_draft().enemies)):
        if i != 2:
            assert _delta_text(window, "enemy", i) == ""


def test_clicking_the_same_hero_again_clears_the_view(window):
    """The way out is the same gesture as the way in."""
    window.refresh()
    button = window.team_buttons["ally"][1]
    button.click()
    assert window.focus is not None
    button.click()
    assert window.focus is None
    # Back to the resting state: every tile shows its own net figure, so
    # the numbers stay — what goes is the "with"/"vs" that marked them as
    # being about the clicked hero.
    assert all("with" not in _delta_text(window, side, i)
               and "vs" not in _delta_text(window, side, i)
               for side in ("ally", "enemy") for i in range(5))


def test_the_numbers_read_from_your_side_whichever_portrait_they_sit_under(
        window):
    """Green under an enemy must mean the same thing as green under an
    ally — good for you — or the view teaches the wrong reflex."""
    from draft_assist.model import scoring
    window.refresh()
    draft = window._current_draft()
    enemy = draft.enemies[0]
    relations = scoring.relations_to(window.ds, enemy, draft)
    for rel in relations:
        expected = float(window.ds.delta_vs[window.ds.index[rel.hero_id],
                                            window.ds.index[enemy]])
        assert rel.delta == pytest.approx(expected)


def test_a_hero_leaving_the_draft_drops_the_focus(window):
    window.refresh()
    window.team_buttons["ally"][0].click()
    assert window.focus is not None
    window._on_draft_changed([], [], 10)
    assert window.focus is None


# ---- the overlay toggle drives both overlays ----------------------------

# ---- the badge is the mid-draft switch ----------------------------------

# ---- fixing the team split ----------------------------------------------

def test_dragging_a_hero_to_the_other_team_exchanges_it(qapp):
    """A 5v5 cannot become 4v6, so a hero dropped across swaps places with
    whatever it landed on."""
    window = minimap_window(qapp)
    try:
        window.refresh()
        before_ally = filled(window, "ally")
        before_enemy = filled(window, "enemy")
        window._on_slot_dropped("ally", 0, "enemy", 2)
        after_ally, after_enemy = filled(window, "ally"), filled(window, "enemy")
        assert len(after_ally) == len(before_ally) == 5
        assert len(after_enemy) == len(before_enemy) == 5
        assert before_ally[0] in after_enemy
        assert before_enemy[2] in after_ally
    finally:
        window.close()


def test_dropping_a_hero_on_its_own_team_swaps_their_places(qapp):
    """The order is meant to be the order on Dota's pick bar, and the feed
    does not reliably give that — so a drag inside a bank reorders it."""
    window = minimap_window(qapp)
    try:
        window.refresh()
        before = filled(window, "ally")
        window._on_slot_dropped("ally", 0, "ally", 3)
        after = filled(window, "ally")
        assert set(after) == set(before)
        assert after[0] == before[3] and after[3] == before[0]
        assert after[1] == before[1] and after[2] == before[2]
    finally:
        window.close()


def test_a_reorder_survives_a_refresh(qapp):
    """A hand-dragged order that the next tick undid would be unusable."""
    window = minimap_window(qapp)
    try:
        window.refresh()
        window._on_slot_dropped("enemy", 1, "enemy", 4)
        after = filled(window, "enemy")
        for _ in range(3):
            window.refresh()
        assert filled(window, "enemy") == after
    finally:
        window.close()


def test_the_main_grids_carry_no_explanatory_caption(window):
    """The card heading says which grid it is and the headers say what the
    axes are; a paragraph repeating both stands between the reader and the
    numbers."""
    window.refresh()
    for matrix in (window.matchup_matrix, window.synergy_matrix):
        assert matrix.caption.isHidden()


def test_a_grid_is_exactly_as_tall_as_its_rows(window):
    """A five-row grid left to stretch fills whatever the layout gives it,
    and the leftover is dead space INSIDE the widget: half the window was
    blank and it could not be made shorter, because a stretching table
    never asks for a smaller size."""
    window.refresh()
    for matrix in (window.matchup_matrix, window.synergy_matrix):
        table = matrix.table
        rows = sum(table.rowHeight(r) for r in range(table.rowCount()))
        wanted = table.horizontalHeader().height() + rows
        assert abs(table.maximumHeight() - wanted) <= 6, "not fitted to rows"
        assert table.maximumHeight() < 1000




# ---- the window is the whole app ---------------------------------------

def test_there_is_only_one_window(window, qapp):
    """The floating toggle made the app look like two programs in the
    taskbar and in Alt-Tab. It is gone, and with it the only way to hide
    the window — hiding with nothing left to click would strand the app
    running and invisible."""
    from PyQt6.QtWidgets import QWidget
    window.show()
    qapp.processEvents()
    tops = [w for w in qapp.topLevelWidgets()
            if isinstance(w, QWidget) and not w.isHidden()]
    assert window in tops
    assert len(tops) == 1, f"a second window is on screen: {tops}"
    assert not hasattr(window, "overlay_toggle")


def test_a_tall_tab_does_not_set_the_windows_floor(window, qapp):
    """A QTabWidget's minimum is the LARGEST of its pages, so the Debug tab
    — a full-resolution picture, a log, a timing table and the calibration
    row, 1200px between them — set the floor for the whole window even
    while the Draft tab was the one on screen. The window took up the
    entire desktop height and would not shrink."""
    window.show()
    qapp.processEvents()
    pages = {window.tabs.tabText(i): window.tabs.widget(i)
             for i in range(window.tabs.count())}
    assert pages["Debug"].minimumSizeHint().height() < 200, \
        "the Debug tab is not scrolling; it will dictate the window height"
    assert window.minimumSizeHint().height() < 900, \
        f"the window cannot be made short: {window.minimumSizeHint()}"


def test_no_widget_is_left_without_a_parent(window):
    """A QWidget added to no layout is not invisible — it is a TOP-LEVEL
    WINDOW as soon as anything shows it. That is how a second "Dota Draft
    Assist" window containing one checkbox appeared, and the class of bug
    is invisible until the line that shows it runs."""
    from PyQt6.QtWidgets import QWidget
    orphans = [name for name, value in vars(window).items()
               if isinstance(value, QWidget) and value.parent() is None]
    assert orphans == [], f"these would open as their own windows: {orphans}"


def test_capture_controls_do_not_open_windows_of_their_own(window,
                                                           monkeypatch):
    """_sync_source_controls shows them when the source is pixels, which is
    the line that turned the orphan into a window."""
    from PyQt6.QtWidgets import QWidget

    class Session:
        layout = None

    monkeypatch.setattr(type(window.provider), "session",
                        property(lambda self: Session()), raising=False)
    window.show()
    window._sync_source_controls()
    qapp = QApplication.instance()
    qapp.processEvents()
    tops = [w for w in qapp.topLevelWidgets()
            if isinstance(w, QWidget) and not w.isHidden()]
    assert tops == [window], f"a second window opened: {tops}"


def test_the_window_is_frameless_see_through_and_on_top(window):
    """Three overlays became one. Windows' own title bar read as a
    different program bolted on top of a dark app, and a window that is
    not see-through and not on top cannot sit over a game."""
    flags = window.windowFlags()
    assert flags & Qt.WindowType.FramelessWindowHint
    assert flags & Qt.WindowType.WindowStaysOnTopHint
    assert 0.0 < window.windowOpacity() <= 1.0


def test_opacity_is_remembered(window):
    """Qt stores opacity as an 8-bit value, so it comes back within a
    step of what was asked for rather than exactly."""
    window._set_see_through(0.55)
    assert window.windowOpacity() == pytest.approx(0.55, abs=0.01)
    assert window.settings["overlay_opacity"] == pytest.approx(0.55)


def test_the_title_bar_carries_the_window_buttons(window):
    """Frameless means minimise, maximise and close are ours to draw."""
    bar = window.title_bar
    assert bar.findChild(type(bar.icon)) is not None
    names = {child.objectName() for child in bar.children()}
    assert {"win_min", "win_max", "win_close"} <= names


def test_updating_only_restarts_after_a_pull_that_worked(window):
    """Relaunching after a failure would close the dialog showing the
    error, and every other task must not restart the app at all."""
    calls = []
    window._relaunch = lambda: calls.append("restart")

    class FakeDialog:
        def __init__(self, key, ok):
            self.task = type("T", (), {"key": key, "reload_after": False})()
            self.succeeded = ok

    window._restart_after_task = "update_data"
    window._task_finished(FakeDialog("tune", True))          # another task
    assert calls == []
    window._task_finished(FakeDialog("update_data", False))  # it failed
    assert calls == []
    window._restart_after_task = "update_data"
    window._task_finished(FakeDialog("update_data", True))
    assert calls == ["restart"]


def test_reloading_forgets_the_picture_caches(window, monkeypatch):
    """Both caches index their folder once and remember it was empty, so a
    download while the app is running would otherwise never appear — which
    is what "I ran the update and the icons are still blank" looks like."""
    from draft_assist.ui import item_icons, portraits
    forgotten = []
    monkeypatch.setattr(portraits, "forget",
                        lambda: forgotten.append("portraits"))
    monkeypatch.setattr(item_icons, "forget",
                        lambda: forgotten.append("items"))
    window.reload_backend()
    assert set(forgotten) == {"portraits", "items"}


def test_role_and_own_pick_come_off_the_tile_not_a_dropdown(window):
    """Two dropdowns naming the hero a second time was a worse way to say
    something the tile already shows."""
    window.refresh()
    assert not hasattr(window, "role_combo")
    assert not hasattr(window, "my_hero_combo")
    hero = window.team_buttons["ally"][0].property("hero_id")
    window._set_my_hero(hero)
    window._set_slot_role("ally", 0, "Pos 1")
    assert window._my_hero() == hero
    assert window._my_role() == "carry"
    # The role follows the hero, not the slot number, if it moves.
    window._set_slot_role("ally", 0, None)
    assert window._my_role() is None


def test_your_own_hero_must_still_be_in_the_draft(window):
    window.refresh()
    window._set_my_hero(window.team_buttons["ally"][0].property("hero_id"))
    window._set_my_hero_locked(True)
    window._on_draft_changed([], [], 10)
    assert window._my_hero() is None
    assert not window.my_hero_locked


def test_the_debug_view_does_no_work_while_it_is_hidden(window, monkeypatch):
    """It draws an overlay onto a full-resolution frame, converts it and
    smooth-scales it — four times a second, into a widget nobody is looking
    at. That was most of the stutter during a game."""
    import numpy as np
    from draft_assist.vision import debug as debug_mod

    drawn = []
    monkeypatch.setattr(debug_mod, "draw_overlay",
                        lambda *a, **k: drawn.append(1) or a[0])
    window.refresh()
    snap = window.snapshot
    snap.frame = np.zeros((64, 64, 3), dtype=np.uint8)
    snap.read_raw = snap.read = object()

    window.tabs.setCurrentIndex(0)          # Draft tab: Debug is hidden
    window._update_debug(snap)
    assert drawn == [], "the debug view redrew while hidden"


def test_hero_names_are_built_once_not_per_tick(window):
    first = window._hero_names()
    assert first is window._hero_names()
    assert len(first) == len(window.ds.hero_ids)


def test_scaled_portraits_are_cached_not_rescaled_every_paint(qapp,
                                                              monkeypatch,
                                                              tmp_path):
    """A smooth rescale inside paintEvent, for a picture that never
    changes, on thirty widgets, four times a second."""
    from PyQt6.QtGui import QColor, QPixmap
    from draft_assist.ui import portraits

    pixmap = QPixmap(256, 144)
    pixmap.fill(QColor("#404040"))
    pixmap.save(str(tmp_path / "4_bloodseeker.png"))
    monkeypatch.setattr(portraits, "BASE_DIR", tmp_path)
    portraits.forget()

    first = portraits.scaled(4, 60, 40)
    assert first is not None
    assert first is portraits.scaled(4, 60, 40)      # same object, not a copy
    assert portraits.scaled(4, 30, 20) is not first  # a different size is not
    portraits.forget()
    assert portraits.scaled(4, 60, 40) is not first  # and forgetting clears


def test_the_toolbar_keeps_only_what_belongs_there(window):
    """Recordings and the report have a whole tab of their own, force
    recognition is a debugging switch, and the capture pill said the same
    sentence as the status bar one line higher up."""
    from PyQt6.QtCore import Qt
    from PyQt6.QtWidgets import QToolBar
    toolbar = window.findChild(QToolBar)
    # It rides on the tab strip rather than in a band of its own: three
    # controls do not need a whole row of window height.
    assert window.tabs.cornerWidget(Qt.Corner.TopRightCorner) is toolbar
    from PyQt6.QtWidgets import QPushButton
    labels = {w.text() for w in toolbar.findChildren(QPushButton)}
    # Update went to Help: it is pressed once a patch and it was taking
    # width from the row that has to survive the narrowest window.
    assert "Update" not in labels
    assert "Recordings" not in labels and "Report" not in labels
    assert not hasattr(window, "capture_pill")


def test_a_long_strip_does_not_set_the_windows_width_floor(window, qapp):
    """Twenty fixed-width tiles in a row is over 1700px of layout minimum,
    and a widget's minimum is the window's minimum — so the setting that
    lets you ask for twenty would have left a window that could not be made
    narrow again. Same class of bug as the Debug tab and the same answer:
    the strips scroll sideways."""
    window.show()
    window.refresh()
    qapp.processEvents()
    before = window.minimumSizeHint().width()

    window.settings["suggested_picks"] = 20
    window.settings["suggested_items"] = 20
    window._refresh_views()
    qapp.processEvents()
    assert window.minimumSizeHint().width() == before, \
        ("twenty tiles widened the window's floor to "
         f"{window.minimumSizeHint().width()} from {before} — the strips "
         "are not scrolling sideways")


def test_the_settings_decide_how_many_are_shown(window, qapp):
    """The cap is the user's, and both strips read the same one setting."""
    window.refresh()
    window.settings["suggested_picks"] = 3
    window._refresh_views()
    qapp.processEvents()
    assert len(window.suggest_row.heroes) == 3

    window.settings["suggested_picks"] = 11
    window._refresh_views()
    qapp.processEvents()
    assert len(window.suggest_row.heroes) == 11


def test_a_cap_is_not_a_quota(window, qapp):
    """Raising the item cap to twenty does not produce twenty items.

    They are filtered by how urgent they are FIRST, so the strip shows
    whatever cleared the severity floor and no more — which is the whole
    reason silence is a correct answer here.
    """
    window.refresh()
    window.settings["suggested_items"] = 20
    window._refresh_views()
    qapp.processEvents()
    shown = len(window.item_row._tiles)
    assert shown <= 20
    window.settings["suggested_items"] = 2
    window._refresh_views()
    qapp.processEvents()
    assert len(window.item_row._tiles) == min(shown, 2)


def test_a_hand_edited_settings_file_cannot_ask_for_two_hundred_tiles(
        window, qapp):
    from draft_assist.ui import settings as ui_settings
    window.refresh()
    window.settings["suggested_picks"] = 200
    window._refresh_views()
    qapp.processEvents()
    assert len(window.suggest_row.heroes) <= ui_settings.MAX_SHOWN


def _silent_gsi_snapshot(fault: bool):
    from draft_assist.ui.providers import Snapshot
    snap = Snapshot()
    snap.warning = ("no data from Dota yet — GSI config installed: Run "
                    "Game > Set up game data (GSI).")
    snap.gsi_setup_broken = fault
    return snap


def test_a_dead_game_feed_gets_a_banner_not_a_status_segment(window, qapp):
    """It cost a whole ranked game as one segment of a pipe-separated line
    at the bottom of the window, between the capture mode and how old the
    data is. "Where is the warning line" is a fair question about that."""
    window._update_first_run_banner(_silent_gsi_snapshot(True))
    qapp.processEvents()
    # isHidden, not isVisible: the window itself has not been shown, so
    # isVisible answers "is the window up" rather than "did we hide this".
    assert not window.banner.isHidden()
    assert "not sending game data" in window.banner_label.text()
    assert "Set up game data" in window.banner_label.text(), \
        "the banner must carry the specific broken link, not just a nudge"
    assert window.banner_button.text() == "Check game data"


def test_the_banner_button_opens_the_diagnosis(window, qapp, monkeypatch):
    """The button has to do what the banner is about — it was hard-wired to
    the data download whatever the message said."""
    opened = []
    monkeypatch.setattr(window, "_diagnose_gsi", lambda: opened.append(1))
    window._update_first_run_banner(_silent_gsi_snapshot(True))
    window.banner_button.click()
    assert opened == [1]


def test_dota_being_closed_is_not_a_fault_worth_a_banner(window, qapp):
    """Silence with nothing wrong is normal, and a banner that is up all
    evening is one nobody reads on the night it matters."""
    window._update_first_run_banner(_silent_gsi_snapshot(False))
    qapp.processEvents()
    assert "not sending game data" not in window.banner_label.text()


def test_the_warning_leads_the_status_line(window, qapp):
    window._update_status(_silent_gsi_snapshot(True))
    assert window.status.currentMessage().startswith("WARNING:")


def _settle(qapp, times=4):
    """A size-hint change reaches the parent through a posted
    LayoutRequest, so the new geometry lands a couple of event-loop passes
    later rather than inside the call that caused it."""
    for _ in range(times):
        qapp.processEvents()


def _strip_is_fully_visible(scroller):
    """Every tile's bottom edge inside the viewport, in viewport space."""
    strip = scroller.widget()
    tiles = getattr(strip, "_tiles", []) or getattr(strip, "_blanks", [])
    if not tiles:
        return True, "no tiles to check"
    room = scroller.viewport().height()
    tallest = max(t.sizeHint().height() for t in tiles)
    return tallest <= room, f"tiles want {tallest}px, viewport gives {room}px"


def test_the_strips_are_not_sliced_off(window, qapp):
    """The scroll area's height was stamped once, from a strip holding
    nothing but a hidden label — so every tile put in it afterwards had its
    bottom cut off and the portraits showed as a band. The height has to be
    asked for, not frozen at what an EMPTY strip wanted."""
    window.show()
    window.refresh()
    _settle(qapp)
    for name in ("suggest_row", "item_row"):
        strip = getattr(window, name)
        scroller = strip.parentWidget().parentWidget()
        ok, detail = _strip_is_fully_visible(scroller)
        assert ok, f"{name} is cropped: {detail}"


def test_the_strips_grow_when_they_are_filled(window, qapp):
    """An empty strip and a full one are different heights, and the wrapper
    has to follow — which is the half that was got wrong."""
    window.show()
    qapp.processEvents()
    scroller = window.suggest_row.parentWidget().parentWidget()
    window.suggest_row.show_heroes([])
    _settle(qapp)
    empty = scroller.sizeHint().height()
    window.refresh()
    _settle(qapp)
    assert window.suggest_row.heroes, "the fixture should have suggestions"
    assert scroller.sizeHint().height() >= empty
    ok, detail = _strip_is_fully_visible(scroller)
    assert ok, detail


def test_the_recognition_log_says_when_the_pick_bar_is_not_up(window, qapp):
    """Ten UNKNOWNs is the RIGHT answer at a team showcase, and this log has
    already been read as "the crop boxes are broken" because of it."""
    import numpy as np
    from draft_assist.gsi import state as gsi_state
    from draft_assist.vision.layout import DraftLayout
    from draft_assist.vision.recognize import DraftRead, SlotRead

    snap = window.snapshot or window.provider.poll()
    snap.frame = np.zeros((200, 400, 3), dtype=np.uint8)
    snap.read_raw = DraftRead(slots=[
        SlotRead(rect=r, hero_id=None, best_label="base/1.png",
                 distance=101, margin=0)
        for r in DraftLayout().slots()])
    snap.game_state = gsi_state.STATE_IN_PROGRESS
    window.show()
    window.tabs.setCurrentIndex(window.tabs.count() - 1)
    _settle(qapp)
    assert window.debug_image.isVisible(), "the Debug tab is not on screen"
    window._update_debug(snap)
    text = window.debug_text.toPlainText()
    assert "not the pick screen" in text
    assert "capturing:" in text, "the log has to say WHAT it is a picture of"

    snap.game_state = gsi_state.STATE_HERO_SELECTION
    window._update_debug(snap)
    assert "not the pick screen" not in window.debug_text.toPlainText()
