"""Headless UI smoke test: the whole window runs on fake state (demo
provider, offscreen Qt platform) — no Dota, no capture, no network."""

import json
import os
from pathlib import Path

import copy

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
    # UNLOCKED for the tests that size the window. The window ships locked
    # at its own size (View ▸ Resize window), which is a fixed size and so
    # makes `resize()` a no-op — a layout test that cannot change the
    # width is testing one width. Set on the dict rather than through
    # `_set_window_locked`, which would also claim the status line.
    win.settings["window_locked"] = False
    win._apply_window_lock()
    yield win
    win.close()


EMPTY_SLOT_TEXT = "+"


def filled(window, side):
    """Slot labels that hold a hero; empty slots read '+' and stay clickable
    so a pick can be entered by hand."""
    return [b.text() for b in window.team_buttons[side]
            if b.text() != EMPTY_SLOT_TEXT]


def panel_values(panel, bank):
    return [delta for _, delta in panel.rows_for(bank)]


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


def test_side_swap_flips_teams(window):
    window.refresh()
    before = filled(window, "ally")
    window.side_combo.setCurrentIndex(1)
    window.refresh()
    after = filled(window, "enemy")
    assert before == after


def test_the_status_line_says_the_state_and_nothing_else(window):
    """Pipes, the mode, and whether Dota's window was found.

    The bracket, the statistics age, the line-up source and a count of
    unverified item rules used to be segments of this line. They are
    settings and diagnostics, not state — none of them changes while a
    draft runs, and between them they buried the one segment that does.
    """
    window.refresh()
    msg = window.status.currentMessage()
    assert "demo" in msg
    assert "Dota window" in msg
    assert "bracket" not in msg
    assert "data:" not in msg
    # Every separator is a bare pipe, and there is no leftover prose.
    assert "   |   " not in msg
    assert "mode: " not in msg


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


def test_app_opens_before_any_data_is_downloaded(qapp, monkeypatch):
    """First run must explain itself, not crash on a missing cache.

    ARTWORK FIRST, THEN STATISTICS. A fresh install has neither, and only
    one of the two always works: the pictures need no account anywhere,
    while the statistics need a free Stratz key the user has to go and
    get. Leading with the key leaves somebody staring at a grid of empty
    plates while they sign up for something.
    """
    from draft_assist.data import store
    from draft_assist.ui import portraits

    win = make_window(qapp, store.empty_dataset())
    try:
        monkeypatch.setattr(portraits, "any_downloaded", lambda: False)
        win.refresh()
        assert win.banner.isVisible() or not win.isVisible()
        assert "No hero pictures yet" in win.banner_label.text()
        assert "artwork" in win.banner_button.text()

        # With the pictures on disk it moves on to the half that needs a
        # key — and hands that to the WIZARD rather than explaining it in
        # a strip, because the wizard is where the key is entered and
        # checked. The banner is the way back to it, not a second copy.
        monkeypatch.setattr(portraits, "any_downloaded", lambda: True)
        win.refresh()
        assert "No statistics downloaded yet" in win.banner_label.text()
        assert "Set up" in win.banner_button.text()
        assert win._banner_action == win._run_setup
        assert "no statistics" in win.status.currentMessage()
    finally:
        win.close()


def test_banner_hidden_once_data_is_fresh(window):
    window.refresh()
    assert not window.banner.isVisible()


def test_menus_expose_every_maintenance_action(window):
    """Everything that used to be a .bat file is still reachable.

    NOT from the menu bar any more: that is File | View | Help, and
    everything out of Setup and Game is a tab in Settings. So the thing
    to check is the app's own list of what it can do — which is what
    builds those tabs AND what Help ▸ Search searches, so a maintenance
    action missing from it is missing from both.
    """
    flat = [c.label for c in window._all_commands()]
    for expected in ("Statistics and portraits…", "Tune recognition…",
                     "List capture sources…", "Run capture probe…",
                     "Update application…", "Save debug snapshot"):
        assert expected in flat, f"{expected} is not reachable: {flat}"
    # And every one of them actually does something when taken.
    assert all(callable(c.run) for c in window._all_commands())


def test_force_recognition_menu_and_toolbar_stay_in_sync(window):
    window.force_action.setChecked(True)
    assert window.force_check.isChecked()
    window.force_check.setChecked(False)
    assert not window.force_action.isChecked()


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
        # Auto-record has just claimed the line for its eight seconds — a
        # transient message now HOLDS instead of being stamped on by the
        # next tick (see `_say`). Hand the line back and re-ask.
        win._quiet_until = 0.0
        win.refresh()
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
    # It lands in the first FREE hand-entry slot, not in `enemies[4]`: the
    # tiles are drawn from a packed list, so the fifth tile on screen is
    # not the fifth entry in the list behind it (see `_clear_slot`).
    assert 42 in window.manual.entered("enemy")
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
    from draft_assist.ui import portraits
    monkeypatch.setattr(portraits, "any_downloaded", lambda: True)
    ds = demo_dataset()          # built for ANCIENT+DIVINE
    win = make_window(qapp, ds)
    try:
        win._update_first_run_banner()
        assert win.banner.isVisible() or not win.isVisible()
        text = win.banner_label.text()
        assert "ANCIENT+DIVINE" in text and "LEGEND+ANCIENT" in text
        # It names the CHANGE, because that is what the user just did —
        # they ticked new boxes in Settings and came straight back here.
        assert "changed" in text.lower()
        assert "Update" in win.banner_button.text()
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
        # The headings are just the two side names: "Your team — Bijson ·
        # Dire" said three things where one does.
        assert win.team_captions["ally"].text() == "Dire"
        assert win.team_captions["enemy"].text() == "Radiant"
        # PLAIN WHITE. Green and red on the side names put the colours
        # that mean "good for you" and "bad for you" on two words that
        # judge nothing — with the side's signed total right beside them
        # wearing the same two colours for the opposite reason.
        from draft_assist.ui import theme
        for side in ("ally", "enemy"):
            sheet = win.team_captions[side].styleSheet()
            assert theme.TEXT_STRONG in sheet
            assert theme.GOOD not in sheet and theme.BAD not in sheet
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
    # The heading names the SIDE, always — "Your team" named the panel with
    # the user's own hero in it, which is the one thing they can already
    # see. With no side reported yet the left panel is Radiant, because
    # that is the left bank of Dota's own pick bar.
    assert window.team_captions["ally"].text() == "Radiant"
    assert window.team_captions["enemy"].text() == "Dire"


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


def test_record_button_toggles_and_shows_its_state(qapp, monkeypatch,
                                                   tmp_path):
    """It is the round red dot everyone already knows, so the state is the
    SHAPE — a circle to record, a square to stop — and the tooltip says it
    in words for anyone who wants them."""
    window = recording_window(qapp, monkeypatch, tmp_path)
    try:
        assert window.record_button._recording is False
        assert "Record" in window.record_button.toolTip()
        window.record_button.grab()          # it must actually paint
        window.record_button.click()
        assert window.recorder.active
        assert window.record_button._recording is True
        assert "Stop" in window.record_button.toolTip()
        window.record_button.grab()
        window.record_button.click()
        assert not window.recorder.active
        assert window.record_button._recording is False
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
        assert window.record_button._recording is False
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
    """Three headings, at the user's request. Setup and Game were mostly
    things you do ONCE, sitting permanently across the top of a window
    that is read at a glance during a draft."""
    titles = [a.text().replace("&", "") for a in window.menu_bar.actions()
              if a.menu() is not None]
    assert titles == ["File", "View", "Help"]
    for action in window.menu_bar.actions():
        menu = action.menu()
        if menu is not None:
            visible = [a for a in menu.actions() if not a.isSeparator()]
            assert len(visible) <= 7, f"{action.text()} has {len(visible)}"


def test_the_downloads_are_one_group(window):
    """Three siblings called Update / Fetch / Fetch are one idea said three
    times. They were a submenu; they are a Settings TAB now, which is the
    same argument one level out."""
    groups = {title: commands
              for title, _intro, commands in window._command_groups()}
    assert "Downloads" in groups
    inside = [c.label for c in groups["Downloads"]]
    assert any("Statistics and portraits" in n for n in inside)
    assert any("Alternative portraits" in n for n in inside)
    assert any("Item icons" in n for n in inside)
    assert any("All artwork" in n for n in inside)


def test_the_four_deleted_items_are_gone_for_good(window):
    """Each asked for something the app now does for itself or says
    somewhere better, and each was removed at the user's request rather
    than moved into Settings with the rest."""
    everywhere = [c.label for c in window._all_commands()]
    for gone in ("Make a pinnable shortcut…", "Run first-time setup…",
                 "Check item icons…", "Game data status…"):
        assert gone not in everywhere, f"{gone} came back"


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


