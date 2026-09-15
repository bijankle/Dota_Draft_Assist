"""Two recognition tools back on the Help menu, and the guard that would
have saved the first real run of one of them.

**WHY THEY ARE BACK.** The whole Recognition checks submenu was removed
at the user's request — "all of those were used to refine the software -
once its done i dont nteed them" — and this REVERSES that for exactly
two of the four: "if its complex - add the code launching via the help
dropdown as you did before". A console IS complex here: a virtual
environment path, a quoted folder with spaces in it, and a flag, all
typed correctly before anything happens.

**AND THE FIRST ATTEMPT PROVED IT.** Run by hand against
`%USERPROFILE%\\OneDrive\\Pictures\\Screenshots` — the general folder,
not the Dota one — `--boxes-only` cut ten tidy rectangles out of a
shopping site, File Explorer, a chat window and this app's own title
bar, and stacked them into a proof sheet that looks exactly like a
measurement. "way off".

Nothing was wrong with the tool: the crop boxes are FRACTIONS, so they
work on anything, and `--boxes-only` skips the search, which is the step
that normally fails loudly on a frame with no pick bar in it. What was
missing is the test below — a full-screen capture is at a resolution a
monitor offers, and a window snip is at whatever size the window
happened to be.
"""

import dataclasses
import json
import os
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


def _tool():
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "find_portraits_under_test", ROOT / "tools" / "find_portraits.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# Every size on the proof sheet the user sent back. Not one of them is a
# display resolution, and every one passed the size-and-aspect test that
# was the only guard at the time.
THE_WRONG_FOLDER = [
    (1272, 549), (1489, 804), (1454, 752), (1610, 722), (922, 612),
    (1652, 1223), (891, 483), (934, 598), (934, 654), (2558, 1190),
    (931, 668), (926, 674), (940, 677),
]

REAL = [(1920, 1080), (3440, 1440), (1920, 1200), (1440, 900),
        (1024, 768), (800, 600), (1280, 1024), (1366, 768)]


def test_every_picture_from_that_run_is_refused_now():
    tool = _tool()
    for size in THE_WRONG_FOLDER:
        why = tool.not_a_client(*size)
        assert why, f"{size[0]}x{size[1]} would still be measured"
        assert "resolution" in why, why


def test_and_every_real_resolution_is_still_kept():
    """The guard has to be narrower than the thing it refuses, or it
    throws away the sample it exists to protect. These are the shapes
    the app's own resolution table is written against."""
    tool = _tool()
    for size in REAL:
        assert tool.not_a_client(*size) == "", size


def test_a_windowed_client_is_askable_for_rather_than_impossible():
    """Windowed Dota really can be 1489x804, and the crop boxes are
    fractions of the WINDOW, so it would still be measured correctly.
    `--any-size` is the difference between "this cannot be right" and
    "this is usually the wrong folder"."""
    tool = _tool()
    assert tool.not_a_client(1489, 804) != ""
    assert tool.not_a_client(1489, 804, any_size=True) == ""
    # The harder tests are NOT turned off by it: a 296x43 snip is not a
    # client at any size.
    assert tool.not_a_client(296, 43, any_size=True) != ""


def test_the_three_tools_are_on_the_help_menu_and_take_a_folder(qapp_window):
    window = qapp_window
    names = {act.text(): act for act in window.help_menu.actions()
             if act.menu()}
    assert "&Recognition" in names, "the submenu is missing"
    items = [a.text() for a in names["&Recognition"].menu().actions()]
    assert items == ["&Check the crop boxes…", "&Locate the portraits…",
                     "&Fix the crop boxes…"]


def test_each_one_runs_the_real_script_with_the_flag_that_names_it():
    """The two answer different questions and the flags are the whole
    difference: `--boxes-only` shows what the app is GRABBING (seconds),
    the search measures where the bar really IS (a minute a picture)."""
    from draft_assist.ui.tasks import TASKS

    boxes = TASKS["check_crop_boxes"].steps
    locate = TASKS["locate_portraits"].steps
    assert boxes == [["{py}", "tools/find_portraits.py", "{arg}",
                      "--boxes-only"]]
    assert locate == [["{py}", "tools/find_portraits.py", "{arg}", "--tall"]]
    # {arg} is the folder the picker returns, filled in by `with_argument`.
    filled = TASKS["check_crop_boxes"].with_argument("D:/shots")
    assert filled.steps[0][2] == "D:/shots"
    assert (ROOT / "tools" / "find_portraits.py").is_file()


