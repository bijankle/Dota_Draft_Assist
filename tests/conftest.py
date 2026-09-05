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
