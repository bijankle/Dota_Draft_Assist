"""Calibrating by drawing on the picture.

Six numbers, each a fraction of Dota's 16:9 HUD box rather than of the
window, is not something anybody can convert "the boxes are 135 pixels too
far left" into — the user could see exactly what was wrong and had no way
to say it. So they draw a box round each bank and the rest is measured.

The measuring is the interesting part. A box round five portraits spans
four pitches plus one portrait, which is one equation for two unknowns, so
the gap between portraits has to come from somewhere. It comes from the
PICTURE: the borders are the strongest vertical edges in the strip, and the
fit that lands all ten of them on an edge is the right one. That also makes
the fit robust to a hand-drawn box, which is never within a few pixels of
anything.
"""

import os

import cv2
import numpy as np
import pytest

pytest.importorskip("PyQt6")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import QPoint                            # noqa: E402
from PyQt6.QtGui import QColor, QPixmap                    # noqa: E402
from PyQt6.QtWidgets import QApplication                   # noqa: E402

from draft_assist.ui.framebox import FrameView             # noqa: E402
from draft_assist.vision import autocal                    # noqa: E402
from draft_assist.vision.layout import DraftLayout         # noqa: E402

FIELDS = ("radiant_x", "dire_x", "y", "slot_w", "slot_h", "pitch")


@pytest.fixture(scope="module")
def qapp():
    yield QApplication.instance() or QApplication([])


def pick_bar(layout: DraftLayout, width=3440, height=1440, seed=4):
    """A frame with ten portraits at a known layout, with real borders."""
    rng = np.random.default_rng(seed)
    frame = np.full((height, width, 3), 22, np.uint8)
    for rect in layout.slots():
        x, y, w, h = rect.to_pixels(width, height)
        art = rng.integers(30, 220, (h, w, 3), dtype=np.uint8)
        frame[y:y + h, x:x + w] = cv2.GaussianBlur(art, (7, 7), 0)
    return frame


def bank_rect(layout, first, last, width=3440, height=1440, slack=0):
    """The rectangle a user would draw round one bank, `slack` px sloppy."""
    slots = layout.slots()
    x0, y0, w0, h0 = slots[first].to_pixels(width, height)
    x4, _y4, w4, _h4 = slots[last].to_pixels(width, height)
    return (x0 - slack, y0 - slack,
            (x4 + w4 + slack) - (x0 - slack), h0 + 2 * slack)


def both_banks(layout, width=3440, height=1440, slack=0):
    return (bank_rect(layout, 0, 4, width, height, slack),
            bank_rect(layout, 5, 9, width, height, slack))


def pixels(layout, field, width, height):
    span = min(width, height * 16 / 9)
    return getattr(layout, field) * (height if field in ("y", "slot_h")
                                     else span)


# ---- the measuring ------------------------------------------------------

def test_two_boxes_give_back_the_layout_they_came_from():
    truth = DraftLayout(radiant_x=0.1102, dire_x=0.5707, y=0.0090,
                        slot_w=0.0605, slot_h=0.0743, pitch=0.0633)
    frame = pick_bar(truth)
    layout, note = autocal.layout_from_banks(frame, *both_banks(truth))
    assert layout is not None, note
    for field in FIELDS:
        off = abs(pixels(layout, field, 3440, 1440)
                  - pixels(truth, field, 3440, 1440))
        assert off <= 3, f"{field} is {off:.1f}px out"


@pytest.mark.parametrize("slack", [0, 6, 12])
def test_a_hand_drawn_box_is_snapped_to_the_real_edges(slack):
    """Nobody draws a rectangle within a pixel of anything, and a span 2%
    too wide misplaces the fifth portrait by a tenth of a portrait — so
    the edges are fitted rather than taken from the drag."""
    truth = DraftLayout(radiant_x=0.1102, dire_x=0.5707, y=0.0090,
                        slot_w=0.0605, slot_h=0.0743, pitch=0.0633)
    frame = pick_bar(truth)
    layout, note = autocal.layout_from_banks(
        frame, *both_banks(truth, slack=slack))
    assert layout is not None, note
    for field in ("radiant_x", "dire_x", "slot_w", "pitch"):
        off = abs(pixels(layout, field, 3440, 1440)
                  - pixels(truth, field, 3440, 1440))
        assert off <= 3, f"{field} is {off:.1f}px out at {slack}px of slack"


@pytest.mark.parametrize("size", [(1920, 1080), (2560, 1440), (1280, 720)])
def test_it_works_at_other_resolutions(size):
    width, height = size
    truth = DraftLayout()
    frame = pick_bar(truth, width, height)
    layout, note = autocal.layout_from_banks(
        frame, *both_banks(truth, width, height, slack=6))
    assert layout is not None, note
    for field in ("radiant_x", "dire_x", "slot_w", "pitch"):
        off = abs(pixels(layout, field, width, height)
                  - pixels(truth, field, width, height))
        assert off <= 3, f"{field} is {off:.1f}px out at {width}x{height}"


