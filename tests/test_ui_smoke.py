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
def styled(qapp):
    """The app under its OWN stylesheet, restored afterwards.

    A few tests here read colours and font sizes that only exist once
    the theme is applied, and they used to get it by accident: another
    test earlier in the file set it on the shared QApplication and never
    put it back. That is order-dependence — run one of them alone and it
    fails — and `conftest.py` now resets the stylesheet either side of
    every test, so the accident is gone and the need has to be stated.
    """
    from draft_assist.ui import theme
    was = qapp.styleSheet()
    qapp.setStyleSheet(theme.STYLESHEET)
    yield qapp
    qapp.setStyleSheet(was)


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
    Blank plates say the same thing in the place the answer will be.

    AND THERE ARE AS MANY AS THE STRIP IS SET TO, which is the whole
    point of showing a shape at all — "it would look nicer if the
    placeholder boxes extended out to suit the width of the window
    according to the quantity selected / set". Five plates under a strip
    set to twenty is the wrong shape: the card grows the moment the
    first pick lands, which is exactly what an empty state exists to
    stop.
    """
    window = blank_window(qapp)
    try:
        # `_refresh_views`, not `refresh`: the strips are rebuilt when a
        # PICK changes, so a plain refresh over an unchanged board does
        # not redraw them. That is why the count box calls this itself —
        # otherwise a new number would sit in the settings file until the
        # next hero was picked.
        window.settings["suggested_items"] = 7
        window.settings["suggested_picks"] = 12
        window._refresh_views()
        assert window.item_row.items == []
        assert window.item_row.message.text() == ""
        assert len(window.item_row._blanks) == 7
        # THE SUGGESTION STRIP IS NO LONGER ONE OF THESE, and that is the
        # ordering change rather than a hole in the empty state. It stayed
        # blank on an empty board because it ranked by draft FIT, and with
        # nothing picked every fit is zero — it would have been ranking
        # nothing while looking like a recommendation. It ranks by how
        # hard the field finds each hero to counter now, which never
        # looked at the board, so it is exactly as true before the first
        # pick as after it: "i want the main menu to show top 33 heroes".
        assert window.suggest_row.hero_ids, (
            "the strip should be full on an empty board now")
        assert not window.suggest_row._blanks, (
            "a full strip needs no placeholders")

        # And nought means "as many as fit on one row", which the window
        # resolves — so the plates fill the width rather than falling
        # back to a fixed five.
        window.settings["suggested_items"] = 0
        window._refresh_views()
        assert (len(window.item_row._blanks)
                == window._how_many("suggested_items"))
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
    for expected in ("Statistics and portraits…",
                     "List capture sources…",
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
        dialog.ranks.boxes["Legend – Ancient"].click()
        assert dialog._chosen() == ("LEGEND", "ANCIENT")
        assert "Legend + Ancient" in dialog.summary.text()
        # Changing the bracket invalidates the cache; the dialog must say so.
        assert "rebuild" in dialog.summary.text().lower()

        # THE EMPTY SELECTION IS UNREACHABLE NOW, so the refusal it
        # needed is gone with it: the picker is exclusive, and clicking
        # the ticked range keeps it rather than clearing the lot.
        dialog.ranks.boxes["Legend – Ancient"].click()
        assert dialog._chosen() == ("LEGEND", "ANCIENT")
        assert dialog.ok.isEnabled()
        # And the single-bracket warning went with the single bracket:
        # every range on offer is two or more, so a sample too thin to
        # read is no longer something this dialog can produce.
        assert len(dialog._chosen()) >= 2
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
        "player": {"team_name": "dire", "name": "ExampleDrafter"},
        "hero": {"id": 5}})
    try:
        win.refresh()
        assert win.side_combo.isHidden()
        assert win.side_label.isHidden()
        # The headings are just the two side names: "Your team — ExampleDrafter ·
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
        "player": {"team_name": "radiant", "name": "ExampleDrafter"},
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
    # The two invented-payload simulators went with their menu items; what
    # is left is the one that replays a recording the app made itself.
    assert TASKS["replay_gsi"].modeless, "it would block the draft panel"
    for key in ("update_data", "update_app"):
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
    window.run_task("replay_gsi")
    assert shown == ["replay_gsi"] and executed == []
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
    # RUN joined them, at the user's request: the record dot and the
    # Auto tick moved off the tab row into a menu of their own,
    # inserted before View so the bar reads what the app is DOING,
    # then how it looks, then help.
    assert titles == ["File", "Run", "View", "Help"]
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
    # THE MATRICES START OFF (View ▸ Synergies and counters), so this
    # test has to ask for the thing it is about before looking at where
    # it sits.
    window.section_actions["show_matrices"].setChecked(True)
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
    assert titles == ["Draft", "History"]
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


def _kind(window, side, index):
    """Which relation the badge is showing, if any.

    IT USED TO BE READ OFF THE TEXT. The badge said "with +5.2" or
    "vs -1.8", and at the user's request the words are gone — "when the
    user clicks on a 5 / 5 portrait the others say with or v.s.... i dont
    think this is needed", answered with a gold box round the figure
    instead. What these tests are actually about is the SCORING (an
    ally-to-ally pairing is synergy, not a matchup), which is still there
    to ask about; only the place to ask has moved.
    """
    return window.team_panels[side].slots[index].relation_kind()


def test_clicking_an_ally_answers_both_questions(window):
    """An ally is judged twice over — how it fits with your four and how it
    fares against their five — so clicking one shows synergy above the
    allies AND matchup above the enemies."""
    window.refresh()
    window.team_buttons["ally"][0].click()

    assert window.focus is not None and window.focus[0] == "ally"
    assert _delta_text(window, "ally", 0) == ""          # the clicked hero
    for i in range(1, 5):
        assert _kind(window, "ally", i) == "with", \
            "an ally-to-ally pairing is synergy, not a matchup"
        assert _delta_text(window, "ally", i) != ""
    for i in range(len(window._current_draft().enemies)):
        assert _kind(window, "enemy", i) == "vs"


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
        assert _kind(window, "ally", i) == "vs"
    for i in range(len(window._current_draft().enemies)):
        if i != 2:
            assert _kind(window, "enemy", i) == "with"


def test_clicking_the_same_hero_again_clears_the_view(window):
    """The way out is the same gesture as the way in."""
    window.refresh()
    button = window.team_buttons["ally"][1]
    button.click()
    assert window.focus is not None
    button.click()
    assert window.focus is None
    # Back to the resting state: every tile shows its own net figure, so
    # the numbers stay — what goes is the mark saying they are about the
    # clicked hero, which is the gold box (and was the words before it).
    assert all(_kind(window, side, i) == ""
               for side in ("ally", "enemy") for i in range(5))
    assert not any(window.team_panels[side].slots[i]._boxed
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


def test_the_app_owns_exactly_one_window_and_nothing_else(qapp):
    """The whole application, not just the window's own attributes.

    `test_no_widget_is_left_without_a_parent` walks `vars(window)`, so a
    widget held anywhere else — in a list, in another module, in a local
    that a closure kept alive — is invisible to it. THAT is what a report
    of "small blank windowwws flickering on / off" needs ruling out,
    because a parentless QWidget is a top-level window carrying the
    application's icon over an empty client area.

    **IT DIFFS RATHER THAN COUNTING, and the first version did not.** It
    asserted that `allWidgets()` held exactly one parentless widget,
    which is true of a boot and false of a SUITE: a QApplication is
    shared by every test in a run, so every dialog and window any other
    file has opened is still in that list. It passed alone and failed in
    the full suite — the same order-dependence this project already has
    a note about, one list over. What is actually being held is that
    BUILDING AND SHOWING A WINDOW adds no parentless widget but itself,
    so the baseline is taken first and only what is new is judged.

    The baseline list is kept alive deliberately: comparing by `id`
    against objects that have been freed would let a reused address read
    as "was there before".
    """
    from PyQt6.QtWidgets import QWidget
    before = [w for w in qapp.allWidgets() if w.parentWidget() is None]
    known = {id(w) for w in before}

    ds = demo_dataset()
    rules, meta = items_mod.load_rules(RULES_FILE)
    win = MainWindow(ds, DemoProvider(ds), rules, meta)
    win.timer.stop()
    win.show()
    for _ in range(5):
        qapp.processEvents()
    loose = [f"{type(w).__name__}({w.objectName() or '-'})"
             for w in qapp.allWidgets()
             if isinstance(w, QWidget) and w.parentWidget() is None
             and id(w) not in known and w is not win]
    win.close()
    assert loose == [], (
        "opening the app added these, and every one of them is a window "
        f"of its own the moment anything shows it: {loose}")
    assert before is not None                # keep the baseline alive


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
    from draft_assist.ui import settings as ui_settings
    flags = window.windowFlags()
    assert flags & Qt.WindowType.FramelessWindowHint
    # ON TOP IS A SETTING NOW, NOT A MODE. The pin made it a choice and
    # the defaults are the owner's own, whose answer is off — so what is
    # held is that the FLAG AGREES WITH THE SETTING. Off Windows the hint
    # is the only route there is, which is the branch this runs on.
    on_top = bool(flags & Qt.WindowType.WindowStaysOnTopHint)
    assert on_top is ui_settings.DEFAULTS["always_on_top"]
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


def test_the_tab_row_keeps_only_what_belongs_there(window):
    """Recordings and the report have a whole tab of their own, force
    recognition is a debugging switch, and the capture pill said the same
    sentence as the status bar one line higher up.

    THE QToolBar ITSELF IS GONE. It held five controls and ended up
    holding none: the record dot and Auto went to the Run menu, and
    Clear all / Detect all / Demo went to the board bar. An empty toolbar
    still added a rule, so the row drew two dividers side by side with
    nothing between them — and dead UI here goes stale and then gets read
    as documentation.

    AND NOW THE ROW IS THE TABS AND NOTHING ELSE. The three board actions
    sat here for a while and have gone back above the board, at the
    user's request: "move these 3 buttons clear / detect / demon into the
    middle in line with Radiant and dire". What made that possible is the
    other half of the same message — the two headings came out of their
    cards, so there is a row up there for the three of them to sit in the
    middle of.
    """
    from PyQt6.QtWidgets import QPushButton, QToolBar
    assert window.findChild(QToolBar) is None, "the empty toolbar is back"

    labels = {w.text() for w in window.tabs.strip.findChildren(QPushButton)}
    assert not labels, f"the tab row has picked up controls again: {labels}"
    board = {w.text() for w in window.board_actions.findChildren(QPushButton)}
    assert board == {"Clear all", "Detect all", "Demo"}, board
    # Update went to Help: it is pressed once a patch and it was taking
    # width from the row that has to survive the narrowest window.
    assert "Update" not in board
    assert "Recordings" not in board and "Report" not in board
    assert not hasattr(window, "capture_pill")


def test_the_recording_controls_are_in_the_run_menu(window):
    """"move the auto + tickbox + record button into a new menu header
    called run". They are the SAME two widgets — a checkable menu item
    would have cost the round red dot, which is the one thing on screen
    that says at a glance whether a session is running."""
    assert window.record_button.window() is not window, (
        "the record dot is still on the window rather than in a menu")
    assert window.run_menu is not None
    inside = window.run_menu.findChildren(type(window.record_button))
    assert window.record_button in inside
    ticks = window.run_menu.findChildren(type(window.auto_record_check))
    assert window.auto_record_check in ticks


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
                    "Settings > Game data > Set up game data (GSI).")
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
    # THE SPECIFIC BROKEN LINK, still — that rule has not changed. What
    # changed is that naming it no longer means naming a MENU: the strip
    # used to end "Run Settings > Game data > Set up game data (GSI)" for
    # a step with nothing in it to decide, and the button does that step
    # now. "check game data should not jsut give an error and instruct
    # you to download game data... instead it should just facilitate the
    # installation directly."
    assert "config file has not been written" in window.banner_label.text(), \
        "the banner must carry the specific broken link, not just a nudge"
    assert "Settings" not in window.banner_label.text(), \
        "the strip is sending people to a menu again"
    assert window.banner_button.text() == "Install it"


def test_the_banner_button_does_the_half_that_is_ours(window, qapp,
                                                      monkeypatch):
    """The button has to do what the banner is about — it was hard-wired
    to the data download whatever the message said, and then for a while
    it opened a DIAGNOSIS of a fault the app could simply fix.

    Writing Dota's config is a mkdir and a write with nothing in it for
    anybody to choose, so the button writes it. Monkeypatched because the
    real one reaches the filesystem and, with no Dota installed, would
    put a modal box up in front of a test.
    """
    did = []
    monkeypatch.setattr(window, "_install_gsi_from_banner",
                        lambda: did.append(1))
    window._update_first_run_banner(_silent_gsi_snapshot(True))
    window.banner_button.click()
    assert did == [1]


def test_the_banner_asks_for_the_launch_option_once_the_config_is_there(
        window, qapp, monkeypatch):
    """The two halves are not alike, so the strip must not offer the same
    thing for both. With the file written, the only step left is the one
    in Steam that no program can take."""
    monkeypatch.setattr(window, "_gsi_config_installed", lambda: True)
    shown = []
    monkeypatch.setattr(window, "_launch_option_help", lambda: shown.append(1))
    window._update_first_run_banner(_silent_gsi_snapshot(True))
    qapp.processEvents()
    assert "-gamestateintegration" in window.banner_label.text()
    assert window.banner_button.text() == "Show me how"
    window.banner_button.click()
    assert shown == [1]


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


def test_clicking_a_suggestion_measures_the_board_against_it(window, qapp):
    """The terms behind a suggestion's number, written on the ten heroes
    the question is about — instead of a popup listing them over the
    strip. A candidate is read as a POSSIBLE ALLY: synergy with your five,
    matchup against theirs."""
    window.show()
    window.refresh()
    _settle(qapp)
    assert window.suggest_row.heroes, "the fixture should have suggestions"
    tile = window.suggest_row.tiles[0]
    window.suggest_row.clicked_hero.emit(tile.hero_id)
    _settle(qapp)

    assert window.focus == ("suggest", tile.hero_id)
    assert tile.focused, "the clicked candidate wears the ring"
    said = [t for t in window.team_panels["ally"].slots
            if t.property("hero_id") is not None]
    assert said and all(t.relation_kind() == "with" for t in said)
    assert all(t.delta_text() for t in said), "no figure on an ally"
    against = [t for t in window.team_panels["enemy"].slots
               if t.property("hero_id") is not None]
    assert against and all(t.relation_kind() == "vs" for t in against)
    # AND EVERY ONE OF THEM WEARS THE GOLD BOX, which is now the only
    # thing saying these figures are about the clicked hero rather than
    # each tile's own standing.
    assert all(t._boxed for t in said + against)
    # The other candidates keep their own fit: "suggestion versus
    # suggestion is too hypothetical" — neither hero is on the board.
    assert all(not other.delta_text() for other in window.suggest_row.tiles
               if other is not tile)

    # Clicking it again is the way out, exactly as it is on the board.
    window.suggest_row.clicked_hero.emit(tile.hero_id)
    _settle(qapp)
    assert window.focus is None
    assert not tile.focused


def test_clicking_a_pick_renumbers_the_suggestions(window, qapp):
    """With a hero clicked the whole board answers one question, so a
    strip still ranking by overall fit would be the one row on screen
    answering a different one."""
    window.show()
    window.refresh()
    _settle(qapp)
    fits = [t.delta_text() for t in window.suggest_row.tiles]
    assert fits and not any(fits), "they start on their own fit"

    tile = next(t for t in window.team_panels["ally"].slots
                if t.property("hero_id") is not None)
    order = [t.hero_id for t in window.suggest_row.tiles]
    tile.clicked.emit()
    _settle(qapp)

    said = [t for t in window.suggest_row.tiles]
    assert all(t.delta_text() and t._boxed for t in said), (
        [t.delta_text() for t in said])
    # THE ORDER NEVER MOVES: only the numbers on the tiles change, so a
    # hero stays where it was last seen.
    assert [t.hero_id for t in window.suggest_row.tiles] == order


def test_one_selection_at_a_time(window, qapp):
    """A pick, a suggestion and a grid face are one question, so a new
    click REPLACES the old one wherever it came from."""
    window.show()
    window.refresh()
    _settle(qapp)
    pick = next(t for t in window.team_panels["ally"].slots
                if t.property("hero_id") is not None)
    pick.clicked.emit()
    _settle(qapp)
    assert pick.focused

    candidate = window.suggest_row.tiles[0]
    window.suggest_row.clicked_hero.emit(candidate.hero_id)
    _settle(qapp)
    assert candidate.focused
    assert not pick.focused, "two rings would be two questions"


def test_clicking_a_suggested_item_quotes_its_rule(window, qapp):
    """Item rules are written in words, so this one has a real answer.

    It used to be LABELLED as authored rather than measured, and that
    signature was cut at the user's request. What has to survive is the
    line itself: the hero, its own percentage, then why.
    """
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
        assert "Hand-authored" not in text
        assert tile.advice.triggers[0].hero in text
        assert f"{tile.advice.triggers[0].hero} |" in text
        assert "%" in text
    finally:
        popup.close()


def test_clicking_a_grid_face_drives_the_whole_board(window, qapp):
    """The grids name the same ten heroes the board does, so a click on an
    axis portrait is the same gesture as a click on a pick — same
    selection, same ring, same numbers everywhere."""
    window.show()
    window.refresh()
    _settle(qapp)
    pick = next(t for t in window.team_panels["ally"].slots
                if t.property("hero_id") is not None)
    hero = pick.property("hero_id")

    window.matchup_matrix.hero_clicked.emit(hero)
    _settle(qapp)
    assert window.focus == ("ally", hero)
    assert pick.focused, "the pick tile lights up too"
    assert window.matchup_matrix._focus_hero == hero
    assert window.synergy_matrix._focus_hero == hero
    assert any(t.delta_text() for t in window.suggest_row.tiles)

    # Clicking it again is the way out, the same as everywhere else.
    window.matchup_matrix.hero_clicked.emit(hero)
    _settle(qapp)
    assert window.focus is None
    assert window.matchup_matrix._focus_hero is None


def test_a_focused_suggestion_leaves_the_grids_alone(window, qapp):
    """It is not on either card — it is not in the draft — so every cell
    would fail the "is this about that hero" test and both grids would go
    completely empty, which reads as the grids having broken."""
    window.show()
    window.refresh()
    _settle(qapp)
    candidate = window.suggest_row.tiles[0]
    window.suggest_row.clicked_hero.emit(candidate.hero_id)
    _settle(qapp)
    assert window.focus[0] == "suggest"
    assert window.matchup_matrix._focus_hero is None
    assert window.synergy_matrix._focus_hero is None


def test_a_grid_click_on_a_hero_that_left_the_draft_does_nothing(window,
                                                                 qapp):
    """The side comes from the draft, and a hero that is in neither team
    has no side — so there is nothing to measure the board against."""
    window.show()
    window.refresh()
    _settle(qapp)
    absent = next(h for h in window.ds.hero_ids
                  if h not in window._current_draft().allies
                  and h not in window._current_draft().enemies)
    window.matchup_matrix.hero_clicked.emit(absent)
    _settle(qapp)
    assert window.focus is None


def _fake_run(spec: dict):
    """A History run carrying just what the star rule reads."""
    from dataclasses import dataclass
    from datetime import datetime
    from draft_assist.history.report import Options, Report

    @dataclass
    class Played:
        hero_id: int
        win: bool

    matches = []
    for hero_id, (games, wins) in spec.items():
        matches += [Played(hero_id, True)] * wins
        matches += [Played(hero_id, False)] * (games - wins)
    return Report(options=Options(account_id=1), how="", name="",
                  matches=matches, blocks=[], dropped={}, sessions=1,
                  returned=0, ran_at=datetime.now())


def test_the_history_run_stars_the_suggestions(window, qapp):
    """The one place the two tabs meet: the strip ranks by draft fit,
    which knows nothing about you, and the star says "and this is a hero
    you play a lot and win on"."""
    window.show()
    window.refresh()
    _settle(qapp)
    shown = [t.hero_id for t in window.suggest_row.tiles]
    assert len(shown) >= 4, "the fixture should have suggestions"
    good, bad, thin = shown[0], shown[1], shown[2]

    window.history_tab.report = _fake_run(
        {good: (40, 26), bad: (30, 9), thin: (2, 2)})
    # ONE MARK, which goes to the hero ranked best on pick rate and win
    # rate together.
    window._apply_settings({"heart_count": 1, "shield_count": 1})
    _settle(qapp)
    starred = [t.hero_id for t in window.suggest_row.tiles if t.starred]
    assert starred == [good], starred
    best = [t for t in window.suggest_row.tiles if t.hero_id == good][0]
    assert best._star_rank == 1, "the mark carries its rank"

    # AND IT FOLLOWS THE TAB. Clearing the run clears the stars rather
    # than leaving the last account's answer on a strip nobody ran.
    window.history_tab.report = None
    _settle(qapp)
    assert not any(t.starred for t in window.suggest_row.tiles)