def test_the_picker_opens_where_the_dota_shots_are(qapp_window):
    """OneDrive REDIRECTS `Pictures` when Backup is on, so the plain path
    is not enough on its own — and the Dota set is a SUBFOLDER of
    Screenshots, which is the distinction the wrong-folder run turned
    on."""
    window = qapp_window
    tails = window.SHOT_FOLDERS
    assert tails[0].endswith("All Resolutions - Dota 2")
    assert any(t.startswith("OneDrive/") for t in tails)
    assert any(not t.startswith("OneDrive/") for t in tails)
    # It always answers something openable rather than "".
    assert Path(window._shots_folder()).is_dir()


@pytest.fixture()
def qapp_window(qapp):
    from draft_assist.config import RULES_FILE
    from draft_assist.model import items as items_mod
    from draft_assist.ui.app import MainWindow
    from draft_assist.ui.demo import demo_dataset
    from draft_assist.ui.providers import DemoProvider

    ds = demo_dataset()
    rules, meta = items_mod.load_rules(RULES_FILE)
    window = MainWindow(ds, DemoProvider(ds), rules, meta)
    window.timer.stop()
    yield window
    window.close()


@pytest.fixture(scope="module")
def qapp():
    from PyQt6.QtWidgets import QApplication
    yield QApplication.instance() or QApplication([])


def test_the_sheet_shows_what_the_box_MISSED_as_well_as_what_it_caught():
    """The first sheet from the right folder could not be acted on.

    Every one of its 220 crops came back holding the player's NAME, and
    a crop cut exactly to the box is consistent with three different
    faults: a box half a portrait too low, a box twice too tall, and a
    screenshot of a screen with no pick bar on it. They need three
    different fixes and the picture could not tell them apart — which is
    the same shape as the refusal that reported "no hero portrait
    recognised" for five distinct reasons.

    So the tile carries a margin of the frame around the box, with the
    box drawn on it: the portrait it missed is in the same tile as the
    miss, and by how much is readable off the picture.
    """
    tool = _tool()
    assert tool.BOX_CONTEXT > 0
    frame = np.zeros((300, 800, 3), np.uint8)
    frame[:, :] = (40, 40, 40)
    boxes = [(100 + i * 60, 120, 40, 50) for i in range(10)]
    # The portrait the box MISSED: a band directly above every box, of a
    # colour that is nowhere inside one.
    MISSED = (200, 30, 160)
    frame[100:120, :] = MISSED

    bare = tool.crop_row(frame, boxes)
    padded = tool.crop_row(frame, boxes, context=tool.BOX_CONTEXT)
    # The tile is the same SHAPE — padding by a fraction of the box in
    # both axes keeps its aspect, so it is not the size that changed but
    # what is in it.
    assert bare.shape == padded.shape
    assert MISSED not in set(map(tuple, bare.reshape(-1, 3).tolist())), (
        "the bare crop should show only what the box caught")
    colours = set(map(tuple, padded.reshape(-1, 3).tolist()))
    assert MISSED in colours, "the padded crop shows no context at all"
    # And the box itself is drawn over it, in each bank's own colour.
    assert (90, 220, 90) in colours, "no green box on the left bank"
    assert (80, 80, 240) in colours, "no red box on the right bank"


