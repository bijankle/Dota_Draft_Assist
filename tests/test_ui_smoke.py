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


def test_refresh_populates_table_and_teams(window):
    window.refresh()
    assert window.table.rowCount() > 100
    named = [b.text() for b in window.team_buttons["ally"] if b.isEnabled()]
    assert len(named) == 5
    enemy_named = [b.text() for b in window.team_buttons["enemy"]
                   if b.isEnabled()]
    assert len(enemy_named) == 4  # demo leaves one dire slot unknown
    assert "unresolved" in window.unknown_label.text()


def test_drafted_heroes_not_in_candidate_list(window):
    window.refresh()
    listed = {window.table.item(r, 0).text()
              for r in range(window.table.rowCount())}
    for side in ("ally", "enemy"):
        for b in window.team_buttons[side]:
            if b.isEnabled():
                assert b.text() not in listed


def test_breakdown_view(window):
    """Selecting a candidate shows its per-opponent terms, not just a sum."""
    window.refresh()
    window.table.selectRow(0)
    hero_name = window.table.item(0, 0).text()
    html = window.detail.toHtml()
    assert hero_name in html
    assert "baseline" in html
    # Every drafted hero the score depends on is itemised by name.
    drafted = [b.text() for side in ("ally", "enemy")
               for b in window.team_buttons[side] if b.isEnabled()]
    assert sum(name in html for name in drafted) >= 5


def test_counters_view(window):
    window.refresh()
    button = window.team_buttons["enemy"][0]
    assert button.isEnabled()
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
    before = [b.text() for b in window.team_buttons["ally"] if b.isEnabled()]
    window.side_combo.setCurrentIndex(1)
    window.refresh()
    after = [b.text() for b in window.team_buttons["enemy"] if b.isEnabled()]
    assert before == after


def test_status_bar_reports_data_and_mode(window):
    window.refresh()
    msg = window.status.currentMessage()
    assert "mode: demo" in msg
    assert "bracket: ANCIENT+DIVINE" in msg


def test_snapshot_button_reports_no_frame_in_demo(window):
    window.refresh()
    window.snapshot_button.click()
    assert "No captured frame" in window.snapshot_label.text()


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
