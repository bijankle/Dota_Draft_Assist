"""The statistics bracket is a data-pull setting, not a display filter.

Baselines and interaction matrices are built for the chosen brackets, so
changing the selection invalidates the cache. These tests pin down that the
preference round-trips, that the pull honours it, and — most importantly —
that a dataset built for one bracket is never quietly presented as another.
"""

import json

import pytest

from draft_assist import config


@pytest.fixture()
def prefs(tmp_path, monkeypatch):
    path = tmp_path / "preferences.json"
    monkeypatch.setattr(config, "PREFS_FILE", path)
    return path


def test_default_when_nothing_is_saved(prefs):
    assert config.target_brackets() == config.DEFAULT_TARGET_BRACKETS


def test_selection_round_trips(prefs):
    config.save_target_brackets(["LEGEND", "ANCIENT"])
    assert config.target_brackets() == ("LEGEND", "ANCIENT")
    assert json.loads(prefs.read_text())["target_brackets"] == \
        ["LEGEND", "ANCIENT"]


def test_selection_is_stored_in_rank_order(prefs):
    """Picked in any order, stored low-to-high, so downstream code and the
    UI label always agree on how to read it."""
    config.save_target_brackets(["DIVINE", "HERALD", "LEGEND"])
    assert config.target_brackets() == ("HERALD", "LEGEND", "DIVINE")


def test_a_single_bracket_is_allowed(prefs):
    config.save_target_brackets(["IMMORTAL"])
    assert config.target_brackets() == ("IMMORTAL",)


def test_empty_selection_is_refused(prefs):
    with pytest.raises(ValueError):
        config.save_target_brackets([])


def test_unknown_or_corrupt_preferences_fall_back(prefs):
    """A bad file must never break the data pull."""
    prefs.write_text('{"target_brackets": ["ATLANTEAN"]}', encoding="utf-8")
    assert config.target_brackets() == config.DEFAULT_TARGET_BRACKETS
    prefs.write_text("not json at all", encoding="utf-8")
    assert config.target_brackets() == config.DEFAULT_TARGET_BRACKETS
    prefs.write_text('{"target_brackets": "LEGEND"}', encoding="utf-8")
    assert config.target_brackets() == config.DEFAULT_TARGET_BRACKETS


def test_unknown_entries_are_dropped_not_fatal(prefs):
    prefs.write_text('{"target_brackets": ["LEGEND", "ATLANTEAN"]}',
                     encoding="utf-8")
    assert config.target_brackets() == ("LEGEND",)


def test_build_uses_the_preference(prefs, monkeypatch):
    """The pull must read the saved bracket, not a hardcoded constant."""
    from draft_assist.data import build

    config.save_target_brackets(["ARCHON", "LEGEND"])
    seen = {}

    def fake_baselines(hero_stats, brackets):
        seen["baselines"] = brackets
        return {}

    def fake_verify(hero_stats, brackets):
        seen["verify"] = brackets
        return {"passed": True}

    def fake_filter(schema, brackets):
        seen["stratz"] = brackets
        return {"arg": "b", "values": [], "exact": True, "covers": []}

    monkeypatch.setattr(build.opendota, "fetch_heroes", lambda: {1: {}})
    monkeypatch.setattr(build.opendota, "fetch_hero_stats", lambda: [])
    monkeypatch.setattr(build.opendota, "baseline_winrates", fake_baselines)
    monkeypatch.setattr(build.verify, "verify_tier_mapping", fake_verify)
    monkeypatch.setattr(build.verify, "format_report", lambda report: "")
    monkeypatch.setattr(build.stratz, "introspect", lambda: {})
    monkeypatch.setattr(build.stratz, "choose_bracket_filter", fake_filter)
    monkeypatch.setattr(build.stratz, "fetch_matchups", lambda ids, f: {})
    monkeypatch.setattr(build.store, "save", lambda ds: seen.update(meta=ds.meta))

    build.build_dataset()
    assert seen["verify"] == ("ARCHON", "LEGEND")
    assert seen["baselines"] == ("ARCHON", "LEGEND")
    assert seen["stratz"] == ("ARCHON", "LEGEND")
    # The bracket is recorded with the data, so a later mismatch is visible.
    assert seen["meta"]["target_brackets"] == ["ARCHON", "LEGEND"]


def test_explicit_brackets_override_the_preference(prefs, monkeypatch):
    from draft_assist.data import build

    config.save_target_brackets(["ARCHON"])
    seen = {}
    monkeypatch.setattr(build.opendota, "fetch_heroes", lambda: {1: {}})
    monkeypatch.setattr(build.opendota, "fetch_hero_stats", lambda: [])
    def record_baselines(hero_stats, brackets):
        seen["b"] = brackets
        return {}

    monkeypatch.setattr(build.opendota, "baseline_winrates", record_baselines)
    monkeypatch.setattr(build.verify, "verify_tier_mapping",
                        lambda hs, b: {"passed": True})
    monkeypatch.setattr(build.verify, "format_report", lambda report: "")
    monkeypatch.setattr(build.stratz, "introspect", lambda: {})
    monkeypatch.setattr(build.stratz, "choose_bracket_filter",
                        lambda schema, b: {"arg": "b", "values": [],
                                           "exact": True, "covers": []})
    monkeypatch.setattr(build.stratz, "fetch_matchups", lambda ids, f: {})
    monkeypatch.setattr(build.store, "save", lambda ds: None)

    build.build_dataset(brackets=("IMMORTAL",))
    assert seen["b"] == ("IMMORTAL",)
