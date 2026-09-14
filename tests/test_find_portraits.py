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
    # Sized from the REAL measurement rather than invented: on a real
    # client a pick portrait is 0.026 to 0.035 of the window's width,
    # and this case used to say 0.0625 - wider than the bar has ever
    # been, which quietly required the sweep to keep searching sizes
    # that do not occur.
    ("800x600",   800,  600,   70,  494, 48, 44, 3),
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


# --------------------------------------------------------------------
# WHAT THE HUD DOES TO A PORTRAIT, which is what decides whether
# matching the artwork can work at all. Measured, not assumed:
#
#   damage            slots located (whole art)   (centre 76%)
#   tint / gamma              10 / 10               10 / 10
#   + HUD border               6 / 10               10 / 10
#
# Normalised cross-correlation ignores brightness and contrast outright,
# so a team tint and a gamma shift cost nothing at all. A BORDER does,
# because a template covering the whole picture necessarily overlaps it
# - and a template covering only the middle never can, which is what
# `INSET` is for and the only reason the border row passes.


def hud_damage(art, team_bgr, border=True):
    """A portrait as the HUD draws it: tinted, gamma-shifted, framed."""
    out = cv2.addWeighted(art, 0.80, np.full_like(art, team_bgr), 0.20, 0)
    out = np.clip(out.astype(np.float32) ** 1.15 / (255 ** 0.15),
                  0, 255).astype(np.uint8)
    if border:
        h, w = out.shape[:2]
        edge = max(2, int(w * 0.04))
        out[:edge] = out[-edge:] = team_bgr
        out[:, :edge] = out[:, -edge:] = team_bgr
    return out


def frame_with_hud(width, height, radiant_x, dire_x, pitch, slot_w, top):
    slot_h = int(round(slot_w / fp.PORTRAIT_ASPECT))
    frame = frame_with_bar(width, height, radiant_x, dire_x, pitch, slot_w,
                           top, heroes=[])
    for index in range(10):
        bank_x = radiant_x if index < 5 else dire_x
        x = bank_x + (index % 5) * pitch
        team = (60, 120, 60) if index < 5 else (60, 60, 140)
        frame[top:top + slot_h, x:x + slot_w] = cv2.resize(
            hud_damage(art_for(index + 1), team), (slot_w, slot_h),
            interpolation=cv2.INTER_AREA)
    return frame


@pytest.mark.parametrize("name,w,h,rx,dx,pitch,slot_w,top", CASES)
def test_a_tinted_and_framed_bar_is_still_located(art, name, w, h, rx, dx,
                                                  pitch, slot_w, top):
    frame = frame_with_hud(w, h, rx, dx, pitch, slot_w, top)
    found = fp.hunt(fp.autocal._grey(frame), art)
    assert found is not None, f"{name}: recognised nothing through the HUD"
    got_w, _got_h, hits = found
    banks = fp.banks_from(hits, got_w)
    assert banks is not None, f"{name}: {len(hits)} hits did not form banks"
    got_rx, got_dx, got_pitch, got_top = banks
    assert got_top < h * 0.05
    assert abs(got_pitch - pitch) <= max(4, pitch * 0.08)
    assert abs(got_rx - rx) <= max(6, slot_w * 0.15)
    assert abs(got_dx - dx) <= max(6, slot_w * 0.15)


def test_the_inset_is_what_carries_the_border_case(art, monkeypatch):
    """Hold the measurement that chose INSET, so it cannot be tuned away.

    With the whole portrait as the template the same framed bar is
    located far worse. If someone sets INSET to 0 because it looks like
    a free simplification, this says what it costs.
    """
    frame = frame_with_hud(*CASES[0][1:])
    grey = fp.autocal._grey(frame)
    with_inset = fp.hunt(grey, art)
    monkeypatch.setattr(fp, "INSET", 0.0)
    without = fp.hunt(grey, art)
    assert with_inset is not None
    kept = len(with_inset[2])
    assert kept >= 8, f"the inset sweep found only {kept}"
    assert kept >= len(without[2]) if without else True


# --------------------------------------------------------------------
# THE HERO ROSTER, which is the thing most likely to be mistaken for a
# pick bar and beat two versions of this sweep. During hero selection
# the screen carries the whole grid - 120-odd REAL portraits in rows -
# so every tile in it is a genuine match and a row of eighteen wins on
# "most distinct heroes found" against a bar of ten.
#
# Counting cannot tell them apart. Shape can: a pick bar is two banks of
# at most five with a wide gap between the teams, and a roster row is
# one long even run.