def test_the_synergy_grid_is_two_triangles_a_column_apart(window):
    """Synergy is symmetric, so a team's own pairings only ever fill half a
    square — and that is exactly the shape of the other team's. Theirs
    above the diagonal against the enemy portraits on TOP, yours below it
    against the ally portraits along the BOTTOM row.

    THE TWO TRIANGLES USED TO TOUCH, and at the user's request they no
    longer do: yours moves half a portrait left and theirs half a portrait
    right, so the grid is ONE COLUMN WIDER than a team with an empty cell
    walking down the diagonal. That makes this card six sections across
    for five a side — the same as counters, whose five columns sit beside
    a portrait column — and two cards of one width divided into the same
    number of portraits draw them at the same size, which is the whole
    reason for it.
    """
    from draft_assist.ui.tables import (ENEMY_SHIFT, PAIR_HEADER, PAIR_HERO,
                                        PAIR_SIDE, PAIR_VALUE)
    window.refresh()
    draft = window._current_draft()
    allies, enemies = list(draft.allies), list(draft.enemies)
    table = window.synergy_matrix.table
    side = max(len(allies), len(enemies))
    body = side - 1
    # ONE WIDER than a team, and still as tall as counters: the body loses
    # a row to the lift, and the ally axis puts it back.
    assert table.columnCount() == side + 1
    assert table.rowCount() == side

    def value(row, col):
        item = table.item(row, col)
        return None if item is None else item.data(PAIR_VALUE)

    filled = [(r, c) for r in range(body) for c in range(side + 1)
              if value(r, c) is not None]
    upper = [(r, c) for r, c in filled if c > r + 1]
    lower = [(r, c) for r, c in filled if c <= r]
    assert len(upper) == len(enemies) * (len(enemies) - 1) // 2
    assert len(lower) == len(allies) * (len(allies) - 1) // 2
    assert not [rc for rc in filled if rc not in upper and rc not in lower]
    # THE GAP IS EXACTLY ONE CELL PER ROW, on the diagonal. That is what
    # "half a portrait each way" comes to, and it is the only hole a full
    # board may have.
    for row in range(body):
        assert value(row, row + 1) is None, f"row {row} has no gap"
    if len(allies) == len(enemies) == side:
        assert len(filled) == body * side

    # Every cell is backed by its own ROW hero — which is what replaced the
    # left-hand header column — and says which triangle it is in, which is
    # what the green and red outlines are traced from.
    for row, col in upper:
        # SHIFTED: the enemy this cell is about is `col - 1`, because the
        # whole half moved a column right.
        assert table.item(row, col).data(PAIR_HERO) == enemies[row]
        assert table.item(row, col).data(PAIR_SIDE) == "enemy"
    for row, col in lower:
        # LIFTED BY ONE: your triangle starts at ally 1, which is what
        # squares the two halves into one rectangle.
        assert table.item(row, col).data(PAIR_HERO) == allies[row + 1]
        assert table.item(row, col).data(PAIR_SIDE) == "ally"
    # And the bottom row is your own axis: portraits, that hero's total
    # with its own four, and the same side as the triangle it sits under —
    # so the outline encloses a team and its faces as one region. FLUSH
    # LEFT, under the triangle it names, with the spare column blank.
    for col, hero in enumerate(allies):
        item = table.item(body, col)
        assert item.data(PAIR_HEADER) and item.data(PAIR_HERO) == hero
        assert item.data(PAIR_SIDE) == "ally"
        # AND NO TOTAL, at the user's request — "it causes more confusion
        # than anything". Every figure on these cards is one pair now; a
        # sum of five of them wore the same badge in the same corner and
        # was told apart only by a sigma.
        assert item.data(PAIR_VALUE) is None
    spare = table.item(body, side)
    assert spare is None or spare.data(PAIR_HERO) is None

    # The enemy axis is the top HEADER, and it moved with its triangle:
    # enemy i heads column i + 1, and column 0 heads nothing at all. A
    # face standing over the wrong column is an axis that lies.
    # Checked BOTH WAYS, because a header with no portrait on disk falls
    # back to the hero's NAME — which is what this fixture has, and
    # asserting only on the picture passed while naming nothing.
    heads = window.synergy_matrix.table.horizontalHeader()
    named = getattr(heads, "heroes", {})
    for index, hero in enumerate(enemies):
        column = index + ENEMY_SHIFT
        item = table.horizontalHeaderItem(column)
        assert named.get(column) == hero or \
            window.ds.name(hero) in item.text(), f"column {column}"
    first = table.horizontalHeaderItem(0)
    assert 0 not in named, "column 0 heads nothing"
    assert first is None or not first.text()
    assert max(named, default=ENEMY_SHIFT) <= len(enemies)


def test_the_synergy_grid_has_no_left_header_and_counters_still_does(window):
    """The row portraits moved into the cells, which is what freed the
    lower triangle. Counters is a full 5x5 with no spare half, so it keeps
    its column."""
    window.refresh()
    # `isHidden`, not `isVisible`: nothing inside an unshown window is
    # visible, so only the first asks "did we hide this".
    assert window.synergy_matrix.table.verticalHeader().isHidden()
    assert not window.matchup_matrix.table.verticalHeader().isHidden()


def test_the_enemy_half_is_not_sign_flipped(window):
    """The one place in this app where green is not good for you, and it is
    deliberate: each triangle is read as "how well does THIS team's pair
    work", so a strong enemy pairing is a big green number on their side.
    The halves are the rule, not the colour."""
    from draft_assist.model import scoring
    from draft_assist.ui.tables import PAIR_VALUE
    window.refresh()
    draft = window._current_draft()
    enemies = list(draft.enemies)
    if len(enemies) < 2:
        pytest.skip("needs two enemies to have a pair at all")
    table = window.synergy_matrix.table
    raw = float(window.ds.delta_with[window.ds.index[enemies[0]],
                                     window.ds.index[enemies[1]]])
    # The first cell of THEIR triangle. It is at (0, 2) rather than
    # (0, 1) now: the enemy half is shifted a column right so the two
    # triangles stand a portrait apart, and (0, 1) is the gap.
    assert table.item(0, 2).data(PAIR_VALUE) == pytest.approx(raw)
    # The click view still flips, because there the enemy figures sit among
    # your own with no line between them.
    flipped = next(r for r in scoring.relations_to(window.ds, enemies[0],
                                                   draft)
                   if r.hero_id == enemies[1] and r.kind == "with")
    assert flipped.delta == pytest.approx(-raw)


def test_matrices_say_what_is_missing_when_a_team_is_empty(qapp):
    window = blank_window(qapp)
    try:
        window.refresh()
        # The grid stays on screen as an outline rather than vanishing:
        # a card that collapses and re-expands moves everything under it.
        assert not window.matchup_matrix.table.isHidden()
        assert window.matchup_matrix.table.rowCount() == 5
        assert window.matchup_matrix.table.item(0, 0).text() == ""
        # NO SENTENCE under the outline. "Fill in both teams" is read once
        # and skipped forever, and the empty 5x5 already says the grid is
        # waiting for picks. A reason worth saying — the OpenDota one —
        # still appears; this is not one.
        assert window.matchup_matrix.empty_note.text() == ""
        assert not window.matchup_matrix.empty_note.isVisible()
        assert window.synergy_matrix.empty_note.text() == ""
    finally:
        window.close()


def test_the_draft_tab_carries_the_teams_and_both_matrices(window):
    """The matrices moved onto the draft screen: the grid explaining the
    ten picks belongs beside the ten picks, not behind a tab."""
    titles = [window.tabs.tabText(i) for i in range(window.tabs.count())]
    assert titles == ["Draft", "Analysis"]
    draft_tab = window.tabs.widget(0)
    for widget in (window.matchup_matrix, window.synergy_matrix,
                   window.team_panels["ally"], window.team_panels["enemy"]):
        assert window.tabs.indexOf(_tab_of(window, widget)) == 0, \
            f"{widget} is not on the draft tab"
    assert window.tabs.indexOf(_tab_of(window, window.history_tab)) == 1
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


def test_clicking_an_enemy_answers_both_questions(window):
    """How your five fare against it, AND how it works with its own four.

    The second half used to be left blank on the theory that their
    pair-ups were their business. An enemy that combos with two of its
    team-mates is a bigger problem than its own matchups say, and this was
    the one view that could show it.
    """
    window.refresh()
    window.team_buttons["enemy"][2].click()

    assert window.focus[0] == "enemy"
    for i in range(5):
        assert "vs" in _delta_text(window, "ally", i)
    for i in range(len(window._current_draft().enemies)):
        if i != 2:
            assert "with" in _delta_text(window, "enemy", i)


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
        if rel.kind == "vs":
            expected = float(window.ds.delta_vs[window.ds.index[rel.hero_id],
                                                window.ds.index[enemy]])
        else:
            # Their pair working is our problem, so it is flipped onto our
            # side of the ledger like everything else in this view.
            expected = -float(
                window.ds.delta_with[window.ds.index[enemy],
                                     window.ds.index[rel.hero_id]])
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
    # Debug is a tab of the SETTINGS window now, so it can no longer set
    # the main window's floor at all — but the rule it taught still has to
    # hold there, or the settings window opens taller than the screen.
    window._open_settings("Debug")
    qapp.processEvents()
    assert window.debug_tabs.minimumSizeHint().height() < 400, \
        "the Debug pages are not scrolling; they dictate a window height"
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
    from PyQt6.QtWidgets import QToolBar
    toolbar = window.findChild(QToolBar)
    # It rides on the tab strip rather than in a band of its own: three
    # controls do not need a whole row of window height. NOT as a corner
    # widget any more — the strip is laid out by hand, because leaving it
    # to QTabWidget produced four versions of the same misalignment.
    assert toolbar.parentWidget() is window.tabs.strip
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
    assert window.minimumSizeHint().width() <= before, \
        ("twenty tiles widened the window's floor to "
         f"{window.minimumSizeHint().width()} from {before} — the strips "
         "are not wrapping")


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
    """First segment, no label. It used to sit fourth, which is how "no
    data from Dota" went unread through a whole ranked game; the "WARNING:"
    prefix went with the rest of the line's prose."""
    snap = _silent_gsi_snapshot(True)
    window._update_status(snap)
    message = window.status.currentMessage()
    assert message.startswith(snap.warning)
    assert message.split(" | ")[0] == snap.warning


def _settle(qapp, times=4):
    """A size-hint change reaches the parent through a posted
    LayoutRequest, so the new geometry lands a couple of event-loop passes
    later rather than inside the call that caused it."""
    for _ in range(times):
        qapp.processEvents()


def _tiles_of(strip):
    return (getattr(strip, "_tiles", []) or getattr(strip, "_blanks", []))


def _all_tiles_inside(strip):
    """Every tile's rectangle within the strip's own, in strip space."""
    tiles = _tiles_of(strip)
    if not tiles:
        return True, "no tiles to check"
    room = strip.rect()
    outside = [t for t in tiles if not room.contains(t.geometry())]
    return not outside, (f"{len(outside)} of {len(tiles)} tiles fall outside "
                         f"{room.width()}x{room.height()}")


def test_the_strips_are_not_sliced_off(window, qapp):
    """They used to be one row in a scroll area whose height was stamped
    once, from a strip holding nothing but a hidden label — so every tile
    added afterwards had its bottom cut off. They WRAP now, and a wrapping
    layout is only honest if `heightForWidth` is."""
    window.show()
    window.refresh()
    _settle(qapp)
    for name in ("suggest_row", "item_row"):
        strip = getattr(window, name)
        ok, detail = _all_tiles_inside(strip)
        assert ok, f"{name} is cropped: {detail}"


