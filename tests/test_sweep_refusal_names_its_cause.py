"""A refusal says WHICH rule refused, and with what numbers.

Eighteen of the user's twenty-two screenshots came back with one
sentence - "no hero portrait recognised in the top 18% of this frame" -
and that sentence is a claim about the PICTURE made out of a fact about
our own rules. `hunt` returns None for five different reasons: nothing
correlated at all, too few in a row, too many, a bank over five, and no
gap between two banks. Those have completely different answers - the
wrong screen, a bar below the searched band, a size the sweep never
tries, a roster row - and the reader was given none of them.

NOTHING HERE TESTS RECOGNITION, and the synthetic pictures below are
not offered as evidence that anything can be recognised: the subject is
the refusal machinery, which is arithmetic over hit positions and says
the same thing whatever produced them. What the portraits actually look
like is settled against real screenshots, elsewhere.
"""

import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools import find_portraits as fp


def row(xs, score=0.7, y=10):
    """Hits in the sweep's own (score, x, y, hero) shape."""
    return [(score, x, y, index + 1) for index, x in enumerate(xs)]


# --- which rule refused, in words ------------------------------------

def test_too_few_in_a_row_says_so_and_names_the_floor():
    why = fp.why_not_a_bar(row([10, 60, 110]), 50)
    assert why and str(fp.MIN_HITS) in why
    assert "3" in why


def test_too_many_in_a_row_calls_it_a_roster_row():
    why = fp.why_not_a_bar(row(range(0, 700, 50)), 50)
    assert why and "roster" in why


def test_a_bank_over_five_says_how_it_split():
    # Six evenly spaced, then a wide gap, then two: 6/2.
    xs = list(range(0, 300, 50)) + [600, 650]
    why = fp.why_not_a_bar(row(xs), 50)
    assert why and "6/2" in why


def test_no_gap_between_banks_prints_both_steps():
    why = fp.why_not_a_bar(row([0, 50, 100, 150, 200, 250]), 50)
    assert why and "50px" in why


def test_a_real_bar_is_not_refused():
    xs = [0, 50, 100, 150, 200, 500, 550, 600, 650, 700]
    assert fp.why_not_a_bar(row(xs), 50) is None
    assert fp.bar_shape(row(xs), 50) == (10, pytest.approx(7.0))


# --- the diagnosis the hunt hands back --------------------------------

def test_nothing_matching_at_all_names_the_peak_and_the_floor():
    diag: dict = {}
    fp._diagnose(diag, (0.08, 0.03, 0.93, 29, 31), None, "the size sweep")
    assert "0.08" in diag["why"]
    assert f"{fp.HIT_FLOOR:.2f}" in diag["why"]
    assert diag["peak"] == pytest.approx(0.08)


def test_a_row_that_was_refused_is_reported_as_such_not_as_nothing_seen():
    diag: dict = {}
    fp._diagnose(diag, (0.71, 0.03, 0.93, 29, 31),
                 (7, 0.03, 0.93, 29, 31, 0.71, "no gap between two banks"),
                 "the size sweep")
    assert "best row held 7" in diag["why"]
    assert "no gap between two banks" in diag["why"]
    # And it must NOT say the frame holds no portraits, which is the
    # sentence every one of these used to get.
    assert "nothing in the top" not in diag["why"]


def test_a_peak_at_the_end_of_the_range_says_the_range_may_be_the_limit():
    diag: dict = {}
    fp._diagnose(diag, (0.66, fp.WIDTH_FRACS[-1], 0.93, 58, 62),
                 (6, fp.WIDTH_FRACS[-1], 0.93, 58, 62, 0.66, "too few"),
                 "the size sweep")
    assert "END of the range" in diag["why"]
    assert f"{fp.WIDTH_FRACS[-1]:.3f}" in diag["why"]