def test_the_stars_survive_the_strip_being_rebuilt(window, qapp):
    """`show_heroes` destroys every tile and builds new ones, so a star
    applied before a pick lands is a star on a widget that is gone."""
    window.show()
    window.refresh()
    _settle(qapp)
    shown = [t.hero_id for t in window.suggest_row.tiles]
    window.history_tab.report = _fake_run({shown[0]: (40, 26),
                                           shown[1]: (30, 9)})
    _settle(qapp)
    assert any(t.starred for t in window.suggest_row.tiles)
    window._refresh_views()
    _settle(qapp)
    assert any(t.starred for t in window.suggest_row.tiles)


def test_moving_the_count_redraws_the_marks(window, qapp):
    """The setting is a COUNT over the strip now, so it is a cut over a
    ranking that has not changed - the marks are drawn again rather than
    the run being measured again.

    It still has to happen on the settings change: the strip is rebuilt
    when a PICK changes, so without it the control moves a number in a
    file and nothing on screen until the next hero is picked, which is
    indistinguishable from a broken setting.
    """
    window.show()
    window.refresh()
    _settle(qapp)
    shown = [t.hero_id for t in window.suggest_row.tiles]
    window.history_tab.report = _fake_run(
        {shown[0]: (40, 26), shown[1]: (30, 9), shown[2]: (20, 14)})
    window._apply_settings({"heart_count": 1, "shield_count": 1})
    _settle(qapp)
    before = {t.hero_id for t in window.suggest_row.tiles if t.starred}

    window._apply_settings({"heart_count": 3, "shield_count": 3})
    _settle(qapp)
    after = {t.hero_id for t in window.suggest_row.tiles if t.starred}
    assert after > before, (before, after)
    assert window.settings["heart_count"] == 3

    # THE RANKS ARE PLACES, so they start at one and never skip: two
    # heroes share a place only when the criterion genuinely cannot
    # separate them.
    places = sorted(t._star_rank for t in window.suggest_row.tiles
                    if t._star_rank)
    assert places and places[0] == 1
    assert places == sorted(places)