def test_a_box_hard_against_the_edge_is_still_drawn_in_the_right_place():
    """The clamp is the trap: the first box of a bank often sits within
    its own width of the left edge, so the crop cannot take the margin it
    asked for — and drawing the rectangle at the PADDING rather than at
    where the crop actually started would put it wherever the clamp left
    it. Nothing raises; the line is simply in the wrong place, on the one
    tile somebody checks first."""
    tool = _tool()
    frame = np.zeros((200, 400, 3), np.uint8)
    # x=2 with a 40-wide box: the 24px margin cannot fit on the left.
    row = tool.crop_row(frame, [(2, 90, 40, 40)], tall=120,
                        context=tool.BOX_CONTEXT)
    green = np.argwhere(np.all(row == (90, 220, 90), axis=2))
    assert green.size, "the box was not drawn at all"
    left = green[:, 1].min()
    # Two frame pixels, scaled up by whatever it took to make the crop
    # 120 tall, plus the sheet's own 6px gutter — a handful of pixels in,
    # NOT the 24px margin that could not fit.
    assert left < 20, f"the box was drawn at {left}, as if unclamped"


def test_apply_writes_the_machines_own_calibration_and_never_the_source():
    """`--apply` is the whole difference between a sheet that shows the
    boxes are wrong and boxes that are not wrong any more.

    What it may write is `calibration_local.json` — gitignored, one
    machine's own, already replaced by the app's own measurement at the
    next strategy time. What it may NOT write is `DraftLayout`'s
    defaults in the source, which every install inherits and which a
    median over one person's screenshots is not evidence enough to move.
    """
    tool = _tool()
    source = (ROOT / "tools" / "find_portraits.py").read_text("utf-8")
    assert "save_calibration" in source
    # The shipped six are read, never assigned.
    assert "DraftLayout.y =" not in source
    assert "shipped = DraftLayout()" in source


def test_apply_refuses_when_no_fraction_has_a_majority(
        tmp_path, monkeypatch):
    """A median is a measurement only while the pictures behind it
    agree. With every frame saying something different there is nothing
    to write, and the refusal names the count rather than the fact."""
    tool = _tool()
    frames = _their_frames(tool)
    for index, frame in enumerate(frames):
        for key in ("x_of_hudbox", "dire_x_of_hudbox", "slot_w_of_hudbox",
                    "pitch_of_hudbox", "y_of_window", "slot_h_of_window"):
            frame[key] = 0.02 + index * 0.05
    assert _apply(tool, frames, tmp_path, monkeypatch) is None


def test_apply_and_boxes_only_together_are_refused():
    """`--boxes-only` makes no measurement by design — it cuts the
    shipped fractions out and stops. Asked for both, the run must say so
    rather than writing back the numbers it just read."""
    out = subprocess.run(
        [sys.executable, str(ROOT / "tools" / "find_portraits.py"),
         str(ROOT), "--boxes-only", "--apply"],
        capture_output=True, text=True, timeout=120)
    assert out.returncode != 0
    assert "--apply needs the search" in (out.stderr + out.stdout)


# The user's own run, transcribed from the table it printed: the pixel
# fit of six screenshots that each located all ten portraits. 1440x900
# is the frame that run named an outlier twice over, and it is kept here
# deliberately — the point of these tests is what it does to the others.
THEIR_RUN = [
    ("1024 x 768",  55, 606,  72,  72,  4, 39, 1024, 768),
    ("1280 x 1024", 70, 757,  91,  90,  6, 50, 1280, 1024),
    ("1360 x 768", 141, 777,  84,  89,  4, 46, 1360, 768),
    ("1440 x 900",  22, 1056, 67,  56, 72, 47, 1440, 900),
    ("1600 x 1200", 81, 950, 112, 114,  6, 63, 1600, 1200),
    ("1920 x 1080", 208, 1096, 118, 124, 6, 66, 1920, 1080),
]


def _their_frames(tool):
    out = []
    for name, rx, dx, sw, pitch, top, sh, w, h in THEIR_RUN:
        _left, span = tool.hud_box(w, h)
        out.append({"file": name,
                    "x_of_hudbox": rx / span, "dire_x_of_hudbox": dx / span,
                    "slot_w_of_hudbox": sw / span,
                    "pitch_of_hudbox": pitch / span,
                    "y_of_window": top / h, "slot_h_of_window": sh / h})
    return out


