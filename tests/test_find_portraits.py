"""The calibration sweep, against the trap that beat two versions of it.

Every one of the user's 23 real screenshots came back with the bar
between 12% and 17% down the window, and the crops showed what was
actually there: CHOOSE HERO, DARK WILLOW, ENTERING BATTLE, LION,
FRIENDS AND FOES. An edge-periodicity fit prefers a row of letters to a
row of portraits, because letters are the stronger regularly spaced
vertical edges. So the frames here carry BOTH - a real pick bar at the
top and a line of interface text below it - and the test is that the
answer is the bar.
"""

import sys
from pathlib import Path

import cv2
import numpy as np
import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools import find_portraits as fp

HEROES = 60          # enough to test discrimination without a slow suite
ART_W, ART_H = 256, 144


def art_for(hero_id: int) -> np.ndarray:
    """A portrait that is this hero's and nobody else's.

    Random noise, from a seed that is the hero id, plus broad blocks of
    its own colour: that is what a portrait is for a correlator's
    purposes - unique, textured, and nothing like a glyph.
    """
    rng = np.random.default_rng(hero_id)
    art = rng.integers(0, 255, (ART_H, ART_W, 3), dtype=np.uint8)
    art = cv2.GaussianBlur(art, (7, 7), 0)
    for band in range(3):
        y0 = band * ART_H // 3
        shade = np.uint8((hero_id * 37 + band * 61) % 200 + 30)
        art[y0:y0 + ART_H // 6] = cv2.addWeighted(
            art[y0:y0 + ART_H // 6], 0.45,
            np.full_like(art[y0:y0 + ART_H // 6], shade), 0.55, 0)
    return art


@pytest.fixture
def art(tmp_path, monkeypatch):
    folder = tmp_path / "base"
    folder.mkdir()
    for hero_id in range(1, HEROES + 1):
        ok, buf = cv2.imencode(".png", art_for(hero_id))
        assert ok
        (folder / f"{hero_id}_hero{hero_id}.png").write_bytes(buf.tobytes())
    monkeypatch.setattr(fp.library, "BASE_DIR", folder)
    return fp.load_art()


def frame_with_bar(width, height, radiant_x, dire_x, pitch, slot_w, top,
                   heroes=range(1, 11), text=True):
    """A pick bar at the top, and the trap underneath it."""
    slot_h = int(round(slot_w / fp.PORTRAIT_ASPECT))
    frame = np.full((height, width, 3), 18, np.uint8)
    picks = list(heroes)
    for index, hero_id in enumerate(picks):
        bank_x = radiant_x if index < 5 else dire_x
        x = bank_x + (index % 5) * pitch
        if x + slot_w > width:
            continue
        frame[top:top + slot_h, x:x + slot_w] = cv2.resize(
            art_for(hero_id), (slot_w, slot_h), interpolation=cv2.INTER_AREA)
    if text:
        # The line that beat the edge fit, at the height it beat it from.
        scale = width / 900.0
        cv2.putText(frame, "CHOOSE HERO", (int(width * 0.30),
                                           int(height * 0.16)),
                    cv2.FONT_HERSHEY_SIMPLEX, 1.6 * scale,
                    (235, 235, 235), max(1, int(3 * scale)), cv2.LINE_AA)
        cv2.putText(frame, "FRIENDS AND FOES", (int(width * 0.24),
                                                int(height * 0.30)),
                    cv2.FONT_HERSHEY_SIMPLEX, 1.2 * scale,
                    (225, 225, 225), max(1, int(2 * scale)), cv2.LINE_AA)
    return frame


# (name, w, h, radiant_x, dire_x, pitch, slot_w, top)
CASES = [
    ("1920x1080", 1920, 1080, 184, 1096, 128, 120, 6),
    ("1280x1024", 1280, 1024, 122, 731, 86, 80, 4),
    ("3440x1440", 3440, 1440, 686, 1902, 172, 160, 8),
    ("800x600",   800,  600,   76,  457, 54, 50, 3),
]


@pytest.mark.parametrize("name,w,h,rx,dx,pitch,slot_w,top", CASES)
def test_it_finds_the_bar_and_not_the_text(art, name, w, h, rx, dx, pitch,
                                           slot_w, top):
    frame = frame_with_bar(w, h, rx, dx, pitch, slot_w, top)
    found = fp.hunt(fp.autocal._grey(frame), art)
    assert found is not None, f"{name}: recognised nothing"
    got_w, _got_h, hits = found
    banks = fp.banks_from(hits, got_w)
    assert banks is not None, f"{name}: {len(hits)} hits did not form banks"
    got_rx, got_dx, got_pitch, got_top = banks

    # THE TOP IS THE ASSERTION THAT MATTERS. Every real screenshot came
    # back at 12-17% of the window height; the bar is at under 1%.
    assert got_top < h * 0.05, (
        f"{name}: bar at {got_top / h:.1%} down the window — that is the "
        "text row again")
    assert abs(got_top - top) <= 4
    assert abs(got_w - slot_w) <= max(3, slot_w * 0.06)
    assert abs(got_pitch - pitch) <= max(3, pitch * 0.06)
    assert abs(got_rx - rx) <= max(4, slot_w * 0.10)
    assert abs(got_dx - dx) <= max(4, slot_w * 0.10)


def test_it_recognises_most_of_the_ten(art):
    frame = frame_with_bar(*CASES[0][1:])
    found = fp.hunt(fp.autocal._grey(frame), art)
    assert found is not None
    assert len(found[2]) >= 8, "should recognise nearly all ten"
    assert len(found[2]) <= 10, "cannot find more heroes than are there"


def test_a_frame_with_only_text_is_refused(art):
    """No portraits on screen must mean NO ANSWER, never the text row.

    This is the whole failure being guarded: the old fit always produced
    a confident answer, and a confident answer about a menu is worse
    than none.
    """
    frame = frame_with_bar(1920, 1080, 184, 1096, 128, 120, 6, heroes=[])
    found = fp.hunt(fp.autocal._grey(frame), art)
    if found is not None:
        assert fp.banks_from(found[2], found[0]) is None
