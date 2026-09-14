"""One field for both marks, labelled with the marks themselves.

"I don't think there is value in being able to set the heart and shield
counts to separate values, instead I'd recommend showing one / the other
as the field label and just have a single field for both... so if you
set it to 2, then we expect to see 2 shield icons and 2 heart icons in
the lineup, and it's written as heart(symbol) / shield(symbol) - when I
say symbol I mean actually show it artistically instead of writing
words."

They answer the same question - how far down the suggestion strip is
worth marking - and two boxes made that read as two decisions.
"""

import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

pytest.importorskip("PyQt6")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtGui import QColor, QImage, QPainter     # noqa: E402
from PyQt6.QtWidgets import QApplication            # noqa: E402

from draft_assist.ui import settings as ui_settings  # noqa: E402
from draft_assist.ui import theme                    # noqa: E402


@pytest.fixture(scope="module")
def qapp():
    yield QApplication.instance() or QApplication([])


# --- the setting -------------------------------------------------------

def test_there_is_one_count_and_not_two():
    assert "mark_count" in ui_settings.DEFAULTS
    # A DEAD KEY IN DEFAULTS IS WRITTEN INTO EVERYBODY'S FILE FOR EVER,
    # because DEFAULTS is the write filter.
    assert "heart_count" not in ui_settings.DEFAULTS
    assert "shield_count" not in ui_settings.DEFAULTS


def test_an_older_file_keeps_the_larger_of_what_it_had(tmp_path):
    """Of the two possible surprises, "a mark I had is gone" is worse
    than "a mark I had is still here"."""
    import json
    where = tmp_path / "ui_settings.json"
    where.write_text(json.dumps({"heart_count": 2, "shield_count": 5}),
                     encoding="utf-8")
    assert ui_settings.load(where)["mark_count"] == 5


def test_a_newer_file_is_left_alone(tmp_path):
    import json
    where = tmp_path / "ui_settings.json"
    where.write_text(json.dumps({"mark_count": 1, "heart_count": 9}),
                     encoding="utf-8")
    assert ui_settings.load(where)["mark_count"] == 1


def test_a_file_with_neither_gets_the_default(tmp_path):
    import json
    where = tmp_path / "ui_settings.json"
    where.write_text(json.dumps({"suggested_picks": 4}), encoding="utf-8")
    assert ui_settings.load(where)["mark_count"] == ui_settings.DEFAULTS[
        "mark_count"]


# --- one number drives BOTH marks --------------------------------------

class OneSetting:
    """Just enough of MainWindow for the two accessors."""
    def __init__(self, count):
        self.settings = {"mark_count": count}

    _heart_count = None
    _shield_count = None


def counts(value):
    from draft_assist.ui.app import MainWindow
    holder = OneSetting(value)
    return (MainWindow._heart_count(holder),
            MainWindow._shield_count(holder))


def test_setting_it_to_two_marks_two_hearts_and_two_shields():
    assert counts(2) == (2, 2)


def test_they_can_never_disagree():
    for value in (0, 1, 3, 7):
        heart, shield = counts(value)
        assert heart == shield, value


def test_nought_means_none_of_either():
    assert counts(0) == (0, 0)


# --- the label is DRAWN, not written -----------------------------------

def painted(widget):
    image = QImage(widget.width(), widget.height(),
                   QImage.Format.Format_ARGB32)
    image.fill(QColor("#101010"))
    painter = QPainter(image)
    widget.render(painter)
    painter.end()
    return image


def has(image, colour, tolerance=60):
    want = QColor(colour)
    for y in range(image.height()):
        for x in range(image.width()):
            got = QColor(image.pixel(x, y))
            if (abs(got.red() - want.red()) < tolerance
                    and abs(got.green() - want.green()) < tolerance
                    and abs(got.blue() - want.blue()) < tolerance):
                return True
    return False


def test_the_label_draws_both_marks(qapp):
    from draft_assist.ui.app import MarkLabel
    both = MarkLabel(None)
    image = painted(both)
    assert has(image, theme.HEART_PINK), "no heart in the label"
    assert has(image, theme.FRAME_GOLD), "no shield in the label"


def test_the_divider_is_painted_rather_than_typed(qapp):
    """A typed "/" is a glyph that resizes with the font and cannot be
    coloured apart from the label holding it - the same reason every
    rule on the toolbar is painted."""
    from draft_assist.ui.app import MarkLabel
    both = MarkLabel(None)
    assert not hasattr(both, "setText"), "that would be a QLabel of words"
    image = painted(both)
    assert has(image, theme.RULE, tolerance=40), "no rule between them"


def test_it_is_wide_enough_for_two(qapp):
    from draft_assist.ui.app import MarkLabel
    assert MarkLabel(None).width() > MarkLabel(True).width()