def _apply(tool, frames, tmp_path, monkeypatch):
    written = tmp_path / "calibration_local.json"
    monkeypatch.setattr(tool, "CALIBRATION_FILE", written)
    monkeypatch.setattr(tool.layout_mod, "save_calibration",
                        lambda layout, f=None: written.write_text(
                            json.dumps(dataclasses.asdict(layout))))
    tool._fitted_layout(frames, apply=True)
    return json.loads(written.read_text()) if written.exists() else None


def test_one_bad_frame_does_not_veto_what_five_others_agree_on(
        tmp_path, monkeypatch):
    """The first version took a MEDIAN and then gated it on the WORST
    MISS — a robust estimator guarded by a non-robust one, so a single
    bad fit vetoed all six fractions.

    On the user's own run `y` measured 0.0052, 0.0059, 0.0052, 0.0050
    and 0.0056 on five frames and 0.0800 on 1440x900, which that same
    run had already named an outlier twice. Nothing was written. The
    whole reason the median is the estimator is that it survives a
    minority of bad fits.
    """
    tool = _tool()
    on_disk = _apply(tool, _their_frames(tool), tmp_path, monkeypatch)
    assert on_disk is not None, "a settled measurement was not written"
    assert round(on_disk["y"], 4) == 0.0054
    assert round(on_disk["slot_h"], 4) == 0.0524


def test_the_two_that_do_not_settle_are_the_two_BANK_ORIGINS(
        tmp_path, monkeypatch):
    """Not a coincidence, and it is the reason to believe the other four.

    `banks_from` reads a bank's origin off the FIRST portrait it found
    in that bank, so a missed leading portrait moves that origin by a
    whole pitch — and moves nothing else: not the row's top edge, not
    the portrait's height, not the median step between portraits. The
    fractions that disagree across the user's six frames are exactly
    `radiant_x` and `dire_x`, which is the only failure mode that can
    reach them.
    """
    tool = _tool()
    on_disk = _apply(tool, _their_frames(tool), tmp_path, monkeypatch)
    shipped = tool.DraftLayout()
    assert on_disk["radiant_x"] == shipped.radiant_x, "an unsettled origin"
    assert on_disk["dire_x"] == shipped.dire_x, "an unsettled origin"
    # …while the four that a missed leading portrait cannot reach moved.
    for name in ("slot_w", "pitch", "y", "slot_h"):
        assert on_disk[name] != getattr(shipped, name), name


def test_a_fraction_nobody_agrees_on_keeps_the_shipped_value(
        tmp_path, monkeypatch):
    """A partial file would leave the rest to whatever a later default
    happened to be, so all six are named either way — the unsettled ones
    with the number they already had."""
    tool = _tool()
    frames = _their_frames(tool)
    for index, frame in enumerate(frames):        # every frame disagrees
        frame["slot_h_of_window"] = 0.02 + index * 0.05
    on_disk = _apply(tool, frames, tmp_path, monkeypatch)
    assert on_disk["slot_h"] == tool.DraftLayout().slot_h
    # The two fractions nothing can measure are kept rather than zeroed.
    assert on_disk["role_dy"] == tool.DraftLayout().role_dy


def test_too_few_pictures_is_not_a_measurement(tmp_path, monkeypatch):
    """One constant measured twice is a definition rather than a law —
    the argument `spread_over_spans` is built on."""
    tool = _tool()
    on_disk = _apply(tool, _their_frames(tool)[:2], tmp_path, monkeypatch)
    assert on_disk is None


def test_a_picture_that_cannot_be_written_says_so_and_does_not_raise(
        tmp_path):
    """A whole run came back with every number on screen and `OSError:
    [Errno 22] Invalid argument` where the proof sheet should have been.
    "Invalid argument" names nothing — so the message carries what was
    being written and whether the FOLDER takes a byte at all, which is
    the difference between this picture and this directory.
    """
    tool = _tool()
    art = np.zeros((40, 60, 3), np.uint8)
    good = tmp_path / "sheet.png"
    where, note = tool.save_png(good, art)
    assert where == good and note == ""
    assert good.stat().st_size > 0
    import cv2
    back = cv2.imread(str(good))
    assert back is not None and back.shape == art.shape

    where, note = tool.save_png(tmp_path / "no-such-folder" / "sheet.png", art)
    assert where is None, "a folder that does not exist wrote something"
    assert note, "a failed write reported nothing at all"
    assert "60x40" in note, f"the picture's size is not in {note!r}"
    assert "bytes" in note
    assert "folder" in note


