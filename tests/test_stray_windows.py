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
        # Mirrors the real callback: a window is RECORDED as it is
        # enumerated, while it is still there to measure.
        handles = windows.pop(0) if windows else [1]
        for handle in handles:
            self._entry(handle)
        return handles

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
    entry.biggest = (200, 150)
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
                        lambda self: [self._entry(7) and 7])
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
                        lambda self: [self._entry(next(seq)).hwnd])
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


def test_a_window_is_measured_while_it_is_still_alive(monkeypatch):
    """Eight real windows came back as `0x0 at (0,0)` because the first
    version collected handles and read their geometry AFTER the
    enumeration finished — and a window that dies in between leaves the
    RECT zeroed. The whole subject is windows that do not last."""
    monkeypatch.setattr(strays.sys, "platform", "win32")
    watcher = strays.Watcher()
    measured = []

    def describe(self, entry):
        measured.append(entry.hwnd)
        entry.rect = (5, 6, 105, 86)
        entry.biggest = (100, 80)

    monkeypatch.setattr(strays.Watcher, "_describe", describe)
    monkeypatch.setattr(strays.Watcher, "_visible_windows",
                        lambda self: [self._describe(self._entry(3)) or 3])
    watcher.sample()
    assert measured == [3]
    assert watcher.seen[3].size == (100, 80)


def test_the_biggest_reading_wins_over_the_last(monkeypatch):
    """A window caught mid-teardown measures nothing, and nought would
    overwrite a real reading of the same window a moment earlier."""
    monkeypatch.setattr(strays.sys, "platform", "win32")
    watcher = strays.Watcher()
    entry = watcher._entry(11)
    entry.biggest = (300, 200)
    sizes = iter([(300, 200), (0, 0)])

    def describe(self, e):
        width, height = next(sizes)
        e.rect = (0, 0, width, height)
        if width * height > e.biggest[0] * e.biggest[1]:
            e.biggest = (width, height)

    monkeypatch.setattr(strays.Watcher, "_describe", describe)
    watcher._describe(entry)
    watcher._describe(entry)
    assert entry.size == (300, 200)


def test_a_window_says_what_the_app_was_doing():
    """A class name says who CREATED a window and nothing about why.
    Eight nameless Qt windows in a row is a mystery; eight during
    "rendering the app icon" is a lead."""
    strays.stage("writing the Start-menu shortcut")
    try:
        entry = strays.Seen(4, 0.0)
        assert entry.stage == "writing the Start-menu shortcut"
        assert "writing the Start-menu shortcut" in entry.line(0.0, ours=0)
    finally:
        strays.stage("starting")


def test_every_step_of_the_boot_names_itself():
    """A stage nobody sets is a window reported against whatever ran
    before it, which is worse than no stage at all."""
    source = pathlib.Path("draft_assist/ui/app.py").read_text()
    body = source.split("def _main")[1]
    for step in ("starting Qt", "rendering the app icon",
                 "writing the Start-menu shortcut", "building the window",
                 "showing the window", "running"):
        assert f'strays.stage("{step}")' in body, step


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


def test_nothing_is_realised_without_a_parent_while_the_window_builds(qapp):
    """The eight flashing windows, held shut at the root.

    A parentless QWidget is a TOP-LEVEL WINDOW, and polishing one
    realises it — so on Windows it is briefly a real window on screen.
    `CountBox.__init__` polishes itself to measure its own width (it has
    to: the font comes from the stylesheet), and every one of its five
    call sites built it parentless and re-parented it a line later. The
    role filter alone does that EIGHT times in a loop, once per role,
    which is what a real boot recorded: eight `Qt6112QWindowIcon`
    windows between 0.86s and 1.57s, all `during 'building the window'`,
    confirmed by eye as "a bunch of small windowws opening and closign
    over about a second, approx 8 of them".

    This holds the PROPERTY rather than the five call sites, because the
    fault is one anybody adding a widget can reintroduce — and it is
    measured at the moment it happens, during construction, since the
    widget is parented a moment later and nothing afterwards can see it.

    A QMenu is exempt: a menu IS a popup window by design, Qt never puts
    one on screen until it is popped up, and on Windows it carries the
    popup window class rather than the ordinary one the report named.
    """
    from PyQt6.QtCore import QEvent, QObject
    from PyQt6.QtWidgets import QMenu, QWidget
    from draft_assist.ui.app import MainWindow
    from draft_assist.ui.demo import demo_dataset
    from draft_assist.ui.providers import DemoProvider

    loose = []

    class Watch(QObject):
        def eventFilter(self, obj, event):
            if (event.type() == QEvent.Type.Polish
                    and isinstance(obj, QWidget)
                    and not isinstance(obj, QMenu)
                    and obj.parentWidget() is None):
                loose.append(type(obj).__name__)
            return False

    watcher = Watch()                   # a temporary is collected at once
    qapp.installEventFilter(watcher)
    try:
        ds = demo_dataset()
        rules, meta = items_mod.load_rules(RULES_FILE)
        win = MainWindow(ds, DemoProvider(ds), rules, meta)
        win.timer.stop()
    finally:
        qapp.removeEventFilter(watcher)
    win.close()
    assert loose == [], (
        "these were realised with no parent, so each is a top-level "
        f"window flashing up while the app starts: {loose}")