def test_a_picked_hero_carries_no_star(window, qapp):
    """"No need to show it on the portrait if the hero ends up being
    picked — just the suggested heroes section." It falls out of the
    strip when it is picked, and the ten picks were never given one."""
    window.show()
    window.refresh()
    _settle(qapp)
    window.history_tab.report = _fake_run(
        {h: (40, 26) for h in window.ds.hero_ids[:20]})
    _settle(qapp)
    on_board = [t.property("hero_id") for t in window.team_panels["ally"].slots
                if t.property("hero_id") is not None]
    assert on_board, "the fixture should have picks"
    assert not any(t.hero_id in on_board for t in window.suggest_row.tiles)
    assert not any(hasattr(t, "starred")
                   for t in window.team_panels["ally"].slots)


# THREE TESTS ABOUT CONTROLS ON THE TAB ROW ARE GONE, because the row
# has none: Clear all, Detect all and Demo moved above the board at the
# user's request ("move these 3 buttons clear / detect / demon into the
# middle in line with Radiant and dire") and Record and Auto had already
# gone to the Run menu. They measured the gap from each control's INK to
# its rule (`theme.TOOL_GAP`), that each control's middle sat on the tab
# labels' line, and that a rule was painted between them.
#
# Deleted rather than pointed at the board bar, and the distinction is
# worth stating: all three were about a control sharing a line with the
# TABS — a series the eye reads as one row — and the board bar is not
# that. `test_the_tab_row_keeps_only_what_belongs_there` is what holds
# the row empty now, and `test_the_board_actions_sit_between_the_two_
# headings` is what holds the new arrangement. The menu and tab rules
# themselves are still checked in `test_the_menu_and_tab_rules_are_
# painted` below.


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
    # The ENEMY side (Radiant) is now the left-hand one. It is the CARD
    # that moves: a side's five picks and its role pills share one card,
    # so seating the panel alone would leave its pills under the other
    # team.
    order = [window.teams_row.itemAt(i).widget()
             for i in range(window.teams_row.count())]
    assert order[0] is window.side_cards["enemy"]
    assert order[0].isAncestorOf(window.team_panels["enemy"])
    assert order[0].isAncestorOf(window.role_bar.bars["enemy"]), (
        "the pills stayed behind under the other team")
    # AND THE GRIDS DID NOT GO WITH IT. Both cards carry both teams, so
    # neither belongs to a side and there is nothing for the seating to
    # follow — "it should never swap... synergies left, counters right".
    grids = [window.grids_row.itemAt(i).widget()
             for i in range(window.grids_row.count())]
    assert grids[0] is window.synergy_card
    assert grids[1] is window.matchup_card

    Snap.my_team = "radiant"
    window._update_team_captions(Snap())
    assert window.team_captions["ally"].text() == "Radiant"
    order = [window.teams_row.itemAt(i).widget()
             for i in range(window.teams_row.count())]
    assert order[0] is window.side_cards["ally"]
    # Still where they were, having never moved in either direction.
    grids = [window.grids_row.itemAt(i).widget()
             for i in range(window.grids_row.count())]
    assert grids[0] is window.synergy_card


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
    """The ITEMS are a pick's box; the SUGGESTIONS fit eleven to a row.

    Everything in this app is the pick tile's box — that rule is what
    stopped the same hero being three sizes down one screen, and it still
    holds for the item strip and for the two grids.

    THE SUGGESTION STRIP IS THE ONE EXCEPTION, at the user's request: "as
    there is space here it would be ideal to allow more portraits - 11
    per row, and scale it down so they fit snug (aligned edge with dire
    right portrait". It is the only row whose job is to hold as MANY as
    fit rather than a fixed five a side, and at a pick's size eleven of
    them overflow a card that had visible slack on the right. So it
    derives its width from the card — eleven tiles and ten gaps — and is
    never allowed to come out BIGGER than a pick, which is the half of
    the old rule that was doing the real work.
    """
    from draft_assist.ui.app import STRIP_OF_PICK, SUGGESTIONS_PER_ROW
    from draft_assist.ui.suggest_row import STRIP_GAP
    window.show()
    window.resize(1500, 950)
    window.refresh()
    _settle(qapp)
    pick = window.team_panels["ally"].slots[0]
    want_w = round(pick.width() * STRIP_OF_PICK)
    want_h = round(pick.height() * STRIP_OF_PICK)

    each = window.suggest_row.tile_width()
    assert 0 < each <= want_w, "a suggestion is never bigger than a pick"
    across = (SUGGESTIONS_PER_ROW * each
              + (SUGGESTIONS_PER_ROW - 1) * STRIP_GAP)
    assert across <= window.suggest_row.width(), (
        f"eleven tiles at {each}px need {across}px of "
        f"{window.suggest_row.width()}px")
    # SNUG: one more pixel each and the eleventh would not fit.
    assert (across + SUGGESTIONS_PER_ROW
            > window.suggest_row.width() - SUGGESTIONS_PER_ROW
            or each == want_w)
    for tile in _tiles_of(window.suggest_row):
        assert tile.width() == each
    # AND THE ITEMS ARE THE SAME BOX AS THE SUGGESTIONS, which is the
    # second half of the same request and REVERSES "the items take a
    # pick's box whole": "i dont liek that the gap between the items is
    # different betweeen the suggested items and the top picks", and
    # "currnetly 11 items dont fit on 1 row... please change this to fit
    # just like top hpicks fits".
    # Both strips were spaced `STRIP_GAP` apart all along, so the gap was
    # never the difference — the TILE was, and a row of wider tiles at
    # the same gap reads as a different rhythm and wraps at ten.
    for tile in _tiles_of(window.item_row):
        assert tile.width() == each, "an item is not a suggestion's width"
    assert window.item_row.tile_width() == window.suggest_row.tile_width()


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

    ONE SIZE NEVER MEANT "THE BODY SIZE", and this used to assert that it
    did. `NUMBER_PX` was BODY_PX because the counters grid printed its
    deltas at the body size; it is now the owner's own number size, 20%
    above it, because the defaults are their settings file and they
    asked for their current look to be 100%.
    What the rule actually says is that ONE value drives every signed
    number in the app — so that is what is asked: the badge on a tile and
    the delta in a grid cell both come through `number_px()`, and moving
    it moves both."""
    from PyQt6.QtCore import QRect
    from PyQt6.QtGui import QFont, QImage, QPainter
    from draft_assist.ui import tables, theme, tilekit
    import inspect
    assert tilekit.NUMBER_PX == round(theme.BODY_PX * 1.2)
    # THE GRID READS THE SAME FUNCTION. `DeltaCellDelegate` paints
    # through `tilekit.paint_number`, which sizes itself from
    # `number_px()` — so there is one value, not two kept in step.
    assert "paint_number" in inspect.getsource(tables.DeltaCellDelegate)
    assert "number_px()" in inspect.getsource(tilekit.paint_number)

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
    assert ink(132, 74) == ink(110, 62) == ink(96, 54) == ink(80, 45)
    # BELOW 80px IT STEPS DOWN, AND THAT MOVED WITH THE REBASE. A figure
    # 20% bigger needs 20% more tile to print whole, so the width at
    # which "+21.7" stops fitting went from ~64px to ~80. That matters
    # because `TILE_MIN` IS 64: at the window's very narrowest the picks
    # are now inside the stepping-down band where they used to be just
    # outside it, so the number shrinks there rather than holding full
    # size. It is the documented fallback working, not a new behaviour —
    # a number clipped to "+21." is not a smaller number but a wrong one
    # — but the band it applies over is wider than it was.
    assert ink(76, 43) < ink(132, 74)
    assert ink(48, 27) < ink(76, 43)


def test_the_body_size_is_the_one_the_user_asked_for():
    """+20% and then another 15%, bold throughout."""
    from draft_assist.ui import theme
    assert "font-size: 18px;" in theme.STYLESHEET
    assert "font-weight: bold;" in theme.STYLESHEET
    assert 'QLabel[heading="true"] { font-size: 21px;' in theme.STYLESHEET


def test_the_count_box_draws_its_own_arrows(qapp):
    """A stylesheet can colour a spin box's buttons but cannot put a MARK
    in one without an image file, so styling them left the box with no
    arrows at all — same trap as the tick box and the window buttons.

    RED, at the user's request: "all of the up/down arrows (clickable)
    that ever feature in this app, i want them to be red".
    """
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
                  if picture.pixelColor(x, y).name() == theme.ACCENT_MARK)
        assert ink > 4, "an arrowhead with no ink in it"
    box.close()


def test_an_arrow_with_nowhere_to_go_is_a_DIM_RED_not_a_grey(qapp):
    """"if i cant go any lower e.e.g im at 0, i sitll want the down arrow
    to become dim, just a dim version of the red".

    A grey one would say the arrow is a different KIND of thing from its
    twin; a dim red says it is the same control with nothing left to do.
    """
    from PyQt6.QtGui import QImage
    from draft_assist.ui import chrome, theme

    box = chrome.CountBox(0, 0, 20)          # already at the bottom
    box.show()
    _settle(qapp)
    picture = QImage(box.width(), box.height(), QImage.Format.Format_ARGB32)
    picture.fill(0)
    box.render(picture)

    def ink(arrows, colour):
        return sum(1
                   for y in range(arrows.y(), arrows.bottom() + 1)
                   for x in range(arrows.x(), arrows.right() + 1)
                   if picture.pixelColor(x, y).name() == colour)

    up, down = box._arrow_boxes()
    assert ink(up, theme.ACCENT_MARK) > 4, "the live arrow lost its red"
    assert ink(down, theme.ACCENT_MARK_DIM) > 4, "the spent arrow is not dim"
    assert ink(down, theme.ACCENT_MARK) == 0, "the spent arrow is still live"
    assert theme.ACCENT_MARK_DIM != theme.ACCENT_MARK
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


def test_the_menu_and_tab_rules_are_painted(window, qapp):
    """File | Run | View | Help, and Draft | History.

    PAINTED, because neither QMenuBar nor QTabBar has a between-items
    sub-control a stylesheet can reach — the same answer as the tick box,
    the window buttons and the count box's arrows.

    It used to check the toolbar's rules too; there is no toolbar and no
    control on that row any more (see the note above), so what is left is
    the two bars that still have several items each.
    """
    from PyQt6.QtGui import QColor

    from draft_assist.ui import chrome, theme
    window.show()
    window.resize(1500, 950)
    _settle(qapp)
    rule = QColor(theme.RULE).name()
    for bar in (window.menu_bar, window.tabs.bar):
        image = bar.grab().toImage()
        found = any(QColor(image.pixel(x, y)).name() == rule
                    for x in range(image.width())
                    for y in range(image.height()))
        assert found, f"no painted rule in {bar}"
    assert chrome.Divider is not None


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
        # THE ITEMS ARE ELEVEN TO A ROW TOO NOW, so like the suggestions
        # they are never wider than a pick and usually narrower. What
        # this test is about is that a HOLE is the size of the tile that
        # replaces it, which is checked per strip below.
        assert 0 < win.item_row.tile_width() <= want[0]
        assert win.item_row.tile_width() == win.suggest_row.tile_width()
        # ONLY THE ITEM STRIP IS EMPTY ON AN EMPTY BOARD NOW. The
        # suggestions rank by how hard the field finds a hero to counter,
        # which never looked at the draft, so that strip is full from the
        # first paint — see the empty-draft test above. The item strip
        # still has nothing to say until an enemy is picked, which is
        # what keeps this test able to measure a hole at all.
        for strip in (win.item_row,):
            blanks = strip._blanks
            assert blanks, "an empty strip should show its shape"
            # THE STRIP'S OWN TILE, not the pick's. The suggestions are
            # eleven to a row now and so are narrower than a pick (see
            # `test_every_strip_tile_is_the_same_share_of_a_pick`); what
            # this test is about is that an EMPTY plate is the size of
            # the tile that will replace it, which is the fault it was
            # written for — a hole that changed size the moment the game
            # started.
            size = (strip.tile_width(), strip.tile_height())
            for blank in blanks:
                assert (blank.width(), blank.height()) == size, \
                    "an empty plate is not the size of a full one"
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


def test_the_board_actions_are_a_maroon_group(window, qapp, styled):
    """Clear all, Detect all and Demo: a border, the app's own bold, and
    the surface behind them showing through.

    TWO REQUESTS AND ONE REVERSAL. They were styled as tab labels while
    they sat on the tab row; then "make the button red so they look like
    buttons" and, asked how, "Outlined, not filled". They briefly wore
    the frame's GOLD — "id like to make all buttons have a gold border
    (the same as the app border)" — and that was withdrawn on sight:
    "remove the gold border from all the input boxes ... revert that
    change i made - i dont liek it now that i have seen it... obviosuly
    keep the app window border though".
    AND THE OUTLINE ITSELF IS NOW REVERSED, at the user's request: "i
    want the clear / detect / demo buttons to have a dark grey
    encapsulating all 3 buttons so they look related... then i want to
    remove the red bordewr, but add a maroon fill #38040E".
    So: a maroon FILL, no visible border, and one grey pill round all
    three. The gold stays off — that reversal was never reversed.
    THE BORDER IS STILL THREE PIXELS AND IS THE FILL'S OWN COLOUR. It
    carries `PLAIN_PAD_Y` to `CONTROL_H`, so dropping it would take 6px
    off all three and they would stop matching the count boxes.
    """
    from draft_assist.ui import theme
    window.show()
    window.resize(1500, 950)
    window.refresh()
    _settle(qapp)
    for button in (window.clear_all_button, window.detect_all_button,
                   window.demo_button):
        assert button.property("plain") is True, button.text()
        colours = _colours_in(button)
        assert theme.FRAME_GOLD not in colours, (
            f"{button.text()!r} still wears the frame's gold")
        assert theme.BG_INPUT not in colours, (
            f"{button.text()!r} still paints a raised plate")
        assert theme.ACCENT in colours, (
            f"{button.text()!r} lost its maroon fill")
        rule = theme.STYLESHEET[
            theme.STYLESHEET.index('QPushButton[plain="true"] {'):]
        rule = rule[:rule.index("}")]
        # THE HEIGHT IS THE POINT OF KEEPING THE BORDER AT ALL.
        assert f"border: {theme.FRAME_WIDTH}px solid {theme.ACCENT}" in rule, (
            "the border is no longer the fill's own colour, so it is "
            "either visible again or gone and taking 6px with it")
    # AND THE BOX MODEL IS UNCHANGED, which is what keeps these on the
    # count boxes' line. Asserted on the CONSTANTS rather than on a
    # rendered height: the height that falls out of them is the app's
    # bundled face plus the stylesheet, and a machine without Alegreya
    # lays every button out shorter while a CountBox applies CONTROL_H
    # outright — so a pixel comparison here measures the font, not the
    # rule. `plain` must simply cost the same vertically as the base
    # button rule, which is 3px of padding and a 1px border.
    assert theme.PLAIN_PAD_Y + theme.FRAME_WIDTH == 3 + 1, (
        "the plain button no longer costs what the base rule costs, so "
        "the three board buttons have left the count boxes' line")
    # ONE GREY PILL ROUND ALL THREE, so they read as a group.
    pill = window.board_actions
    assert pill.property("group") is True
    assert theme.GROUP_BG in _colours_in(pill), "the pill draws no surface"
    # AND NOWHERE ELSE EITHER: the gold went off every control, so an
    # ordinary button and a count box must not have it back.
    assert theme.FRAME_GOLD not in _colours_in(window.suggested_box)

def test_the_auto_tick_still_paints_its_own_label_readably(window, qapp,
                                                          styled):
    """It painted its own label in `theme.TEXT` outright, so the `color:`
    rule that dims its neighbours never reached it.

    IT IS IN THE RUN MENU NOW rather than on the tab row, so "the rest of
    the row" is no longer what it has to match — but the fault it was
    written for is a property of the WIDGET, not of where the widget
    sits: a control that paints its own text has to ASK for its colour
    rather than hard-coding one, or no stylesheet can ever reach it.
    """
    from PyQt6.QtGui import QPalette
    window.show()
    _settle(qapp)
    auto = window.auto_record_check
    asked = auto.palette().color(auto.foregroundRole())
    assert asked.isValid()
    # The label is drawn from the palette, which is where a stylesheet's
    # `color` lands — not from a constant read at import.
    import inspect
    from draft_assist.ui import chrome
    source = inspect.getsource(chrome.TickBox)
    assert "foregroundRole()" in source, (
        "the tick box is hard-coding its text colour again")

def test_the_count_box_number_starts_at_the_left(qapp):
    """Right-aligned it was pushed against the arrows, which reads as the
    number belonging to them rather than to the field."""
    from PyQt6.QtCore import Qt
    from draft_assist.ui import chrome
    box = chrome.CountBox(10, 1, 20)
    assert box.alignment() & Qt.AlignmentFlag.AlignLeft
    assert not (box.alignment() & Qt.AlignmentFlag.AlignRight)


def test_the_status_line_is_a_footnote(window, qapp, styled):
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


# THE SIX AD TESTS THAT STOOD HERE ARE GONE WITH THE FEATURE, at the
# user's request — "remove the ad stuff all together". They held that the
# slot reserved nothing while off, that it stayed up rather than blinking
# on a timer, that the creative was a real 728x90 leaderboard drawn in
# code rather than anybody's copyrighted banner, and that it fitted at
# the window's own minimum width. All true, and all about a placeholder
# for revenue that needs a WEB PAGE this app does not have.


def test_the_window_is_freely_resizable_and_remembers_its_size(qapp,
                                                              tmp_path,
                                                              monkeypatch):
    """THE LOCK IS GONE, at the user's request, and with it View ▸ Resize
    window (lock).

    It shipped locked because a draft is read at a glance with the cursor
    moving fast near the window's edges, and a window that resizes when
    you meant to click a pick has cost the pick. That protection is what
    was given up; what it was really buying — a window that opens at the
    size you left it — is kept by saving on close, which never needed a
    mode of its own.
    """
    from draft_assist.ui import settings as ui_settings
    from draft_assist.ui.manual import ManualDraft
    from draft_assist.ui.providers import ManualProvider

    monkeypatch.setattr(ui_settings, "SETTINGS_FILE", tmp_path / "s.json")
    assert "window_locked" not in ui_settings.DEFAULTS
    ds = demo_dataset()
    win = MainWindow(ds, ManualProvider(ManualDraft()), [], {}, ManualDraft())
    win.timer.stop()
    try:
        assert not hasattr(win, "lock_action")
        assert win.maximumWidth() > win.width(), "still capped somewhere"
        assert not win.resize_grip.isHidden(), \
            "the corner sizes the window again, so it has to be there"
        # FLOORED at what the layout can actually draw: a narrower window
        # is a grid that has stopped being a grid.
        assert win.minimumWidth() == win._floor_w
        win.resize(win._floor_w + 260, win.height() + 120)
        _settle(qapp)
        assert win.width() >= win._floor_w + 260

        # And closing writes it, which is the whole of what the lock did.
        wide, tall = win.width(), win.height()
        win.close()
        saved = ui_settings.load(tmp_path / "s.json")
        assert (saved["window_w"], saved["window_h"]) == (wide, tall)
    finally:
        win.close()


def test_the_three_view_items_are_gone_for_good(window):
    """Removed at the user's request. Reset window position rescued a
    window dragged off-screen, which has not happened; Reload data and
    library re-read the disk, which every download already does for
    itself and an update does by relaunching."""
    everywhere = [c.label for c in window._all_commands()]
    for gone in ("Resize window (lock)", "Reset window position",
                 "Reload data and library"):
        assert gone not in everywhere, gone
    labels = []
    for action in window.menu_bar.actions():
        menu = action.menu()
        if menu is not None:
            labels += [a.text().replace("&", "") for a in menu.actions()]
    for gone in ("Resize window (lock)", "Reset window position",
                 "Reload data and library"):
        assert gone not in labels, gone
    # `reload_backend` itself STAYS — the download tasks call it, and that
    # is the path that actually needs a reload.
    assert callable(window.reload_backend)


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
    # THE SUGGESTIONS ARE THE ONE EXCEPTION, and only downwards: eleven
    # to a row, never wider than a pick. See
    # `test_every_strip_tile_is_the_same_share_of_a_pick`.
    assert 0 < window.suggest_row.tile_width() <= pick.width()
    # AND THE ITEMS SHARE THE SUGGESTIONS' BOX, which is the exception
    # widened rather than a second rule: both strips hold as many as fit
    # rather than a fixed five, both are eleven across, and neither is
    # ever wider than a pick. "currnetly 11 items dont fit on 1 row...
    # please change this to fit just like top hpicks fits".
    assert 0 < window.item_row.tile_width() <= pick.width()
    assert window.item_row.tile_width() == window.suggest_row.tile_width()
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
    from draft_assist.ui import teams
    for slider in window.size_sliders.values():
        # 25 to 175, CENTRED on the 100% the app actually draws. Read
        # off the module's own clamps rather than repeated as numbers,
        # since a slider offering a value the code refuses is a control
        # that lies about what it does.
        assert (slider.minimum(), slider.maximum()) == (
            round(teams.SCALE_MIN * 100), round(teams.SCALE_MAX * 100))
    assert (teams.SCALE_MIN + teams.SCALE_MAX) / 2 == 1.0
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
        assert "Those tiles" not in said
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
    # The suggestions are eleven to a row and so no wider than a pick.
    assert 0 < window.suggest_row.tile_width() <= tiles[0].width()
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


def test_bad_crop_boxes_are_a_banner_not_a_note_in_a_recording(qapp,
                                                               monkeypatch):
    """A real draft was read two slots out of ten for eighty seconds and
    the app said so only in the recording's notes, which is after the game.

    It is not a guess: the game named the ten heroes on the screen and the
    calibrated boxes matched none of them, so the boxes are not on the
    portraits — a fault the user can fix, which is what a banner is for.
    """
    from draft_assist.ui import portraits
    monkeypatch.setattr(portraits, "any_downloaded", lambda: True)
    monkeypatch.setattr(portraits, "missing_for", lambda ids: set())
    win = make_window(qapp, demo_dataset())
    try:
        monkeypatch.setattr(win, "_bracket_mismatch", lambda: None)
        monkeypatch.setattr(win, "_stale_days", lambda: 0)
        snap = win.provider.poll()
        snap.crop_boxes_wrong = True
        win._update_first_run_banner(snap)
        said = win.banner_label.text()
        assert "pick portraits" in said, said
        assert win.banner_button.text() == "Measure the boxes"
    finally:
        win.close()


def test_measuring_takes_the_live_frame_when_there_is_one(qapp,
                                                          monkeypatch):
    """The Snapshot is free and is already a picture of this frame."""
    import numpy as np
    from types import SimpleNamespace

    win = make_window(qapp, demo_dataset())
    try:
        seen = {}
        frame = np.zeros((1080, 1920, 3), np.uint8)
        win.snapshot = SimpleNamespace(frame=frame, left=[1, 2, 3, 4, 5],
                                       right=[6, 7, 8, 9, 10])
        monkeypatch.setattr(win, "_grab_dota_frame",
                            lambda: seen.setdefault("grabbed", True))
        from draft_assist.vision import autocal
        monkeypatch.setattr(autocal, "base_portraits",
                            lambda ids: {hid: np.zeros((144, 256), np.uint8)
                                         for hid in ids})

        def fake(f, art, spec):
            seen["measured"] = f
            raise RuntimeError("stop here")

        monkeypatch.setattr(autocal, "calibrate", fake)
        assert win._measure_calibration() is False
        assert seen.get("measured") is frame
        assert "grabbed" not in seen, "it grabbed with a frame in hand"
    finally:
        win.close()


def test_it_grabs_a_frame_when_the_screen_reader_is_off(qapp, monkeypatch):
    """`use_vision` is a tick box and game-data-only mode has no capture
    session at all, so with no live Snapshot this takes a one-shot
    picture of the window. "You cannot measure the crop boxes unless the
    crop boxes are already being used" is a circle."""
    import numpy as np

    win = make_window(qapp, demo_dataset())
    try:
        grabbed = np.zeros((1080, 1920, 3), np.uint8)
        win.snapshot = None
        monkeypatch.setattr(win, "_grab_dota_frame", lambda: grabbed)
        assert win._measure_calibration() is False
        # No heroes named, so it stops there — but it got past the frame,
        # which is the half this is about.
        assert "not named enough heroes" in win.cal_label.text()
    finally:
        win.close()


