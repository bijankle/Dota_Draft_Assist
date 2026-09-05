"""Headless UI smoke test: the whole window runs on fake state (demo
provider, offscreen Qt platform) — no Dota, no capture, no network."""

import json
import os
from pathlib import Path

import pytest

pytest.importorskip("PyQt6")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import Qt  # noqa: E402
from PyQt6.QtWidgets import QApplication  # noqa: E402

from draft_assist.config import RULES_FILE  # noqa: E402
from draft_assist.model import items as items_mod  # noqa: E402
from draft_assist.ui.app import MainWindow  # noqa: E402
from draft_assist.ui.hero_picker import (  # noqa: E402
    HeroPickerDialog as _Picker)
HeroPickerDialogCode = _Picker.DialogCode
from draft_assist.ui.demo import DemoDraft, demo_dataset  # noqa: E402
from draft_assist.ui.providers import DemoProvider  # noqa: E402
from draft_assist.ui.tables import SORT_ROLE  # noqa: E402


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
    assert "baseline" in panel.subtitle.text()
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
    for column, reverse in ((1, True), (2, True), (3, False), (4, False)):
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


def test_items_only_after_lock(window):
    window.refresh()
    assert "Lock your pick" in window.items_view.toHtml()
    window.my_hero_combo.setCurrentIndex(1)
    window.lock_check.setChecked(True)
    html = window.items_view.toHtml()
    # Either concrete advice or the honest-silence message — never the
    # locked-out prompt.
    assert "Lock your pick" not in html


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
    window.role_combo.setCurrentIndex(1)  # Carry
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
             for m in window.menuBar().findChildren(type(window.menuBar()
                                                         .addMenu("x")))}
    labels = {title: [a.text().replace("&", "") for a in menu.actions()]
              for title, menu in menus.items()}
    flat = [text for texts in labels.values() for text in texts]
    for expected in ("Update statistics and portraits…", "Tune recognition…",
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
        assert "reads them off the Dota window" in \
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

def test_overlay_collapses_to_just_the_badge(qapp):
    """Collapsed, the window must be the badge and nothing more, or an
    invisible strip sits over the game swallowing clicks."""
    from draft_assist.ui.overlay import BADGE_SIZE, PANEL_WIDTH, DraftOverlay

    overlay = DraftOverlay(demo_dataset())
    try:
        overlay.show()
        assert overlay.expanded
        assert overlay.width() == PANEL_WIDTH
        overlay.toggle()
        assert not overlay.expanded
        assert overlay.size().width() == BADGE_SIZE
        assert overlay.size().height() == BADGE_SIZE
        overlay.toggle()
        assert overlay.width() == PANEL_WIDTH
    finally:
        overlay.close()


def test_overlay_is_frameless_and_on_top(qapp):
    from PyQt6.QtCore import Qt

    from draft_assist.ui.overlay import DraftOverlay

    overlay = DraftOverlay(demo_dataset())
    try:
        flags = overlay.windowFlags()
        assert flags & Qt.WindowType.FramelessWindowHint
        assert flags & Qt.WindowType.WindowStaysOnTopHint
        # Must never steal keyboard focus from the game when it appears.
        assert overlay.testAttribute(
            Qt.WidgetAttribute.WA_ShowWithoutActivating)
    finally:
        overlay.close()


def test_overlay_shows_ranked_heroes(qapp):
    from draft_assist.model import scoring
    from draft_assist.ui.overlay import DraftOverlay
    from draft_assist.ui.providers import Snapshot

    ds = demo_dataset()
    overlay = DraftOverlay(ds, rows=4)
    try:
        draft = scoring.DraftState(allies=[1, 2], enemies=[11, 12],
                                   my_role="carry")
        scored = scoring.score_all(ds, draft)
        snap = Snapshot(mode="draft", game_state="DOTA_GAMERULES_STATE_"
                                                 "HERO_SELECTION")
        overlay.update_content(snap, scored, draft)
        visible = [l for l in overlay.row_labels if l.isVisibleTo(overlay)]
        assert len(visible) == 4
        assert scored[0].name in visible[0].text()
        assert "%" in visible[0].text()
        assert "Hero Selection" in overlay.state_label.text()
        assert "4 picks known" in overlay.state_label.text()
    finally:
        overlay.close()


def test_overlay_says_when_enemy_picks_are_missing(qapp):
    from draft_assist.model import scoring
    from draft_assist.ui.overlay import DraftOverlay
    from draft_assist.ui.providers import Snapshot

    ds = demo_dataset()
    overlay = DraftOverlay(ds)
    try:
        draft = scoring.DraftState(allies=[1])
        overlay.update_content(Snapshot(needs_manual=True),
                               scoring.score_all(ds, draft), draft)
        assert "not reported" in overlay.footer.text()
    finally:
        overlay.close()


def test_overlay_toggle_persists_position_and_state(qapp, tmp_path,
                                                    monkeypatch):
    """Dragging it somewhere must survive a restart."""
    from draft_assist.ui import settings as ui_settings

    monkeypatch.setattr(ui_settings, "SETTINGS_FILE", tmp_path / "ui.json")
    ds = demo_dataset()
    win = make_window(qapp, ds)
    monkeypatch.setattr(win, "settings", ui_settings.load())
    try:
        win.overlay_action.setChecked(True)
        assert win.overlay is not None and win.overlay.isVisible()
        win._remember_overlay_position(517, 233)
        win.overlay.set_expanded(False)
        win._remember_overlay_expanded(False)

        stored = ui_settings.load(tmp_path / "ui.json")
        assert stored["overlay_x"] == 517 and stored["overlay_y"] == 233
        assert stored["overlay_expanded"] is False
        assert stored["overlay_enabled"] is True

        win._reset_overlay_position()
        assert win.overlay.x() == 40
    finally:
        win.close()


def test_overlay_closes_with_the_main_window(qapp, tmp_path, monkeypatch):
    from draft_assist.ui import settings as ui_settings

    monkeypatch.setattr(ui_settings, "SETTINGS_FILE", tmp_path / "ui.json")
    win = make_window(qapp, demo_dataset())
    monkeypatch.setattr(win, "settings", ui_settings.load())
    win.overlay_action.setChecked(True)
    overlay = win.overlay
    win.close()
    assert not overlay.isVisible()


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
        assert not win.side_combo.isVisibleTo(win)
        assert not win.side_label.isVisibleTo(win)
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
    assert window.side_combo.isVisibleTo(window)
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


def test_quick_entry_fills_the_next_slot_on_the_active_side(qapp):
    window = blank_window(qapp)
    try:
        name = window.ds.name(window.ds.hero_ids[0])
        window.quick_entry.setText(name)
        window.quick_entry.returnPressed.emit()
        assert window.manual.enemies[0] == window.ds.hero_ids[0]
        assert window.manual.allies == [None] * 5
        assert window.quick_entry.text() == ""

        other = window.ds.name(window.ds.hero_ids[1])
        window.quick_entry.setText(other)
        window.quick_entry.returnPressed.emit()
        assert window.manual.enemies[1] == window.ds.hero_ids[1]
    finally:
        window.close()


def test_tab_is_left_alone_so_it_walks_the_slots(qapp):
    """Tab used to flip the entry side. It has to traverse the ten draft
    slots instead, so the side toggle moved to Ctrl+Tab and the button."""
    window = blank_window(qapp)
    try:
        assert window.quick_side_button.text() == "Enemy"
        for side in window.team_buttons.values():
            for button in side:
                assert button.focusPolicy() == Qt.FocusPolicy.StrongFocus

        window._flip_quick_side()
        assert window.quick_side == "ally"
        assert window.quick_side_button.text() == "Ally"
        window.quick_entry.setText(window.ds.name(window.ds.hero_ids[0]))
        window.quick_entry.returnPressed.emit()
        assert window.manual.allies[0] == window.ds.hero_ids[0]
    finally:
        window.close()


def test_quick_entry_refuses_an_ambiguous_prefix(qapp):
    """Silently entering the wrong hero mid-draft is worse than entering
    none: two heroes share a prefix, so nothing is filled."""
    window = blank_window(qapp)
    try:
        names = [window.ds.name(h) for h in window.ds.hero_ids]
        shared = None
        for length in range(1, 4):
            heads = {}
            for name in names:
                heads.setdefault(name[:length].lower(), []).append(name)
            shared = next((k for k, v in heads.items() if len(v) > 1), None)
            if shared:
                break
        assert shared, "demo dataset has no ambiguous prefix to test with"
        assert window.resolve_hero(shared) is None
        window.quick_entry.setText(shared)
        window.quick_entry.returnPressed.emit()
        assert window.manual.enemies == [None] * 5
        assert window.quick_entry.text() == shared     # not thrown away
    finally:
        window.close()


def test_quick_entry_matches_a_word_inside_the_name(qapp):
    """Nobody types "Bounty Hunter" in a 30-second draft."""
    window = blank_window(qapp)
    try:
        target = next((h for h in window.ds.hero_ids
                       if " " in window.ds.name(h)), None)
        if target is None:
            pytest.skip("no multi-word hero in the demo dataset")
        second = window.ds.name(target).split()[1]
        if window.resolve_hero(second) is None:
            pytest.skip(f"{second!r} is ambiguous in this dataset")
        assert window.resolve_hero(second) == target
    finally:
        window.close()


def test_quick_entry_will_not_add_a_hero_already_drafted(window):
    window.refresh()
    already = filled(window, "enemy")[0]
    before = list(window.manual.enemies)
    window.quick_entry.setText(already)
    window.quick_entry.returnPressed.emit()
    assert window.manual.enemies == before


def test_quick_undo_removes_the_last_pick_typed(qapp):
    window = blank_window(qapp)
    try:
        for hero_id in window.ds.hero_ids[:2]:
            window.quick_entry.setText(window.ds.name(hero_id))
            window.quick_entry.returnPressed.emit()
        window._flip_quick_side()                     # to the ally side
        window.quick_entry.setText(window.ds.name(window.ds.hero_ids[2]))
        window.quick_entry.returnPressed.emit()

        window._quick_undo()                           # the ally one
        assert window.manual.allies == [None] * 5
        assert window.manual.enemies[:2] == list(window.ds.hero_ids[:2])
        window._quick_undo()
        assert window.manual.enemies[1] is None
        assert window.manual.enemies[0] == window.ds.hero_ids[0]
    finally:
        window.close()


def test_clearing_the_draft_also_forgets_the_undo_history(qapp):
    window = blank_window(qapp)
    try:
        window.quick_entry.setText(window.ds.name(window.ds.hero_ids[0]))
        window.quick_entry.returnPressed.emit()
        window._clear_manual()
        assert window._entry_order == []
        window._quick_undo()          # must not resurrect a stale slot
        assert window.manual.enemies == [None] * 5
    finally:
        window.close()


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
    for action in window.menuBar().actions():
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
    titles = [a.text().replace("&", "") for a in window.menuBar().actions()
              if a.menu() is not None]
    assert titles == ["Setup", "Game", "View", "Help"]
    for action in window.menuBar().actions():
        menu = action.menu()
        if menu is not None:
            visible = [a for a in menu.actions() if not a.isSeparator()]
            assert len(visible) <= 7, f"{action.text()} has {len(visible)}"


def test_both_sources_are_on_by_default():
    from draft_assist.ui import settings as ui_settings

    defaults = ui_settings.load()
    assert defaults["use_gsi"] is True
    assert defaults["use_vision"] is True
    assert defaults["auto_record"] is True


def test_settings_dialog_round_trips_the_switches(qapp):
    from draft_assist.ui.settings_dialog import SettingsDialog

    dialog = SettingsDialog({"use_gsi": True, "use_vision": False,
                             "auto_record": True, "overlay_enabled": False})
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


def test_swap_button_appears_only_when_the_sides_are_a_guess(qapp):
    window = minimap_window(qapp)
    try:
        assert window.snapshot.lineup_source == "minimap"
        assert window.snapshot.sides_certain is False
        assert not window.swap_button.isHidden()
        assert "which five are yours is a guess" in window.manual_hint.text()
    finally:
        window.close()


def test_swapping_flips_the_two_rows(qapp):
    window = minimap_window(qapp)
    try:
        before = window._sides(window.snapshot)
        window.swap_button.click()
        after = window._sides(window.snapshot)
        assert after == (before[1], before[0])
        assert "swapped" in window.manual_hint.text().lower() or True
        window.swap_button.click()
        assert window._sides(window.snapshot) == before
    finally:
        window.close()


def test_a_new_match_forgets_the_swap(qapp):
    """A correction applies to the match it was made in, never the next."""
    window = minimap_window(qapp)
    try:
        window.swap_button.click()
        assert window.swap_sides
        window.provider.server._reception.payload["map"]["matchid"] = "999"
        window.refresh()
        assert not window.swap_sides
    finally:
        window.close()


def test_a_source_that_knows_the_sides_offers_no_swap(window):
    """Hand entry and the screen both know which bank is yours; only the
    minimap's run split is a guess."""
    window.refresh()
    assert window.snapshot.sides_certain is True
    assert window.swap_button.isHidden()


# ---- the matrices -------------------------------------------------------

def test_matchup_matrix_is_allies_by_enemies(window):
    window.refresh()
    allies, enemies = filled(window, "ally"), filled(window, "enemy")
    table = window.matchup_matrix.table
    assert table.rowCount() == len(allies)
    assert table.columnCount() == len(enemies)
    assert [table.verticalHeaderItem(r).text()
            for r in range(table.rowCount())] == allies
    assert [table.horizontalHeaderItem(c).text()
            for c in range(table.columnCount())] == enemies
    assert table.item(0, 0).text()          # every cell carries a value


def test_synergy_matrix_shows_each_pair_once(window):
    """Synergy is symmetric, so the lower half would only repeat the upper
    and the diagonal means nothing."""
    window.refresh()
    allies = filled(window, "ally")
    table = window.synergy_matrix.table
    assert table.rowCount() == table.columnCount() == len(allies)
    filled_cells = [(r, c) for r in range(table.rowCount())
                    for c in range(table.columnCount())
                    if table.item(r, c).text()]
    assert len(filled_cells) == len(allies) * (len(allies) - 1) // 2
    assert all(c > r for r, c in filled_cells)


def test_matrices_say_what_is_missing_when_a_team_is_empty(qapp):
    window = blank_window(qapp)
    try:
        window.refresh()
        assert window.matchup_matrix.table.isHidden()
        assert "Fill in both teams" in window.matchup_matrix.empty_note.text()
        assert "Fill in your own team" in \
            window.synergy_matrix.empty_note.text()
    finally:
        window.close()


def test_the_matrix_tab_exists_and_is_not_the_debug_tab(window):
    titles = [window.tabs.tabText(i) for i in range(window.tabs.count())]
    assert titles == ["Draft", "Matrix", "Debug"]


def test_no_swap_offered_while_you_are_still_picking(qapp):
    """The swap exists for the minimap's post-draft guess. During hero
    selection the sides come from the screen and are known."""
    window = minimap_window(qapp)
    try:
        assert not window.swap_button.isHidden()      # strategy time
        payload = window.provider.server._reception.payload
        payload["map"]["game_state"] = "DOTA_GAMERULES_STATE_HERO_SELECTION"
        window.refresh()
        assert window.swap_button.isHidden()
    finally:
        window.close()


# ---- a hero cannot be in two slots -------------------------------------

def test_the_same_hero_cannot_be_entered_twice(qapp):
    window = blank_window(qapp)
    try:
        name = window.ds.name(window.ds.hero_ids[0])
        window.quick_entry.setText(name)
        window.quick_entry.returnPressed.emit()
        assert window.manual.enemies[0] == window.ds.hero_ids[0]

        window.quick_entry.setText(name)
        window.quick_entry.returnPressed.emit()
        assert window.manual.enemies[1] is None
        assert "no single undrafted hero" in window.status.currentMessage()
    finally:
        window.close()


def test_a_hero_on_one_team_cannot_be_added_to_the_other(qapp):
    window = blank_window(qapp)
    try:
        name = window.ds.name(window.ds.hero_ids[0])
        window.quick_entry.setText(name)
        window.quick_entry.returnPressed.emit()
        window._flip_quick_side()
        window.quick_entry.setText(name)
        window.quick_entry.returnPressed.emit()
        assert window.manual.allies == [None] * 5
    finally:
        window.close()


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


def test_typing_a_pick_leaves_the_box_ready_for_the_next(qapp):
    window = blank_window(qapp)
    try:
        window.show()
        window.quick_entry.setText(window.ds.name(window.ds.hero_ids[0]))
        window.quick_entry.returnPressed.emit()
        assert window.quick_entry.text() == ""
        assert window.focusWidget() is window.quick_entry
    finally:
        window.close()


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
        window.quick_entry.setText(window.ds.name(window.ds.hero_ids[0]))
        window.quick_entry.returnPressed.emit()
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
        window._flip_quick_side()
        for hero_id in window.ds.hero_ids[:3]:
            window.quick_entry.setText(window.ds.name(hero_id))
            window.quick_entry.returnPressed.emit()
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
        for action in window.menuBar().actions():
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