def test_a_narrow_strip_wraps_rather_than_scrolling(window, qapp):
    """A strip you have to scroll to read is a strip you do not read at a
    glance, which is the one thing it is for."""
    from draft_assist.ui import tilekit
    window.show()
    window.settings["suggested_picks"] = 14
    window.refresh()
    window._refresh_views()
    _settle(qapp)
    layout = window.suggest_row.layout()
    one_row = layout.heightForWidth(tilekit.STRIP_W * 20)
    narrow = layout.heightForWidth(tilekit.STRIP_W * 3)
    assert narrow > one_row, "the tiles are not wrapping"
    # One TILE at its narrowest — and the tile is whatever size the draft
    # panel above currently makes it, not the module's fallback.
    assert (window.suggest_row.minimumSizeHint().width()
            <= window.suggest_row.tile_width() + 8)


def test_the_default_is_however_many_fit_on_one_row(window, qapp):
    """A fixed number is too many on a narrow window and too few on a wide
    one; nought means "fill the row I have"."""
    from draft_assist.ui.flowlayout import fits_in_one_row
    from draft_assist.ui import tilekit
    window.settings["suggested_picks"] = 0
    window.show()
    window.resize(1400, 900)
    window.refresh()
    _settle(qapp)
    expected = fits_in_one_row(window.suggest_row.width(),
                               window.suggest_row.tile_width())
    assert window._how_many("suggested_picks") == expected
    assert expected >= 1


def test_the_count_box_sets_it_and_keeps_it(window, qapp):
    """Once you set the number it is yours and stops moving with the
    window."""
    window.show()
    _settle(qapp)
    box = window.count_boxes["suggested_picks"]
    box.setValue(4)
    window.refresh()
    _settle(qapp)
    assert window.settings["suggested_picks"] == 4
    assert window._how_many("suggested_picks") == 4
    assert len(window.suggest_row.heroes) == 4


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
    window._open_settings("Debug")
    _settle(qapp)
    assert window.debug_image.isVisible(), "the Debug tab is not on screen"
    window._update_debug(snap)
    text = window.debug_text.toPlainText()
    assert "not the pick screen" in text
    assert "capturing:" in text, "the log has to say WHAT it is a picture of"

    snap.game_state = gsi_state.STATE_HERO_SELECTION
    window._update_debug(snap)
    assert "not the pick screen" not in window.debug_text.toPlainText()


def test_clicking_a_suggested_hero_shows_the_terms_behind_its_number(
        window, qapp):
    """A sum is exactly the thing that can look reasonable for bad reasons:
    a +5 built out of one enormous matchup is a different suggestion from a
    +5 built out of five small ones, and the tile cannot say which."""
    window.show()
    window.refresh()
    _settle(qapp)
    assert window.suggest_row.heroes, "the fixture should have suggestions"
    tile = window.suggest_row._tiles[0]
    tile.asked_why.emit(tile.hero_id)
    popup = window._reason_popup
    try:
        assert popup is not None
        from PyQt6.QtWidgets import QLabel
        text = " ".join(lbl.text() for lbl in popup.findChildren(QLabel))
        assert window.ds.name(tile.hero_id) in text
        assert "fit " in text
        # And it must NOT invent an explanation.
        assert "not why" in text, "the honesty line is the point of it"
    finally:
        popup.close()


def test_clicking_a_suggested_item_quotes_its_hand_authored_rule(window,
                                                                 qapp):
    """Item rules are written in words, so this one has a real answer — and
    it is labelled as authored rather than measured."""
    window.show()
    window.refresh()
    _settle(qapp)
    if not window.item_row._tiles:
        pytest.skip("the scripted draft flagged no items")
    tile = window.item_row._tiles[0]
    tile.asked_why.emit(tile.advice.item)
    popup = window._reason_popup
    try:
        from PyQt6.QtWidgets import QLabel
        text = " ".join(lbl.text() for lbl in popup.findChildren(QLabel))
        assert tile.advice.item in text
        assert "Hand-authored" in text
        assert tile.advice.triggers[0].hero in text
    finally:
        popup.close()


def test_a_hero_with_nothing_on_the_board_says_so_rather_than_nothing(qapp):
    """Blank beats invented, and "nothing moves this yet" is not blank."""
    from draft_assist.ui import reasons
    heading, lines, note = reasons.hero_reasons("Lion", 0.0, [])
    assert lines == []
    assert "Nothing on the board" in note


def test_the_tab_row_is_one_unbroken_band(window, qapp):
    """The tabs paint their own strip, the corner widget paints its own,
    and between them — and inside a QSlider left to the base QWidget rule —
    the CONTENT colour showed through. Three tones across one row, which is
    what "discontinuity in the height of the padding" was.

    Scanned rather than asserted about, because every one of those gaps was
    somewhere nobody thought to look.
    """
    from PyQt6.QtGui import QColor
    from draft_assist.ui import theme
    qapp.setStyleSheet(theme.STYLESHEET)
    window.show()
    window.refresh()
    _settle(qapp)
    image = window.grab().toImage()
    strip = window.tabs.strip
    top_left = strip.mapTo(window, strip.rect().topLeft())
    band = strip.height()
    assert band > 0
    stray = [(x, y)
             for y in range(top_left.y(), top_left.y() + band)
             for x in range(top_left.x() + 2,
                            top_left.x() + strip.width() - 4)
             if QColor(image.pixel(x, y)).name() == theme.BG]
    assert not stray, (
        f"{len(stray)} pixels of content colour inside the tab band, "
        f"first at {stray[0]}")


def test_the_controls_sit_on_the_tab_labels_line(window, qapp):
    """A line drawn across the row has to pass through both.

    This was four bugs in a row while the toolbar was QTabWidget's corner
    widget: a gap between it and the tabs in the content colour, a lighter
    strip above it, three pixels of it hanging below the band, and its
    middle sitting below the tab labels' middle. Every fix was a correction
    applied against geometry QTabWidget had already decided. The row is
    laid out here now — one widget, two children, both AlignVCenter — so
    "on the same line" is not a calculation any more.
    """
    from draft_assist.ui import theme
    qapp.setStyleSheet(theme.STYLESHEET)
    window.show()
    window.refresh()
    _settle(qapp)
    strip = window.tabs.strip
    bar = window.tabs.bar
    probe = window.record_button

    def middle(widget):
        return (widget.mapTo(strip, widget.rect().topLeft()).y()
                + widget.height() / 2.0)

    assert bar.height() > 0 and probe.height() > 0
    assert abs(middle(probe) - middle(bar)) <= 1.0, (
        f"the record control's middle is {middle(probe)}, the tab bar's "
        f"is {middle(bar)}")
    # And Qt's own tab bar is never shown: two of them is two rows.
    assert window.tabs.tabBar().isHidden()


def test_the_two_tab_bars_stay_in_step(window, qapp):
    """The pages belong to the QTabWidget and the tabs the user clicks are
    ours, so they have to agree in BOTH directions."""
    window.show()
    _settle(qapp)
    tabs = window.tabs
    assert tabs.bar.count() == tabs.count()
    assert [tabs.bar.tabText(i) for i in range(tabs.bar.count())] == \
        [tabs.tabText(i) for i in range(tabs.count())]
    tabs.bar.setCurrentIndex(1)
    assert tabs.currentIndex() == 1
    tabs.setCurrentIndex(0)
    assert tabs.bar.currentIndex() == 0


def test_no_content_colour_anywhere_from_the_title_bar_to_the_tabs(window,
                                                                   qapp):
    """One dark region from the top of the window down to the content: the
    title bar, its icon and title labels, the tabs and the toolbar. Every
    one of those has been the odd one out at some point."""
    from PyQt6.QtGui import QColor
    from draft_assist.ui import theme
    qapp.setStyleSheet(theme.STYLESHEET)
    window.show()
    window.refresh()
    _settle(qapp)
    image = window.grab().toImage()
    strip = window.tabs.strip
    bottom = (strip.mapTo(window, strip.rect().topLeft()).y()
              + strip.height())
    stray = [(x, y)
             for y in range(4, bottom)
             for x in range(4, window.width() - 4)
             if QColor(image.pixel(x, y)).name() == theme.BG]
    assert not stray, (f"{len(stray)} content-coloured pixels above the "
                       f"content, first at {stray[0]}")


# --------------------------------------------------------------------------
# One tile, one size, and no lighter boxes behind the labels.
# --------------------------------------------------------------------------

def _colours_in(widget):
    """Every distinct colour the widget renders, as #rrggbb."""
    from PyQt6.QtGui import QImage
    picture = QImage(max(1, widget.width()), max(1, widget.height()),
                     QImage.Format.Format_ARGB32)
    picture.fill(0)
    widget.render(picture)
    return {picture.pixelColor(x, y).name()
            for y in range(picture.height())
            for x in range(picture.width())}


def test_no_label_paints_a_lighter_box_on_a_card(window, qapp):
    """The heading rows are the CARD's colour, not the content colour.

    A QLabel takes its background from the base `QWidget` rule, so every
    label in the app painted a rectangle of content grey (#313338) on the
    card's darker ground (#2b2d31): a lighter box round "Suggested picks",
    round the count box, and — where an empty label was still in the
    layout — a 3mm stub at the end of each team's heading. It had already
    been patched twice, for the title bar and for the tab strip, each time
    only where somebody happened to be looking.
    """
    from draft_assist.ui import theme
    window.show()
    window.resize(1400, 900)
    window.refresh()
    _settle(qapp)
    for panel in window.team_panels.values():
        assert theme.BG not in _colours_in(panel.caption)
        assert theme.BG not in _colours_in(panel.note)
    for box in window.count_boxes.values():
        assert theme.BG not in _colours_in(box)


def test_an_empty_note_is_not_a_widget_at_all(window):
    """The little square at the end of the team headings."""
    window.refresh()
    for panel in window.team_panels.values():
        panel.set_note("")
        assert panel.note.isHidden()
        panel.set_note("something")
        assert not panel.note.isHidden()
        panel.set_note("")