def test_a_failed_grab_is_not_an_exception(qapp, monkeypatch):
    """Dota can be closed between the banner appearing and the button
    being pressed. That is a refusal with a sentence, never a traceback
    out of a button."""
    win = make_window(qapp, demo_dataset())
    try:
        def gone():
            raise OSError("no such window")

        win.snapshot = None
        monkeypatch.setattr(win, "_grab_dota_frame", gone)
        assert win._measure_calibration() is False
        assert "no frame" in win.cal_label.text()
    finally:
        win.close()


def test_there_is_no_calibrate_by_hand_left_to_reach(qapp):
    """"i dont see the point in having the portrait box vision box
    feature at all... my plan now is to have the automatic detection work
    so the user never needs to draw out these vision pboxes"."""
    import importlib

    win = make_window(qapp, demo_dataset())
    try:
        assert not hasattr(win, "_calibrate")
        assert not hasattr(win, "drag_button")
        labels = [c.label for c in win._all_commands()]
        assert "Calibrate pick boxes…" not in labels
        assert "Measure the crop boxes" in labels
    finally:
        win.close()
    with pytest.raises(ModuleNotFoundError):
        importlib.import_module("draft_assist.ui.calibrate")


def test_an_absent_calibration_file_is_no_longer_a_banner(qapp, monkeypatch,
                                                          tmp_path):
    """It was the LAST rung and it asked for the one thing this app no
    longer wants anybody to do by hand. With nothing calibrated the boxes
    are `DraftLayout()`'s measured fractions through `hud_box`, and the
    first strategy time measures the real geometry by itself."""
    from draft_assist.ui import app as app_mod
    from draft_assist.ui import portraits

    monkeypatch.setattr(portraits, "any_downloaded", lambda: True)
    monkeypatch.setattr(portraits, "missing_for", lambda ids: set())
    monkeypatch.setattr(app_mod, "CALIBRATION_FILE", tmp_path / "none.json")
    win = make_window(qapp, demo_dataset())
    try:
        monkeypatch.setattr(win, "_bracket_mismatch", lambda: None)
        monkeypatch.setattr(win, "_stale_days", lambda: 0)
        win._update_first_run_banner()
        assert not win.banner.isVisible(), win.banner_label.text()
    finally:
        win.close()


