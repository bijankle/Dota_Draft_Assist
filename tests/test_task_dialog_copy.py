"""The progress dialog's output is visible, and copyable BY HAND.

At the user's request, and the reasoning is theirs: "I don't trust that
the copy and paste works unless I can see the console in the app." The
dialog has always streamed the output live; what it lacked was a button,
so the only copy was the automatic one, which is convenient and
invisible. Invisible is the half that had to be fixed.
"""

import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication            # noqa: E402

from draft_assist.ui.task_dialog import TaskDialog  # noqa: E402
from draft_assist.ui.tasks import TASKS             # noqa: E402


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture()
def dialog(qapp):
    # ANY task will do: what is under test is the DIALOG, and the
    # one it used to name was a recognition instrument that has
    # since been removed with the rest of them.
    box = TaskDialog(TASKS["update_data"])
    yield box
    box.deleteLater()


def test_the_copy_button_copies_the_whole_transcript(dialog, qapp):
    dialog._append("slots RIGHT 88%")
    dialog._append("slots WRONG 1%")
    dialog._copy()
    copied = qapp.clipboard().text()
    assert "slots RIGHT 88%" in copied
    assert "slots WRONG 1%" in copied


def test_it_says_so_in_place_rather_than_silently(dialog, qapp):
    """A button that does its job silently is one nobody believes, which
    is the whole reason it exists beside the automatic copy. The answer
    is on the button - no second dialog to dismiss - and it goes back
    afterwards so it reads as a button again rather than a status."""
    dialog._append("one line")
    dialog._copy()
    assert "Copied" in dialog.copy_button.text()
    assert not dialog.copy_button.isEnabled()
    dialog._copy_button_back()
    assert dialog.copy_button.text() == "Copy output"
    assert dialog.copy_button.isEnabled()


def test_the_bar_follows_the_tools_own_percentage(dialog):
    """Nothing guesses a percentage out of ordinary output: a run prints
    tables, hero names and paths, and a bar driven by whatever looked
    like a number would jump about through all of it."""
    assert dialog.progress.maximum() == 0        # indeterminate to start
    dialog._append("PROGRESS 40%  looking for the pick bar")
    assert dialog.progress.maximum() == 100
    assert dialog.progress.value() == 40
    dialog._append("PROGRESS 100%  done")
    assert dialog.progress.value() == 100


def test_a_tool_that_reports_nothing_keeps_a_spinning_bar(qapp):
    """A bar stuck at 0 reads as NO progress, where a spinning one reads
    as progress of an unknown amount - which is the truth about a tool
    that does not report."""
    box = TaskDialog(TASKS["update_app"])
    try:
        box._append("Pulling from origin/main - the release branch.")
        assert box.progress.maximum() == 0
    finally:
        box.deleteLater()


def test_copying_an_empty_log_does_not_raise(dialog, qapp):
    dialog._copy()
    assert "Copied" in dialog.copy_button.text()


# --------------------------------------------------------------------
# TEN UNKNOWNS AT THE MENU IS THE RIGHT ANSWER, and the log has to say
# so. A real paste came back with eight UNKNOWN, two EMPTY and distances
# of 84-104 against a ceiling of 51 - which reads as ten broken crop
# boxes and was in fact Dota sitting in the menu with no pick bar on
# screen at all.


def test_a_blank_game_state_is_explained_in_the_recognition_log():
    """`game_state` is BLANK when Dota is open with no match - the
    commonest moment anybody presses Copy everything. The guard used to
    be `if state and ...`, so blank fell straight through and printed
    ten failures with nothing saying why."""
    source = (ROOT / "draft_assist" / "ui" / "app.py").read_text(
        encoding="utf-8")
    body = source[source.index("gate score: {snap.gate_score"):]
    body = body[:body.index("for s in read.slots")]
    assert "if not state:" in body, (
        "a blank game state must be explained, not skipped")
    assert "not in a match" in body


# --------------------------------------------------------------------
# THE TUNER MAY NOT REJECT HEROES IT IDENTIFIED CORRECTLY.
#
# Measured on a live 3440x1440 strategy screen, all ten crops matched
# the RIGHT hero as nearest — Primal Beast, Warlock, Dragon Knight,
# Death Prophet, Lion / Necrophos, Juggernaut, Witch Doctor, Axe,
# Vengeful Spirit, each in its own slot — at distances of 40 to 66 bits
# with margins of 30 to 62. Eight of the ten were thrown away by a
# ceiling of 51 that `proving/tune.py` had written, having optimised
# against synthetic screens where the portrait on screen IS the base art.

REAL_DRAFT = [            # (distance, margin), one per slot, measured
    (64, 32), (54, 42), (62, 36), (40, 62), (66, 30),
    (56, 46), (60, 38), (48, 46), (56, 40), (64, 32),
]
REAL_MENU = [             # the same ten boxes with no match on screen
    (84, 16), (100, 2), (100, 0), (98, 2), (102, 0),
    (104, 0), (100, 2), (100, 2),
]
BITS = 256


