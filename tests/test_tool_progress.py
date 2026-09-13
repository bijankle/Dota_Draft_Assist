"""A run that says nothing is indistinguishable from a hang.

"There is no ability to see what the program is thinking." The
resolution sweep is about a minute PER PICTURE across 23 pictures, and
it shipped printing nothing in that minute — so this checks the plumbing
that carries a percentage out of the tool and into the dialog's bar and
the window's status line.

Two faults behind it, and the second is why the first was not enough.
`find_portraits` had no PROGRESS protocol at all, so the dialog's bar
(`task_dialog.PERCENT`) never moved and `_tool_progress` never fired.
And what it DID print per picture was a `[3/23] name ...` written with
`end=""` and erased with a carriage return — which does nothing in a
text box, and worse: `tasks.Worker` reads the child with `for raw in
proc.stdout`, which yields LINES, so a write with no newline is not
emitted at all until the next one arrives. `score_recording` carries
this lesson in a comment; this tool was written without it.
"""

import importlib.util
import sys
from pathlib import Path

import numpy as np
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


def test_every_progress_line_moves_the_dialogs_bar(tool, capsys):
    """The bar reads the tool's own marked lines rather than guessing at
    numbers in ordinary output."""
    from draft_assist.ui.task_dialog import PERCENT
    for share in (0.0, 0.014, 0.337, 0.999, 1.0):
        tool.step(share, "1920x1200.png")
    lines = capsys.readouterr().out.splitlines()
    assert len(lines) == 5
    assert [PERCENT.match(line).group(1) for line in lines] == [
        "0", "1", "34", "100", "100"]


def test_a_progress_line_is_a_whole_line(tool, capsys):
    """The carriage-return version never reached the dialog at all,
    because the worker iterates LINES."""
    tool.step(0.5, "half way")
    out = capsys.readouterr().out
    assert out.endswith("\n")
    assert "\r" not in out


def test_the_share_is_clamped(tool, capsys):
    """Rounding inside the tool must never print 101% or -0%."""
    for share in (-0.2, 1.4):
        tool.step(share, "x")
    assert [line.split()[1] for line in
            capsys.readouterr().out.splitlines()] == ["0%", "100%"]


def test_the_line_also_carries_words_for_the_status_bar(tool, capsys):
    tool.step(0.25, "1920x1200.png  (6 of 23)")
    line = capsys.readouterr().out.strip()
    assert line.startswith("PROGRESS 25%")
    assert "1920x1200.png  (6 of 23)" in line


def test_the_hunt_reports_while_it_sweeps(tool):
    """THE MINUTE THAT WAS SILENT. The size sweep is 24 widths x 3
    aspects over every hero, and it is nearly the whole of a picture's
    time — so it has to report from inside, not only at each end."""
    art = {i: (np.random.default_rng(i).random((144, 256)) * 255
               ).astype("uint8") for i in range(12)}
    grey = (np.random.default_rng(0).random((1080, 1920)) * 255
            ).astype("uint8")
    seen = []
    tool.hunt(grey, art, tick=seen.append)
    sweep = len(tool.WIDTH_FRACS) * len(tool.ASPECTS)
    assert len(seen) >= sweep, (
        f"{len(seen)} reports for {sweep} passes — the sweep is silent")
    assert seen == sorted(seen), "progress went backwards"
    assert 0.0 <= min(seen) <= max(seen) <= 1.0


def test_the_sweep_does_not_claim_the_whole_bar(tool):
    """A bar that reaches 100% and then sits there is the same silence
    with a number on it — the refine after the sweep is real work."""
    assert 0.0 < tool.SWEEP_SHARE < 1.0
    art = {i: (np.random.default_rng(i).random((144, 256)) * 255
               ).astype("uint8") for i in range(12)}
    grey = (np.random.default_rng(0).random((1080, 1920)) * 255
            ).astype("uint8")
    seen = []
    tool.hunt(grey, art, tick=seen.append)
    sweep = len(tool.WIDTH_FRACS) * len(tool.ASPECTS)
    assert seen[sweep - 1] == pytest.approx(tool.SWEEP_SHARE, abs=1e-6)


def test_the_erase_trick_is_gone_from_the_tool():
    """It is invisible in a console (where it worked) and junk in the
    dialog (where this is actually run), so it must not come back.

    CODE ONLY, never the whole file: the comment explaining this bug
    quotes the very thing being banned, and a scan that cannot tell a
    warning about a mistake from the mistake is a scan that forces the
    explanation to be deleted.
    """
    import io
    import tokenize

    path = ROOT / "tools" / "find_portraits.py"
    with open(path, "rb") as handle:
        tokens = list(tokenize.tokenize(handle.readline))
    code = "".join(
        token.string for token in tokens
        if token.type not in (tokenize.COMMENT, tokenize.STRING))
    assert "\r" not in code, "a carriage return is back in the tool"
    assert "end=" not in code, "a print without a newline is back"


def test_each_run_names_itself_on_the_status_bar():
    """Two tools report through one handler; a resolution sweep calling
    itself "Recognition check" is a status line lying about what is
    happening."""
    import inspect

    from draft_assist.ui.app import MainWindow
    assert "Recognition check" in inspect.getsource(
        MainWindow._recognition_progress)
    assert "Resolutions" in inspect.getsource(
        MainWindow._resolutions_progress)
    body = inspect.getsource(MainWindow._tool_progress)
    assert "{label}" in body


def test_the_resolution_run_is_wired_to_its_own_label():
    import inspect

    from draft_assist.ui.app import MainWindow
    body = inspect.getsource(MainWindow._check_resolutions)
    assert 'label="Resolutions"' in body
    opener = inspect.getsource(MainWindow._open_tool)
    assert "_tool_progress" in opener


def test_the_picker_starts_where_onedrive_actually_puts_screenshots():
    """OneDrive REDIRECTS the Pictures folder, so `~/Pictures/
    Screenshots` is not where they are when Backup is on — which is why
    the first version opened on an empty folder."""
    from draft_assist.ui.app import MainWindow
    assert MainWindow.SHOT_FOLDERS[0] == (
        "OneDrive", "Pictures", "Screenshots")
    assert ("Pictures", "Screenshots") in MainWindow.SHOT_FOLDERS
    # Never raises, whatever exists on this machine.
    assert isinstance(MainWindow._shots_folder(), Path)


def test_an_empty_folder_is_refused_before_the_run_starts():
    """The tool exits with "No images in ..." on stderr, which arrives
    as a FAILED run with one line in it — a worse way to say "wrong
    folder" than saying so before anything starts.

    It lives on the WINDOW now rather than ahead of it: the folder row
    is inside the same window as Run, so a wrong folder is corrected
    without starting over. `tests/test_tool_window.py` drives it."""
    import inspect

    from draft_assist.ui.tool_window import ToolWindow
    body = inspect.getsource(ToolWindow._choose)
    assert "no pictures in this folder" in body
    ready = inspect.getsource(ToolWindow._ready)
    assert "self.folder" in ready, "Run has to be gated on having one"
