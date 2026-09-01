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
    window.refresh()
    window.table.selectRow(0)
    html = window.detail.toHtml()
    assert "component breakdown" in html
    assert "vs " in html or "with " in html


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
    window.refresh()
    window.role_combo.setCurrentIndex(1)  # Carry
    highlighted = sum(
        1 for r in range(window.table.rowCount())
        if window.table.item(r, 0).background().color().green() > 60)
    assert highlighted > 0


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