def accepted(rows, max_distance, min_margin):
    return sum(1 for d, m in rows if d <= max_distance and m >= min_margin)


def test_the_shipped_default_accepts_every_real_hero():
    from draft_assist.vision.library import RecognitionParams
    from dataclasses import replace
    params = replace(RecognitionParams(), hash_size=16)
    assert params.bits == BITS
    assert accepted(REAL_DRAFT, params.max_distance,
                    params.min_margin) == 10


def test_the_tuner_cannot_pull_the_ceiling_under_a_real_hud():
    """`HUD_HEADROOM` is the floor, and it has to clear the worst real
    portrait. Without it the proving ground writes a ceiling that is free
    on its own screens and rejects most of a real draft."""
    from draft_assist.proving.tune import HUD_HEADROOM
    floor = round(HUD_HEADROOM * BITS)
    assert accepted(REAL_DRAFT, floor, 26) == 10, (
        f"a ceiling of {floor} bits still rejects real heroes")


def test_it_still_keeps_the_menu_out():
    """Raising the ceiling must not buy wrong answers. It does not,
    because the MARGIN is what discriminates: real portraits cleared
    theirs by 30-62 bits and menu crops by 0-2."""
    from draft_assist.proving.tune import HUD_HEADROOM
    floor = round(HUD_HEADROOM * BITS)
    assert accepted(REAL_MENU, floor, 26) == 0


def test_the_old_tuned_ceiling_is_what_lost_the_heroes():
    """Names the number that caused this, so the fixture stays a real
    regression rather than an arbitrary pair of thresholds."""
    assert accepted(REAL_DRAFT, 51, 26) == 2


# --------------------------------------------------------------------
# A SECOND REAL DRAFT, and it moved the numbers. Zeus and Viper came in
# at d=76 - eight bits from the MENU population, which starts at 84. So
# the distance ceiling has almost nothing left to separate with, and the
# MARGIN is what does the work: real portraits clear theirs by 20 to 48,
# menu crops by 0 to 2.

SECOND_DRAFT = [          # (distance, margin) per slot, measured
    (68, 30), (52, 44), (60, 38), (76, 20), (68, 30),
    (76, 24), (54, 42), (60, 34), (52, 48), (46, 42),
]


def test_the_operating_point_accepts_both_real_drafts():
    from tools.score_recording import CEILING_CAP, MARGIN_FLOOR
    ceiling = round(CEILING_CAP * BITS)
    margin = round(MARGIN_FLOOR * BITS)
    assert accepted(REAL_DRAFT, ceiling, margin) == 10
    assert accepted(SECOND_DRAFT, ceiling, margin) == 10


def test_it_still_rejects_every_menu_crop():
    from tools.score_recording import CEILING_CAP, MARGIN_FLOOR
    assert accepted(REAL_MENU, round(CEILING_CAP * BITS),
                    round(MARGIN_FLOOR * BITS)) == 0


def test_neither_threshold_separates_them_alone():
    """The honest shape of it, and worth a test because a wrong story
    here leads to the wrong fix later. Distance populations are eight
    bits apart, margin populations four - so the ceiling and the floor
    are a CONJUNCTION, not one doing the work with the other along for
    the ride."""
    from tools.score_recording import CEILING_CAP, MARGIN_FLOOR
    real = REAL_DRAFT + SECOND_DRAFT
    ceiling = round(CEILING_CAP * BITS)
    margin = round(MARGIN_FLOOR * BITS)

    # The ceiling alone would pass every real hero AND keep the menu out,
    # but only by eight bits.
    assert max(d for d, _m in real) < min(d for d, _m in REAL_MENU)
    assert min(d for d, _m in REAL_MENU) - max(d for d, _m in real) <= 10

    # The margin alone would NOT: a menu crop has come within four bits
    # of the worst real hero, so it cannot be the sole guard either.
    assert min(m for _d, m in real) - max(m for _d, m in REAL_MENU) <= 6

    # Together they hold, which is the only claim being made.
    assert accepted(real, ceiling, margin) == 20
    assert accepted(REAL_MENU, ceiling, margin) == 0


def test_a_tie_goes_to_the_bigger_margin():
    """A recording of one good draft holds no wrong answers, so every
    margin scores the same and the sweep used to take whichever it met
    first - which wrote a margin of 1 and threw away the second guard
    entirely. The tie-break has to prefer the safer setting, because the
    sample cannot show the value of something it never tests."""
    source = (ROOT / "tools" / "score_recording.py").read_text(
        encoding="utf-8")
    body = source[source.index("def tune("):source.index("def score(")]
    assert "min_margin, -max_distance" in body
