"""The watcher that answers "what was that window?".

It exists because the fault is invisible from here: the report is of a
small, blank, TRANSLUCENT rectangle with the desktop showing through it,
flashing up while the app starts on Windows. Every check this project can
write in Qt's terms already says the Qt side is clean, so what is left is
something only Windows can name.
"""

import pathlib
import threading
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


def test_it_starts_before_the_qapplication_on_a_thread():
    """The fault the first version had. A QTimer cannot fire until the
    event loop runs — which is after the window has been built and
    shown — so its earliest sample was 1.91s and everything it was
    written to catch had already happened."""
    import ast
    source = (pathlib.Path("draft_assist/ui/app.py")).read_text()
    tree = ast.parse(source)
    main = next(n for n in ast.walk(tree)
                if isinstance(n, ast.FunctionDef) and n.name == "_main")
    order = []
    for node in ast.walk(main):
        if not isinstance(node, ast.Call):
            continue
        name = getattr(node.func, "attr", None) or getattr(node.func, "id",
                                                           None)
        if name in ("start", "QApplication"):
            mod = getattr(getattr(node.func, "value", None), "id", "")
            if name == "QApplication" or mod == "strays":
                order.append((node.lineno, f"{mod}.{name}" if mod else name))
    order.sort()
    assert [n for _, n in order][:2] == ["strays.start", "QApplication"], \
        f"the watcher must be running before Qt is: {order}"


def test_the_report_says_when_sampling_actually_began(monkeypatch):
    """Because that is what showed the first version was watching the
    wrong span: 199 samples, earliest at 1.91s, window already up."""
    monkeypatch.setattr(strays.sys, "platform", "win32")
    monkeypatch.setattr(strays.Watcher, "_visible_windows",
                        lambda self: [7])
    monkeypatch.setattr(strays.Watcher, "_describe", lambda self, e: None)
    watcher = strays.Watcher()
    watcher.sample()
    assert "first window seen" in watcher.report()


def test_the_report_can_be_read_while_the_thread_is_writing(monkeypatch):
    """Iterating a dict another thread is inserting into raises, and the
    report is read from the GUI thread while the sampler runs."""
    monkeypatch.setattr(strays.sys, "platform", "win32")
    monkeypatch.setattr(strays.Watcher, "_describe", lambda self, e: None)
    watcher = strays.Watcher()
    seq = iter(range(1, 4000))
    monkeypatch.setattr(strays.Watcher, "_visible_windows",
                        lambda self: [next(seq)])
    stop = threading.Event()

    def churn():
        while not stop.is_set():
            watcher.sample()

    worker = threading.Thread(target=churn, daemon=True)
    worker.start()
    try:
        for _ in range(200):
            watcher.report()                # must not raise
    finally:
        stop.set()
        worker.join(timeout=5)


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
    window._copy_debug_log()
    paste = QApplication.clipboard().text()
    assert "windows this process opened" in paste
    assert "on top:" in paste, "which route always-on-top took"