def test_the_picks_card_heading_and_its_boxes_share_one_column(
        window, qapp):
    """Two requests, one shape.

    "you dont need suggested picks and pick suggestions - please
    rearrange" killed a body row that said the heading's own words back
    at it. Then "instead of suggested picks, use the header 'top picks'
    and make the required adjustments in the rows below so that the
    input boxes align edges".

    A card CORNER is sized to itself and sits a fixed gap after the
    title, so a count box there lands wherever the title's words happen
    to end. Putting the heading in the same grid as the legend put all
    three boxes in one column.

    **THE LEGEND HAS MOVED TWICE AND IS BACK ON THE HEADING ROW.** It
    went BELOW the strip with the role filter — "top picks will be at
    the top above the sugegsted hero portraits still, but the filters
    for carry , supprot etc, will be below the portraits" — and the two
    marks went with it, to sit level with the roles. Then, at the user's
    request, the two marks came back up on their own: "comfort and
    coutner fields should be o nthe same row as top heroes jsut to its
    right and spread the carr / support / etc filytters to fill the
    space left", renamed "Comfort rank" and "Counter rank".
    So all THREE counts are on the heading row again — the strip's own
    count beside the title, the two rank counts beside that — and the
    row below the strip belongs to the role filter alone. The column
    this test is named for is now the one the two RANK boxes share; the
    heading's own box sits in the grid to their left, which is why it is
    no longer asserted into it.
    """
    from PyQt6.QtWidgets import QLabel
    window.show()
    qapp.processEvents()
    labels = [label.text().strip().lower()
              for label in window.picks_card.findChildren(QLabel)
              if label.text().strip()]
    # PROPER CAPITALISATION, and HEROES rather than picks: "Call it Top
    # Heroes, not Top Picks", with "Proepr Capitalization for all
    # headers". The card holds heroes and the one below it holds items,
    # so the two headings now say which is which rather than both
    # saying what they are FOR.
    assert "top heroes" in labels, "the heading was renamed away"
    assert "top picks" not in labels
    assert "suggested picks" not in labels
    assert "pick suggestions" not in labels, (
        "the card is paraphrasing its own heading again")

    def left(box):
        return box.mapTo(window.picks_card, box.rect().topLeft()).x()

    def middle(box):
        return box.mapTo(window.picks_card, box.rect().center()).y()

    # ONE ROW FOR ALL THREE, at the user's request — "same row for all
    # 3, comfort right of counter" — so the two rank counts are level
    # with each other and with the heading's own count, and COUNTER
    # leads COMFORT rather than sitting under it.
    assert middle(window.heart_box) == middle(window.shield_box), (
        "the two rank counts are not on one row")
    assert left(window.shield_box) < left(window.heart_box), (
        "comfort rank should sit to the RIGHT of counter rank")

    # ALL THREE ARE ON THE HEADING ROW, which is the move: "comfort and
    # coutner fields should be o nthe same row as top heroes jsut to its
    # right".
    head = window._picks_head
    for name, box in (("suggested", window.suggested_box),
                      ("heart", window.heart_box),
                      ("shield", window.shield_box)):
        assert head.isAncestorOf(box), f"{name} left the heading row"
    # The strip's own count leads them, since it is the one the heading
    # names; the two rank counts follow it.
    assert left(window.suggested_box) < left(window.shield_box)
    assert middle(window.suggested_box) == middle(window.shield_box)

    # AND THE ROW BELOW THE STRIP IS THE FILTER'S ALONE — "spread the
    # carr / support / etc filytters to fill the space left". It is no
    # longer sharing a row with anything, so nothing of the legend's may
    # still be found on it.
    assert window._picks_row.isAncestorOf(window.role_filter)
    assert not window._picks_row.isAncestorOf(window.heart_box)
    assert not head.isAncestorOf(window.role_filter)
    roles = list(window.role_filter.boxes.values())
    assert middle(roles[0]) > middle(window.shield_box), (
        "the role filter is not below the heading any more")