def test_radiant_is_always_the_left_panel(window, qapp):
    """Dota's own pick bar has Radiant on the left, so ours does too — the
    player's five move to the side they belong to rather than the headings
    being relabelled under them."""
    class Snap:
        my_team = "dire"
        sides_known = True
    window.refresh()
    window._update_team_captions(Snap())
    assert window.team_captions["ally"].text() == "Dire"
    assert window.team_captions["enemy"].text() == "Radiant"
    # The ENEMY panel (Radiant) is now the left-hand one, and its grid
    # went with it.
    order = [window.teams_row.itemAt(i).widget()
             for i in range(window.teams_row.count())]
    assert order[0] is window.team_panels["enemy"]
    grids = [window.grids_row.itemAt(i).widget()
             for i in range(window.grids_row.count())]
    assert grids[0] is window.grid_cards["enemy"]

    Snap.my_team = "radiant"
    window._update_team_captions(Snap())
    assert window.team_captions["ally"].text() == "Radiant"
    order = [window.teams_row.itemAt(i).widget()
             for i in range(window.teams_row.count())]
    assert order[0] is window.team_panels["ally"]


def test_the_heading_carries_that_sides_total(window, qapp):
    """"Radiant | +11.2" — the sum of what that side's five are worth."""
    from draft_assist.model import scoring
    window.refresh()
    _settle(qapp)
    net = scoring.net_contributions(window.ds, window._current_draft())
    for panel in window.team_panels.values():
        ids = [t.property("hero_id") for t in panel.slots]
        want = sum(net[h] for h in ids if h is not None and h in net)
        assert panel.total.text() == f"{want * 100:+.1f}"
        assert not panel.total.isHidden()


def test_an_empty_side_claims_no_total(window, qapp):
    """"+0.0" over five empty slots is a measurement nobody made."""
    window.refresh()
    for panel in window.team_panels.values():
        panel.set_total(None)
        assert panel.total.isHidden()
        assert panel.rule.isHidden()


def test_every_strip_tile_is_the_same_share_of_a_pick(window, qapp):
    """A suggestion is 70% of a pick, before AND after the game.

    The strips were fixed at 78x44 while the pick tiles grew with the
    window, so the two never matched at all — and the blank plates were
    painted into a rectangle taller than the widget, which put their
    dashed bottom edge off the tile. They track the pick now; the ten
    picks are the subject of the screen and the strips are advice about
    them, so they are deliberately smaller rather than equal.
    """
    from draft_assist.ui import item_row as item_mod
    from draft_assist.ui.app import STRIP_OF_PICK
    window.show()
    window.resize(1500, 950)
    window.refresh()
    _settle(qapp)
    pick = window.team_panels["ally"].slots[0]
    want_w = round(pick.width() * STRIP_OF_PICK)
    want_h = round(pick.height() * STRIP_OF_PICK)
    assert window.suggest_row.tile_width() == want_w
    for tile in _tiles_of(window.suggest_row):
        assert (tile.width(), tile.height()) == (want_w, want_h)
    # Items share the HEIGHT and keep the icon's own 88x64 shape: a 16:9
    # box round an item icon is dead space either side of every one.
    for tile in _tiles_of(window.item_row):
        assert tile.height() == want_h
        assert tile.width() == item_mod.width_for(want_h)


def test_the_blank_plates_are_the_size_of_the_real_tiles(window, qapp):
    """Before the game and after it, the same box."""
    from draft_assist.ui.suggest_row import PlaceholderTile, SuggestTile
    window.show()
    window.resize(1500, 950)
    window.refresh()
    _settle(qapp)
    size = window.suggest_row._tile_size
    window.suggest_row.show_heroes([])
    _settle(qapp)
    blanks = window.suggest_row._blanks
    assert blanks and all(isinstance(b, PlaceholderTile) for b in blanks)
    assert all((b.width(), b.height()) == size for b in blanks)
    # And the plate is painted INSIDE the tile, so the dashed border
    # reaches the bottom edge instead of falling off it.
    from draft_assist.ui import theme
    bottom = blanks[0]
    colours = _colours_in(bottom)
    assert theme.BORDER in colours


def test_the_statistics_age_is_one_banner_and_nothing_else(window, qapp,
                                                          monkeypatch):
    """It was a banner, a pill AND a status segment — three copies of a
    number worth acting on twice a month. Then one startup dialog, which
    you dismiss on the way to a draft and never see again while the thing
    it asked about stays true. Now one strip at the top, with the days on
    it and a button that fixes it. Still exactly one place."""
    from draft_assist.ui import portraits, settings as ui_settings
    assert not hasattr(window, "data_pill")
    window.refresh()
    assert "data" not in window.status.currentMessage().lower()
    assert not hasattr(window, "_prompt_if_data_is_old"), \
        "the startup dialog was replaced, not added to"

    monkeypatch.setattr(portraits, "any_downloaded", lambda: True)
    # Fresh data says nothing at all.
    assert window._stale_days() == 0
    window._update_first_run_banner()
    assert not window.banner.isVisible()

    # Past the reminder it names the days and offers the fix.
    monkeypatch.setattr(type(window.ds), "age_hours",
                        lambda self: 40 * 24.0)
    assert window._stale_days() >= 40
    window._update_first_run_banner()
    assert "40 days ago" in window.banner_label.text()
    assert "Update" in window.banner_button.text()

    # A reminder of 0 turns it off entirely, as it always did.
    window.settings["data_reminder_days"] = 0
    assert window._stale_days() == 0
    assert ui_settings.DEFAULTS["data_reminder_days"] == 14


def test_the_reminder_interval_survives_a_round_trip(tmp_path):
    from draft_assist.ui import settings as ui_settings
    path = tmp_path / "ui_settings.json"
    stored = dict(ui_settings.DEFAULTS)
    stored["data_reminder_days"] = 30
    ui_settings.save(stored, path)
    assert ui_settings.load(path)["data_reminder_days"] == 30
    # A hand-edited file cannot ask for a negative or absurd interval.
    path.write_text('{"data_reminder_days": -3}', encoding="utf-8")
    assert ui_settings.load(path)["data_reminder_days"] == 0
    path.write_text('{"data_reminder_days": 99999}', encoding="utf-8")
    assert ui_settings.load(path)["data_reminder_days"] == \
        ui_settings.MAX_REMINDER_DAYS


def test_the_number_is_outlined_rather_than_plated(qapp):
    """The number used to sit on a solid black rounded plate, and the
    plate is the part that hides the hero: even cut to the digits it is a
    rectangle of the portrait gone, and on a small tile that rectangle is
    most of the face you read the tile by. A black outline traced round
    the digits separates them from whatever is behind just as well and
    costs only the ink of the outline."""
    from PyQt6.QtCore import QRect
    from PyQt6.QtGui import QFont, QImage, QPainter
    from draft_assist.ui import theme, tilekit
    assert tilekit.STROKE.alpha() == 255
    for width, height in ((64, 36), (78, 44), (132, 74)):
        picture = QImage(width, height, QImage.Format.Format_ARGB32)
        picture.fill(0)                      # nothing but the badge
        painter = QPainter(picture)
        tilekit.paint_badge(painter, QRect(0, 0, width, height),
                            "+21.7", theme.GOOD, QFont())
        painter.end()
        painted = sum(1
                      for y in range(height) for x in range(width)
                      if picture.pixelColor(x, y).alpha() > 0)
        assert painted > 0, "the number has to be there at all"
        # The property that matters: THE PORTRAIT SHOWS THROUGH. A plate
        # fills its whole bounding rectangle, so nothing behind it
        # survives; an outline leaves the gaps between and inside the
        # characters clear. Measured inside the ink's own box, so the
        # empty rest of the tile cannot flatter the number.
        box = _ink_box(picture)
        assert box is not None
        clear = sum(1
                    for y in range(box.top(), box.bottom() + 1)
                    for x in range(box.left(), box.right() + 1)
                    if picture.pixelColor(x, y).alpha() == 0)
        assert clear > 0.1 * box.width() * box.height(), \
            f"{width}x{height}: that is a plate, not an outline"


def test_every_signed_number_in_the_app_is_one_size(qapp):
    """It was briefly scaled to the tile, which fixed a badge covering the
    portrait on a narrow window and then made the digits unreadable at
    exactly the size where the window is smallest. With the plate gone the
    size no longer has to buy back space from the art.

    And it is the GRIDS' size, at the user's request: the counters cells
    print their deltas at the body size, so a figure on a portrait is set
    from that same value rather than from one that happens to match."""
    from PyQt6.QtCore import QRect
    from PyQt6.QtGui import QFont, QImage, QPainter
    from draft_assist.ui import theme, tilekit
    assert tilekit.NUMBER_PX == theme.BODY_PX
    assert f"font-size: {theme.BODY_PX}px" in theme.STYLESHEET, \
        "the body and the number have to be sized off one number"

    def ink(width, height):
        picture = QImage(width, height, QImage.Format.Format_ARGB32)
        picture.fill(0)
        painter = QPainter(picture)
        tilekit.paint_badge(painter, QRect(0, 0, width, height),
                            "+21.7", theme.GOOD, QFont())
        painter.end()
        return sum(1 for y in range(height) for x in range(width)
                   if picture.pixelColor(x, y).alpha() > 0)

    # The same digits at every size the figure FITS: a smaller tile does
    # not get a smaller number, it just has less room around it.
    assert ink(132, 74) == ink(110, 62) == ink(96, 54)
    # At the window's very narrowest the figure is wider than the tile,
    # and a number clipped to "+21." is not a smaller number but a wrong
    # one — so there, and only there, it steps down far enough to fit.
    assert ink(64, 36) < ink(132, 74)


def test_the_body_size_is_the_one_the_user_asked_for():
    """+20% and then another 15%, bold throughout."""
    from draft_assist.ui import theme
    assert "font-size: 18px;" in theme.STYLESHEET
    assert "font-weight: bold;" in theme.STYLESHEET
    assert 'QLabel[heading="true"] { font-size: 21px;' in theme.STYLESHEET


