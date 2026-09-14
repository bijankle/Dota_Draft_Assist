"""How many pictures does a scaling law actually need?

"Don't you need to update the 'Check other resolutions' to only check 1
now?" Half right, and the half that is wrong is the important one: ONE
PICTURE CANNOT DEMONSTRATE SCALING AT ALL. A single point fits any
constant you care to name, so `slot_w = k x span` measured on one
screenshot is not a law - it is a definition of k. What shows the law
is the same k predicting a span it never saw.

It does not need all fourteen either. The folder holds eight distinct
spans from 800 to 1920, and five spread across that range cover it
exactly as well, in a third of the time.
"""

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools import find_portraits as fp

FOLDER = {
    "800x600": (800, 600), "1024x768": (1024, 768), "1152x864": (1152, 864),
    "1280x768": (1280, 768), "1280x800": (1280, 800),
    "1280x960": (1280, 960), "1280x1024": (1280, 1024),
    "1440x900": (1440, 900), "1440x1080": (1440, 1080),
    "1600x1024": (1600, 1024), "1600x1200": (1600, 1200),
    "1680x1050": (1680, 1050), "1920x1200": (1920, 1200),
    "1920x1440": (1920, 1440),
}


@pytest.fixture()
def folder(tmp_path):
    shots = [tmp_path / f"{name}.png" for name in FOLDER]
    sizes = {shot: FOLDER[shot.stem] for shot in shots}
    return shots, sizes


def spans(picked, sizes):
    return sorted(round(fp.hud_box(*sizes[shot])[1]) for shot in picked)


def test_five_cover_the_same_range_as_all_of_them(folder):
    shots, sizes = folder
    picked = fp.spread_over_spans(shots, sizes, 5)
    assert len(picked) == 5
    got, every = spans(picked, sizes), spans(shots, sizes)
    assert min(got) == min(every), "the smallest span must be in"
    assert max(got) == max(every), "the largest span must be in"


def test_the_ends_are_always_taken(folder):
    """The RANGE is what is being tested; an interpolation between two
    close points proves the least."""
    shots, sizes = folder
    for how_many in (2, 3, 4, 5, 6):
        got = spans(fp.spread_over_spans(shots, sizes, how_many), sizes)
        assert got[0] == 800 and got[-1] == 1920, (how_many, got)


def test_no_two_picked_share_a_span(folder):
    """Two pictures at 1280 are one point, not two - four resolutions in
    that folder share it."""
    shots, sizes = folder
    for how_many in (2, 3, 5, 7):
        got = spans(fp.spread_over_spans(shots, sizes, how_many), sizes)
        assert len(got) == len(set(got)), got


def test_asking_for_more_than_there_are_gives_everything(folder):
    shots, sizes = folder
    assert fp.spread_over_spans(shots, sizes, 99) == list(shots)
    assert fp.spread_over_spans(shots, sizes, 0) == list(shots)


def test_one_is_allowed_but_is_a_single_point(folder):
    """The tool does not refuse it - the caller may have a reason - but
    nothing about scaling can be concluded from it, which is what the
    docstring and the app's own choice of five are for."""
    shots, sizes = folder
    assert len(fp.spread_over_spans(shots, sizes, 1)) == 1


# `test_the_app_asks_for_five` stood here and asserted that the in-app
# task passed `--tall --sample 5`. There is no in-app task any more — the
# recognition instruments were removed at the user's request — so what
# five buys is tested against `spread_over_spans` itself, above, rather
# than against a command line that no longer exists.


def test_naming_a_picture_outright_beats_the_sample():
    """`--only` is somebody asking for one frame on purpose."""
    import inspect
    body = inspect.getsource(fp.main)
    assert "if args.sample and not args.only:" in body