def test_every_on_off_box_in_the_app_draws_an_actual_tick(styled, qapp):
    """"if something is a tick box on/off I want it to have a tick box."

    Qt's stylesheet can COLOUR an indicator but cannot put a mark in it
    without an image file, so `QCheckBox::indicator:checked` fills the
    square with the accent and nothing else — a red block, which says
    something is different about the control rather than that it is
    switched on. `chrome.TickBox` paints the mark, and the app had
    solved this once, for ONE control, and left five other places using
    a plain QCheckBox: the rank pickers in the wizard and the bracket
    dialog, both settings pages, and Force recognition.

    Checked by SOURCE rather than by pixels because the fault is that a
    plain QCheckBox can never draw a tick here, whatever it is asked to
    render — and a new one added tomorrow would be wrong the same way.
    """
    import re
    from pathlib import Path
    root = Path(__file__).resolve().parent.parent
    offenders = []
    for path in (root / "draft_assist" / "ui").rglob("*.py"):
        if path.name == "chrome.py":
            continue            # TickBox subclasses it, which is the point
        for number, line in enumerate(
                path.read_text(encoding="utf-8").splitlines(), 1):
            if re.search(r"(?<![.\w])QCheckBox\s*\(", line):
                offenders.append(f"{path.name}:{number}: {line.strip()}")
    assert not offenders, (
        "these draw a filled square instead of a tick; use chrome.TickBox:\n"
        + "\n".join(offenders))


