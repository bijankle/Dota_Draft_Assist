"""Choosing which site the pairwise numbers come from.

One at a time, never blended: averaging two sites' interaction terms would
produce a figure neither site would recognise. The choice lives in
preferences.json because the pull runs in a subprocess.
"""

import numpy as np
import pytest

from draft_assist import config
from draft_assist.data import normalize


@pytest.fixture()
def prefs(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "PREFS_FILE", tmp_path / "preferences.json")
    yield tmp_path / "preferences.json"


def test_the_source_defaults_to_stratz(prefs):
    """The only one that fills the synergy grid, so the default cannot be
    the other."""
    assert config.pair_source() == config.DEFAULT_PAIR_SOURCE == "stratz"


def test_the_source_round_trips(prefs):
    config.save_pair_source("opendota")
    assert config.pair_source() == "opendota"
    config.save_pair_source("stratz")
    assert config.pair_source() == "stratz"


def test_an_unknown_source_is_refused_rather_than_stored(prefs):
    with pytest.raises(ValueError):
        config.save_pair_source("dotabuff")
    assert config.pair_source() == "stratz"


def test_garbage_in_the_file_falls_back_instead_of_crashing(prefs):
    prefs.write_text('{"pair_source": "who knows"}')
    assert config.pair_source() == "stratz"


def test_saving_one_preference_does_not_wipe_the_other(prefs):
    """Both settings live in this file now, and saving one used to replace
    the whole document."""
    config.save_target_brackets(["ANCIENT", "DIVINE"])
    config.save_pair_source("opendota")
    assert config.target_brackets() == ("ANCIENT", "DIVINE")
    assert config.pair_source() == "opendota"
    config.save_target_brackets(["LEGEND"])
    assert config.pair_source() == "opendota"


def test_an_all_zero_synergy_matrix_is_reported_not_swallowed():
    """A source with no ally-pair data must not look like a source that
    found no synergy anywhere."""
    zeros = np.zeros((4, 4), dtype=np.float32)
    vs = np.zeros((4, 4), dtype=np.float32)
    vs[0, 1], vs[1, 0] = 0.02, -0.02
    problems = normalize.sanity_check(vs, zeros, expect_synergy=True)
    assert any("ally-pair" in p for p in problems)
    assert normalize.sanity_check(vs, zeros, expect_synergy=False) == []
