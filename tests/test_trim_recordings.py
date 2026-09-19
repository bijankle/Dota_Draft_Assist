"""Old recordings kept pictures of the main menu. This deletes them.

"can you delete all the images that have been created fro mthese old
recordings... if its easy to fgilter can you keep the key snaps of the
draft menus? if not jjsut delete all those recording capture photos".
"""

import json
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from tools import trim_recordings as trim                      # noqa: E402

ROOT = Path(__file__).resolve().parent.parent


def make_session(root: Path, name: str, states: list[tuple[float, str]],
                 frames: list[float]) -> Path:
    """A session with a state log and frames at given ages in seconds."""
    folder = root / name
    (folder / "frames").mkdir(parents=True)
    if states is not None:
        folder.joinpath("state.jsonl").write_text(
            "\n".join(json.dumps({"at": at, "game_state": state})
                      for at, state in states), encoding="utf-8")
    start = time.time() - 10_000
    for number, age in enumerate(frames, start=1):
        path = folder / "frames" / f"{number:05d}.png"
        path.write_bytes(b"x" * 1_000_000)
        os.utime(path, (start + age, start + age))
    return folder


DRAFT = [(0.0, "HERO_SELECTION"), (30.0, "STRATEGY_TIME"),
         (60.0, "PRE_GAME"), (90.0, "GAME_IN_PROGRESS")]


def test_the_draft_frames_are_kept_and_the_rest_go(tmp_path):
    folder = make_session(tmp_path, "2026-09-19_120000", DRAFT,
                          [0.0, 20.0, 40.0, 70.0, 120.0])
    keep, drop = trim.sort_frames(folder)
    assert [p.name for p in keep] == ["00001.png", "00002.png", "00003.png"]
    assert [p.name for p in drop] == ["00004.png", "00005.png"]


def test_a_session_with_no_state_log_is_left_alone(tmp_path):
    """Not knowing which pictures are the draft is a reason to keep
    them, not a reason to guess - the unresolved-slot rule."""
    folder = make_session(tmp_path, "2026-09-19_130000", None,
                          [0.0, 50.0, 500.0])
    keep, drop = trim.sort_frames(folder)
    assert len(keep) == 3 and drop == []


def test_all_takes_everything_including_an_unreadable_session(tmp_path):
    folder = make_session(tmp_path, "2026-09-19_140000", None, [0.0, 9.0])
    keep, drop = trim.sort_frames(folder, everything=True)
    assert keep == [] and len(drop) == 2


def test_check_deletes_nothing(tmp_path, capsys):
    make_session(tmp_path, "2026-09-19_150000", DRAFT, [0.0, 200.0])
    gone, freed = trim.trim(tmp_path, dry_run=True)
    assert gone == 1 and freed > 0.9
    assert sorted(p.name for p in
                  (tmp_path / "2026-09-19_150000" / "frames").iterdir()) == \
        ["00001.png", "00002.png"]


def test_the_payloads_and_the_log_are_never_touched(tmp_path):
    """Kilobytes, and what every report and measurement is built from."""
    folder = make_session(tmp_path, "2026-09-19_160000", DRAFT,
                          [0.0, 300.0])
    folder.joinpath("payloads.jsonl").write_text("{}", encoding="utf-8")
    trim.trim(tmp_path)
    assert folder.joinpath("state.jsonl").is_file()
    assert folder.joinpath("payloads.jsonl").is_file()
    assert [p.name for p in trim.frames_of(folder)] == ["00001.png"]


def test_one_refused_file_does_not_stop_the_tidy(tmp_path, monkeypatch):
    make_session(tmp_path, "2026-09-19_170000", DRAFT,
                 [0.0, 100.0, 200.0])
    make_session(tmp_path, "2026-09-19_180000", DRAFT, [0.0, 100.0])
    real = Path.unlink
    seen = {"n": 0}

    def flaky(self, *a, **kw):
        seen["n"] += 1
        if seen["n"] == 1:
            raise OSError("held open by a picture viewer")
        return real(self, *a, **kw)

    monkeypatch.setattr(Path, "unlink", flaky)
    gone, _ = trim.trim(tmp_path)
    assert gone == 2, "the other two were still deleted"


def test_it_reads_the_state_through_the_measuring_tool():
    """Two ways of answering "what was on screen in this picture" is one
    of them going stale, so the filter is the same `state_at` the
    measurement uses, against the app's own DRAFTING_STATES."""
    from draft_assist.gsi import state as gsi_state
    assert trim.BAR_IS_UP == {
        name.replace("DOTA_GAMERULES_STATE_", "")
        for name in gsi_state.DRAFTING_STATES}


def test_every_line_it_prints_is_ascii():
    text = (ROOT / "tools" / "trim_recordings.py").read_text(
        encoding="utf-8")
    bad = [c for c in text if ord(c) > 127]
    assert not bad, f"non-ASCII in the tool: {sorted(set(bad))}"


def test_the_path_is_resolved_at_call_time(monkeypatch, tmp_path):
    monkeypatch.setattr(trim, "ROOT", tmp_path)
    assert trim.recordings_dir() == tmp_path / "recordings"
