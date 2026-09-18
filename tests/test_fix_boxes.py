"""The guided page for "the app cannot find the portraits on MY screen".

What it must not do is what the button it replaces did: refuse, explain
why, and leave nothing to press.
"""

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication                      # noqa: E402

from draft_assist.ui import theme                             # noqa: E402
from draft_assist.ui.fixboxes import (RECORD_STEPS,           # noqa: E402
                                      FixBoxesDialog)


@pytest.fixture(scope="module")
def qapp():
    yield QApplication.instance() or QApplication([])


@pytest.fixture
def styled(qapp):
    from draft_assist.ui import fonts
    fonts.load_bundled()
    qapp.setStyleSheet(theme.STYLESHEET)
    yield


@pytest.fixture()
def guided(qapp, styled):
    made = {}

    def measure():
        made["measured"] = made.get("measured", 0) + 1
        return "measured and saved"

    def report():
        made["reported"] = made.get("reported", 0) + 1
        return "it attached the zip"

    dialog = FixBoxesDialog("crop boxes: no reading for 1920x1080",
                            measure, report)
    yield dialog, made
    dialog.deleteLater()


def test_it_names_the_display_and_where_the_boxes_came_from(guided):
    """An exact row being wrong and a whole shape being wrong are two
    different faults, and the six numbers do not say which."""
    dialog, _ = guided
    text = " ".join(w.text() for w in dialog.findChildren(type(dialog.measure_note)))
    assert "1920x1080" in text


def test_measuring_reports_what_happened(guided):
    dialog, made = guided
    dialog._do_measure()
    assert made["measured"] == 1
    assert "measured and saved" in dialog.measure_note.text()


def test_a_refused_measurement_points_at_the_next_step(guided):
    """The whole reason this page exists: a refusal used to be the end."""
    dialog, _ = guided
    dialog._measure = lambda: ""
    dialog._do_measure()
    assert dialog.measure_note.text().strip()
    assert "2" in dialog.measure_note.text()


def test_a_raising_measurement_is_a_note_and_not_a_crash(guided):
    dialog, _ = guided

    def boom():
        raise RuntimeError("no portraits downloaded")

    dialog._measure = boom
    dialog._do_measure()
    assert "no portraits downloaded" in dialog.measure_note.text()


def test_the_report_is_offered_and_never_taken_on_its_own(guided):
    """The zip carries pictures of the user's own screen."""
    dialog, made = guided
    assert "reported" not in made
    dialog._do_report()
    assert made["reported"] == 1
    assert "attached the zip" in dialog.report_note.text()


def test_a_raising_report_is_a_note_and_not_a_crash(guided):
    dialog, _ = guided

    def boom():
        raise OSError("no mail client")

    dialog._report = boom
    dialog._do_report()
    assert "no mail client" in dialog.report_note.text()


def test_the_recording_route_is_one_action_per_line():
    """A procedure is scanned a line at a time, so a line is one thing."""
    for step in RECORD_STEPS:
        assert len(step) < 120, step
        assert "\n" not in step


def test_no_widget_here_is_left_without_a_parent(guided):
    """A parentless QWidget is a top-level WINDOW the moment it is shown."""
    dialog, _ = guided
    for name in ("measure_note", "report_note"):
        assert getattr(dialog, name).parent() is not None
