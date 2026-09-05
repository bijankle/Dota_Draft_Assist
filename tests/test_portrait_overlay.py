"""The in-game numbers under the ten portraits.

Everything here is geometry and state — the halo itself is a look, not a
behaviour, so what is checked is that the numbers land on the crop boxes,
that they move with the user's nudge, and that a locked overlay cannot
swallow a click meant for Dota.
"""

import os

import pytest

pytest.importorskip("PyQt6")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import Qt  # noqa: E402
from PyQt6.QtWidgets import QApplication  # noqa: E402

from draft_assist.ui.portrait_overlay import PortraitOverlay  # noqa: E402
from draft_assist.vision import layout as layout_mod  # noqa: E402


@pytest.fixture(scope="module")
def qapp():
    yield QApplication.instance() or QApplication([])


@pytest.fixture()
def overlay(qapp):
    o = PortraitOverlay(layout_mod.DraftLayout())
    o.resize(1920, 1080)
    yield o
    o.close()


def test_the_anchors_are_the_crop_boxes(overlay):
    """Anchoring to the vision layout is the whole reason the numbers land
    anywhere near the portraits: it is the only geometry in the app known
    to line up with them."""
    spec = overlay.layout_spec
    anchors = overlay._anchors()
    assert len(anchors) == 10
    for rect, (team, index, box) in zip(spec.slots(), anchors):
        x, y, w, h = rect.to_pixels(1920, 1080)
        assert (team, index) == (rect.team, rect.slot)
        assert (box.x(), box.y(), box.width(), box.height()) == (x, y, w, h)


def test_the_anchors_move_with_the_users_nudge(overlay):
    before = overlay._anchors()[0][2]
    overlay.set_offset(0.01, 0.02)
    after = overlay._anchors()[0][2]
    # Fractions of the HUD box and of window height — never pixels, so the
    # nudge survives a resolution change like every other coordinate here.
    assert after.x() - before.x() == pytest.approx(0.01 * 1920)
    assert after.y() - before.y() == pytest.approx(0.02 * 1080)


def test_ultrawide_anchors_follow_the_pillarboxed_hud(qapp):
    """Dota pillarboxes its HUD into a centred 16:9 area, so on 21:9 the
    boxes sit in the middle 2560 pixels — the same rule that put the crop
    boxes 440px off when it was missed."""
    o = PortraitOverlay(layout_mod.DraftLayout())
    o.resize(3440, 1440)
    try:
        left_edge, span = layout_mod.hud_box(3440, 1440)
        assert span == pytest.approx(2560)
        first = o._anchors()[0][2]
        assert first.x() == pytest.approx(
            round(left_edge + o.layout_spec.radiant_x * span))
    finally:
        o.close()


def test_locked_it_cannot_take_a_click_from_dota(overlay):
    """Click-through is not cosmetic: an overlay strip sitting over the
    pick bar that ate clicks would be worse than no overlay."""
    assert overlay.attribute_transparent() is True
    overlay.set_unlocked(True)
    assert overlay.attribute_transparent() is False
    overlay.set_unlocked(False)
    assert overlay.attribute_transparent() is True


def test_dragging_reports_a_fractional_offset(overlay):
    from PyQt6.QtCore import QPointF
    from PyQt6.QtGui import QMouseEvent

    seen = []
    overlay.anchors_moved.connect(lambda dx, dy: seen.append((dx, dy)))
    overlay.set_unlocked(True)

    def press(kind, x, y):
        return QMouseEvent(kind, QPointF(x, y), QPointF(x, y),
                           Qt.MouseButton.LeftButton,
                           Qt.MouseButton.LeftButton,
                           Qt.KeyboardModifier.NoModifier)

    overlay.mousePressEvent(press(QMouseEvent.Type.MouseButtonPress, 100, 100))
    overlay.mouseMoveEvent(press(QMouseEvent.Type.MouseMove, 100 + 192, 100 + 108))
    overlay.mouseReleaseEvent(
        press(QMouseEvent.Type.MouseButtonRelease, 100 + 192, 100 + 108))

    assert seen and seen[-1][0] == pytest.approx(0.1)
    assert seen[-1][1] == pytest.approx(0.1)


def test_values_are_padded_to_five_a_bank(overlay):
    """A half-filled draft is the normal case mid-pick, not an error."""
    overlay.set_values([0.01, -0.02], [])
    assert overlay.left == [0.01, -0.02, None, None, None]
    assert overlay.right == [None] * 5


def test_the_badge_can_be_dragged_without_toggling(qapp):
    """The badge is both the toggle and the handle: a press stays a click
    until it has moved far enough to mean a drag, and a drag must not also
    flip the panel open."""
    from PyQt6.QtCore import QEvent, QPoint, QPointF
    from PyQt6.QtGui import QMouseEvent

    from draft_assist.ui.demo import demo_dataset
    from draft_assist.ui.overlay import DraftOverlay

    overlay = DraftOverlay(demo_dataset(), expanded=True)
    try:
        overlay.move(100, 100)
        was_expanded = overlay.expanded
        moves = []
        overlay.moved.connect(lambda x, y: moves.append((x, y)))

        def event(kind, gx, gy):
            point = QPointF(4, 4)
            return QMouseEvent(kind, point, QPointF(gx, gy),
                               Qt.MouseButton.LeftButton,
                               Qt.MouseButton.LeftButton,
                               Qt.KeyboardModifier.NoModifier)

        overlay.eventFilter(overlay.badge,
                            event(QEvent.Type.MouseButtonPress, 110, 110))
        overlay.eventFilter(overlay.badge,
                            event(QEvent.Type.MouseMove, 170, 150))
        swallowed = overlay.eventFilter(
            overlay.badge, event(QEvent.Type.MouseButtonRelease, 170, 150))

        assert swallowed, "a drag must not also reach the button as a click"
        assert overlay.pos() == QPoint(160, 140)
        assert moves and moves[-1] == (160, 140)
        assert overlay.expanded is was_expanded
    finally:
        overlay.close()


def test_a_press_that_does_not_move_is_still_a_click(qapp):
    from PyQt6.QtCore import QEvent, QPointF
    from PyQt6.QtGui import QMouseEvent

    from draft_assist.ui.demo import demo_dataset
    from draft_assist.ui.overlay import DraftOverlay

    overlay = DraftOverlay(demo_dataset(), expanded=True)
    try:
        overlay.move(100, 100)

        def event(kind, gx, gy):
            point = QPointF(4, 4)
            return QMouseEvent(kind, point, QPointF(gx, gy),
                               Qt.MouseButton.LeftButton,
                               Qt.MouseButton.LeftButton,
                               Qt.KeyboardModifier.NoModifier)

        overlay.eventFilter(overlay.badge,
                            event(QEvent.Type.MouseButtonPress, 110, 110))
        swallowed = overlay.eventFilter(
            overlay.badge, event(QEvent.Type.MouseButtonRelease, 111, 110))
        assert not swallowed, "a click must still reach the button"
    finally:
        overlay.close()
