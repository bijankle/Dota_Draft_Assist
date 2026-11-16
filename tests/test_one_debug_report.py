"""The Debug tab has ONE report button, and it carries everything.

At the user's request: "a lot of the debugging menu buttons were
developed as i was debuggign and many arent relevant as some bugs were
resolved... please consolidate these buttons and only keep those which
are requried... also, i think that any error reports should be in 1 ...
as in copy to clipboard the whole game log info as text for many
aspects... no point in multiple aspectsd haivbng a button eavchj".

What was there: "Copy everything" on the Live page (status line, the
reading, the tick log, loop timings), "Copy report" beside the session
list (that recording's report), and a zip body in `_diagnostic_text`
carrying the crop boxes that NEITHER of them had. Three descriptions of
one app, and which one you sent depended on which page you were on.
"""

from PyQt6.QtWidgets import QApplication, QPushButton

from draft_assist.config import RULES_FILE
from draft_assist.model import items as items_mod

import pytest


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture()
def window(qapp, monkeypatch, tmp_path):
    from draft_assist.ui import app as ui_app
    from draft_assist.ui.app import MainWindow
    from draft_assist.ui.demo import demo_dataset
    from draft_assist.ui.providers import DemoProvider
    monkeypatch.setattr(ui_app, "RECORDINGS_DIR", tmp_path)
    ds = demo_dataset()
    rules, meta = items_mod.load_rules(RULES_FILE)
    win = MainWindow(ds, DemoProvider(ds), rules, meta)
    win.timer.stop()
    yield win
    win.close()


def buttons(root):
    return [b for b in root.findChildren(QPushButton)]


def test_exactly_one_button_copies_a_report(window):
    """Not "about one" - one. Two was the fault."""
    copiers = [b for b in buttons(window.debug_page)
               if "copy" in b.text().lower()]
    assert len(copiers) == 1, (
        f"{len(copiers)} copy buttons on the Debug tab: "
        f"{[b.text() for b in copiers]}")
    assert copiers[0] is window.copy_log_button


def test_it_is_reachable_from_both_pages(window):
    """A button on the Live page is one you have to leave the recording
    to reach, which is why it sits above both."""
    assert window.copy_log_button.parent() is not None
    assert window.copy_log_button not in buttons(window.debug_tabs)
    assert window.copy_log_button in buttons(window.debug_page)


def test_the_one_paste_is_the_superset(window, tmp_path):
    """Everything the two buttons and the zip body carried between them."""
    folder = tmp_path / "2026-11-16_1200"
    (folder / "gsi").mkdir(parents=True)
    (folder / "state.jsonl").write_text("")
    window._refresh_sessions()
    window._copy_debug_log()
    paste = QApplication.clipboard().text()
    for wanted in (
            "Dota Draft Assist",      # the header
            "screen layout in use",   # was ONLY in the emailed zip
            "status:",                # was only on the Live page
            "loop timings",           # was only on the Live page
            "what the app is reading",
            "2026-11-16_1200",        # was only behind "Copy report"
    ):
        assert wanted in paste, f"the one paste dropped {wanted!r}"


def test_the_zip_and_the_clipboard_share_one_body(window):
    """They described different things, which is how the crop boxes -
    the commonest cause of a bad draft - ended up in whichever one
    nobody had sent."""
    body = window._diagnostic_text()
    window._copy_debug_log()
    paste = QApplication.clipboard().text()
    assert body in paste, "the clipboard is not built from the zip's body"


def test_no_button_opens_what_another_button_already_opens(window):
    """Three folder-openers and a tab that opened itself.

    "Recordings" opened the recordings folder, which lives INSIDE the
    debug folder that "Open debug folder" opens; "Report" refreshed the
    session list and switched to Debug > Recordings, which is what
    clicking that tab does.
    """
    labels = [b.text() for b in buttons(window)]
    for gone in ("Recordings", "Report", "Copy report",
                 "Replay this session"):
        assert gone not in labels, f"{gone} is back"
    assert not hasattr(window, "report_button")
    assert not hasattr(window, "open_recordings_button")
    assert not hasattr(window, "refresh_sources_button")


def test_opening_a_debug_page_refreshes_it(window, tmp_path):
    """What replaced the two Refresh buttons: both answered "something
    changed while I was looking elsewhere", and the moment that matters
    is the moment the page comes up."""
    folder = tmp_path / "2026-11-16_1300"
    (folder / "gsi").mkdir(parents=True)
    (folder / "state.jsonl").write_text("")
    # Nothing has listed it yet.
    window.sessions = []
    window.session_list.clear()
    window._debug_page_changed(1)
    assert [f.name for f in window.sessions] == ["2026-11-16_1300"]
    assert window.session_list.count() == 1


def test_the_refresh_keeps_the_recording_you_were_reading(window, tmp_path):
    """The auto-refresh replaced a button, and must not cost the
    selection the button never touched.

    Opening the page rebuilds the list now, so dropping to row 0 would
    move you off the recording you were reading every time you looked
    at Live and came back.
    """
    for name in ("2026-11-14_0900", "2026-11-15_0900", "2026-11-16_0900"):
        folder = tmp_path / name
        (folder / "gsi").mkdir(parents=True)
        (folder / "state.jsonl").write_text("")
    window._refresh_sessions()
    # Newest first, so pick the oldest - the one a reset would lose.
    window.session_list.setCurrentRow(2)
    chosen = window._current_session().name
    assert chosen == "2026-11-14_0900"

    window._debug_page_changed(0)
    window._debug_page_changed(1)
    assert window._current_session().name == chosen


def test_a_recording_that_went_away_falls_back_to_the_newest(window,
                                                             tmp_path):
    for name in ("2026-11-15_0900", "2026-11-16_0900"):
        folder = tmp_path / name
        (folder / "gsi").mkdir(parents=True)
        (folder / "state.jsonl").write_text("")
    window._refresh_sessions()
    window.session_list.setCurrentRow(1)
    import shutil
    shutil.rmtree(tmp_path / "2026-11-15_0900")
    window._refresh_sessions()
    assert window._current_session().name == "2026-11-16_0900"