def test_a_peak_in_the_middle_of_the_range_makes_no_such_claim():
    middle = fp.WIDTH_FRACS[len(fp.WIDTH_FRACS) // 2]
    diag: dict = {}
    fp._diagnose(diag, (0.66, middle, 0.93, 40, 43),
                 (6, middle, 0.93, 40, 43, 0.66, "too few"), "the size sweep")
    assert "END of the range" not in diag["why"]


def test_the_refined_re_read_failing_is_its_own_answer():
    diag: dict = {}
    fp._diagnose(diag, (0.9, 0.05, 0.93, 96, 103),
                 (4, 0.05, 0.93, 96, 103, 0.9, "only 4 in a row"),
                 "the re-read at the refined size (101x98)")
    assert "101x98" in diag["why"]


# --- and the hunt actually fills it -----------------------------------

@pytest.fixture
def art():
    """Two templates. What they are of does not matter here."""
    rng = np.random.default_rng(7)
    return {1: rng.integers(0, 255, (144, 256), dtype=np.uint8),
            2: rng.integers(0, 255, (144, 256), dtype=np.uint8)}


def test_an_empty_frame_comes_back_with_a_measured_peak(art):
    flat = np.full((400, 900), 20, np.uint8)
    diag: dict = {}
    assert fp.hunt(flat, art, diag=diag) is None
    assert "why" in diag and "peak" in diag
    assert diag["peak"] < fp.HIT_FLOOR
    assert diag["stage"] == "the size sweep"


def test_the_hunt_without_a_diag_still_just_answers_none(art):
    """Every other caller passes nothing, and must go on working."""
    flat = np.full((400, 900), 20, np.uint8)
    assert fp.hunt(flat, art) is None


def test_measure_carries_the_diagnosis_into_its_row(tmp_path, art):
    flat = np.full((400, 900, 3), 20, np.uint8)
    import cv2
    ok, buf = cv2.imencode(".png", flat)
    assert ok
    shot = tmp_path / "flat.png"
    shot.write_bytes(buf.tobytes())
    out = tmp_path / "out"
    row_ = fp.measure(shot, out, art, lib=None)
    assert "diag" in row_
    assert row_["why"] == row_["diag"]["why"]
    assert "at any of the" in row_["why"]


# --- and the summary reads as a pattern -------------------------------

def test_the_failure_table_prints_a_line_for_every_picture(capsys):
    bad = [{"file": f"{n}.png", "w": 1920, "h": 1080,
            "why": "x",
            "diag": {"peak": 0.09, "peak_frac": 0.03, "peak_box": [57, 61],
                     "stage": "the size sweep"}}
           for n in ("a", "b")]
    fp._failures(bad)
    printed = capsys.readouterr().out
    assert "a.png" in printed and "b.png" in printed
    assert "0.09" in printed
    # All below the floor is itself the finding, and it is said outright.
    assert "no hero artwork in the searched band" in printed


def test_the_failure_table_says_nothing_when_everything_located(capsys):
    fp._failures([])
    assert capsys.readouterr().out == ""


# --- and the instrument that answers "is it a size we even try" -------

def test_the_size_map_covers_the_apps_own_grid(art):
    """The map's job is to be BIGGER than the sweep, or it says nothing.

    `autocal.find_scale` found the shipped layout on a real client by
    searching 19 widths of the HUD span against 17 independent heights;
    the sweep tries 24 widths of the window against three fixed aspects.
    The map has to be the former, or it cannot tell us the sweep's box
    is the thing at fault.
    """
    flat = np.full((300, 900), 20, np.uint8)
    cells = fp.size_map(flat, art, span=900, top=5)
    assert cells, "the map tried nothing"
    assert len(cells) <= 5
    aspects = {cell["aspect"] for cell in cells}
    assert len(aspects) > 1, "a map with one aspect is the sweep again"
    for cell in cells:
        assert cell["w_of_span"] in fp.autocal.WIDTHS
        assert cell["h_of_frame"] in fp.autocal.HEIGHTS


def test_the_map_says_whether_the_sweep_could_have_reached_its_best(capsys):
    fp.print_size_map([
        {"w_of_span": 0.0520, "h_of_frame": 0.0920, "box": [50, 50],
         "peak": 0.81, "row": 10, "w_of_window": 0.0390, "aspect": 1.0,
         "bar": True}])
    printed = capsys.readouterr().out
    assert "IN range" in printed
    # The nearest aspect the sweep tries is 0.93 against a square tile,
    # which on a 50px box is 4px out in height - and the map must say so
    # in pixels rather than leaving an aspect number to be interpreted.
    assert "NOT CLOSE" in printed
    assert "50x54" in printed


def test_a_best_outside_the_swept_widths_is_called_out(capsys):
    fp.print_size_map([
        {"w_of_span": 0.0820, "h_of_frame": 0.0920, "box": [79, 50],
         "peak": 0.77, "row": 9, "w_of_window": 0.0820, "aspect": 1.58,
         "bar": True}])
    printed = capsys.readouterr().out
    assert "OUT OF RANGE" in printed


def test_the_map_ranks_a_bar_above_a_bigger_count():
    """A box a third of a portrait matches part of all ten and reports
    fourteen. Counting alone puts that above the right answer."""
    cells = [
        {"w_of_span": 0.028, "h_of_frame": 0.05, "box": [27, 38],
         "peak": 0.92, "row": 14, "w_of_window": 0.028, "aspect": 0.71,
         "bar": False},
        {"w_of_span": 0.064, "h_of_frame": 0.05, "box": [61, 38],
         "peak": 0.92, "row": 10, "w_of_window": 0.064, "aspect": 1.60,
         "bar": True},
    ]
    cells.sort(key=fp.map_order, reverse=True)
    assert cells[0]["box"] == [61, 38]