def test_a_name_it_cannot_have_is_not_a_reason_to_lose_the_picture(
        tmp_path, monkeypatch):
    """At the user's request: "make sure that a copy of the file gets
    created with a new name if it is not able to be created".

    The proof sheet is the ONE file here written to the same name every
    run — the per-picture files are named after their picture — so it is
    the one that can be open in a viewer while the next run tries to
    overwrite it, which on Windows is a locked file and a refused write.
    Twenty minutes of measurement should not be lost to a name.
    """
    tool = _tool()
    art = np.zeros((20, 30, 3), np.uint8)
    taken = tmp_path / "proof-sheet.png"
    taken.write_bytes(b"pretend this is open in a viewer")

    import builtins
    real_open = builtins.open

    def boom(file, mode="r", *args, **kwargs):
        if "w" in mode and Path(file).name == taken.name:
            raise OSError(22, "Invalid argument")
        return real_open(file, mode, *args, **kwargs)
    monkeypatch.setattr(builtins, "open", boom)

    where, note = tool.save_png(taken, art)
    monkeypatch.undo()
    assert where is not None, "the picture was lost to a name"
    assert where.name == "proof-sheet-2.png", where.name
    assert where.read_bytes()[:4] == b"\x89PNG"
    # THE ONE THAT COULD NOT BE WRITTEN IS UNTOUCHED — whatever is
    # holding it keeps it.
    assert taken.read_bytes() == b"pretend this is open in a viewer"
    # AND THE CALLER IS TOLD, because a file that quietly appears under
    # a name nobody was given is a file nobody opens.
    assert "proof-sheet.png" in note and "proof-sheet-2.png" in note


def test_the_fallback_is_a_last_resort_rather_than_the_habit(tmp_path):
    """Overwriting is right — a folder of proof-sheet-2, -3, -4 nobody
    can tell apart is worse than one sheet that is always the latest."""
    tool = _tool()
    art = np.zeros((20, 30, 3), np.uint8)
    for _ in range(3):
        where, note = tool.save_png(tmp_path / "proof-sheet.png", art)
        assert where.name == "proof-sheet.png" and note == ""
    assert [f.name for f in tmp_path.iterdir()] == ["proof-sheet.png"]


def test_the_marked_SHEET_line_names_the_file_that_was_actually_written(
        tmp_path, monkeypatch):
    """The window opens what that line names, so a sheet that fell back
    to another name and a line still naming the first one is a window
    opening a stale picture — or none."""
    tool = _tool()
    row = np.zeros((166, 400, 3), np.uint8)
    (tmp_path / tool.SHEET_NAME).write_bytes(b"held open")

    import builtins
    real_open = builtins.open

    def boom(file, mode="r", *args, **kwargs):
        if "w" in mode and Path(file).name == tool.SHEET_NAME:
            raise OSError(22, "Invalid argument")
        return real_open(file, mode, *args, **kwargs)
    monkeypatch.setattr(builtins, "open", boom)
    where = tool.proof_sheet([("1920x1080", row)], tmp_path)
    monkeypatch.undo()
    assert where is not None and where.name != tool.SHEET_NAME
    assert where.exists() and where.stat().st_size > 0


def test_every_picture_this_tool_writes_goes_through_one_writer():
    """Four of the six were `if ok:` and nothing else, so an encode that
    failed or a write that was refused left no file and said NOTHING —
    while the closing advice went on telling the reader to open them."""
    source = (ROOT / "tools" / "find_portraits.py").read_text("utf-8")
    assert source.count("cv2.imencode") == 1, "a second encode-and-write"
    assert "write_bytes(buffer" not in source
