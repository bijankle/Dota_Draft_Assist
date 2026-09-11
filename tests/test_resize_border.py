"""Resizing a frameless window from any corner or edge.

The window had ONE handle — a `ResizeGrip` in the bottom-right of the
status bar — and a window stretched off the bottom of the screen does not
have that corner on screen any more. The fault and the only way out went
off the display together, which is what "it stretched very tall so I
can't make it smaller" was.
"""

import os

import pytest

pytest.importorskip("PyQt6")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import QEvent, QPoint, QPointF, QRect, Qt  # noqa: E402
from PyQt6.QtGui import QMouseEvent  # noqa: E402
from PyQt6.QtWidgets import QApplication, QWidget  # noqa: E402

from draft_assist.ui import chrome  # noqa: E402

L, R = Qt.Edge.LeftEdge, Qt.Edge.RightEdge
T, B = Qt.Edge.TopEdge, Qt.Edge.BottomEdge


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture()
def window(qapp):
    w = QWidget()
    w.setGeometry(200, 200, 800, 600)
    w.setMinimumSize(400, 300)
    yield w
    w.close()


# ---- which border is under the pointer ---------------------------------

def test_every_corner_is_a_handle(window):
    """The whole point of the change: four corners, not one."""
    right, bottom = window.width() - 1, window.height() - 1
    assert edge(window, 2, 2) == L | T
    assert edge(window, right - 2, 2) == R | T
    assert edge(window, 2, bottom - 2) == L | B
    assert edge(window, right - 2, bottom - 2) == R | B