def test_the_gap_between_portraits_is_measured_not_assumed():
    """The whole reason this is not arithmetic: a box round five portraits
    is one equation for two unknowns, and the two layouts below fill the
    same span with very different portraits."""
    for slot_w, pitch in ((0.0525, 0.0640), (0.0630, 0.0640)):
        truth = DraftLayout(slot_w=slot_w, pitch=pitch)
        frame = pick_bar(truth, 2560, 1440)
        layout, note = autocal.layout_from_banks(
            frame, *both_banks(truth, 2560, 1440))
        assert layout is not None, note
        off = abs(pixels(layout, "slot_w", 2560, 1440)
                  - pixels(truth, "slot_w", 2560, 1440))
        assert off <= 3, f"width {off:.1f}px out for gap {pitch - slot_w:.4f}"


def test_the_banks_can_be_drawn_in_either_order():
    """Radiant is always the LEFT bank; which one was drawn first is a
    mistake worth absorbing rather than reporting."""
    truth = DraftLayout()
    frame = pick_bar(truth)
    left, right = both_banks(truth)
    layout, note = autocal.layout_from_banks(frame, right, left)
    assert layout is not None, note
    assert layout.radiant_x < layout.dire_x
    assert abs(pixels(layout, "radiant_x", 3440, 1440)
               - pixels(truth, "radiant_x", 3440, 1440)) <= 3


def test_a_flat_picture_says_so_rather_than_fitting_noise():
    """With nothing to measure the honest answer is the even split, said
    out loud, not whatever noise happened to win."""
    frame = np.full((1440, 3440, 3), 24, np.uint8)
    layout, note = autocal.layout_from_banks(
        frame, (700, 20, 800, 100), (1900, 20, 800, 100))
    assert layout is not None, note
    assert "equal slots" in note
    assert layout.pitch * 2560 == pytest.approx(160, abs=2)


def test_a_rectangle_too_small_to_hold_five_is_refused():
    frame = np.full((1440, 3440, 3), 24, np.uint8)
    layout, note = autocal.layout_from_banks(
        frame, (700, 20, 12, 8), (1900, 20, 800, 100))
    assert layout is None
    assert "too small" in note


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


def test_two_drags_calibrate_and_save(window):
    """The whole point: no numbers typed, and it sticks."""
    win, saved = window
    truth = DraftLayout(radiant_x=0.1102, dire_x=0.5707, y=0.0090,
                        slot_w=0.0605, slot_h=0.0743, pitch=0.0633)
    win._still = pick_bar(truth)
    win.drag_button.setChecked(True)
    assert win.debug_image.picking, "the picture is not accepting drags"

    for rect in both_banks(truth, slack=6):
        win.debug_image.boxed.emit(*rect)

    assert not win.drag_button.isChecked(), "it should finish by itself"
    for field in FIELDS:
        off = abs(pixels(win.layout_spec, field, 3440, 1440)
                  - pixels(truth, field, 3440, 1440))
        # The horizontal fit has ten edges agreeing with each other; the
        # top and bottom have one each, so they are pulled towards the
        # drawn box rather than snapped hard onto a weak edge.
        limit = 6 if field in ("y", "slot_h") else 3
        assert off <= limit, f"{field} is {off:.1f}px out"
    assert saved.exists(), "the numbers were not written to disk"
    assert "Saved" in win.drag_label.text()


def test_the_spin_boxes_follow_the_drag(window):
    """They are the same numbers; leaving them stale would be two answers
    on one screen."""
    win, _saved = window
    truth = DraftLayout(radiant_x=0.1102, dire_x=0.5707, y=0.0090,
                        slot_w=0.0605, slot_h=0.0743, pitch=0.0633)
    win._still = pick_bar(truth)
    win.drag_button.setChecked(True)
    for rect in both_banks(truth):
        win.debug_image.boxed.emit(*rect)
    assert win.cal_spins["radiant_x"].value() == pytest.approx(
        truth.radiant_x, abs=0.0015)


def test_it_walks_you_through_the_two(window):
    """A prompt per step, because "drag two rectangles" is not enough to
    act on."""
    win, _saved = window
    win._still = np.zeros((1440, 3440, 3), dtype=np.uint8)
    win.drag_button.setChecked(True)
    assert "1 of 2" in win.drag_label.text()
    assert "ALL FIVE" in win.drag_label.text()
    win.debug_image.boxed.emit(700, 10, 800, 100)
    assert "2 of 2" in win.drag_label.text()


def test_a_bad_set_of_rectangles_says_why_and_changes_nothing(window):
    win, saved = window
    win._still = np.zeros((1440, 3440, 3), dtype=np.uint8)
    before = win.layout_spec.radiant_x
    win.drag_button.setChecked(True)
    for _ in range(2):
        win.debug_image.boxed.emit(200, 10, 30, 20)     # far too small
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
