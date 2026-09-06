"""Calibrating by drawing on the picture.

Six numbers, each a fraction of Dota's 16:9 HUD box rather than of the
window, is not something anybody can convert "the boxes are 135 pixels too
far left" into — the user could see exactly what was wrong and had no way
to say it. So they draw three rectangles and the numbers fall out.
"""

import os

import numpy as np
import pytest

pytest.importorskip("PyQt6")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import QPoint                            # noqa: E402
from PyQt6.QtGui import QColor, QPixmap                    # noqa: E402
from PyQt6.QtWidgets import QApplication                   # noqa: E402

from draft_assist.ui.framebox import FrameView             # noqa: E402
from draft_assist.vision.layout import (DraftLayout,       # noqa: E402
                                        layout_from_drags)


@pytest.fixture(scope="module")
def qapp():
    yield QApplication.instance() or QApplication([])


def rects_for(layout: DraftLayout, width=3440, height=1440):
    """The three rectangles a user would draw for this layout."""
    slots = layout.slots()
    first = slots[0].to_pixels(width, height)
    last = slots[4].to_pixels(width, height)
    other = slots[5].to_pixels(width, height)
    return first, last, other


# ---- the arithmetic -----------------------------------------------------

def test_three_rectangles_give_back_the_layout_they_came_from():
    truth = DraftLayout(radiant_x=0.1102, dire_x=0.5707, y=0.0,
                        slot_w=0.0605, slot_h=0.0743, pitch=0.0633)
    first, last, other = rects_for(truth)
    layout, note = layout_from_drags(first, last, other, 3440, 1440)
    assert layout is not None, note
    for field in ("radiant_x", "dire_x", "y", "slot_w", "slot_h", "pitch"):
        assert getattr(layout, field) == pytest.approx(
            getattr(truth, field), abs=0.0006), field


def test_it_works_on_16_9_as_well_as_ultrawide():
    """The x fractions are of the HUD box, which is the whole window at
    16:9 and a centred slice of it wider than that."""
    truth = DraftLayout()
    first, last, other = rects_for(truth, 1920, 1080)
    layout, note = layout_from_drags(first, last, other, 1920, 1080)
    assert layout is not None, note
    assert layout.radiant_x == pytest.approx(truth.radiant_x, abs=0.001)
    assert layout.pitch == pytest.approx(truth.pitch, abs=0.001)


def test_dragging_the_banks_the_other_way_round_still_works():
    """Radiant is always the LEFT bank; which one the user drew first is a
    mistake worth absorbing rather than reporting."""
    truth = DraftLayout()
    first, last, other = rects_for(truth)
    # Pretend they started on the right bank.
    right_first = (other[0], other[1], other[2], other[3])
    right_last = (other[0] + 4 * round(truth.pitch * 2560), other[1],
                  other[2], other[3])
    layout, note = layout_from_drags(right_first, right_last, first,
                                     3440, 1440)
    assert layout is not None, note
    assert layout.radiant_x < layout.dire_x
    assert layout.radiant_x == pytest.approx(truth.radiant_x, abs=0.001)


def test_drawing_the_same_portrait_twice_is_refused_with_a_reason():
    """Rather than a pitch of zero and ten boxes in a stack."""
    first, _last, other = rects_for(DraftLayout())
    layout, note = layout_from_drags(first, first, other, 3440, 1440)
    assert layout is None
    assert "FIFTH" in note


def test_a_layout_that_falls_off_the_frame_is_refused():
    layout, note = layout_from_drags((3400, 10, 100, 80), (3430, 10, 100, 80),
                                     (10, 10, 100, 80), 3440, 1440)
    assert layout is None
    assert "off the frame" in note or "overlap" in note


# ---- the view that turns a drag into frame pixels -----------------------