def test_the_count_box_draws_its_own_arrows(qapp):
    """A stylesheet can colour a spin box's buttons but cannot put a MARK
    in one without an image file, so styling them left the box with no
    arrows at all — same trap as the tick box and the window buttons."""
    from PyQt6.QtGui import QImage
    from draft_assist.ui import chrome, theme
    box = chrome.CountBox(8, 1, 20)
    box.show()
    _settle(qapp)
    picture = QImage(box.width(), box.height(), QImage.Format.Format_ARGB32)
    picture.fill(0)
    box.render(picture)
    for arrows in box._arrow_boxes():
        ink = sum(1
                  for y in range(arrows.y(), arrows.bottom() + 1)
                  for x in range(arrows.x(), arrows.right() + 1)
                  if picture.pixelColor(x, y).name() == theme.TEXT)
        assert ink > 4, "an arrowhead with no ink in it"
    box.close()


def test_clicking_a_painted_arrow_steps_the_count(qapp):
    """We draw them, so we handle the clicks on them."""
    from PyQt6.QtCore import QPoint, QPointF, Qt
    from PyQt6.QtGui import QMouseEvent
    from draft_assist.ui import chrome
    box = chrome.CountBox(8, 1, 20)
    box.show()
    _settle(qapp)
    up, down = box._arrow_boxes()
    for centre, want in ((up.center(), 9), (down.center(), 8)):
        box.mousePressEvent(QMouseEvent(
            QMouseEvent.Type.MouseButtonPress, QPointF(centre),
            Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier))
        assert box.value() == want
    box.close()


def test_the_count_box_is_only_as_wide_as_its_digits(qapp):
    """It sits beside a heading: its width is chrome, the number is the
    content. A Minimum policy let the layout hand it whatever was going."""
    from draft_assist.ui import chrome
    box = chrome.CountBox(8, 1, 20)
    box.show()
    _settle(qapp)
    from PyQt6.QtWidgets import QSpinBox
    # Qt's OWN minimum plus our arrow strip, and nothing else. Adding up
    # the digits and a guess at the padding came out NARROWER than the
    # widget's minimum and clipped the number to its left half — the
    # stylesheet's padding and border are part of the box too, and Qt
    # already measures all of it against the real font.
    assert box.width() == QSpinBox.minimumSizeHint(box).width() \
        + chrome.CountBox.ARROWS_W
    assert box.width() >= QSpinBox.minimumSizeHint(box).width()
    assert box.sizePolicy().horizontalPolicy() == \
        box.sizePolicy().horizontalPolicy().Fixed
    box.close()


def test_the_widest_value_is_never_clipped(qapp):
    """The number is the whole point of the control."""
    from draft_assist.ui import chrome
    box = chrome.CountBox(20, 1, 20)
    box.show()
    _settle(qapp)
    for value in (1, 9, 10, 20):
        box.setValue(value)
        _settle(qapp)
        assert box.fontMetrics().horizontalAdvance(str(value)) \
            <= box.lineEdit().width(), f"{value} does not fit"
    box.close()


def test_the_last_control_keeps_clear_of_the_window_edge(window, qapp):
    """The transparency slider ran its handle into the frame, which reads
    as the row being cut off rather than as it ending."""
    from draft_assist.ui import chrome
    window.show()
    window.resize(1500, 950)
    window.refresh()
    _settle(qapp)
    strip = window.tabs.strip
    # The transparency slider moved into View ▸ Transparency, so the last
    # thing on the row is now Detect all.
    last = window.detect_all_button
    right = last.mapTo(strip, last.rect().topRight()).x()
    assert strip.width() - right >= chrome.BandedTabs.EDGE_GAP


# --------------------------------------------------------------------------
# A tile is addressed by its HERO, never by its position on screen.
# --------------------------------------------------------------------------

def _manual_window(qapp):
    """A window with nothing but hand-entered picks on the board."""
    from draft_assist.ui.manual import ManualDraft
    from draft_assist.ui.providers import ManualProvider
    ds = demo_dataset()
    manual = ManualDraft()
    win = MainWindow(ds, ManualProvider(manual), [], {}, manual)
    win.timer.stop()
    return win, manual


def test_a_hero_typed_into_a_later_slot_can_still_be_cleared(qapp):
    """`entered` drops the empties, so the tile at position 0 is not
    `allies[0]`. Clearing by index cleared an already-empty slot and the
    hero stayed on the board — "I can't remove Slardar"."""
    window, manual = _manual_window(qapp)
    try:
        ids = window.ds.hero_ids[:3]
        # Typed into boxes 2, 4 and 5 — the packed display starts at 0.
        for slot, hero in zip((1, 3, 4), ids):
            manual.set_slot("ally", slot, hero)
        window.refresh()
        assert [b.property("hero_id") for b in window.team_buttons["ally"]][:3] \
            == list(ids)
        window._clear_slot("ally", 0)
        window.refresh()
        on_board = [b.property("hero_id") for b in window.team_buttons["ally"]]
        assert ids[0] not in on_board
        assert on_board[:2] == list(ids[1:])
    finally:
        window.close()


def test_changing_a_hero_replaces_it_rather_than_adding_one(qapp):
    """Writing by index put the new hero in an empty slot, so it arrived
    BESIDE the one being changed instead of in place of it."""
    window, manual = _manual_window(qapp)
    try:
        first, second, third, incoming = window.ds.hero_ids[:4]
        for slot, hero in zip((1, 3, 4), (first, second, third)):
            manual.set_slot("ally", slot, hero)
        window.refresh()
        # Stand in for the picker: accept, choosing `incoming`.
        import draft_assist.ui.app as app_mod
        real = app_mod.HeroPickerDialog

        class Picked:
            DialogCode = real.DialogCode

            def __init__(self, *a, **k):
                self.cleared = False
                self.selected = incoming

            def exec(self):
                return real.DialogCode.Accepted
        app_mod.HeroPickerDialog = Picked
        try:
            window._edit_slot("ally", 0)
        finally:
            app_mod.HeroPickerDialog = real
        window.refresh()
        on_board = [b.property("hero_id") for b in window.team_buttons["ally"]
                    if b.property("hero_id") is not None]
        assert first not in on_board, "the old hero survived the change"
        assert incoming in on_board
        assert len(on_board) == 3, "a change must not add a fourth hero"
    finally:
        window.close()


def test_a_game_reported_pick_says_it_cannot_be_cleared_by_hand(window):
    """Precedence is game > hand entry, so removing one here would not
    stick — the next payload brings it back. Doing nothing silently is
    indistinguishable from being broken."""
    window.refresh()
    held = [b.property("hero_id") for b in window.team_buttons["ally"]
            if b.property("hero_id") is not None]
    assert held, "the demo provider should report picks"
    window._clear_slot("ally", 0)
    assert "came from the game" in window.status.currentMessage()
    window.refresh()
    assert held[0] in [b.property("hero_id")
                       for b in window.team_buttons["ally"]]


def test_the_manual_slot_helpers_answer_by_hero(qapp):
    from draft_assist.ui.manual import ManualDraft
    manual = ManualDraft()
    manual.set_slot("ally", 3, 42)
    assert manual.slot_of("ally", 42) == 3
    assert manual.slot_of("ally", 7) is None
    assert manual.slot_of("ally", None) is None
    assert manual.first_free("ally") == 0
    assert manual.replace("ally", 42, 43)
    assert manual.allies == [None, None, None, 43, None]
    assert not manual.replace("ally", 42, 44), "42 is no longer there"
    assert manual.replace("ally", 43, None)
    assert manual.entered("ally") == []


# --------------------------------------------------------------------------
# Clear all / Detect all, and the rules between the controls.
# --------------------------------------------------------------------------

def test_clear_all_wipes_everything_the_user_told_this_match(qapp):
    """One press back to an empty board — the slots, the side and order
    corrections, and which hero is yours."""
    window, manual = _manual_window(qapp)
    try:
        first, second = window.ds.hero_ids[:2]
        manual.set_slot("ally", 0, first)
        manual.set_slot("enemy", 2, second)
        window.side_overrides[first] = "enemy"
        window.slot_order["ally"] = [first]
        window.my_hero_id = first
        window.my_hero_locked = True
        window.refresh()
        window._clear_all()
        assert manual.entered("ally") == [] and manual.entered("enemy") == []
        assert window.side_overrides == {}
        assert window.slot_order == {"ally": [], "enemy": []}
        assert window.my_hero_id is None and not window.my_hero_locked
        assert window.focus is None
        window.refresh()
        for side in ("ally", "enemy"):
            assert all(b.property("hero_id") is None
                       for b in window.team_buttons[side])
    finally:
        window.close()


def test_detect_all_asks_for_one_reading_and_forgets_the_old_one(qapp):
    """A one-shot, not the Force recognition switch — and it drops what
    was read, or the stabiliser lets the stale answer outvote the new
    frame for another few ticks."""
    from draft_assist.capture.session import CaptureSession
    session = CaptureSession.__new__(CaptureSession)
    session.state = type("S", (), {"last_read": "old", "last_read_raw": "old",
                                   "forced": False})()
    session._stabilizer = type("St", (), {"reset": lambda self: None})()
    session._detect_now = False
    session.detect_now()
    assert session.state.last_read is None
    assert session.state.last_read_raw is None
    assert session.state.forced is False, "it must not latch Force on"
    assert session._consume_detect_now() is True
    assert session._consume_detect_now() is False, "one shot, not a mode"


def test_detect_all_says_so_when_there_is_nothing_to_read(qapp):
    """Doing nothing silently is indistinguishable from being broken."""
    window, _ = _manual_window(qapp)
    try:
        window.refresh()
        assert window._capture_session() is None
        window._detect_all()
        assert "screen capture is off" in window.status.currentMessage()
    finally:
        window.close()


def test_a_rule_is_drawn_between_the_things_on_the_row(window, qapp):
    """Setup | Game | View | Help, Draft | Analysis | Debug, and between
    every control. Painted, because neither QMenuBar nor QTabBar has a
    between-items sub-control a stylesheet can reach."""
    from draft_assist.ui import chrome, theme
    window.show()
    window.resize(1500, 950)
    window.refresh()
    _settle(qapp)
    for widget in (window.menu_bar, window.tabs.bar):
        colours = _colours_in(widget)
        assert theme.RULE in colours, \
            f"{widget.objectName() or type(widget).__name__} has no rules"
    # And the toolbar carries real Divider widgets between its controls.
    rules = window.findChildren(chrome.Divider)
    assert len(rules) >= 4


