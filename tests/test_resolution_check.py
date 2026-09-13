"""Does the layout read the same at every screen resolution?

The app's coordinates are fractions of Dota's 16:9 HUD box, so every
16:9 resolution shares one calibration and anything WIDER is handled by
`hud_box` — confirmed on a real 3440x1440 client. What has never been
settled is the VERTICAL on a display TALLER than 16:9: `SlotRect.
to_pixels` reads `y` as a fraction of the WINDOW height, and if Dota
scales its HUD by width (which pillarboxing implies) it should be a
fraction of the HUD BOX's height instead. On 1920x1200 those are 60px
apart, which is most of a portrait.

CLAUDE.md says to settle that with a real frame rather than by
reasoning. `find_portraits` already measures both readings per
screenshot; what is checked here is the part that DECIDES between them —
including its refusal to decide from a sample that cannot answer.
"""

import importlib.util
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture(scope="module")
def tool():
    spec = importlib.util.spec_from_file_location(
        "find_portraits", ROOT / "tools" / "find_portraits.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules["find_portraits"] = module
    spec.loader.exec_module(module)
    return module


def shot(width, height, top, slot_h, bar="window"):
    """One measured screenshot, with the bar placed by one convention.

    A set built under one model must come out consistent under that
    model's reading and spread under the other two — which is exactly
    the discrimination being tested.
    """
    from draft_assist.vision.layout import hud_box
    _left, span = hud_box(width, height)
    hud_h = span / (16 / 9)
    return {
        "file": f"{width}x{height}.png", "w": width, "h": height,
        "aspect": round(width / height, 4),
        "x_of_hudbox": 0.0575, "slot_w_of_hudbox": 0.0525,
        "pitch_of_hudbox": 0.0640,
        "y_of_window": round(top / height, 5),
        "y_of_hudbox": round(top / hud_h, 5),
        "y_of_hudbox_centred": round(
            (top - (height - hud_h) / 2) / hud_h, 5),
        "slot_h_of_window": round(slot_h / height, 5),
        "slot_h_of_hudbox": round(slot_h / hud_h, 5),
    }


def by_window(width, height):
    return shot(width, height, top=0.033 * height, slot_h=0.093 * height)


def by_hud(width, height):
    """A 16:9 HUD hung at the TOP of a taller display."""
    from draft_assist.vision.layout import hud_box
    _left, span = hud_box(width, height)
    hud_h = span / (16 / 9)
    return shot(width, height, top=0.033 * hud_h, slot_h=0.093 * hud_h)


def by_letterbox(width, height):
    """A 16:9 HUD CENTRED in a taller display — the damaging one."""
    from draft_assist.vision.layout import hud_box
    _left, span = hud_box(width, height)
    hud_h = span / (16 / 9)
    return shot(width, height, top=(height - hud_h) / 2 + 0.033 * hud_h,
                slot_h=0.093 * hud_h)


MIXED = [(1920, 1080), (1920, 1200), (1600, 1200), (1280, 1024),
         (1440, 900), (2560, 1440)]
ALL_16_9 = [(1280, 720), (1600, 900), (1920, 1080), (2560, 1440)]


def test_it_finds_the_window_convention(tool, capsys):
    tool._vertical([by_window(w, h) for w, h in MIXED])
    out = capsys.readouterr().out
    assert "the bar is measured against the WINDOW's height" in out
    assert "nothing needs changing" in out


def test_it_finds_a_top_hung_hud_box(tool, capsys):
    tool._vertical([by_hud(w, h) for w, h in MIXED])
    out = capsys.readouterr().out
    assert "the bar is measured against a HUD BOX hung at the TOP" in out
    # The cost of being right about this is stated where it is decided.
    assert "invalidates every saved" in out


def test_it_finds_a_letterboxed_hud_box(tool, capsys):
    """The model that actually costs something, and the one that was
    missing until a test caught the arithmetic behind it."""
    tool._vertical([by_letterbox(w, h) for w, h in MIXED])
    out = capsys.readouterr().out
    assert "CENTRED (letterboxed)" in out
    assert "-> the bar is measured against a HUD BOX CENTRED" in out


def test_an_all_16_9_sample_is_refused(tool, capsys):
    """THE TRAP THIS GUARD EXISTS FOR. At 16:9 the HUD box IS the window,
    so the two readings are the same number by arithmetic and whichever
    the code prints would be an identity dressed as a measurement."""
    tool._vertical([by_window(w, h) for w, h in ALL_16_9])
    out = capsys.readouterr().out
    assert "UNDECIDABLE" in out
    assert "same number by arithmetic" in out
    assert "1920x1200" in out and "1600x1200" in out, (
        "a refusal has to name what would answer it")
    assert "measured against" not in out


def test_the_two_readings_really_are_identical_at_16_9(tool):
    """The premise of that refusal, checked rather than asserted."""
    for width, height in ALL_16_9:
        row = by_window(width, height)
        assert row["y_of_window"] == pytest.approx(row["y_of_hudbox"], abs=1e-4)
        assert row["y_of_window"] == pytest.approx(
            row["y_of_hudbox_centred"], abs=1e-4)
        assert row["slot_h_of_window"] == pytest.approx(
            row["slot_h_of_hudbox"], abs=1e-4)


def test_which_of_the_three_is_worth_the_measurement(tool):
    """Window-height against a TOP-HUNG hud box differ by the bar's own
    fraction of the slack — about 4px on 1920x1200, which nobody would
    see. The LETTERBOXED model differs by half the slack, 56px, which
    misses the portraits outright. That is the one this exists for."""
    row = by_window(1920, 1200)
    top_hung = abs(row["y_of_window"] - row["y_of_hudbox"]) * 1200
    letterboxed = abs(row["y_of_window"]
                      - row["y_of_hudbox_centred"]) * 1200
    assert top_hung < 8, f"{top_hung:.0f}px"
    assert letterboxed > 40, f"{letterboxed:.0f}px"


def test_a_wider_than_16_9_display_cannot_settle_it_either(tool, capsys):
    """Which is why the user's own 3440x1440 never could: there the HUD
    box is the full height and the vertical slack is nought."""
    tool._vertical([by_window(3440, 1440), by_window(2560, 1080),
                    by_window(1920, 1080)])
    assert "UNDECIDABLE" in capsys.readouterr().out


def test_noise_in_both_readings_produces_no_verdict(tool, capsys):
    """A measurement that cannot separate them must say so rather than
    pick the marginally tidier one."""
    rows = []
    for index, (width, height) in enumerate(MIXED):
        row = by_window(width, height)
        row["y_of_window"] += 0.03 * (index % 2)
        row["y_of_hudbox"] += 0.031 * (index % 2)
        rows.append(row)
    tool._vertical(rows)
    out = capsys.readouterr().out
    assert "NO VERDICT" in out


def test_one_picture_says_nothing_at_all(tool, capsys):
    tool._vertical([by_window(1920, 1200)])
    assert capsys.readouterr().out == ""


def test_the_measurement_reports_both_readings(tool):
    """`_vertical` can only decide because `measure` emits both. The
    HUD-box slot height was missing and is the half that was added."""
    import inspect
    source = inspect.getsource(tool.measure)
    for key in ("y_of_window", "y_of_hudbox", "y_of_hudbox_centred",
                "slot_h_of_window", "slot_h_of_hudbox"):
        assert f'"{key}"' in source


def test_the_check_is_a_button_rather_than_a_command(tool):
    """"I still don't understand why I need to manually type this
    command into Command Prompt." """
    from draft_assist.ui.tasks import TASKS
    task = TASKS["check_resolutions"]
    assert any("find_portraits.py" in part
               for step in task.steps for part in step)
    assert any("{arg}" in part for step in task.steps for part in step)
    filled = task.with_argument("/some/folder")
    assert any("/some/folder" in part
               for step in filled.steps for part in step)
