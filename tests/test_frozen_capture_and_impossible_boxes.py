"""Two faults from one real bug report, 2026-10-06, 3440x1440.

The app said "the app could not find the hero portraits on screen" and
"nothing was read for 90s of hero selection". Both true. Neither was
about the crop boxes.

THE CAPTURE WAS FROZEN. 579 ticks, every one with a frame,
recognition run on 386 of them, `read_heroes` 0 on all 579 - and the
four frames the report carried, spread over three minutes of a draft,
were BYTE-IDENTICAL to one another and were a picture of the Dota main
menu. `stalled` could not see it: that watches whether a frame
ARRIVED, and they kept arriving.

AND THE CALIBRATION WAS IMPOSSIBLE. `dire_x` 0.6996 against the
shipped 0.5710 - 329px, which is 1.99 portrait pitches - with the
other five fractions matching the table to within four pixels. That is
the one failure `autocal` has: `banks_from` reads a bank's origin off
the first portrait it finds there, so missing the leading ones moves
that bank and nothing else. The result put the Dire bank 46px off the
right-hand edge of the HUD box, and the app used it anyway - for ever,
because a calibration file outranks the table and the boxes have to
land before a better one can be measured.
"""

import dataclasses
import json

import pytest

from draft_assist import bugreport
from draft_assist.vision.layout import (DraftLayout, calibration_in_use,
                                        load_layout, save_calibration,
                                        why_impossible)

# Exactly what the report said the app was using.
REPORTED = {"y": 0.0056, "slot_h": 0.0611, "radiant_x": 0.1090,
            "dire_x": 0.6996, "slot_w": 0.0605, "pitch": 0.0645}


# ---- the boxes --------------------------------------------------------

def test_the_shipped_layout_is_plausible():
    """The premise. If the shipped table ever fails this, the check is
    wrong rather than the table."""
    for size in ((3440, 1440), (1920, 1080), (2560, 1600), (1280, 1024)):
        assert why_impossible(load_layout(*size)) == "", size


def test_the_reported_calibration_is_refused():
    bad = dataclasses.replace(load_layout(3440, 1440), **REPORTED)
    why = why_impossible(bad)
    assert "off the right-hand edge" in why, why


def test_a_bank_one_pitch_out_is_refused_too():
    """The subtler form, and the one that stays ON the screen: a single
    missed leading portrait. The edge check cannot see it; the bar being
    centred can."""
    good = load_layout(3440, 1440)
    one_out = dataclasses.replace(good, dire_x=good.dire_x + good.pitch)
    assert why_impossible(one_out) == "" or "mirror" in why_impossible(one_out)
    assert why_impossible(one_out), "a whole pitch out must not pass"


def test_a_bad_file_is_ignored_and_the_table_takes_over(tmp_path):
    """The rescue. The machine in the report could never have recovered:
    the boxes never landed, so `repair` could never locate ten portraits,
    so it could never write a better file."""
    path = tmp_path / "calibration_local.json"
    path.write_text(json.dumps(REPORTED), encoding="utf-8")
    got = load_layout(3440, 1440, calibration_file=path)
    shipped = load_layout(3440, 1440)
    assert got.dire_x == pytest.approx(shipped.dire_x)
    assert got.radiant_x == pytest.approx(shipped.radiant_x)


def test_a_good_file_is_still_obeyed(tmp_path):
    """A real measurement must still outrank the table - that is the
    whole point of the file."""
    shipped = load_layout(3440, 1440)
    mine = dataclasses.replace(shipped, y=shipped.y + 0.001)
    path = tmp_path / "calibration_local.json"
    save_calibration(mine, calibration_file=path)
    got = load_layout(3440, 1440, calibration_file=path)
    assert got.y == pytest.approx(mine.y)


def test_an_impossible_calibration_cannot_be_saved(tmp_path):
    bad = dataclasses.replace(load_layout(3440, 1440), **REPORTED)
    path = tmp_path / "calibration_local.json"
    with pytest.raises(ValueError, match="refusing to save"):
        save_calibration(bad, calibration_file=path)
    assert not path.exists()


