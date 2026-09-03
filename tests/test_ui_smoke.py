"""Headless UI smoke test: the whole window runs on fake state (demo
provider, offscreen Qt platform) — no Dota, no capture, no network."""

import os

import pytest

pytest.importorskip("PyQt6")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication  # noqa: E402

from draft_assist.config import RULES_FILE  # noqa: E402
from draft_assist.model import items as items_mod  # noqa: E402
from draft_assist.ui.app import MainWindow  # noqa: E402
from draft_assist.ui.demo import DemoDraft, demo_dataset  # noqa: E402
from draft_assist.ui.providers import DemoProvider  # noqa: E402


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
    """Selecting a candidate shows its per-opponent terms, not just a sum."""
    window.refresh()
    window.table.selectRow(0)
    hero_name = window.table.item(0, 0).text()
    html = window.detail.toHtml()
    assert hero_name in html
    assert "baseline" in html
    # Every drafted hero the score depends on is itemised by name.
    drafted = filled(window, "ally") + filled(window, "enemy")
    assert sum(name in html for name in drafted) >= 5


def test_counters_view(window):
    window.refresh()
    button = window.team_buttons["enemy"][0]
    assert button.text() != EMPTY_SLOT_TEXT
    button.click()
    assert "Best against" in window.detail.toHtml()


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
        assert "not the other line-up" in win.manual_hint.text()
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