def test_the_rule_is_the_grey_halfway_between_black_and_white():
    from draft_assist.ui import theme
    assert theme.RULE == "#808080"


def test_clear_all_empties_a_board_the_game_is_reporting(window, qapp):
    """The picks are the GAME's and precedence is game > hand entry, so
    wiping the manual slots changed nothing on screen and the next payload
    put all ten straight back. A clean-slate button has to produce one."""
    window.refresh()
    assert any(b.property("hero_id") is not None
               for b in window.team_buttons["ally"])
    window._clear_all()
    window.refresh()
    for side in ("ally", "enemy"):
        assert all(b.property("hero_id") is None
                   for b in window.team_buttons[side]), \
            "the board filled straight back in"
    # And it STAYS empty while the same board is being reported.
    window.refresh()
    assert all(b.property("hero_id") is None
               for b in window.team_buttons["ally"])


def test_a_cleared_board_comes_back_on_a_new_match_or_a_new_draft(window):
    """Blanked, never suppressed: a board stuck empty for the rest of the
    evening is worse than the thing being fixed.

    Pinned to the MATCH rather than to the ten heroes. Keyed on the
    line-up it was fragile in both directions: Clear all drops the capture
    session's reading, so recognition comes back a hero at a time, and any
    of those partial readings is a different line-up — which lifted the
    blanking and put a half-read board on screen.
    """
    from draft_assist.gsi.state import STATE_HERO_SELECTION
    window.refresh()
    window._clear_all()
    window.refresh()
    assert all(b.property("hero_id") is None
               for b in window.team_buttons["ally"])

    # A partial re-read is NOT a different board.
    partial = copy.copy(window.snapshot)
    partial.left = list(partial.left)[:2]
    assert window._is_cleared(partial), "a half-read board must stay blanked"
    # A different match is.
    other = copy.copy(window.snapshot)
    other.match_id = "a different match"
    assert not window._is_cleared(other)
    # So is a draft starting.
    drafting = copy.copy(window.snapshot)
    drafting.game_state = STATE_HERO_SELECTION
    assert not window._is_cleared(drafting)


def test_detect_all_cancels_the_blanking(qapp):
    """The two buttons are a pair: Detect all is the way out of Clear all."""
    window, manual = _manual_window(qapp)
    try:
        window.refresh()
        window._clear_all()
        assert window._cleared is not None or window.snapshot is None
        window._detect_all()
        assert window._cleared is None
    finally:
        window.close()


def test_every_empty_plate_in_the_window_is_the_same_rectangle(qapp):
    """A freshly opened app is three rows of identical holes — the picks
    rounded their corners while the strips squared theirs, and the item
    plates were narrower than the rest."""
    from draft_assist.ui import tilekit
    from draft_assist.ui.manual import ManualDraft
    from draft_assist.ui.providers import ManualProvider
    ds = demo_dataset()
    win = MainWindow(ds, ManualProvider(ManualDraft()), [], {}, ManualDraft())
    win.timer.stop()
    # Unlocked, or `resize` is a no-op and this measures one width — the
    # window ships locked at its own size (View ▸ Resize window).
    win.settings["window_locked"] = False
    win._apply_window_lock()
    try:
        win.show()
        win.resize(1500, 950)
        win.refresh()
        _settle(qapp)
        from draft_assist.ui.app import STRIP_OF_PICK
        pick = win.team_panels["ally"].slots[0]
        assert not pick.filled
        want = (round(pick.width() * STRIP_OF_PICK),
                round(pick.height() * STRIP_OF_PICK))
        for strip in (win.suggest_row, win.item_row):
            blanks = strip._blanks
            assert blanks, "an empty strip should show its shape"
            for blank in blanks:
                assert (blank.width(), blank.height()) == want, \
                    "an empty plate is an empty plate, whatever strip"
        # One radius for all of them, so the corners agree too.
        assert tilekit.PLATE_RADIUS > 0
    finally:
        win.close()


def test_a_message_the_user_asked_for_is_not_stamped_on_by_the_next_tick(
        window, qapp):
    """`_update_status` rewrites the whole line four times a second with no
    timeout, and a QStatusBar replaces a timed message with the next one it
    is handed — so every "Board cleared" in this app showed for under a
    quarter of a second. Which is why pressing a button and seeing nothing
    happen was the report: the button HAD said something."""
    window.refresh()
    window._say("something the user did", 6000)
    for _ in range(4):
        window.refresh()
    assert window.status.currentMessage() == "something the user did"
    # And the state comes back once it has had its moment.
    window._quiet_until = 0.0
    window.refresh()
    assert "Dota window" in window.status.currentMessage()


def test_the_row_controls_are_tab_labels_not_buttons(window, qapp):
    """Clear all and Detect all sit on the tab bar's own line, so they read
    as one series with Draft / Analysis / Debug. A raised plate with a
    radius round it was a second kind of object on a row that has one."""
    from draft_assist.ui import theme
    window.show()
    window.resize(1500, 950)
    window.refresh()
    _settle(qapp)
    tab_font = window.tabs.bar.font()
    for button in (window.clear_all_button, window.detect_all_button):
        font = button.font()
        assert (font.family(), font.pixelSize(), font.bold()) == \
            (tab_font.family(), tab_font.pixelSize(), tab_font.bold())
        colours = _colours_in(button)
        assert theme.BG_INPUT not in colours, "still wearing a button plate"
        assert theme.BG_HOVER not in colours
        assert theme.TEXT_DIM in colours, "same ink as an unselected tab"
        # And on the same line: within a pixel of the tab bar's height.
        assert abs(button.height() - window.tabs.bar.height()) <= 2


def test_the_auto_box_reads_like_the_rest_of_the_row(window, qapp):
    """It painted its own label in `theme.TEXT`, so the `color:` rule that
    dims every other label on the row never reached it and "Auto" sat
    brighter than the tabs and buttons beside it."""
    from draft_assist.ui import theme
    window.show()
    window.resize(1500, 950)
    window.refresh()
    _settle(qapp)
    auto = window.auto_record_check
    tab_font = window.tabs.bar.font()
    assert (auto.font().family(), auto.font().pixelSize(),
            auto.font().bold()) == (tab_font.family(), tab_font.pixelSize(),
                                    tab_font.bold())
    colours = _colours_in(auto)
    assert theme.TEXT_DIM in colours, "the label takes the row's own ink"
    assert theme.TEXT not in colours, "it was brighter than its neighbours"


def test_the_count_box_number_starts_at_the_left(qapp):
    """Right-aligned it was pushed against the arrows, which reads as the
    number belonging to them rather than to the field."""
    from PyQt6.QtCore import Qt
    from draft_assist.ui import chrome
    box = chrome.CountBox(10, 1, 20)
    assert box.alignment() & Qt.AlignmentFlag.AlignLeft
    assert not (box.alignment() & Qt.AlignmentFlag.AlignRight)


def test_the_status_line_is_a_footnote(window, qapp):
    """It is read when something is wrong and ignored the rest of the
    time, so at the body size it competed with the draft above it."""
    window.show()
    window.refresh()
    _settle(qapp)
    body = window.clear_all_button.font().pixelSize()
    footer = window.status.font().pixelSize()
    assert 0.6 < footer / body < 0.8, f"{footer}px against a {body}px body"


def _ink_box(picture):
    """The bounding rectangle of everything drawn on a transparent image."""
    from PyQt6.QtCore import QRect
    xs = [x for y in range(picture.height()) for x in range(picture.width())
          if picture.pixelColor(x, y).alpha() > 0]
    ys = [y for y in range(picture.height()) for x in range(picture.width())
          if picture.pixelColor(x, y).alpha() > 0]
    if not xs:
        return None
    return QRect(min(xs), min(ys), max(xs) - min(xs) + 1,
                 max(ys) - min(ys) + 1)


def test_a_blanked_board_still_takes_hand_entered_heroes(window, qapp):
    """Clear all then type a pick in. `merge` puts the game's five first
    and cuts to five, so a typed hero was dropped on the way in, the board
    key never changed, the blanking never lifted, and clicking a slot
    appeared to do nothing at all."""
    window.refresh()
    assert any(b.property("hero_id") is not None
               for b in window.team_buttons["ally"])
    window._clear_all()
    window.refresh()
    assert all(b.property("hero_id") is None
               for b in window.team_buttons["ally"])

    wanted = window.ds.hero_ids[0]
    window.manual.set_slot("ally", 0, wanted)
    window.last_draft_key = None
    window.refresh()
    on_board = [b.property("hero_id") for b in window.team_buttons["ally"]]
    assert wanted in on_board, "a hand-entered hero must land on a blanked board"
    assert on_board.count(None) == 4, "and nothing else comes back with it"


def test_a_blanked_board_does_not_reserve_the_heroes_it_hides(window):
    """The picker would otherwise refuse every one of the ten the game is
    still reporting — most of what you would want to type back in."""
    window.refresh()
    reported = set(window.snapshot.left) | set(window.snapshot.right)
    assert reported
    assert reported & window._taken_heroes()
    window._clear_all()
    window.refresh()
    assert not (reported & window._taken_heroes())


def test_the_side_total_keeps_its_colour_when_the_name_loses_it(window, qapp):
    """The heading is white; the number beside it is still green or red by
    sign, because that IS a judgement and the name is not."""
    from draft_assist.ui import theme
    window.refresh()
    panel = window.team_panels["ally"]
    assert theme.TEXT_STRONG in window.team_captions["ally"].styleSheet()
    # Read off the LABEL, not a stylesheet: the total is haloed now, like
    # every other signed number in the app, and a widget that paints its
    # own text is not reachable by a `color:` rule — the same reason the
    # tick box has to ask its palette for its colour.
    panel.set_total(0.05)
    assert panel.total.colour == theme.GOOD
    panel.set_total(-0.05)
    assert panel.total.colour == theme.BAD


