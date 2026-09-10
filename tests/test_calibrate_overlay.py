"""Calibration as a first-class action: two red boxes ON the game.

It was a drag on a small picture inside the debug panel — "it should not
be done in this silly debugging menu" — and it is the one setup step the
whole draft reading depends on. What is tested here is the part that has
to be right without a screen: screen coordinates in, a saved layout out,
and the guard that says to open Dota first.
"""

import os

import pytest

pytest.importorskip("PyQt6")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication                    # noqa: E402

from draft_assist.ui import calibrate                       # noqa: E402
from draft_assist.vision.layout import DraftLayout          # noqa: E402

from test_calibrate_drag import both_banks, pick_bar        # noqa: E402


@pytest.fixture(scope="module")
def qapp():
    yield QApplication.instance() or QApplication([])


# ---- screen coordinates to frame pixels ---------------------------------

def test_a_box_on_the_screen_becomes_pixels_in_the_frame():
    """The frame is a picture of the client area, so the two differ by
    the window's origin on screen."""
    box = (120, 90, 400, 60)
    client = (100, 50, 1920, 1080)
    assert calibrate.to_frame_rect(box, client, (1920, 1080)) == (
        20, 40, 400, 60)


def test_a_capture_at_another_size_is_scaled_rather_than_assumed():
    """A capture that hands back a different size than the client area
    would otherwise put every box a fixed fraction out."""
    box = (100, 50, 400, 60)
    client = (100, 50, 1920, 1080)
    assert calibrate.to_frame_rect(box, client, (960, 540)) == (0, 0, 200, 30)


def test_the_two_boxes_give_back_the_layout_they_were_drawn_on():
    """The round trip that matters: draw round each bank on screen, get
    the calibration the bar was built from."""
    want = DraftLayout()
    frame = pick_bar(want)
    first, second = both_banks(want, slack=6)
    origin = (300, 120)
    on_screen = [(r[0] + origin[0], r[1] + origin[1], r[2], r[3])
                 for r in (first, second)]
    client = (origin[0], origin[1], frame.shape[1], frame.shape[0])

    got, note = calibrate.measure_from_boxes(frame, client, *on_screen)
    assert got is not None, note
    assert got.radiant_x == pytest.approx(want.radiant_x, abs=0.002)
    assert got.dire_x == pytest.approx(want.dire_x, abs=0.002)
    assert got.pitch == pytest.approx(want.pitch, abs=0.002)
    assert got.slot_w == pytest.approx(want.slot_w, abs=0.002)


def test_with_no_picture_it_says_so_rather_than_measuring_nothing():
    got, note = calibrate.measure_from_boxes(
        None, (0, 0, 100, 100), (0, 0, 10, 10), (20, 0, 10, 10))
    assert got is None
    assert "picture" in note


# ---- the boxes themselves -----------------------------------------------

def test_the_boxes_stay_out_of_the_taskbar(qapp):
    """Two more top-level windows in Alt-Tab is what got the floating
    overlay toggle deleted from this app."""
    from PyQt6.QtCore import Qt

    box = calibrate.BankBox("Radiant")
    try:
        assert box.windowFlags() & Qt.WindowType.Tool
        assert box.windowFlags() & Qt.WindowType.WindowStaysOnTopHint
        assert box.windowFlags() & Qt.WindowType.FramelessWindowHint
    finally:
        box.deleteLater()


def test_a_box_reports_the_rectangle_and_not_its_name_strip(qapp):
    """Qt lays out in logical pixels and the window rect is physical, so
    on a display at 150% the two disagree by half again — and the name
    strip is chrome, so handing the widget's own geometry to the measurer
    would put every box a label's height out."""
    box = calibrate.BankBox("Dire")
    try:
        box.move(40, 30)
        box.resize(200, 80 + calibrate.LABEL_H)
        ratio = box.devicePixelRatioF() or 1.0
        assert box.screen_rect() == (
            round(40 * ratio), round((30 + calibrate.LABEL_H) * ratio),
            round(200 * ratio), round(80 * ratio))
    finally:
        box.deleteLater()


@pytest.mark.parametrize("height", [1080, 536])
def test_the_name_never_opens_off_the_top_of_the_screen(qapp, height):
    """Dota's pick bar hugs the top edge. Where the gap above it is
    smaller than the name strip the strip goes UNDER the rectangle
    instead, because a label at a negative y is clipped off the
    display — and where there is room it stays above, out of the way."""
    worker = calibrate.Calibrator((0, 0, 1920, height))
    try:
        for box in worker.boxes:
            assert box.y() >= 0, "the name opened off the top"
            if box.below:
                assert box.label_rect().top() >= box.box_rect().top()
            else:
                assert box.label_rect().bottom() <= box.box_rect().top()
    finally:
        worker._close(False, "")


def test_it_opens_two_named_boxes_and_takes_them_away_again(qapp):
    """They exist only while calibrating, at the user's request."""
    worker = calibrate.Calibrator((0, 0, 1920, 1080))
    worker.show()
    assert [box.name for box in worker.boxes] == ["Radiant", "Dire"]
    assert all(box.isVisible() for box in worker.boxes)
    said = []
    worker.finished.connect(lambda saved, note: said.append(saved))
    worker.panel.cancelled.emit()
    qapp.processEvents()
    assert said == [False]
    assert not any(box.isVisible() for box in worker.boxes)


def test_a_refusal_keeps_the_boxes_up(qapp):
    """Closing on a failure would throw away the drag."""
    worker = calibrate.Calibrator((0, 0, 1920, 1080))
    worker.show()
    worker.frame_of = lambda: None          # nothing to measure
    ended = []
    worker.finished.connect(lambda saved, note: ended.append(saved))
    worker.panel.confirmed.emit()
    qapp.processEvents()
    assert ended == [], "it closed on a failure"
    assert all(box.isVisible() for box in worker.boxes)
    assert "picture" in worker.panel.note.text()
    worker.panel.cancelled.emit()
    qapp.processEvents()