def frame_with_roster(width, height, radiant_x, dire_x, pitch, slot_w, top):
    """A pick bar at the top and the hero grid below it."""
    frame = frame_with_hud(width, height, radiant_x, dire_x, pitch, slot_w,
                           top)
    icon = max(12, int(slot_w * 0.55))
    tall = int(round(icon / fp.PORTRAIT_ASPECT))
    across = max(8, int((width * 0.62) // (icon + 4)))
    hero = 11
    for row in range(4):
        y = int(height * 0.30) + row * (tall + 6)
        if y + tall >= height:
            break
        for column in range(across):
            x = int(width * 0.19) + column * (icon + 4)
            if x + icon >= width:
                break
            hero = hero % HEROES + 1
            frame[y:y + tall, x:x + icon] = cv2.resize(
                art_for(hero), (icon, tall), interpolation=cv2.INTER_AREA)
            hero += 1
    return frame


@pytest.mark.parametrize("name,w,h,rx,dx,pitch,slot_w,top", CASES)
def test_the_hero_grid_does_not_win(art, name, w, h, rx, dx, pitch,
                                    slot_w, top):
    frame = frame_with_roster(w, h, rx, dx, pitch, slot_w, top)
    found = fp.hunt(fp.autocal._grey(frame), art)
    assert found is not None, f"{name}: recognised nothing"
    got_w, _got_h, hits = found
    assert len(hits) <= fp.MOST_HITS, (
        f"{name}: {len(hits)} portraits in one row is a roster, not a bar")
    banks = fp.banks_from(hits, got_w)
    assert banks is not None, f"{name}: hits did not form two banks"
    got_rx, got_dx, got_pitch, got_top = banks
    assert got_top < h * 0.12, (
        f"{name}: bar at {got_top / h:.1%} down the window — that is the "
        "grid, not the pick bar")
    assert abs(got_pitch - pitch) <= max(4, pitch * 0.08)
    assert abs(got_rx - rx) <= max(6, slot_w * 0.15)


def test_a_roster_row_is_refused_outright(art):
    """Shape, not count: eighteen evenly spaced heroes is never a bar."""
    hits = [(0.9, 40 + i * 60, 300, i + 1) for i in range(18)]
    assert fp.bar_shape(hits, 55) is None


def test_two_banks_of_five_are_accepted(art):
    """The same test must still say yes to the thing it is looking for."""
    xs = [40 + i * 60 for i in range(5)] + [700 + i * 60 for i in range(5)]
    hits = [(0.9, x, 8, i + 1) for i, x in enumerate(xs)]
    assert fp.bar_shape(hits, 55) is not None


# ---- a folder of the wrong pictures -------------------------------------

def test_a_snip_is_named_as_not_a_client():
    """**THE CROP BOXES ARE FRACTIONS, SO THEY "WORK" ON ANYTHING.**

    Six numbers times a width and a height cut ten tidy rectangles out of
    a 296x43 snip of a chat window, and the sheet then shows ten rows of
    nothing with no hint the folder was wrong. A real run over a real
    Screenshots folder produced exactly that: twelve pictures, none of
    them a game, every one processed. `--boxes-only` made it worse by
    design, since skipping the search skips the thing that would
    otherwise have failed loudly on a frame with no pick bar in it.
    """
    from tools.find_portraits import not_a_client

    # The shapes that actually turned up in that folder.
    assert "smaller than any resolution" in not_a_client(296, 43)
    assert "smaller than any resolution" in not_a_client(1045, 98)
    assert "smaller than any resolution" in not_a_client(928, 260)
    assert "wider than 32:9" in not_a_client(2279, 575)
    # The app's own window, which is taller than it is wide.
    assert "taller than it is wide" in not_a_client(923, 993)


def test_every_resolution_the_app_cares_about_is_allowed():
    """The guard must not refuse the frames the whole exercise is for —
    especially the two that fail today, which are the smallest and the
    ones most likely to trip a size floor."""
    from tools.find_portraits import not_a_client

    for width, height in [(800, 600), (1024, 768), (1280, 800), (1280, 1024),
                          (1440, 900), (1680, 1050), (1920, 1080),
                          (1920, 1200), (2560, 1440), (3440, 1440),
                          (5120, 1440)]:
        assert not_a_client(width, height) == "", f"{width}x{height} refused"
