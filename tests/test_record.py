"""Recording sessions: what was captured, and what it says about accuracy.

The comparison is the reason recording exists. During hero selection GSI
names no hero, so recognition cannot be checked at the time — but from
strategy time the minimap carries all ten in the same match, which makes
the screen's reading gradeable hero by hero without anyone eyeballing a
screenshot.
"""

import json
import time

import pytest

from draft_assist import record


def session(tmp_path, rows, meta=None):
    folder = tmp_path / "2026-09-05_2031"
    (folder / "gsi").mkdir(parents=True)
    (folder / "frames").mkdir()
    (folder / "state.jsonl").write_text(
        "\n".join(json.dumps(row) for row in rows), encoding="utf-8")
    (folder / "meta.json").write_text(json.dumps(meta or {}), encoding="utf-8")
    return folder


def row(at, state, source, allies, enemies):
    return {"at": at, "game_state": f"DOTA_GAMERULES_STATE_{state}",
            "source": source, "allies": allies, "enemies": enemies}


TRUTH_ALLIES = ["Rubick", "Silencer", "Abaddon", "Windrunner", "Gyrocopter"]
TRUTH_ENEMIES = ["Zuus", "Sniper", "Marci", "Viper", "Nevermore"]


def test_a_perfect_screen_reading_scores_ten_out_of_ten(tmp_path):
    folder = session(tmp_path, [
        row(20, "HERO_SELECTION", "screen", TRUTH_ALLIES, TRUTH_ENEMIES),
        row(70, "STRATEGY_TIME", "minimap", TRUTH_ALLIES, TRUTH_ENEMIES),
    ])
    result = record.compare_sources(record.read_states(folder))
    assert result["correct"] == 10
    assert result["wrong"] == 0 and result["missed"] == 0
    assert "10/10 heroes read correctly" in \
        record.format_session_report(folder)


def test_a_misread_hero_is_reported_as_wrong_not_missing(tmp_path):
    """The two failures need different fixes, and only one of them made the
    app advise against a hero that was never in the game."""
    folder = session(tmp_path, [
        row(20, "HERO_SELECTION", "screen", TRUTH_ALLIES,
            ["Zuus", "Sniper", "Marci", "Viper", "Pudge"]),
        row(70, "STRATEGY_TIME", "minimap", TRUTH_ALLIES, TRUTH_ENEMIES),
    ])
    result = record.compare_sources(record.read_states(folder))
    assert result["enemies"]["wrong"] == ["Pudge"]
    assert result["enemies"]["missed"] == ["Nevermore"]
    assert result["correct"] == 9
    text = record.format_session_report(folder)
    assert "A WRONG hero is the serious one" in text


def test_swapped_sides_are_named_as_a_mapping_fault(tmp_path):
    """A reading that matches the other team better than its own is a
    side-mapping bug, not a recognition one."""
    folder = session(tmp_path, [
        row(20, "HERO_SELECTION", "screen", TRUTH_ENEMIES, TRUTH_ALLIES),
        row(70, "STRATEGY_TIME", "minimap", TRUTH_ALLIES, TRUTH_ENEMIES),
    ])
    result = record.compare_sources(record.read_states(folder))
    assert result["swapped"]
    assert result["correct"] == 10        # scored after un-swapping
    assert "SIDES WERE SWAPPED" in record.format_session_report(folder)


def test_the_last_screen_reading_before_the_game_took_over_is_the_one(
        tmp_path):
    """Early in a draft the screen legitimately has fewer picks; grading
    against those would score the app for reading a half-finished draft."""
    folder = session(tmp_path, [
        row(10, "HERO_SELECTION", "screen", ["Rubick"], []),
        row(20, "HERO_SELECTION", "screen", TRUTH_ALLIES, TRUTH_ENEMIES),
        row(70, "STRATEGY_TIME", "minimap", TRUTH_ALLIES, TRUTH_ENEMIES),
        row(90, "STRATEGY_TIME", "screen", ["nonsense"], []),
    ])
    result = record.compare_sources(record.read_states(folder))
    assert result["correct"] == 10


def test_no_verdict_without_ground_truth(tmp_path):
    folder = session(tmp_path, [
        row(20, "HERO_SELECTION", "screen", TRUTH_ALLIES, TRUTH_ENEMIES)])
    result = record.compare_sources(record.read_states(folder))
    assert not result["comparable"]
    assert "never reached strategy time" in result["reason"]
    assert "Not comparable" in record.format_session_report(folder)