def make_view(qapp, view_size=(800, 400), frame=(3440, 1440)):
    view = FrameView()
    view.resize(*view_size)
    pixmap = QPixmap(frame[0] // 5, frame[1] // 5)   # a fitted picture
    pixmap.fill(QColor("#202020"))
    view.show_frame(pixmap, frame[0], frame[1])
    return view


def test_a_click_maps_back_to_the_pixel_it_is_over(qapp):
    """The picture is scaled to fit AND centred, so both a margin and a
    ratio stand between a click and the pixel under it."""
    view = make_view(qapp)
    drawn = view._drawn_rect()
    assert drawn is not None
    assert view.to_frame(drawn.topLeft()) == (0, 0)
    middle = view.to_frame(QPoint(drawn.left() + drawn.width() // 2,
                                  drawn.top() + drawn.height() // 2))
    assert middle == pytest.approx((1720, 720), abs=6)


def test_a_click_outside_the_picture_is_clamped_not_negative(qapp):
    view = make_view(qapp)
    assert view.to_frame(QPoint(0, 0)) == (0, 0)
    assert view.to_frame(QPoint(5000, 5000)) == (3439, 1439)


def test_a_stray_click_is_not_a_rectangle(qapp):
    """A click while picking must not be read as a zero-sized box and move
    everything somewhere absurd."""
    from PyQt6.QtCore import QEvent, QPointF, Qt
    from PyQt6.QtGui import QMouseEvent

    view = make_view(qapp)
    view.set_picking(True)
    seen = []
    view.boxed.connect(lambda *args: seen.append(args))

    def click(kind, x, y):
        view_event = QMouseEvent(kind, QPointF(x, y), QPointF(x, y),
                                 Qt.MouseButton.LeftButton,
                                 Qt.MouseButton.LeftButton,
                                 Qt.KeyboardModifier.NoModifier)
        (view.mousePressEvent if kind == QEvent.Type.MouseButtonPress
         else view.mouseReleaseEvent)(view_event)

    click(QEvent.Type.MouseButtonPress, 100, 100)
    click(QEvent.Type.MouseButtonRelease, 102, 101)
    assert seen == []

    click(QEvent.Type.MouseButtonPress, 100, 100)
    click(QEvent.Type.MouseButtonRelease, 160, 140)
    assert len(seen) == 1
    assert seen[0][2] > 0 and seen[0][3] > 0


def test_picking_is_off_until_it_is_asked_for(qapp):
    view = make_view(qapp)
    assert not view.picking
    view.set_picking(True)
    assert view.picking
    view.set_picking(False)
    assert not view.picking


# ---- the whole flow, in the window --------------------------------------

@pytest.fixture()
def window(qapp, tmp_path, monkeypatch):
    from draft_assist.config import RULES_FILE
    from draft_assist.model import items as items_mod
    from draft_assist.ui.app import MainWindow
    from draft_assist.ui.demo import demo_dataset
    from draft_assist.ui.providers import DemoProvider
    from draft_assist.vision import layout as layout_mod

    monkeypatch.setattr(layout_mod, "CALIBRATION_FILE",
                        tmp_path / "calibration_local.json")
    monkeypatch.setattr(
        layout_mod.save_calibration, "__defaults__",
        (tmp_path / "calibration_local.json",))
    ds = demo_dataset()
    rules, meta = items_mod.load_rules(RULES_FILE)
    win = MainWindow(ds, DemoProvider(ds), rules, meta)
    win.timer.stop()
    yield win, tmp_path / "calibration_local.json"
    win.close()


def test_three_drags_calibrate_and_save(window):
    """The whole point: no numbers typed, and it sticks."""
    win, saved = window
    truth = DraftLayout(radiant_x=0.1102, dire_x=0.5707, y=0.0,
                        slot_w=0.0605, slot_h=0.0743, pitch=0.0633)
    win._still = np.zeros((1440, 3440, 3), dtype=np.uint8)
    win.drag_button.setChecked(True)
    assert win.debug_image.picking, "the picture is not accepting drags"

    for rect in rects_for(truth):
        win.debug_image.boxed.emit(*rect)

    assert not win.drag_button.isChecked(), "it should finish by itself"
    for field in ("radiant_x", "dire_x", "slot_w", "slot_h", "pitch"):
        assert getattr(win.layout_spec, field) == pytest.approx(
            getattr(truth, field), abs=0.0006), field
    assert saved.exists(), "the numbers were not written to disk"
    assert "Saved" in win.drag_label.text()


def test_the_spin_boxes_follow_the_drag(window):
    """They are the same numbers; leaving them stale would be two answers
    on one screen."""
    win, _saved = window
    truth = DraftLayout(radiant_x=0.1102, dire_x=0.5707, y=0.0,
                        slot_w=0.0605, slot_h=0.0743, pitch=0.0633)
    win._still = np.zeros((1440, 3440, 3), dtype=np.uint8)
    win.drag_button.setChecked(True)
    for rect in rects_for(truth):
        win.debug_image.boxed.emit(*rect)
    assert win.cal_spins["radiant_x"].value() == pytest.approx(
        truth.radiant_x, abs=0.0006)


def test_it_walks_you_through_the_three(window):
    """A prompt per step, because "drag three rectangles" is not enough to
    act on."""
    win, _saved = window
    win._still = np.zeros((1440, 3440, 3), dtype=np.uint8)
    win.drag_button.setChecked(True)
    assert "1 of 3" in win.drag_label.text()
    win.debug_image.boxed.emit(100, 10, 80, 60)
    assert "2 of 3" in win.drag_label.text()
    win.debug_image.boxed.emit(500, 10, 80, 60)
    assert "3 of 3" in win.drag_label.text()


def test_a_bad_set_of_rectangles_says_why_and_changes_nothing(window):
    win, saved = window
    win._still = np.zeros((1440, 3440, 3), dtype=np.uint8)
    before = win.layout_spec.radiant_x
    win.drag_button.setChecked(True)
    for _ in range(3):
        win.debug_image.boxed.emit(200, 10, 80, 60)     # the same box thrice
    assert win.layout_spec.radiant_x == before
    assert "Not saved" in win.drag_label.text()
    assert not saved.exists()


def test_dragging_needs_a_picture(window):
    """With nothing on screen there is nothing to drag onto, and silently
    accepting the drags would calibrate against a blank."""
    win, _saved = window
    win._still = None
    win.debug_image.setPixmap(QPixmap())
    win.drag_button.setChecked(True)
    assert not win.drag_button.isChecked()
    assert "No picture" in win.drag_label.text()
