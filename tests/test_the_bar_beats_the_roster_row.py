"""The pick bar is not the biggest row on a hero selection screen.

Ten of fourteen real screenshots came back "portraits matched but not in
the shape of a pick bar: the best row held 19/20/21/22 ... a roster row,
not a pick bar", at peaks of 0.89 to 0.93. The tool found the hero GRID,
named it correctly, and gave up on the picture without ever looking at
the bar standing above it — `_one_row` chose by COUNT and `bar_shape`
was only ever handed the winner, so the shape test could reject the
roster row and never promote the real bar.

The frames here carry BOTH, at the sizes and counts the real run
reported. Nothing here claims anything about recognition accuracy: the
subject is which ROW gets chosen out of a frame holding two.
"""

import sys
from pathlib import Path

import cv2
import numpy as np
import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

sys.path.insert(0, str(ROOT / "tests"))

from tools import find_portraits as fp          # noqa: E402
from test_find_portraits import art_for         # noqa: E402


@pytest.fixture(scope="module")
def art(tmp_path_factory):
    folder = tmp_path_factory.mktemp("base")
    for hero_id in range(1, 61):
        ok, buf = cv2.imencode(".png", art_for(hero_id))
        assert ok
        (folder / f"{hero_id}_hero{hero_id}.png").write_bytes(buf.tobytes())
    saved = fp.library.BASE_DIR
    fp.library.BASE_DIR = folder
    try:
        yield fp.load_art()
    finally:
        fp.library.BASE_DIR = saved


def paste(frame, hero_id, x, y, w, h):
    if x < 0 or y < 0 or x + w > frame.shape[1] or y + h > frame.shape[0]:
        return
    frame[y:y + h, x:x + w] = cv2.resize(
        art_for(hero_id), (w, h), interpolation=cv2.INTER_AREA)


def bar_and_roster(width, height, radiant_x, dire_x, pitch, slot_w, top,
                   roster_y, roster_n=18, roster_w=None):
    """A pick bar at the top with a ROSTER ROW under it, both inside the
    band the sweep searches."""
    frame = np.full((height, width, 3), 18, np.uint8)
    slot_h = int(round(slot_w / fp.PORTRAIT_ASPECT))
    for index, hero_id in enumerate(range(1, 11)):
        bank_x = radiant_x if index < 5 else dire_x
        paste(frame, hero_id, bank_x + (index % 5) * pitch, top,
              slot_w, slot_h)
    # The grid: MORE tiles, evenly spaced, no gap in the middle - and
    # close enough in size to the bar's that they still correlate with a
    # template cut for the bar. That last part is what makes this a
    # reproduction rather than a sketch: a roster of half-size tiles
    # scores nothing at the bar's size, so the bar wins by default and
    # the bug never appears.
    grid_w = roster_w or max(12, int(round(slot_w * 0.82)))
    grid_h = int(round(grid_w / fp.PORTRAIT_ASPECT))
    step = int(round(width / (roster_n + 1)))
    for index in range(roster_n):
        paste(frame, 11 + (index % 50), 10 + index * step, roster_y,
              grid_w, grid_h)
    return frame


# (name, w, h, radiant_x, dire_x, pitch, slot_w, top, roster_y)
CASES = [
    ("1920x1200", 1920, 1200, 184, 1096, 128, 120, 6, 150),
    ("1280x1024", 1280, 1024, 122, 731, 86, 80, 4, 110),
    ("1600x1200", 1600, 1200, 152, 913, 107, 100, 5, 140),
]