def test_the_latch_asks_whether_one_is_usable(tmp_path):
    """Not whether a file exists. Latching on existence would pin the
    session to the sizeless defaults and stop it keying the table on the
    real frame - worse than never having written the file."""
    path = tmp_path / "calibration_local.json"
    assert calibration_in_use(path) is False
    path.write_text(json.dumps(REPORTED), encoding="utf-8")
    assert calibration_in_use(path) is False
    save_calibration(load_layout(3440, 1440), calibration_file=path)
    assert calibration_in_use(path) is True


def test_rubbish_in_the_file_is_not_a_crash(tmp_path):
    path = tmp_path / "calibration_local.json"
    path.write_text("not json at all", encoding="utf-8")
    assert calibration_in_use(path) is False


# ---- the frozen picture ----------------------------------------------

def a_tick(**over):
    row = {"at": 0.0, "game_state": "DOTA_GAMERULES_STATE_HERO_SELECTION",
           "has_frame": True, "ran_recognition": True, "read_heroes": 0,
           "source": "none", "allies": ["Rubick"], "enemies": [],
           "crop_boxes_wrong": False, "sides_certain": True,
           "frozen_for": 0.0}
    row.update(over)
    return row


def a_folder(tmp_path, rows):
    folder = tmp_path / "2026-10-06_114634"
    (folder / "gsi").mkdir(parents=True)
    (folder / "frames").mkdir()
    (folder / "state.jsonl").write_text(
        "".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
    return folder


def test_a_frozen_capture_is_named_rather_than_the_boxes(tmp_path):
    rows = [a_tick(at=float(n), frozen_for=float(n), crop_boxes_wrong=True)
            for n in range(0, 95)]
    verdict = bugreport.grade(a_folder(tmp_path, rows))
    keys = [f.key for f in verdict.faults]
    assert keys == ["frozen"], keys
    assert "crop_boxes" not in keys, (
        "blaming the boxes sends somebody to recalibrate geometry that "
        "was never wrong")
    assert "blind" not in keys


def test_a_picture_that_keeps_changing_is_not_frozen(tmp_path):
    rows = [a_tick(at=float(n), frozen_for=0.2) for n in range(0, 95)]
    verdict = bugreport.grade(a_folder(tmp_path, rows))
    assert "frozen" not in [f.key for f in verdict.faults]


def test_a_recording_from_before_this_was_measured_says_nothing(tmp_path):
    """"not measured" rather than "it was fine" - the fault was invisible
    until it was recorded."""
    rows = [a_tick(at=float(n)) for n in range(0, 95)]
    for row in rows:
        row.pop("frozen_for")
    verdict = bugreport.grade(a_folder(tmp_path, rows))
    assert "frozen" not in [f.key for f in verdict.faults]


def test_the_session_measures_the_picture_not_its_arrival():
    """`stalled` watches whether a frame ARRIVED. They kept arriving."""
    import ast
    from pathlib import Path
    from draft_assist.capture import session as session_mod
    source = Path(session_mod.__file__).read_text(encoding="utf-8")
    assert "FROZEN_AFTER" in source
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "tick":
            body = ast.dump(node)
            assert "frozen_for" in body
            assert "_fingerprint" in body


def test_the_tolerance_clears_the_shipped_defaults():
    """`DraftLayout()`'s own six predate the table and are deliberately
    untouched. They are 0.0285 out of mirror, so a check that refused
    them would refuse the app's own starting point."""
    assert why_impossible(DraftLayout()) == ""


def test_the_tolerance_still_catches_one_portrait():
    """The bound on the other side: the smallest pitch any group uses is
    0.0645, well clear of the 0.04 tolerance."""
    from draft_assist.vision import measured
    for group in measured.GROUPS:
        assert group.reading.pitch > 0.04 * 1.5, group.label