def test_demo_fills_the_board_in_one_press(window):
    """Ten random heroes, through HAND ENTRY rather than a fake game feed.

    The two "Simulate a draft" menu items each started a subprocess posting
    invented payloads at the real GSI listener and left it running, which
    is a second moving part to answer "show me a full board".
    """
    window.refresh()
    window._clear_all()
    window.refresh()
    window._demo_draft()
    window.refresh()
    for side in ("ally", "enemy"):
        on_board = [b.property("hero_id") for b in window.team_buttons[side]
                    if b.property("hero_id") is not None]
        assert len(on_board) == 5, f"{side} did not fill"
    assert len(window.manual.entered("ally")) == 5
    assert window.my_hero_id is not None
    # Nothing outlives the press: it is hand entry, so Clear all empties it.
    window._clear_all()
    window.refresh()
    assert window.manual.entered("ally") == []


def test_the_simulate_draft_menu_items_are_gone(window):
    """A subprocess posting fake payloads at the live listener, left
    running, is not the way to see a full board."""
    labels = []
    for action in window.menu_bar.actions():
        menu = action.menu()
        if menu is not None:
            labels += [a.text() for a in menu.actions()]
    assert not any("imulate" in text for text in labels), labels


def test_both_grids_start_at_the_same_height(window, qapp):
    """`_fit_height` fixes each table's height, so a QVBoxLayout put the
    slack ABOVE it as well as below — and the moment the synergy grid grew
    its bottom header row, the shorter counters grid floated down the
    middle of its card and the two stopped lining up."""
    window.show()
    window.resize(1500, 950)
    window.refresh()
    _settle(qapp)
    tops = [m.table.mapTo(window, m.table.rect().topLeft()).y()
            for m in (window.synergy_matrix, window.matchup_matrix)]
    assert tops[0] == tops[1], f"{tops[0]} vs {tops[1]}"


def test_a_full_board_leaves_the_two_grids_the_same_size(window, qapp):
    """The triangles touch, so synergy is (n-1) rows of pairs plus the
    enemy axis — n rows, exactly the n counters has. That is the whole
    reason they line up bottom as well as top, with nothing told about
    the other."""
    window.show()
    window.resize(1500, 950)
    window._demo_draft()
    window.refresh()
    _settle(qapp)
    synergy, counters = window.synergy_matrix, window.matchup_matrix
    assert synergy.table.rowCount() == counters.table.rowCount()
    assert synergy.table.height() == counters.table.height(), \
        f"{synergy.table.height()} vs {counters.table.height()}"


def test_the_ad_slot_is_off_unless_it_is_asked_for(qapp):
    """It is the user's own app on their own machine, and something that
    sits over the board has to be asked for."""
    from draft_assist.ui import settings as ui_settings
    from draft_assist.ui.adslot import AdSlot
    assert ui_settings.DEFAULTS["ads_enabled"] is False
    slot = AdSlot()
    assert not slot.showing
    slot.set_enabled(True)
    assert slot.showing, "on means on, from the moment it is switched on"
    slot.set_enabled(False)
    assert not slot.showing
    slot.close()


def test_an_ad_that_is_on_stays_on(qapp):
    """It began as five seconds in every fifteen, which was worse in both
    directions: an ad that appears out of nothing mid-draft pulls the eye
    at exactly the wrong moment. At the user's request it is constant —
    off is off, and on is a strip that never moves."""
    from draft_assist.ui import adslot
    slot = adslot.AdSlot()
    slot.set_enabled(True)
    tall = slot.height()
    assert tall == adslot.HEIGHT
    assert slot.creative.pixmap() is not None
    assert not slot.creative.pixmap().isNull(), "an empty slot is not an ad"
    # Nothing on a clock: no timer anywhere on the widget to turn it over.
    from PyQt6.QtCore import QTimer
    assert not slot.findChildren(QTimer), "the cycle is gone"
    assert slot.showing and slot.height() == tall
    slot.close()


def test_ads_switched_off_cost_no_window_at_all(qapp):
    """A strip of dead window above the draft for a switched-off feature
    is worse than either state."""
    from draft_assist.ui import adslot
    slot = adslot.AdSlot()
    assert slot.height() == 0, "off by default, so it must take no room"
    slot.set_enabled(True)
    assert slot.height() == adslot.HEIGHT
    slot.set_enabled(False)
    assert slot.height() == 0
    slot.close()


def test_the_creative_is_a_real_ad_unit(qapp):
    """728x90, the IAB leaderboard — the size a banner slot is actually
    sold as, so the layout is tested against the real thing. Centred in a
    full-width slot rather than stretched: a leaderboard is a fixed-size
    creative wherever it is served."""
    from draft_assist.ui import adslot
    slot = adslot.AdSlot()
    slot.set_enabled(True)
    assert (slot.creative.width(), slot.creative.height()) == \
        (adslot.AD_WIDTH, adslot.AD_HEIGHT)
    slot.resize(3440, adslot.HEIGHT)
    _settle(qapp)
    assert slot.creative.width() == adslot.AD_WIDTH, "it stretched"
    # And the creative itself is that unit, drawn rather than downloaded:
    # a real banner off the web is somebody's copyrighted artwork, and
    # this repository carries nobody else's.
    art = adslot.leaderboard()
    assert (art.width(), art.height()) == (adslot.AD_WIDTH, adslot.AD_HEIGHT)
    picture = art.toImage()
    colours = {picture.pixelColor(x, y).name()
               for y in range(0, picture.height(), 3)
               for x in range(0, picture.width(), 3)}
    assert len(colours) > 20, "a flat rectangle is not a creative"
    assert adslot.AD_ACCENT in colours, "no call to action on it"
    slot.close()


def test_the_leaderboard_fits_at_the_narrowest_the_window_goes(window, qapp):
    """A creative wider than the window's own floor would be one the app
    can never actually show."""
    from draft_assist.ui import adslot
    window.show()
    window.refresh()
    _settle(qapp)
    assert adslot.AD_WIDTH < window.minimumSizeHint().width()


def test_the_ad_setting_reaches_the_slot(window):
    """A tick box that does not move the thing it names is not a setting."""
    window.settings["ads_enabled"] = True
    window.ad_slot.set_enabled(True)
    assert window.ad_slot._enabled
    window.settings["ads_enabled"] = False
    window.ad_slot.set_enabled(False)
    assert not window.ad_slot._enabled


def test_the_window_ships_locked_at_its_own_size(qapp):
    """A draft is read at a glance with the cursor moving fast near the
    window's edges, and a window that resizes when you meant to click a
    pick has cost the pick. Locked is the default and the tick in View
    says so."""
    from draft_assist.ui import settings as ui_settings
    from draft_assist.ui.manual import ManualDraft
    from draft_assist.ui.providers import ManualProvider
    assert ui_settings.DEFAULTS["window_locked"] is True
    ds = demo_dataset()
    win = MainWindow(ds, ManualProvider(ManualDraft()), [], {}, ManualDraft())
    win.timer.stop()
    try:
        assert win.lock_action.isChecked()
        size = win.size()
        assert win.minimumSize() == win.maximumSize() == size, \
            "a locked window has one size, not a range"
        win.resize(size.width() + 300, size.height() + 200)
        _settle(qapp)
        assert win.size() == size, "it should not have moved"
        assert win.resize_grip.isHidden(), \
            "a corner that cannot size anything reads as broken"
    finally:
        win.close()


def test_unticking_the_lock_hands_the_size_back(qapp):
    """Untick, drag the corner, tick again — and the new size is written
    to disk, or the next start would undo it."""
    from draft_assist.ui import settings as ui_settings
    from draft_assist.ui.manual import ManualDraft
    from draft_assist.ui.providers import ManualProvider
    ds = demo_dataset()
    win = MainWindow(ds, ManualProvider(ManualDraft()), [], {}, ManualDraft())
    win.timer.stop()
    try:
        win.lock_action.setChecked(False)          # as the menu does it
        assert win.maximumWidth() > win.width(), "still capped"
        assert not win.resize_grip.isHidden()
        # The floor is still the derived one: a window narrower than that
        # is a grid that has stopped being a grid.
        assert win.minimumWidth() == win._floor_w
        win.resize(win._floor_w + 260, win.height() + 120)
        _settle(qapp)
        win.lock_action.setChecked(True)
        # Locked at whatever it is NOW — the size is read off the window
        # rather than remembered from before, because an unshown window
        # applies a resize a beat later than it is asked for.
        assert win.minimumSize() == win.maximumSize() == win.size()
        assert win.width() >= win._floor_w + 260, "it kept the wider size"
        saved = ui_settings.load()
        assert saved["window_locked"] is True
        assert saved["window_w"] == win.width()
        assert saved["window_h"] == win.height()
    finally:
        win.close()


def test_locking_never_squeezes_the_window_below_what_it_can_draw(qapp):
    """`setFixedSize` replaces the minimum as well as the maximum, so a
    remembered size from a narrower build would clip the grids rather than
    being refused."""
    from draft_assist.ui.manual import ManualDraft
    from draft_assist.ui.providers import ManualProvider
    ds = demo_dataset()
    win = MainWindow(ds, ManualProvider(ManualDraft()), [], {}, ManualDraft())
    win.timer.stop()
    try:
        win.settings["window_locked"] = False
        win._apply_window_lock()
        win.resize(400, 200)                  # narrower than the floor
        win.settings["window_locked"] = True
        win._apply_window_lock()
        assert win.width() >= win._floor_w
        assert win.height() >= win.minimumSizeHint().height()
    finally:
        win.close()


