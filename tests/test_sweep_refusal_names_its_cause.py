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
                 ((True, -3, 0.71), 7, 0.03, 0.93, 29, 31, 0.71,
                  "no gap between two banks"),
                 "the size sweep")
    assert "NEAREST MISS was 7" in diag["why"]
    assert "no gap between two banks" in diag["why"]
    # And it must NOT say the frame holds no portraits, which is the
    # sentence every one of these used to get.
    assert "nothing in the top" not in diag["why"]


def test_a_peak_at_the_end_of_the_range_says_the_range_may_be_the_limit():
    diag: dict = {}
    fp._diagnose(diag, (0.66, fp.WIDTH_FRACS[-1], 0.93, 58, 62),
                 ((True, -4, 0.66), 6, fp.WIDTH_FRACS[-1], 0.93, 58, 62,
                  0.66, "too few"), "the size sweep")
    assert "END of the range" in diag["why"]
    assert f"{fp.WIDTH_FRACS[-1]:.3f}" in diag["why"]


def test_a_peak_in_the_middle_of_the_range_makes_no_such_claim():
    middle = fp.WIDTH_FRACS[len(fp.WIDTH_FRACS) // 2]
    diag: dict = {}
    fp._diagnose(diag, (0.66, middle, 0.93, 40, 43),
                 ((True, -4, 0.66), 6, middle, 0.93, 40, 43, 0.66,
                  "too few"), "the size sweep")
    assert "END of the range" not in diag["why"]


def test_the_refined_re_read_failing_is_its_own_answer():
    diag: dict = {}
    fp._diagnose(diag, (0.9, 0.05, 0.93, 96, 103),
                 ((True, -6, 0.9), 4, 0.05, 0.93, 96, 103, 0.9,
                  "only 4 in a row"),
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
    # Both axes are answered, because the sweep now has two of them.
    assert printed.count("IN range") == 2
    assert "OUT OF RANGE" not in printed
    # And it says what that MEANS, rather than leaving it to be worked
    # out: a reachable size that still finds nothing is a different bug.
    assert "the fault is in what is KEPT" in printed


def test_a_best_outside_the_swept_widths_is_called_out(capsys):
    fp.print_size_map([
        {"w_of_span": 0.2000, "h_of_frame": 0.0920, "box": [190, 50],
         "peak": 0.77, "row": 9, "w_of_window": 0.2000, "aspect": 3.8,
         "bar": True}])
    printed = capsys.readouterr().out
    assert "OUT OF RANGE" in printed
    assert "the fault is in what is KEPT" not in printed


def test_a_best_outside_the_swept_heights_is_called_out_too(capsys):
    """Two axes, two ways to be out of reach. The height was the one
    that could not be expressed at all while the sweep used fixed
    aspects, and it is the one the map found."""
    fp.print_size_map([
        {"w_of_span": 0.0520, "h_of_frame": 0.3000, "box": [50, 160],
         "peak": 0.77, "row": 9, "w_of_window": 0.0520, "aspect": 0.31,
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


# --- and the name you can actually type --------------------------------

def test_a_multiplication_sign_and_an_x_name_the_same_picture():
    """The Snipping Tool writes U+00D7 and nobody types one.

    Twenty of the user's twenty-two screenshots carry it, and `--only`
    matched the filename exactly — so the one picture worth re-running
    could not be named at a Windows prompt. Same character, same family
    of fault as `read_image`, one layer up.
    """
    assert fp.same_name("1920 × 1080.png") == fp.same_name("1920x1080.png")
    assert fp.same_name("3440x1440.PNG") == fp.same_name("3440 X 1440.png")


def test_two_different_pictures_still_do_not_collide():
    assert fp.same_name("1920 × 1080.png") != fp.same_name("1920x1200.png")
    assert fp.same_name("800 × 600.png") != fp.same_name("1800x600.png")


# --- and only the pictures that can answer the question ---------------

@pytest.mark.parametrize("w,h,votes", [
    (800, 600, True),        # 4:3
    (1024, 768, True),       # 4:3
    (1280, 1024, True),      # 5:4
    (1600, 1200, True),      # 4:3
    (1680, 1050, True),      # 16:10
    (1920, 1200, True),      # 16:10
    (1280, 720, False),      # 16:9 - no vertical slack at all
    (1366, 768, False),      # ~16:9
    (1920, 1080, False),     # 16:9
    (2560, 1440, False),     # 16:9
    (3440, 1440, False),     # 21:9 - pillarboxed, still full height
])
def test_only_a_display_taller_than_16_9_can_settle_the_vertical(w, h, votes):
    """Arithmetic, not preference. At 16:9 and wider the HUD box is the
    full height, so all three vertical readings are the same number and
    no picture can separate equal numbers."""
    assert fp.can_vote(w, h) is votes


def test_the_size_comes_off_the_header_without_decoding(tmp_path):
    import cv2
    shot = tmp_path / "1920 × 1200.png"
    ok, buf = cv2.imencode(".png", np.full((1200, 1920, 3), 7, np.uint8))
    assert ok
    shot.write_bytes(buf.tobytes())
    assert fp.size_of(shot) == (1920, 1200)


def test_a_file_that_is_not_an_image_has_no_size(tmp_path):
    bad = tmp_path / "notes.png"
    bad.write_text("this is not a picture", encoding="utf-8")
    assert fp.size_of(bad) is None


# --- the swept range has to contain what the tool itself measures -----

def test_the_swept_widths_reach_past_every_portrait_yet_measured():
    """Two of the four real screenshots that located measured a portrait
    WIDER than the old 0.060 ceiling — 0.0645 and 0.0617 of the window.
    They arrived there only because `_refine` walks past the grid, from
    a grid point already beyond the peak. The grid has to contain them."""
    measured = (0.0645, 0.0617, 0.0563, 0.0362)
    assert max(fp.WIDTH_FRACS) > max(measured), (
        f"ceiling {max(fp.WIDTH_FRACS)} is under a measured "
        f"{max(measured)}")
    assert min(fp.WIDTH_FRACS) <= min(measured)


def test_the_grid_is_even_in_both_axes():
    """An uneven grid has a blind spot nobody can predict."""
    for frac in (fp.WIDTH_FRACS, fp.HEIGHT_FRACS):
        steps = {round(b - a, 4) for a, b in zip(frac, frac[1:])}
        assert len(steps) == 1, steps


def test_the_refine_reaches_half_a_grid_step():
    """0.99 at the true size, 0.12 four pixels out. The grid is coarse
    on purpose - two axes at the cost of one - so the walk after it MUST
    be able to cross half a step, or the coarseness is a miss."""
    import inspect
    body = inspect.getsource(fp.hunt)
    assert "0.5 * (WIDTH_FRACS[1] - WIDTH_FRACS[0])" in body
    assert "0.5 * (HEIGHT_FRACS[1] - HEIGHT_FRACS[0])" in body
    assert "int(step_w) + 1" in body and "int(step_h) + 1" in body


def test_the_widths_are_of_the_hud_span_like_the_apps_own_search():
    """`autocal.find_scale` measures widths against the HUD span. Two
    units for one quantity is one of them being wrong on an ultrawide."""
    import inspect
    assert "hud_box(width, rows)" in inspect.getsource(fp.hunt)


def test_there_are_no_guessed_aspects_left():
    """The map found bar-shaped fits at aspects from 1.31 to 2.03. A
    list of three cannot be nudged into a shape nobody has measured."""
    assert not hasattr(fp, "ASPECTS")
