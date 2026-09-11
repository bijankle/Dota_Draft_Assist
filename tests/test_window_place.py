"""The window opens where it was closed.

The SIZE was already remembered and the place was not, which is half of
"where I left it" — and on an always-on-top window parked deliberately
clear of the game, the place is the half that took the arranging.
"""

import os

import pytest

pytest.importorskip("PyQt6")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import QPoint, QSize  # noqa: E402
from PyQt6.QtWidgets import QApplication  # noqa: E402

from draft_assist.ui import chrome  # noqa: E402
from draft_assist.ui import settings as ui_settings  # noqa: E402


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture()
def window(qapp):
    from draft_assist.config import RULES_FILE
    from draft_assist.model import items as items_mod
    from draft_assist.ui.app import MainWindow
    from draft_assist.ui.demo import demo_dataset
    from draft_assist.ui.providers import DemoProvider
    ds = demo_dataset()
    rules, meta = items_mod.load_rules(RULES_FILE)
    win = MainWindow(ds, DemoProvider(ds), rules, meta)
    win.timer.stop()
    yield win
    win.close()


# ---- the preference actually reaches the disk --------------------------

def test_the_position_survives_the_write_filter(tmp_path):
    """DEFAULTS is the write FILTER as well as the fallback, so a key it
    does not name is kept for the session and dropped on the way to
    disk — the bug that once lost the transparency setting. A preference
    that is written and then silently discarded looks exactly like one
    that was never written."""
    assert "window_x" in ui_settings.DEFAULTS
    assert "window_y" in ui_settings.DEFAULTS
    path = tmp_path / "ui_settings.json"
    saved = ui_settings.load(path)
    saved["window_x"], saved["window_y"] = 412, 233
    ui_settings.save(saved, path)
    back = ui_settings.load(path)
    assert (back["window_x"], back["window_y"]) == (412, 233)


def test_a_fresh_install_has_no_remembered_place(tmp_path):
    """None, not (0, 0). A first run should be placed by the window
    manager rather than jammed into the top-left corner."""
    fresh = ui_settings.load(tmp_path / "nothing.json")
    assert fresh["window_x"] is None
    assert fresh["window_y"] is None


# ---- closing writes it, opening applies it -----------------------------

def test_closing_remembers_where_the_window_was(window):
    window.show()
    window.setGeometry(260, 180, 1100, 700)
    QApplication.instance().processEvents()
    at = window.geometry()
    window.close()
    assert window.settings["window_x"] == at.x()
    assert window.settings["window_y"] == at.y()


def test_a_window_closed_MAXIMISED_remembers_its_NORMAL_place(window):
    """Off the same rectangle as the size, and for the same reason: a
    maximised window's position is the corner of the screen, not the
    corner the user put it at, so saving the live one would forget where
    the window lives every time it is closed maximised."""
    window.show()
    window.setGeometry(260, 180, 1100, 700)
    qapp = QApplication.instance()
    qapp.processEvents()
    normal = window.geometry()
    window.showMaximized()
    qapp.processEvents()
    if not window.isMaximized():
        pytest.skip("this Qt platform does not maximise")
    window.close()
    assert window.settings["window_x"] == normal.x()
    assert window.settings["window_y"] == normal.y()


def test_the_remembered_place_is_applied_on_open(window):
    area = chrome.work_area(window)
    spot = QPoint(area.left() + 90, area.top() + 70)
    window.settings["window_x"], window.settings["window_y"] = (
        spot.x(), spot.y())
    window.move(0, 0)
    window._restore_position()
    assert window.pos() == spot


def test_a_first_run_is_left_where_the_window_manager_put_it(window):
    window.settings["window_x"] = window.settings["window_y"] = None
    window.move(140, 120)
    window._restore_position()
    assert window.pos() == QPoint(140, 120), "nothing was restored"


# ---- a remembered place is only as good as the screen it was on --------

def test_a_place_on_a_screen_that_is_gone_is_refused(qapp):
    """Unplug the second monitor and the spot the window was closed at
    is somewhere no display reaches. It would open invisible — and the
    title bar being the only thing that moves this window means
    invisible is gone, not merely misplaced."""
    assert chrome.reachable(QPoint(60_000, 40_000), QSize(900, 700)) is None


def test_a_title_bar_above_the_top_of_the_screen_is_pulled_back_down(qapp):
    """The fatal direction. A bar above the top edge cannot be grabbed at
    all, however much of the window is showing below it."""
    area = qapp.primaryScreen().availableGeometry()
    where = chrome.reachable(QPoint(area.left() + 50, area.top() - 300),
                             QSize(900, 700))
    assert where is not None
    assert where.y() >= area.top()
    assert where.x() == area.left() + 50, "the other axis is left alone"


def test_hanging_off_the_side_is_allowed_but_a_grip_is_kept(qapp):
    """Deliberately a NUDGE rather than a centring: parking a window half
    off the side is a thing people do, so "reachable" is a lower bar than
    "fully visible" on purpose."""
    area = qapp.primaryScreen().availableGeometry()
    size = QSize(900, 700)
    where = chrome.reachable(QPoint(area.left() - 200, area.top() + 40), size)
    assert where is not None
    assert where.x() < area.left(), "still hanging off the left"
    assert where.x() + size.width() >= area.left() + 120, "grabbable"

    far = chrome.reachable(QPoint(area.right() - 20, area.top() + 40), size)
    assert far is not None
    assert far.x() <= area.right() - 120
