"""One picture: every resolution's ten crops, a labelled row each.

"If there are five different resolutions, I want you to show me five
sets of 10 portraits that you have snipped out of the example
screenshots that I put in that folder."

The per-picture `-slices.png` files have existed throughout and were no
use for this — fourteen files in a folder, opened one at a time, is not
a comparison, and nothing ever opened them. That is the same fault as
the dialog that was never shown: a thing produced where nobody is
looking has not been produced.
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


def a_row(width=900, tall=120):
    return np.full((tall + 46, width, 3), 60, np.uint8)


def test_one_row_per_resolution(tmp_path):
    rows = [("1920x1200", a_row(900)), ("1280x1024", a_row(700)),
            ("800x600", a_row(400))]
    where = fp.proof_sheet(rows, tmp_path)
    assert where is not None and where.is_file()
    sheet = cv2.imdecode(
        np.frombuffer(where.read_bytes(), np.uint8), cv2.IMREAD_COLOR)
    # As tall as every row plus the gaps, and as wide as the widest.
    assert sheet.shape[0] >= sum(r.shape[0] for _n, r in rows)
    assert sheet.shape[1] == fp.LABEL_W + 900


def test_the_label_column_is_left_of_every_crop(tmp_path):
    """A row you cannot name is a row you cannot act on."""
    where = fp.proof_sheet([("1920x1200", a_row(600))], tmp_path)
    sheet = cv2.imdecode(
        np.frombuffer(where.read_bytes(), np.uint8), cv2.IMREAD_COLOR)
    label = sheet[:, :fp.LABEL_W]
    assert label.max() > 200, "nothing was written in the label column"
    # And the crops start after it, not under it.
    assert sheet.shape[1] > fp.LABEL_W


def test_nothing_is_written_when_nothing_located(tmp_path):
    assert fp.proof_sheet([], tmp_path) is None
    assert fp.proof_sheet([("1920x1200", None)], tmp_path) is None
    assert not (tmp_path / fp.SHEET_NAME).exists()


def test_a_picture_that_failed_contributes_no_row(tmp_path):
    where = fp.proof_sheet(
        [("1920x1200", a_row(600)), ("1024x768", None)], tmp_path)
    sheet = cv2.imdecode(
        np.frombuffer(where.read_bytes(), np.uint8), cv2.IMREAD_COLOR)
    assert sheet.shape[0] < 2 * (a_row(600).shape[0] + 8) + 8


def test_the_crops_are_the_slices_that_are_already_written():
    """Two spellings of "cut the ten boxes out" is one of them drifting,
    so `slices` and the sheet share `crop_row`."""
    import inspect
    body = inspect.getsource(fp.slices)
    assert "crop_row(" in body


def test_the_run_marks_the_sheet_rather_than_printing_a_bare_path():
    import inspect
    body = inspect.getsource(fp.main)
    assert "{SHEET} {where}" in body


def test_the_json_report_never_carries_pixels(tmp_path):
    """`json.dumps` cannot encode an ndarray, and it is the very last
    line of a twenty-minute run."""
    import inspect
    body = inspect.getsource(fp.main)
    assert 'k != "crops"' in body


# --- and the window opens it -------------------------------------------

def test_a_write_that_fails_costs_the_picture_and_nothing_else(
        tmp_path, monkeypatch, capsys):
    """It took a fourteen-minute run down to prove this. The sheet is
    the LAST thing written, after every measurement is already on
    screen: the rule `Recorder` has always followed is that a full disk
    costs the recording and never the draft."""
    # THE REAL WRITE, which is `open(path, "wb")` and a chunked write —
    # this test used to patch `Path.write_bytes` and went on passing
    # against a writer that no longer exists. Errno 22 is the one the
    # user's own run came back with.
    import builtins
    real_open = builtins.open

    def boom(file, mode="r", *args, **kwargs):
        if "w" in mode and str(file).endswith(fp.SHEET_NAME):
            raise OSError(22, "Invalid argument")
        return real_open(file, mode, *args, **kwargs)
    monkeypatch.setattr(builtins, "open", boom)
    assert fp.proof_sheet([("1920x1200", a_row(600))], tmp_path) is None
    monkeypatch.undo()
    printed = capsys.readouterr().out
    assert "could not be written" in printed
    # AND IT NAMES THE PATH. "Invalid argument" on a path nobody can
    # see is unanswerable.
    assert "proof-sheet.png" in printed
    # …and what it was asked to write, and whether the FOLDER takes a
    # byte at all, which is the difference between this picture and
    # this directory. Both were missing from the message that reached
    # the user, and between them they are the whole diagnosis.
    assert "bytes" in printed
    assert "folder" in printed


def test_a_runaway_row_cannot_blow_the_sheet_up(tmp_path):
    """Every crop is scaled to one HEIGHT, so a fit that came back a
    quarter of the true height is blown up four times as wide."""
    rows = [("1920x1200", a_row(900)), ("1280x1024", a_row(700)),
            ("1680x1050", a_row(30000))]
    where = fp.proof_sheet(rows, tmp_path)
    assert where is not None
    sheet = cv2.imdecode(
        np.frombuffer(where.read_bytes(), np.uint8), cv2.IMREAD_COLOR)
    assert sheet.shape[1] < 30000