@pytest.mark.parametrize("name,w,h,rx,dx,pitch,slot_w,top,roster_y", CASES)
def test_the_bar_is_found_with_a_roster_row_in_the_same_band(
        art, name, w, h, rx, dx, pitch, slot_w, top, roster_y):
    frame = bar_and_roster(w, h, rx, dx, pitch, slot_w, top, roster_y)
    found = fp.hunt(fp.autocal._grey(frame), art)
    assert found is not None, f"{name}: gave up, exactly as the real run did"
    got_w, _got_h, hits = found
    assert len(hits) >= fp.MIN_HITS
    banks = fp.banks_from(hits, got_w)
    assert banks is not None, f"{name}: {len(hits)} hits did not form banks"
    radiant, dire, _pitch, bar_top = banks
    # It found the BAR, not the grid: the bar is the row at the top.
    assert abs(bar_top - top) <= max(6, slot_w // 8), (
        f"{name}: landed on y={bar_top}, the bar is at {top}")
    assert abs(radiant - rx) <= max(8, slot_w // 4)
    assert abs(dire - dx) <= max(8, slot_w // 4)


def test_every_candidate_row_is_offered_not_only_the_biggest():
    """`_rows` is the whole fix: the chooser sees all of them."""
    bar = [(0.9, x, 10, i + 1) for i, x in enumerate(
        [0, 60, 120, 180, 240, 700, 760, 820, 880, 940])]
    roster = [(0.9, x, 200, 50 + i) for i, x in enumerate(range(0, 1200, 60))]
    rows = fp._rows(bar + roster, 55)
    assert len(rows) >= 2
    # The biggest is the roster, and it is still first.
    assert len(rows[0]) > len(bar)
    # But the bar is in there, and it is the one that is bar-shaped.
    shaped = [row for row in rows if fp.bar_shape(row, 55) is not None]
    assert shaped, "the bar-shaped row was not offered at all"
    assert len(shaped[0]) == 10


def test_the_chooser_takes_the_bar_over_the_bigger_roster_row():
    bar = [(0.9, x, 10, i + 1) for i, x in enumerate(
        [0, 60, 120, 180, 240, 700, 760, 820, 880, 940])]
    roster = [(0.95, x, 200, 50 + i)
              for i, x in enumerate(range(0, 1200, 60))]
    picked = fp.best_bar(bar + roster, 55)
    assert picked is not None
    _rank, row = picked
    assert len(row) == 10
    assert {hit[2] for hit in row} == {10}, "took the roster row"


def test_a_frame_with_only_a_roster_row_is_still_refused():
    """The grid must not become acceptable just because we look harder."""
    roster = [(0.9, x, 200, 50 + i) for i, x in enumerate(range(0, 1200, 60))]
    assert fp.best_bar(roster, 55) is None


def test_the_most_populous_row_is_still_what_the_diagnosis_reports():
    """"The best row held 22" is a fact about the picture worth keeping."""
    bar = [(0.9, x, 10, i + 1) for i, x in enumerate(
        [0, 60, 120, 180, 240, 700, 760, 820, 880, 940])]
    roster = [(0.9, x, 200, 50 + i) for i, x in enumerate(range(0, 1200, 60))]
    assert len(fp._one_row(bar + roster, 55)) == len(roster)


# --- and the diagnosis must report the nearest MISS, not the biggest --

def test_the_nearest_miss_beats_a_bigger_row_of_noise():
    """A 26x20 box matches texture everywhere, so the most populous row
    over all sizes is always one of the smallest boxes. Reporting it
    called ten real screenshots "a roster row" — a statement about the
    picture that was really about the smallest box in our own grid."""
    noise = [(0.9, x, 200, 50 + i) for i, x in enumerate(range(0, 1200, 55))]
    near = [(0.8, x, 10, i + 1) for i, x in enumerate(
        [0, 60, 120, 700, 760, 820, 880, 940])]
    assert len(noise) > len(near)
    assert fp.miss_rank(near) > fp.miss_rank(noise)


def test_a_row_of_ten_beats_a_row_of_eight():
    ten = [(0.7, x, 10, i + 1) for i, x in enumerate(range(0, 600, 60))]
    eight = [(0.9, x, 20, i + 1) for i, x in enumerate(range(0, 480, 60))]
    assert len(ten) == 10 and len(eight) == 8
    assert fp.miss_rank(ten) > fp.miss_rank(eight)


def test_the_count_gate_outranks_everything_else():
    """Inside MIN_HITS..MOST_HITS first, whatever the scores say."""
    inside = [(0.4, x, 10, i + 1) for i, x in enumerate(range(0, 300, 60))]
    outside = [(0.99, x, 20, i + 1) for i, x in enumerate(range(0, 1500, 50))]
    assert fp.MIN_HITS <= len(inside) <= fp.MOST_HITS
    assert len(outside) > fp.MOST_HITS
    assert fp.miss_rank(inside) > fp.miss_rank(outside)
