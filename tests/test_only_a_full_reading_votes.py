"""A partial fit is not a quieter measurement; it is a different one.

The run that located ten of fourteen reported NOT CONSISTENT on the slot
width and NO VERDICT on the vertical — and both were decided by the two
frames that had located FIVE portraits, not ten. `banks_from` reads a
bank's origin off the first portrait it found in it, so a frame with
half the bar missing has its start, its pitch and its top edge measured
from whichever five those were. It is the same rule
`_remember_measured_layout` already applies: nine answers the sides, it
takes ten to answer where the boxes go.

The numbers below are the real ones from that run.
"""

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools import find_portraits as fp


def frame(name, w, h, seen, top, slot_h, rad, dire, slot_w, pitch):
    """One row exactly as `measure` builds it. All of these are taller
    than 16:9, so the HUD span is the window width."""
    span = float(w)
    hud_h = span / (16 / 9)
    return {
        "file": name, "w": w, "h": h, "aspect": round(w / h, 4),
        "heroes": seen,
        "x_of_hudbox": round(rad / span, 5),
        "slot_w_of_hudbox": round(slot_w / span, 5),
        "pitch_of_hudbox": round(pitch / span, 5),
        "y_of_window": round(top / h, 5),
        "slot_h_of_window": round(slot_h / h, 5),
        "y_of_hudbox": round(top / hud_h, 5),
        "slot_h_of_hudbox": round(slot_h / hud_h, 5),
        "y_of_hudbox_centred": round((top - (h - hud_h) / 2) / hud_h, 5),
    }


FULL = [
    frame("1152 x 864.png", 1152, 864, 10, 4, 46, 58, 682, 82, 82),
    frame("1280 x 1024.png", 1280, 1024, 10, 6, 50, 70, 757, 91, 90),
    frame("1280 x 800.png", 1280, 800, 10, 4, 49, 58, 758, 88, 93),
    frame("1280 x 960.png", 1280, 960, 10, 5, 50, 70, 757, 91, 90),
    frame("1440 x 1080.png", 1440, 1080, 10, 7, 54, 80, 857, 93, 102),
    frame("1600 x 1024.png", 1600, 1024, 10, 5, 64, 65, 952, 113, 117),
    frame("1600 x 1200.png", 1600, 1200, 10, 6, 63, 81, 950, 112, 114),
    frame("1920 x 1200.png", 1920, 1200, 10, 7, 74, 95, 1139, 133, 138),
]
PARTIAL = [
    frame("1440 x 900.png", 1440, 900, 5, 77, 17, 110, 1267, 43, 72),
    frame("800 x 600.png", 800, 600, 5, 71, 21, 59, 572, 29, 72),
]


def say(rows, capsys):
    fp._consensus(list(rows))
    return capsys.readouterr().out


def test_the_partial_fits_are_set_aside_and_said_to_be(capsys):
    printed = say(FULL + PARTIAL, capsys)
    assert "one constant measured 8 times" in printed
    assert "2 frame(s) located fewer than ten" in printed


def test_without_them_the_horizontal_is_consistent(capsys):
    printed = say(FULL + PARTIAL, capsys)
    for line in printed.splitlines():
        if "slot_w_of_hudbox" in line or "pitch_of_hudbox" in line:
            assert "NOT CONSISTENT" not in line, line


def test_with_them_it_was_not(capsys):
    """The frames are the evidence that the rule is needed."""
    fp._consensus([dict(r, heroes=10) for r in FULL + PARTIAL])
    printed = capsys.readouterr().out
    assert "NOT CONSISTENT" in printed


def test_the_letterboxed_model_is_struck_out_as_impossible(capsys):
    printed = say(FULL + PARTIAL, capsys)
    assert "CENTRED" in printed
    centred = [ln for ln in printed.splitlines() if "CENTRED" in ln]
    assert centred and "IMPOSSIBLE" in centred[0], centred
    assert "ABOVE the" in centred[0]


def test_the_window_reading_is_not_struck_out(capsys):
    printed = say(FULL + PARTIAL, capsys)
    window = [ln for ln in printed.splitlines()
              if "WINDOW's height" in ln and "spread" in ln]
    assert window and "IMPOSSIBLE" not in window[0], window


def test_a_struck_out_model_cannot_win(capsys):
    printed = say(FULL + PARTIAL, capsys)
    assert "-> the bar is measured against a HUD BOX CENTRED" not in printed


def test_the_refusal_still_names_what_was_settled(capsys):
    """Window and top-hung are within 2x of each other, so the tool
    declines between them — but it must not bury the model it killed."""
    printed = say(FULL + PARTIAL, capsys)
    if "NO VERDICT" in printed:
        assert "struck-out model" in printed


def test_nothing_is_claimed_when_no_frame_saw_all_ten(capsys):
    printed = say(PARTIAL, capsys)
    assert "nothing here that can be called a measurement" in printed


@pytest.mark.parametrize("row", FULL)
def test_every_full_frame_puts_the_bar_inside_the_window(row):
    assert 0.0 <= row["y_of_window"] < 0.02


@pytest.mark.parametrize("row", FULL)
def test_and_the_letterboxed_model_puts_it_outside_the_box(row):
    assert row["y_of_hudbox_centred"] < 0