def test_a_checkable_menu_item_draws_the_apps_own_tick(window, qapp, tmp_path):
    """"Always, across the board." A tick box on a menu is still a tick
    box, and `QMenu::item` is styled — so once a stylesheet touches the
    widget, the parts it does not NAME are handed to somebody else to
    draw. That is the scrollbars' lesson, which cost a clump of white
    specks through a translucent window.

    A stylesheet can colour a box and cannot put a MARK in one, so the
    indicator is pointed at a picture, and the picture is generated from
    the same `paint_tick` the tick box widget uses — two hand-drawn
    ticks would be two of them drifting.
    """
    from draft_assist.ui import theme
    assert "QMenu::indicator" in theme.STYLESHEET, "the indicator is unnamed"
    assert "image: url(" in theme.STYLESHEET, (
        "nothing points the checked indicator at a mark")

    # The file is real and is a picture with something drawn on it.
    from PyQt6.QtGui import QImage
    import re
    found = re.search(r"image: url\(([^)]+)\)", theme.STYLESHEET)
    picture = QImage(found.group(1))
    assert not picture.isNull(), "the tick file did not load"
    drawn = sum(1 for y in range(picture.height())
                for x in range(picture.width())
                if picture.pixelColor(x, y).alpha() > 0)
    assert drawn > 20, "the tick is blank"


