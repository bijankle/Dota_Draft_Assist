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
    from draft_assist.ui import settings as ui_settings

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
