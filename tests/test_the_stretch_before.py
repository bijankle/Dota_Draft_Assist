"""The equal-length stretch before the window, and when it is refused.

It exists for one thing — the two deltas in the profile callout, at the
user's request: "in brackets after that i want the delta from the
previous XXX duration". Everything interesting about it is the cases
where the honest answer is NO ANSWER.
"""

import sys
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from draft_assist.history import opendota, runner            # noqa: E402
from draft_assist.history.report import Before, Options      # noqa: E402

HEROES = {1: "Anti-Mage", 2: "Axe"}
RANKED = 7                      # `shape.RANKED_LOBBY`


def a_row(days_ago: float, win: bool = True, hero: int = 1) -> dict:
    return {"match_id": 8000000001, "start_time": time.time() - days_ago * 86400,
            "duration": 2000, "player_slot": 0, "radiant_win": win,
            "hero_id": hero, "lobby_type": RANKED, "game_mode": 22}


def _answer(rows, monkeypatch):
    seen = {}

    def fake(account_id, cap, days):
        seen["cap"], seen["days"] = cap, days
        return rows
    monkeypatch.setattr(opendota, "matches", fake)
    return seen


def test_it_asks_for_twice_the_window_and_keeps_the_older_half(monkeypatch):
    """The run's own fetch asks for the last `days` days, so the matches
    before that were never sent — there is no filtering them in. And the
    endpoint takes only "the last N days", so the way to reach them is to
    ask for twice as long and split locally."""
    rows = ([a_row(10) for _ in range(6)]            # inside the window
            + [a_row(200, win=True) for _ in range(3)]
            + [a_row(250, win=False) for _ in range(1)])
    seen = _answer(rows, monkeypatch)
    got = runner.measure_before(Options(account_id=1, window="6m", cap=100),
                                HEROES)
    assert seen["days"] == 2 * 182
    assert seen["cap"] == 200, "the doubled window needs a doubled limit"
    assert got == Before(matches=4, wins=3)


def test_all_history_has_nothing_before_it(monkeypatch):
    monkeypatch.setattr(opendota, "matches",
                        lambda *a, **k: pytest.fail("no request expected"))
    assert runner.measure_before(Options(account_id=1, window="all"),
                                 HEROES) is None


def test_a_clipped_fetch_is_refused(monkeypatch):
    """**THE CASE THIS GUARD EXISTS FOR.** A limit keeps the most RECENT
    rows, so the half that gets lost is exactly the half being measured —
    a delta drawn from a clipped fetch would say the account played far
    less last year, which is a claim about the cap rather than about
    them."""
    rows = [a_row(1) for _ in range(20)] + [a_row(200) for _ in range(20)]
    _answer(rows, monkeypatch)
    assert runner.measure_before(Options(account_id=1, window="6m", cap=20),
                                 HEROES) is None
    # One row short of the limit and it is trusted again.
    _answer(rows[:-1], monkeypatch)
    assert runner.measure_before(
        Options(account_id=1, window="6m", cap=20), HEROES) is not None


def test_a_failed_request_is_never_fatal(monkeypatch):
    """Cosmetic: the two figures beside it are the answer and the delta
    is the sentence after it."""
    def boom(*a, **k):
        raise opendota.ApiError("rate", "rate limited")
    monkeypatch.setattr(opendota, "matches", boom)
    assert runner.measure_before(Options(account_id=1, window="3m"),
                                 HEROES) is None


def test_a_window_with_nothing_before_it_answers_zero_rather_than_none(
        monkeypatch):
    """A real answer, not a missing one: a new account has a window's
    worth of history and nothing behind it, and the games delta should
    say so rather than going blank."""
    _answer([a_row(3), a_row(5)], monkeypatch)
    got = runner.measure_before(Options(account_id=1, window="3m"), HEROES)
    assert got == Before(matches=0, wins=0)


def test_the_older_half_takes_the_same_filters(monkeypatch):
    """Or the delta would compare a ranked, turbo-free sample against
    everything the account has played and report a change that is
    entirely the filters."""
    rows = [a_row(200) for _ in range(3)]
    rows.append({**a_row(210), "game_mode": 23})          # turbo
    rows.append({**a_row(220), "lobby_type": 0})          # unranked
    _answer(rows, monkeypatch)
    strict = runner.measure_before(
        Options(account_id=1, window="3m", no_turbo=True, ranked_only=True),
        HEROES)
    loose = runner.measure_before(
        Options(account_id=1, window="3m", no_turbo=False, ranked_only=False),
        HEROES)
    assert strict.matches == 3
    assert loose.matches == 5


def test_a_cancelled_run_does_not_make_the_extra_request(monkeypatch):
    monkeypatch.setattr(opendota, "matches",
                        lambda *a, **k: pytest.fail("no request expected"))
    assert runner.measure_before(Options(account_id=1, window="3m"),
                                 HEROES, cancelled=lambda: True) is None


# ---- and it survives the cache -----------------------------------------

def test_the_cache_keeps_it_because_it_cannot_be_recomputed(tmp_path):
    """Every block is rebuilt from `matches` on the way back in — but the
    stretch BEFORE the window is not in that list and never will be, so
    it has to be stored or re-opening a cached run silently drops both
    deltas with nothing on screen saying why."""
    from datetime import datetime

    from draft_assist.history import cache
    from draft_assist.history.report import Report
    from draft_assist.history.shape import Match

    matches = [Match(match_id=8000000001, start=0, when=datetime(2026, 9, 1),
                     duration=2000, slot=1, radiant=True, win=i % 2 == 0,
                     hero_id=1, hero="Anti-Mage") for i in range(30)]
    report = Report(options=Options(account_id=4242424242, window="6m"),
                    how="", name="ExampleDrafter", matches=matches, blocks=[],
                    dropped={}, sessions=1, returned=30,
                    before=Before(matches=25, wins=12))
    assert cache.save(report, tmp_path)
    back = cache.load(4242424242, where=tmp_path)
    assert back is not None
    assert back.before == Before(matches=25, wins=12)


def test_a_run_cached_before_this_existed_reads_as_not_measured(tmp_path):
    """None, not a zero: "not measured" and "exactly the same as last
    time" must not look alike."""
    import json
    from datetime import datetime

    from draft_assist.history import cache
    from draft_assist.history.report import Report
    from draft_assist.history.shape import Match

    matches = [Match(match_id=8000000001, start=0, when=datetime(2026, 9, 1),
                     duration=2000, slot=1, radiant=True, win=True,
                     hero_id=1, hero="Anti-Mage") for _ in range(20)]
    report = Report(options=Options(account_id=4242424242), how="",
                    name="", matches=matches, blocks=[], dropped={},
                    sessions=1, returned=20)
    assert cache.save(report, tmp_path)
    path = next(tmp_path.glob("*.json"))
    raw = json.loads(path.read_text(encoding="utf-8"))
    raw.pop("before")
    path.write_text(json.dumps(raw), encoding="utf-8")
    assert cache.load(4242424242, where=tmp_path).before is None
