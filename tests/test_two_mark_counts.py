"""A count per mark, each on the row that names what the mark means.

THIS REVERSES `test_one_mark_count.py`, which is deleted, and the
reversal is the point of the file. The two were merged into a single
`mark_count` on this argument:

    "I don't think there is value in being able to set the heart and
    shield counts to separate values, instead I'd recommend showing one
    / the other as the field label and just have a single field for
    both"

Sound while the label WAS the two marks side by side. It stopped being
sound when the heading became a legend — "i want a legend added to the
title (suggested picks)... so i want 1 row below the header to show the
symbols and what they mean" — because a legend gives each mark its own
row and its own word, and one value behind two rows each printing a
number is the fault this app has a standing rule about: two places to
read one setting is two places for it to go stale.
"""

import json
import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

pytest.importorskip("PyQt6")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication            # noqa: E402

from draft_assist.ui import settings as ui_settings  # noqa: E402
from draft_assist.ui.app import MainWindow           # noqa: E402


@pytest.fixture(scope="module")
def qapp():
    yield QApplication.instance() or QApplication([])


# --- the settings ------------------------------------------------------

def test_there_are_two_counts_and_the_merged_one_is_gone():
    assert "heart_count" in ui_settings.DEFAULTS
    assert "shield_count" in ui_settings.DEFAULTS
    # A DEAD KEY IN DEFAULTS IS WRITTEN INTO EVERYBODY'S FILE FOR EVER,
    # because DEFAULTS is the write filter.
    assert "mark_count" not in ui_settings.DEFAULTS


def test_a_file_from_the_merged_era_keeps_the_number_it_had(tmp_path):
    """`mark_count` drove BOTH marks, so both take it. Neither mark may
    appear or disappear on the update — the reader set that number
    deliberately and it still means the same thing."""
    where = tmp_path / "ui_settings.json"
    where.write_text(json.dumps({"mark_count": 5}), encoding="utf-8")
    loaded = ui_settings.load(where)
    assert loaded["heart_count"] == 5
    assert loaded["shield_count"] == 5


def test_a_file_that_already_has_the_two_is_left_alone(tmp_path):
    """Written by a version after the split — or before the merge — and
    either way its own two values win over anything derived."""
    where = tmp_path / "ui_settings.json"
    where.write_text(json.dumps({"mark_count": 5, "heart_count": 1,
                                 "shield_count": 9}), encoding="utf-8")
    loaded = ui_settings.load(where)
    assert (loaded["heart_count"], loaded["shield_count"]) == (1, 9)


def test_a_file_with_neither_takes_the_defaults(tmp_path):
    where = tmp_path / "ui_settings.json"
    where.write_text(json.dumps({"suggested_picks": 7}), encoding="utf-8")
    loaded = ui_settings.load(where)
    for key in ("heart_count", "shield_count"):
        assert loaded[key] == ui_settings.DEFAULTS[key]


# --- what the window reads ---------------------------------------------

class _Holder:
    def __init__(self, hearts, shields):
        self.settings = {"heart_count": hearts, "shield_count": shields}

    _heart_count = None
    _shield_count = None


def _counts(hearts, shields):
    holder = _Holder(hearts, shields)
    return (MainWindow._heart_count(holder),
            MainWindow._shield_count(holder))


def test_each_mark_reads_its_own_number(qapp):
    assert _counts(2, 7) == (2, 7)


def test_nought_is_a_real_answer_for_either_mark_alone(qapp):
    """Turning the hearts off must not take the shields with them —
    which is exactly what one shared count could not express."""
    assert _counts(0, 4) == (0, 4)
    assert _counts(4, 0) == (4, 0)


def test_a_hand_edited_file_cannot_ask_for_a_silly_number(qapp):
    assert _counts(-3, 10_000) == (0, ui_settings.MAX_SHOWN)