def test_every_edge_is_a_handle(window):
    right, bottom = window.width() - 1, window.height() - 1
    assert edge(window, 2, bottom // 2) == L
    assert edge(window, right - 2, bottom // 2) == R
    assert edge(window, right // 2, 2) == T
    assert edge(window, right // 2, bottom - 2) == B


def test_the_middle_of_the_window_is_not_a_handle(window):
    assert edge(window, 400, 300) is None


def test_a_corner_is_a_BIGGER_target_than_an_edge(window):
    """Tested first and with a longer reach, deliberately.

    Asking "within EDGE of the left AND within EDGE of the top" would
    make the corner the smallest target on the border rather than the
    largest — and the corner is the one you reach for when the window
    has to be rescued, which is the harder aim.
    """
    assert chrome.CORNER > chrome.EDGE
    # Ten pixels in from both: past the edge strip, inside the corner.
    assert edge(window, 10, 10) == L | T
    # Ten pixels from the left but nowhere near the top: nothing, because
    # ten is outside the edge strip.
    assert edge(window, 10, 300) is None


def edge(window, x, y):
    return chrome.edge_at(window, QPoint(x, y))


# ---- dragging -----------------------------------------------------------

def drag(window, edges, by_x, by_y):
    """Grab `edges`, move the pointer, and return where the window lands."""
    border = chrome.ResizeBorder(window)
    start = QPoint(500, 500)
    border.begin(edges, start)
    return border.geometry_for(start + QPoint(by_x, by_y))


def test_dragging_the_TOP_edge_grows_the_window_upwards(window):
    """Not slides it. The dragged edge moves and the far edge is HELD —
    a resize that moved both edges would be a drag with extra steps."""
    was = QRect(window.geometry())
    box = drag(window, T, 0, -100)
    assert box.top() == was.top() - 100
    assert box.bottom() == was.bottom(), "the far edge is held"
    assert box.height() == was.height() + 100


def test_dragging_the_TOP_RIGHT_corner_moves_both_of_its_edges(window):
    """The corner the user named: visible when the bottom-right is not."""
    was = QRect(window.geometry())
    box = drag(window, R | T, 60, -40)
    assert box.top() == was.top() - 40
    assert box.right() == was.right() + 60
    assert box.left() == was.left(), "the held edges do not move"
    assert box.bottom() == was.bottom()


def test_dragging_the_TOP_LEFT_corner_can_shrink_a_runaway_window(window):
    """Squeezing in from the top-left is the rescue when the bottom and
    right of the window are both off the screen."""
    window.setGeometry(0, 0, 3000, 4000)
    box = drag(window, L | T, 500, 900)
    assert box.width() == 2500
    assert box.height() == 3100
    assert box.right() == 2999, "the off-screen edges stay where they are"
    assert box.bottom() == 3999


def test_the_minimum_pushes_back_the_DRAGGED_edge(window):
    """Never the held one. Clamping the far edge would walk the window
    across the screen while the pointer stood still."""
    was = QRect(window.geometry())
    box = drag(window, L, 10_000, 0)      # drag the left edge way right
    assert box.width() == window.minimumWidth()
    assert box.right() == was.right(), "the held edge did not move"


def test_the_window_cannot_be_dragged_taller_than_the_screen(window, qapp):
    """At the user's request: "the window should never be able to be made
    longer than the height of the screen"."""
    area = chrome.work_area(window)
    assert area is not None, "offscreen Qt still reports a screen"
    assert window.height() < area.height(), "starts inside the cap"
    box = drag(window, B, 0, 100_000)
    assert box.height() <= area.height()


def test_the_cap_never_YANKS_a_window_that_is_already_oversized(window):
    """It stops the window growing past the screen and nothing else.

    Clamping outright looks like the same rule and strands the window:
    4000 tall on an 800 tall screen would snap to 800 anchored to the
    held edge, which is off the bottom — so the whole window lands below
    the display, title bar included. That is the original complaint one
    drag later and worse.
    """
    window.setGeometry(0, 0, 3000, 4000)
    assert window.height() > chrome.work_area(window).height()
    box = drag(window, B, 0, -400)
    assert box.height() == 3600, "shrinks the ordinary way"


def test_that_cap_pushes_back_the_dragged_edge_too(window):
    """Dragging the TOP up into the cap must not drag the bottom up with
    it — the window would crawl up the screen under a still pointer."""
    was = QRect(window.geometry())
    box = drag(window, T, 0, -100_000)
    assert box.bottom() == was.bottom()
    assert box.height() <= chrome.work_area(window).height()


# ---- the real window ---------------------------------------------------

@pytest.fixture()
def app_window(qapp):
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


def test_the_window_watches_the_widgets_that_ACCEPT_border_presses(
        app_window):
    """The window alone is not enough. It catches everything that IGNORES
    a press and propagates up to it, which is most of the border — but a
    widget that accepts its own presses swallows them silently, and the
    title bar and the status bar are both on the border and both do.
    """
    watched = app_window.resize_border.watching
    assert app_window in watched
    assert app_window.title_bar in watched, "the whole top edge"
    assert app_window.status in watched, "the whole bottom edge"
    assert app_window.centralWidget() in watched, "the frame's own inset"


def test_the_close_button_keeps_every_pixel_of_its_hit_area(app_window):
    """`WindowButton` is 46 by the title bar's FULL height, so Close
    reaches the very top-right pixel of the window. Handle WIDGETS laid
    round the border would sit on top of it and take a bite out — a
    resize handle that eats the close button is a worse bug than the one
    being fixed. An event filter only ever sees what a widget did not
    accept, and a button accepts its own press.
    """
    app_window.resize(1240, 820)
    app_window.show()
    app_window.layout().activate()
    buttons = app_window.title_bar.findChildren(chrome.WindowButton)
    close = max(buttons, key=lambda b: b.mapTo(app_window, QPoint(0, 0)).x())

    corner = close.mapTo(app_window, QPoint(close.width() - 1, 0))
    assert chrome.edge_at(app_window, corner) == R | T, (
        "the conflict is real: Close does reach into the corner zone")

    # The filter is not installed on the button, so the press it accepts
    # never reaches the border handler at all.
    assert close not in app_window.resize_border.watching
    assert not app_window.resize_border.dragging()


def test_a_window_closed_MAXIMISED_reopens_at_its_normal_size(app_window):
    """The root cause. `height()` while maximised is the maximised
    height, and a frameless window maximised on Windows OVERHANGS the
    work area — so closing maximised wrote a height bigger than the
    screen, which the next start applied with `resize()` as an ordinary
    size. One double-click on the title bar and a close was the recipe.
    """
    app_window.show()
    app_window.setGeometry(100, 100, 1100, 700)
    app_window.layout().activate()
    normal = app_window.geometry()
    app_window.showMaximized()
    qapp = QApplication.instance()
    qapp.processEvents()
    if not app_window.isMaximized():
        pytest.skip("this Qt platform does not maximise")
    assert app_window.height() > normal.height(), "maximising did grow it"

    app_window.close()
    assert app_window.settings["window_h"] == normal.height()
    assert app_window.settings["window_w"] == normal.width()


# ---- the cursor, and the whole press-move-release cycle -----------------

def press(widget, where):
    return QMouseEvent(QEvent.Type.MouseButtonPress, QPointF(0, 0),
                       QPointF(where), QPointF(where),
                       Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton,
                       Qt.KeyboardModifier.NoModifier)


def move(widget, where):
    return QMouseEvent(QEvent.Type.MouseMove, QPointF(0, 0),
                       QPointF(where), QPointF(where),
                       Qt.MouseButton.NoButton, Qt.MouseButton.LeftButton,
                       Qt.KeyboardModifier.NoModifier)


def test_the_cursor_does_not_stick_on_the_widget_being_LEFT(qapp):
    """Four widgets are watched and the pointer crosses between them.

    Tracking only "a cursor was set" unsets it on the widget being
    ENTERED — which never had one — and leaves the widget being left
    wearing a resize arrow for the rest of the session.
    """
    window = QWidget()
    window.setGeometry(0, 0, 800, 600)
    first, second = QWidget(window), QWidget(window)
    border = chrome.ResizeBorder(window)
    border.watch(first)
    border.watch(second)

    border.hover(first, L)
    assert first.cursor().shape() == Qt.CursorShape.SizeHorCursor
    border.hover(second, R)
    assert second.cursor().shape() == Qt.CursorShape.SizeHorCursor
    assert first.cursor().shape() != Qt.CursorShape.SizeHorCursor, (
        "the widget left behind got its cursor back")
    border.hover(second, None)
    assert second.cursor().shape() != Qt.CursorShape.SizeHorCursor
    window.close()


def test_a_press_on_the_border_resizes_and_a_press_inside_does_not(qapp):
    """The whole cycle through real events, not by calling the handler."""
    window = QWidget()
    window.setGeometry(100, 100, 800, 600)
    window.setMinimumSize(200, 150)
    window.show()
    border = chrome.ResizeBorder(window)
    border.watch(window)

    # A press in the middle is not a handle. (`sendEvent` answers the
    # event's own accepted flag, not whether a filter took it, so the
    # handler's state is the thing to ask.)
    qapp.sendEvent(window, press(window, window.mapToGlobal(
        QPoint(window.width() // 2, window.height() // 2))))
    assert not border.dragging()

    # A press on the top-right corner is.
    corner = window.mapToGlobal(QPoint(window.width() - 3, 3))
    qapp.sendEvent(window, press(window, corner))
    assert border.dragging(), "the corner started a resize"

    qapp.sendEvent(window, move(window, corner + QPoint(50, -30)))
    assert window.width() == 850, "wider by the drag"
    assert window.height() == 630, "and taller"
    # The top edge is the one that moved. Only the DIRECTION is asserted
    # here: a platform is free to nudge a top-level window by a pixel or
    # two for its frame, and the exact arithmetic is held by the
    # `geometry_for` tests above, which ask the pure function.
    assert window.y() < 100, "the top edge moved, the bottom was held"

    release = QMouseEvent(
        QEvent.Type.MouseButtonRelease, QPointF(0, 0), QPointF(corner),
        QPointF(corner), Qt.MouseButton.LeftButton, Qt.MouseButton.NoButton,
        Qt.KeyboardModifier.NoModifier)
    qapp.sendEvent(window, release)
    assert not border.dragging(), "and the release ends it"
    window.close()


def test_a_maximised_window_has_no_handles(qapp):
    """Resizing a maximised window by its border would leave it maximised
    at a size that is not the screen, which is a state with no way back."""
    window = QWidget()
    window.setGeometry(0, 0, 800, 600)
    window.show()
    border = chrome.ResizeBorder(window)
    border.watch(window)
    window.showMaximized()
    qapp.processEvents()
    if not window.isMaximized():
        window.close()
        pytest.skip("this Qt platform does not maximise")
    corner = window.mapToGlobal(QPoint(window.width() - 3, 3))
    qapp.sendEvent(window, press(window, corner))
    assert not border.dragging()
    window.close()
