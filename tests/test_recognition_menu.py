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


def test_apply_refuses_pictures_that_do_not_agree(tmp_path, monkeypatch):
    """A median is a measurement only while the frames behind it agree.
    One bad fit — a bank's origin read off the wrong portrait — moves it
    for every resolution, and the result would be a number on this
    machine that no single screenshot supports."""
    tool = _tool()
    written = tmp_path / "calibration_local.json"
    monkeypatch.setattr(tool.layout_mod, "CALIBRATION_FILE", written,
                        raising=False)
    monkeypatch.setattr(tool, "CALIBRATION_FILE", written)
    monkeypatch.setattr(tool.layout_mod, "save_calibration",
                        lambda layout, f=None: written.write_text(
                            json.dumps(dataclasses.asdict(layout))))

    tight = [(name, 0.05, 0.001, 0.04, "span")
             for name, *_ in tool.FRACTIONS]
    tool._write_calibration(tight)
    assert written.exists(), "an agreeing measurement was not written"
    on_disk = json.loads(written.read_text())
    assert on_disk["y"] == 0.05
    # The two it cannot measure are KEPT rather than left empty.
    assert on_disk["role_dy"] == tool.DraftLayout().role_dy

    written.unlink()
    loose = list(tight)
    loose[0] = (loose[0][0], 0.05, tool.AGREE_WITHIN + 0.01, 0.04, "span")
    tool._write_calibration(loose)
    assert not written.exists(), "a loose measurement was written anyway"


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