def test_no_verdict_when_the_screen_read_nothing(tmp_path):
    folder = session(tmp_path, [
        row(70, "STRATEGY_TIME", "minimap", TRUTH_ALLIES, TRUTH_ENEMIES)])
    result = record.compare_sources(record.read_states(folder))
    assert not result["comparable"]
    assert "never read a pick" in result["reason"]


def test_a_torn_last_line_does_not_lose_the_session(tmp_path):
    """A crash mid-write leaves half a line; the rest is still evidence."""
    folder = session(tmp_path, [
        row(20, "HERO_SELECTION", "screen", TRUTH_ALLIES, TRUTH_ENEMIES)])
    with (folder / "state.jsonl").open("a", encoding="utf-8") as handle:
        handle.write('\n{"at": 70, "game_st')
    assert len(record.read_states(folder)) == 1


def test_the_timeline_collapses_ticks_that_changed_nothing(tmp_path):
    """A one-second tick over a four-minute draft is 240 identical lines."""
    rows = [row(t, "HERO_SELECTION", "screen", ["Rubick"], [])
            for t in range(1, 40)]
    rows.append(row(41, "HERO_SELECTION", "screen", ["Rubick", "Silencer"], []))
    folder = session(tmp_path, rows)
    timeline = record.format_session_report(folder).split("TIMELINE")[1]
    assert timeline.count("HERO_SELECTION") == 2


# ---- the recorder itself ------------------------------------------------

def test_frames_are_taken_only_while_drafting(tmp_path):
    recorder = record.Recorder(tmp_path)
    recorder.start()
    assert recorder.wants_frame("DOTA_GAMERULES_STATE_HERO_SELECTION")
    assert not recorder.wants_frame("DOTA_GAMERULES_STATE_GAME_IN_PROGRESS")
    assert not recorder.wants_frame("")


def test_frames_are_rate_limited_and_capped(tmp_path, monkeypatch):
    recorder = record.Recorder(tmp_path)
    recorder.start()
    assert recorder.wants_frame("DOTA_GAMERULES_STATE_HERO_SELECTION")
    recorder._last_frame = time.monotonic()
    assert not recorder.wants_frame("DOTA_GAMERULES_STATE_HERO_SELECTION")
    recorder._last_frame = time.monotonic() - record.FRAME_INTERVAL - 0.1
    assert recorder.wants_frame("DOTA_GAMERULES_STATE_HERO_SELECTION")
    recorder.frames = record.MAX_FRAMES
    assert not recorder.wants_frame("DOTA_GAMERULES_STATE_HERO_SELECTION")


def test_two_sessions_in_the_same_second_do_not_collide(tmp_path,
                                                        monkeypatch):
    monkeypatch.setattr(time, "strftime", lambda *_a: "2026-09-05_203100")
    recorder = record.Recorder(tmp_path)
    first = recorder.start()
    recorder.stop()
    second = recorder.start()
    recorder.stop()
    assert first != second
    assert first.is_dir() and second.is_dir()


def test_stopping_writes_a_report_beside_the_data(tmp_path):
    """A session folder has to be self-contained — zippable, movable,
    readable without the app that produced it."""
    recorder = record.Recorder(tmp_path)
    folder = recorder.start()
    recorder.log_state({"game_state": "DOTA_GAMERULES_STATE_HERO_SELECTION",
                        "source": "screen", "allies": ["Rubick"],
                        "enemies": []})
    recorder.stop()
    report = (folder / "report.txt").read_text(encoding="utf-8")
    assert "RECORDING" in report and "Rubick" in report
    assert json.loads((folder / "meta.json").read_text())["finished"] is True


def test_nothing_is_written_when_not_recording(tmp_path):
    recorder = record.Recorder(tmp_path)
    recorder.log_state({"source": "screen"})
    assert recorder.save_frame(object()) is None
    assert not list(tmp_path.iterdir())


def test_sessions_are_listed_newest_first(tmp_path):
    for name in ("2026-09-01_1000", "2026-09-05_2031", "2026-09-03_1200"):
        (tmp_path / name).mkdir()
        (tmp_path / name / "meta.json").write_text("{}")
    (tmp_path / "not-a-session").mkdir()
    assert [p.name for p in record.sessions(tmp_path)] == [
        "2026-09-05_2031", "2026-09-03_1200", "2026-09-01_1000"]


def test_listing_a_missing_folder_is_not_an_error(tmp_path):
    assert record.sessions(tmp_path / "nope") == []
