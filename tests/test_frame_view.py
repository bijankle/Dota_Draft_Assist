"""The debug picture does not grow the panel it sits in.

Reported from a real session: "Debug > Live keeps expanding bigger over
time and after about 20 seconds it stops."
"""

import os

import pytest

pytest.importorskip("PyQt6")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import numpy as np  # noqa: E402
from PyQt6.QtGui import QPixmap  # noqa: E402
from PyQt6.QtWidgets import QApplication  # noqa: E402

from draft_assist.ui.framebox import FrameView  # noqa: E402


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


def test_the_picture_does_not_set_the_views_floor(qapp):
    """The loop, in one assertion.

    QLabel answers `minimumSizeHint` with its pixmap's size PLUS its own
    margins and frame, and this label is a card, so the stylesheet draws
    a 1px border round it. The caller fits the frame into the size the
    widget currently has — so the floor landed two pixels ABOVE the room
    the picture was fitted into, the layout granted it, and the next
    frame was fitted two pixels taller.
    """
    view = FrameView()
    view.resize(800, 400)
    view.show_frame(QPixmap(796, 396), 3440, 1440)
    assert view.minimumSizeHint().height() == 0, (
        "a view of something else's size has no size of its own")
    assert view.minimumSizeHint().width() == 0


def test_it_still_honours_a_floor_it_was_GIVEN(qapp):
    """Breaking the loop must not stop the panel reserving room for the
    picture — an empty debug view that collapsed to nothing would be a
    different bug in the same place."""
    view = FrameView()
    view.setMinimumHeight(320)
    view.show_frame(QPixmap(100, 50), 3440, 1440)
    assert view.minimumHeight() == 320
    assert view.sizeHint().height() == 320


def test_the_live_debug_view_settles_instead_of_creeping(qapp):
    """The whole mechanism, driven the way the app drives it.

    Eighty ticks is about twenty-five seconds of the real refresh loop,
    which is how long the growth was reported to run for.
    """
    from draft_assist.config import RULES_FILE
    from draft_assist.model import items as items_mod
    from draft_assist.ui.app import MainWindow
    from draft_assist.ui.demo import demo_dataset
    from draft_assist.ui.providers import DemoProvider, Snapshot
    from draft_assist.vision import debug as vdebug

    was = vdebug.draw_overlay
    vdebug.draw_overlay = lambda frame, read, names: frame
    try:
        ds = demo_dataset()
        rules, meta = items_mod.load_rules(RULES_FILE)
        win = MainWindow(ds, DemoProvider(ds), rules, meta)
        win.timer.stop()
        win.resize(940, 998)
        win.show()
        qapp.processEvents()
        win._open_settings("Debug")
        win.settings_window.resize(1200, 900)
        qapp.processEvents()

        class Slot:
            def __init__(self, i):
                self.rect = type("R", (), {"team": "R", "slot": i})()
                self.hero_id = None
                self.best_label = "x"
                self.distance = 1
                self.margin = 2

        read = type("Read", (), {"slots": [Slot(i) for i in range(10)]})()
        snap = Snapshot(mode="replay",
                        frame=np.full((1440, 2560, 3), 40, dtype=np.uint8),
                        read=read, read_raw=read, gate_score=0.9,
                        frames_arrived=1, game_state="")

        heights = []
        for _ in range(80):
            win._update_debug(snap)
            qapp.processEvents()
            heights.append(win.debug_image.height())

        assert heights[-1] == heights[3], (
            "the view settled: %d -> %d over 80 ticks"
            % (heights[3], heights[-1]))
        win.close()
    finally:
        vdebug.draw_overlay = was