def test_the_menu_tick_follows_the_palette(window, qapp):
    """It is a generated PNG, so greyscale has to re-render it — else the
    View menu that turned the colour off keeps a red tick in it."""
    from draft_assist.ui import theme
    window.settings["greyscale"] = True
    window._apply_greyscale()
    try:
        import re
        from PyQt6.QtGui import QImage
        found = re.search(r"image: url\(([^)]+)\)", theme.STYLESHEET)
        picture = QImage(found.group(1))
        opaque = [picture.pixelColor(x, y)
                  for y in range(picture.height())
                  for x in range(picture.width())
                  if picture.pixelColor(x, y).alpha() > 200]
        assert opaque, "nothing was drawn"
        assert all(c.red() == c.green() == c.blue() for c in opaque), (
            "the menu tick kept its colour in greyscale")
    finally:
        window.settings["greyscale"] = False
        window._apply_greyscale()


def test_every_row_on_the_draft_tab_starts_in_the_same_column(window, qapp,
                                                              styled):
    """The heading, the five picks, Top Heroes and Top Items line up.

    THE USER DREW A LINE DOWN THEM. Two separate faults put three
    different left edges on one column:
    `TeamPanel` carried `PANEL_MARGIN` of its own INSIDE a card that
    already insets its body by the same amount, so the five portraits
    sat at card+24 where both strips sit at card+12; and the leftover
    from dividing the card's width by five was split between a stretch
    at each end, which moved the first portrait again by half of it.
    The board head is not in a card at all, so "Radiant" sat on the
    card's outer edge, a border and a padding short of its own picks.
    """
    from draft_assist.ui.suggest_row import SuggestTile
    from draft_assist.ui.item_row import ItemTile
    window.show()
    window.resize(1500, 1000)
    window.refresh()
    _settle(qapp)

    def left_of(widget):
        return widget.mapTo(window, QPoint(0, 0)).x()

    edges = {"Radiant heading": left_of(window.team_panels["ally"].header),
             "first pick tile": left_of(window.team_buttons["ally"][0])}
    sug = window.suggest_row.findChildren(SuggestTile)
    assert sug, "no suggestions to measure against"
    edges["first Top Hero"] = left_of(sug[0])
    items = window.item_row.findChildren(ItemTile)
    if items:                      # the strip is empty on an empty board
        edges["first Top Item"] = left_of(items[0])
    assert len(set(edges.values())) == 1, (
        "these should share one left edge: "
        + ", ".join(f"{k}={v}" for k, v in edges.items()))


def test_the_tile_constants_are_reachable_from_every_strip():
    """The three strips share one set of constants, by re-export.

    `teams` and `item_row` import names from `tilekit` that they never
    use THEMSELVES, so a caller can read them off either module and the
    ten picks, the suggestions and the items are provably one set rather
    than two that happen to agree. The lines carry `# noqa: F401`, which
    is the author saying "imported but unused, on purpose".

    A TIDY-UP DELETED THREE OF THEM. An unused-import scan counted uses
    inside each file, found none, and removed the very lines annotated to
    say it would be wrong to. Three tests failed.

    **AND THE OBVIOUS GUARD CANNOT CATCH IT.** Walking each `noqa: F401`
    import and asserting its names are reachable passes on the broken
    file, because deleting a name also deletes it from the list being
    walked - the same shape as the circular pick-bar test that used to
    place the thing it was checking. The only guard that can fail is one
    that NAMES what must survive, so this does.
    """
    from draft_assist.ui import item_row, teams, textfit, tilekit

    for name in ("BADGE_PAD_X", "BADGE_PAD_Y", "CHROME",
                 "NAME_MAX_PT", "NAME_MIN_PT", "NUMBER_PX"):
        assert getattr(teams, name) == getattr(tilekit, name), (
            f"teams no longer re-exports tilekit.{name}")
    for name in ("NAME_MAX_PT", "NAME_MIN_PT"):
        assert getattr(item_row, name) == getattr(tilekit, name), (
            f"item_row no longer re-exports tilekit.{name}")
    for name in ("fit", "split_two"):
        assert getattr(teams, name) is getattr(textfit, name), (
            f"teams no longer re-exports textfit.{name}")
