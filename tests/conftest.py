"""Shared test setup.

Recording now starts by itself when the game reports a draft, which means
any test that refreshes a window over a drafting payload would write a real
session folder into the repository. Both of those are redirected here so a
test run leaves nothing behind.
"""

import pytest


@pytest.fixture(autouse=True)
def _recordings_go_to_tmp(tmp_path, monkeypatch):
    import draft_assist.ui.app as app_mod
    from draft_assist import debugdir
    from draft_assist.ui import settings as ui_settings

    # THE WHOLE `debug/` TREE, not just the recordings under it. A crash
    # reporter, a setup log and a problem report all write there now, so
    # one redirect covers every one of them - and without it a test that
    # renders a crash box would leave a dated folder in the repository.
    monkeypatch.setattr(debugdir, "ROOT", tmp_path)
    monkeypatch.setattr(app_mod, "RECORDINGS_DIR", tmp_path / "recordings")
    monkeypatch.setattr(ui_settings, "SETTINGS_FILE",
                        tmp_path / "ui_settings.json")


@pytest.fixture(autouse=True)
def _history_stays_out_of_the_repository(tmp_path, monkeypatch):
    """The remembered accounts and their cached runs are per-machine files
    that live in the repository root, so a test that opens the Analysis
    tab would read the developer's own and write its fixtures over them.
    Same reason recordings and the settings file are redirected above.
    """
    from draft_assist.history import cache, store
    monkeypatch.setattr(store, "STORE_FILE", tmp_path / "accounts.json")
    monkeypatch.setattr(cache, "CACHE_DIR", tmp_path / "history_cache")


@pytest.fixture(autouse=True)
def _sizes_start_at_one():
    """The two size multipliers are MODULE state (View ▸ Sizes).

    A test that turns the portraits down and then fails leaves every test
    after it measuring smaller tiles, which is a failure in a file nobody
    touched. Reset either side, so the leak cannot happen at all.
    """
    from draft_assist.ui import teams, tilekit
    teams.set_scale(1.0)
    tilekit.set_scale(1.0)
    # AND THE GRIDS' CAP, which is the same hazard from a new direction:
    # the matrix cards now have a vote on the one portrait box every tile
    # in the app uses (`teams.set_grid_cap`), so a test that opens a
    # narrow window leaves every test after it measuring smaller tiles.
    teams.set_grid_cap(None)
    yield
    teams.set_scale(1.0)
    tilekit.set_scale(1.0)
    teams.set_grid_cap(None)


@pytest.fixture(autouse=True)
def _the_stylesheet_does_not_leak_between_tests():
    """A QApplication is shared by the whole run, and so is its style.

    Several tests need the real theme because they check PIXELS, and
    setting it on the way past leaves every test after them rendering in
    a different font — this app's is 18px bold against Qt's default, so
    every measured width changes. That is a leak with a very long reach:
    a width assertion in `test_section_bar.py` passed on its own and
    failed in the full suite because a file loaded earlier had restyled
    the application and walked away.

    Same rule as the size multipliers and the portrait cache below:
    reset either side, so the leak cannot happen at all rather than
    being tidied up by whichever test remembers.
    """
    from PyQt6.QtWidgets import QApplication
    app = QApplication.instance()
    was = app.styleSheet() if app is not None else ""
    yield
    app = QApplication.instance()
    if app is not None and app.styleSheet() != was:
        app.setStyleSheet(was)


@pytest.fixture(autouse=True)
def _the_palette_starts_in_colour():
    """`theme`'s colours are MODULE state, reassigned in place.

    `set_greyscale` swaps every colour name in the module and rebuilds
    `STYLESHEET`, so a test that turns it on and walks away leaves every
    test after it measuring a grey app —
    `test_greyscale.test_the_window_frame_goes_grey_too` does exactly
    that, deliberately, because its subject is the frame rather than the
    tidying up.

    It reaches further than a colour: the menus' tick is a GENERATED PNG
    written to `assets/`, re-rendered from these colours whenever they
    change, and shared by the whole run. So a leak here is a file on
    disk that a later test reads and asserts about, which is how adding
    an unrelated test file between two others moved the answer.

    Same rule as the stylesheet, the size multipliers and the portrait
    caches above: reset either side, so the leak cannot happen at all
    rather than being tidied up by whichever test remembers.
    """
    from draft_assist.ui import theme
    theme.set_greyscale(False)
    yield
    theme.set_greyscale(False)


@pytest.fixture(autouse=True)
def _portrait_caches_start_empty():
    """The portrait index is MODULE state too, and it caches ABSENCE.

    `_index` is built once and remembers what it found — including
    finding nothing. So a test that asked anything about portraits before
    another test wrote one left that second test drawing blank tiles
    against a cache nothing would invalidate, and the failure landed in a
    file nobody had touched. Same rule as the size multipliers above:
    reset either side, so the leak cannot happen at all.
    """
    from draft_assist.ui import portraits
    portraits.forget()
    yield
    portraits.forget()
