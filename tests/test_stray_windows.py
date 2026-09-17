"""The watcher that answers "what was that window?".

It exists because the fault is invisible from here: the report is of a
small, blank, TRANSLUCENT rectangle with the desktop showing through it,
flashing up while the app starts on Windows. Every check this project can
write in Qt's terms already says the Qt side is clean, so what is left is
something only Windows can name.
"""

import time

import pytest
from PyQt6.QtWidgets import QApplication

from draft_assist.config import RULES_FILE
from draft_assist.model import items as items_mod
from draft_assist.ui import strays


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture()
def window(qapp):
    from draft_assist.ui.app import MainWindow
    from draft_assist.ui.demo import demo_dataset
    from draft_assist.ui.providers import DemoProvider
    ds = demo_dataset()
    rules, meta = items_mod.load_rules(RULES_FILE)
    win = MainWindow(ds, DemoProvider(ds), rules, meta)
    win.timer.stop()
    yield win
    win.close()


def test_it_does_nothing_at_all_off_windows():
    """A diagnostic that raises on the development machine is one nobody
    can develop against."""
    watcher = strays.Watcher()
    watcher.sample()
    assert watcher.note == "not Windows"
    assert watcher.seen == {}
    assert watcher.report() == "not Windows"


def test_sampling_never_raises_whatever_windows_answers(monkeypatch):
    """Never fatal: this runs on a timer during startup, and a failed
    diagnostic must not be able to take the app down with it."""
    monkeypatch.setattr(strays.sys, "platform", "win32")
    monkeypatch.setattr(strays.Watcher, "_visible_windows",
                        lambda self: (_ for _ in ()).throw(OSError("boom")))
    watcher = strays.Watcher()
    watcher.sample()
    assert "OSError" in watcher.note and "boom" in watcher.note


def test_a_window_that_came_and_went_is_still_in_the_report(monkeypatch):
    """The whole point. A flash is gone by the time anybody looks, so
    what matters is that it was RECORDED, with how many samples held
    it — one sample being "gone before we looked again"."""
    monkeypatch.setattr(strays.sys, "platform", "win32")
    windows = [[1, 2], [1]]

    def next_sample(self):
        return windows.pop(0) if windows else [1]

    monkeypatch.setattr(strays.Watcher, "_visible_windows", next_sample)
    monkeypatch.setattr(strays.Watcher, "_describe", lambda self, e: None)
    watcher = strays.Watcher()
    watcher.sample()
    watcher.sample()
    assert set(watcher.seen) == {1, 2}
    assert watcher.seen[1].samples == 2
    assert watcher.seen[2].samples == 1, "the one that vanished"


def test_the_line_names_what_the_eye_reported():
    """A caption is what draws an icon in a corner and layered is what
    lets the desktop through — the two things the report described, so
    the two the line has to be able to say."""
    entry = strays.Seen(99, 0.0)
    entry.cls, entry.title = "Qt5152QWindowIcon", ""
    entry.rect = (10, 20, 210, 170)
    entry.style = strays._WS_CAPTION | strays._WS_VISIBLE
    entry.exstyle = strays._WS_EX_LAYERED
    line = entry.line(0.0, ours=1)
    assert "200x150" in line and "(10,20)" in line
    assert "native caption" in line
    assert "layered" in line
    assert "THE APP'S OWN WINDOW" not in line
    assert "THE APP'S OWN WINDOW" in strays.Seen(1, 0.0).line(0.0, ours=1)


def test_it_samples_fast_enough_to_catch_a_flash():
    """A window on screen for a tenth of a second has to land in at
    least one sample, or the watcher answers "nothing happened" about
    the very thing it was written for."""
    assert strays.PERIOD <= 0.05, strays.PERIOD


def test_it_stops_rather_than_running_all_evening():
    """The complaint is about BOOT, and this app measures its refresh
    loop precisely so that nothing else runs on a timer over a draft."""
    watcher = strays.Watcher()
    assert not watcher.expired()
    watcher.started = time.monotonic() - strays.WATCH_FOR - 1
    assert watcher.expired()
    assert 10 <= strays.WATCH_FOR <= 120, strays.WATCH_FOR


def test_the_window_runs_it_and_puts_it_in_the_paste(window):
    """Wired, and reaching the one place somebody will paste from."""
    assert isinstance(window.strays, strays.Watcher)
    window._watch_for_strays()              # must not raise off Windows
    window.strays.started = time.monotonic() - strays.WATCH_FOR - 1
    window._watch_for_strays()
    assert not window.stray_timer.isActive(), \
        "the sampler has to stop once the boot window has passed"
    window._copy_debug_log()
    paste = QApplication.clipboard().text()
    assert "windows this process opened" in paste
    assert "on top:" in paste, "which route always-on-top took"