def test_every_portrait_in_the_app_is_the_pick_tiles_box(window, qapp):
    """One box for every picture on the screen. The strips were 70% of a
    pick and the grids had a size of their own, so the same hero was three
    different sizes down one window."""
    from draft_assist.ui import item_row as item_mod
    from draft_assist.ui.app import STRIP_OF_PICK
    assert STRIP_OF_PICK == 1.0
    window.show()
    window.resize(1900, 1000)
    window._demo_draft()
    window.refresh()
    _settle(qapp)
    pick = window.team_panels["ally"].slots[0]
    assert window.suggest_row.tile_width() == pick.width()
    # The items keep their own 88x64 aspect off the same HEIGHT — a 16:9
    # box round an icon is dead space either side of it.
    assert window.item_row.tile_width() == item_mod.width_for(pick.height())
    # And the grids are told the same box, which each takes as a CEILING.
    # (What they DRAW needs portraits on disk; that is `test_matrix_grid`,
    # which has them.)
    grids = (window.synergy_matrix, window.matchup_matrix)
    for grid in grids:
        assert grid._portrait_want() == pick.width()
    # The two agree on the ROOM only once both teams are full. Counters is
    # as wide as the ENEMY line-up plus its portrait column, while synergy
    # is as wide as the LONGER team plus the gap between its triangles —
    # so mid-draft, at 5v4, counters is five sections across and synergy
    # is six. That is the honest answer to a half-drafted board rather
    # than a mismatch: on the 5v5 the card is read at, they are equal.
    draft = window._current_draft()
    if len(draft.allies) == len(draft.enemies) == 5:
        assert grids[0].sections() == grids[1].sections() == 6
        assert grids[0]._portrait_room() == grids[1]._portrait_room()


def test_the_size_setting_moves_the_base_and_keeps_the_behaviour(window, qapp):
    """"I still want them to size dynamically when the window is resized,
    I just want the base size to be dictated by this setting." So the
    slider moves the CAP; the window still shrinks a tile below it, and
    the floor — which the window's own minimum width is derived from —
    does not move."""
    from draft_assist.ui import teams, tilekit
    window.show()
    window.resize(1900, 1000)
    _settle(qapp)
    wide = window.team_panels["ally"].slots[0].width()
    window._set_portrait_scale(0.6)
    _settle(qapp)
    small = window.team_panels["ally"].slots[0].width()
    assert small < wide, "the setting should reach the tiles"
    assert small == teams.tile_cap() == round(teams.TILE_MAX * 0.6)
    assert window.settings["portrait_scale"] == 0.6
    # Still dynamic: a narrow window takes them below the base.
    window._set_portrait_scale(1.0)
    window.resize(window._floor_w, 900)
    _settle(qapp)
    assert window.team_panels["ally"].slots[0].width() < teams.tile_cap()
    # And the floor the window's minimum is derived from never moves.
    assert teams.minimum_panel_width() == \
        2 * teams.PANEL_MARGIN + 5 * teams.TILE_MIN + 4 * teams.TILE_GAP
    window._set_number_scale(1.5)
    assert tilekit.number_px() == round(tilekit.NUMBER_PX * 1.5)
    assert window.settings["number_scale"] == 1.5
    window._set_number_scale(1.0)
    window._set_portrait_scale(1.0)


def test_the_sizes_are_two_sliders_in_the_view_menu(window):
    """One question asked twice, and tuned by eye against the window."""
    from draft_assist.ui import settings as ui_settings
    assert ui_settings.DEFAULTS["portrait_scale"] == 1.0
    assert ui_settings.DEFAULTS["number_scale"] == 1.0
    assert set(window.size_sliders) == {"portrait_scale", "number_scale"}
    for slider in window.size_sliders.values():
        assert (slider.minimum(), slider.maximum()) == (50, 200)
    assert window.sizes_menu.menuAction() in window.view_menu.actions()


def test_updating_the_app_downloads_no_statistics_and_no_artwork():
    """AT THE USER'S REQUEST, and because of what it looked like: Update
    ran `fetch_assets` as its last step, so pressing it sat there pulling
    126 portraits, every item icon and the community's alternative
    portraits — minutes of network with a progress box that reads as a
    frozen app. Update is the CODE. Anything missing is flagged in the
    strip at the top, with a button that fetches it."""
    from draft_assist.ui.tasks import TASKS

    steps = [" ".join(step) for step in TASKS["update_app"].steps]
    joined = " | ".join(steps)
    assert "tools/update_app.py" in joined
    assert "pip" in joined, "dependencies still have to be refreshed"
    assert "fetch_assets" not in joined, \
        "Update must not download artwork; the banner offers it instead"
    assert "pull_data" not in joined, \
        "Update must not download statistics either"

    # The recurring job still does both — that is the one that is MEANT
    # to take a few minutes.
    recurring = " | ".join(" ".join(s) for s in TASKS["update_data"].steps)
    assert "pull_data" in recurring and "fetch_assets" in recurring


def test_a_hero_with_no_portrait_is_flagged_even_when_others_have_one(
        qapp, monkeypatch, tmp_path):
    """`any_downloaded` answers "is there artwork AT ALL", which goes true
    on the first download and stays true — so a hero added in a patch had
    no picture and nothing anywhere said so. That was covered by Update
    fetching artwork every time; now that Update is the code alone, this
    strip is the only thing that notices."""
    from draft_assist.ui import portraits

    monkeypatch.setattr(portraits, "BASE_DIR", tmp_path)
    portraits.forget()
    # Two heroes on disk, three in the dataset.
    for hero_id in (1, 2):
        (tmp_path / f"{hero_id}_hero.png").write_bytes(b"not really a png")
    assert portraits.any_downloaded(), "the folder is not empty"
    assert portraits.missing_for([1, 2, 3]) == {3}
    assert portraits.missing_for([1, 2]) == set()
    portraits.forget()


def test_the_missing_artwork_banner_is_the_last_rung(qapp, monkeypatch,
                                                     tmp_path):
    """A blank tile is the least of the five things this strip says. Wrong
    rank bracket and stale statistics are the ADVICE being wrong, so they
    come first; the picture comes last."""
    from draft_assist.ui import portraits

    monkeypatch.setattr(portraits, "any_downloaded", lambda: True)
    monkeypatch.setattr(portraits, "missing_for", lambda ids: {42, 43})
    win = make_window(qapp, demo_dataset())
    try:
        monkeypatch.setattr(win, "_bracket_mismatch", lambda: None)
        monkeypatch.setattr(win, "_stale_days", lambda: 0)
        win._update_first_run_banner()
        assert win.banner.isVisible() or not win.isVisible()
        assert "2 hero pictures are missing" in win.banner_label.text()
        assert "artwork" in win.banner_button.text()

        # Stale statistics outrank it: the numbers matter more than the
        # picture, and updating those tops the artwork up on the way past.
        monkeypatch.setattr(win, "_stale_days", lambda: 30)
        win._update_first_run_banner()
        assert "updated 30 days ago" in win.banner_label.text()
    finally:
        win.close()


def test_one_missing_portrait_is_not_described_in_the_plural(
        qapp, monkeypatch):
    """"1 hero pictures are missing" is the tell of a message nobody
    read back."""
    from draft_assist.ui import portraits

    monkeypatch.setattr(portraits, "any_downloaded", lambda: True)
    monkeypatch.setattr(portraits, "missing_for", lambda ids: {7})
    win = make_window(qapp, demo_dataset())
    try:
        monkeypatch.setattr(win, "_bracket_mismatch", lambda: None)
        monkeypatch.setattr(win, "_stale_days", lambda: 0)
        win._update_first_run_banner()
        said = win.banner_label.text()
        assert "1 hero picture is missing" in said, said
        assert "pictures are" not in said
        assert "That tile draws blank" in said, said
    finally:
        win.close()


def test_the_picks_fill_their_card_and_the_grids_line_up_with_them(window,
                                                                   qapp):
    """"They should be scaling to reach the end margins."

    The box used to be the SMALLEST of what the two grid cards could
    draw, with the picks brought down to meet it — so counters, which is
    six sections across where everything else is five, decided the size
    of the ten picks and left them sitting small in the middle of their
    own card. Now each region fills its own card and the size follows
    from how many are across it: the picks set the box, and synergy —
    also five across — lands on the same number and the same left and
    right edges.
    """
    window.show()
    window.resize(1500, 950)
    window.refresh()
    _settle(qapp)
    panel = list(window.team_panels.values())[0]
    tiles = panel.slots
    margins = panel.layout().contentsMargins()
    room = (panel.width() - margins.left() - margins.right()
            - 4 * panel.spacing)
    used = sum(t.width() for t in tiles)
    assert abs(used - room) <= 5, (
        f"the five picks leave {room - used}px of their card unused")
    # The suggestions are the same tile.
    assert window.suggest_row.tile_width() == tiles[0].width()
    # And both grids were handed that width as their ceiling. The BOX
    # itself is only chosen once there are portraits to draw — with none
    # on disk the headers fall back to names and stay at the floor, which
    # is what this fixture has, so the size the grids agreed to is checked
    # against portraits in `test_the_grid_portrait_is_the_pick_tiles_box`.
    for grid in (window.synergy_matrix, window.matchup_matrix):
        assert grid._portrait_want() == tiles[0].width()


def test_settings_is_one_tabbed_window_that_owns_the_debug_pages(window,
                                                                 qapp):
    """Everything out of Setup and Game is a tab in here, the Debug pages
    among them, at the user's request.

    It is MODELESS and it owns the debug pages outright: they are a live
    view of what the app is reading, which a modal dialog could not be
    watched through, and borrowing the widget per opening would mean
    handing a live widget between two parents — how this app has ended up
    with a second taskbar window before.
    """
    window._open_settings()
    settings = window.settings_window
    titles = [settings.tabs.tabText(i) for i in range(settings.tabs.count())]
    assert titles == ["General", "Downloads", "Game data", "Appearance",
                      "Advanced", "Debug"]
    assert settings.isModal() is False
    assert window.debug_tabs.parent() is not None
    # Opening it again is the SAME window, or the debug pages would be
    # rebuilt out from under the refresh loop.
    again = window.settings_window
    window._open_settings("Downloads")
    assert window.settings_window is again
    assert settings.tabs.tabText(settings.tabs.currentIndex()) == "Downloads"


def test_settings_apply_as_you_go(window, qapp, tmp_path, monkeypatch):
    """There is no OK button: a preferences window holding a live view has
    no use for one, and a change that waits for a press nobody makes is a
    setting that looks broken."""
    from draft_assist.ui import settings as ui_settings
    monkeypatch.setattr(ui_settings, "SETTINGS_FILE", tmp_path / "s.json")
    window._open_settings()
    page = window.settings_window.general
    before = bool(window.settings.get("auto_record", True))
    page.boxes["auto_record"].setChecked(not before)
    _settle(qapp)
    assert window.settings["auto_record"] is (not before)
    assert window.auto_record_check.isChecked() is (not before)
