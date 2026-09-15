"""The equal-length stretch before the window, and when it is refused.

It exists for one thing — the two deltas in the profile callout, at the
user's request: "in brackets after that i want the delta from the
previous XXX duration". Everything interesting about it is the cases
where the honest answer is NO ANSWER.
"""

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from draft_assist.history import opendota, runner            # noqa: E402
from draft_assist.history.report import Before, Options      # noqa: E402

HEROES = {1: "Anti-Mage", 2: "Axe"}
RANKED = 7                      # `shape.RANKED_LOBBY`


NOW = 1_800_000_000.0           # a fixed clock, so the split is testable


def a_row(days_ago: float, win: bool = True, hero: int = 1) -> dict:
    return {"match_id": 8000000001, "start_time": NOW - days_ago * 86400,
            "duration": 2000, "player_slot": 0, "radiant_win": win,
            "hero_id": hero, "lobby_type": RANKED, "game_mode": 22}


# ---- what to ask for ---------------------------------------------------

def test_one_request_covers_both_halves():
    """"when you run it just make the range of data requested double what
    was selected, so that you haev that data to work with".

    It was two requests — the run's own, and a second one twice as long
    for the comparison — which is two trips to a free API for two figures
    in a callout, and two chances for the halves to disagree about what
    the account has played.
    """
    assert runner.fetch_span(Options(window="6m", cap=1000)) == (2000, 364)
    assert runner.fetch_span(Options(window="1m", cap=250)) == (500, 60)


def test_the_limit_doubles_with_the_span():
    """A limit keeps the most RECENT rows, so doubling the days and
    leaving the limit alone would clip away exactly the older half being
    reached for."""
    limit, span = runner.fetch_span(Options(window="12m", cap=500))
    assert (limit, span) == (1000, 730)


def test_all_history_asks_for_everything_and_has_nothing_behind_it():
    assert runner.fetch_span(Options(window="all", cap=800)) == (800, None)
    assert runner.measure_before([], Options(window="all"), HEROES) is None


# ---- splitting it ------------------------------------------------------

def test_the_split_is_by_date_and_the_cap_is_the_windows():
    """The two halves are defined by the DATE the user chose; the row
    order is only incidentally the same thing. And the cap is what was
    asked for IN the window, not in the doubled fetch."""
    rows = ([a_row(10) for _ in range(6)]
            + [a_row(200) for _ in range(3)]
            + [a_row(250) for _ in range(1)])
    recent, earlier = runner.split_window(rows, 182, cap=1000, now=NOW)
    assert (len(recent), len(earlier)) == (6, 4)
    recent, earlier = runner.split_window(rows, 182, cap=4, now=NOW)
    assert len(recent) == 4, "the cap did not reach the window"
    assert len(earlier) == 4, "the cap should not touch the older half"


def test_all_history_keeps_everything_in_one_half():
    rows = [a_row(n) for n in (1, 100, 900)]
    recent, earlier = runner.split_window(rows, None, cap=1000, now=NOW)
    assert len(recent) == 3 and earlier == []


# ---- measuring it ------------------------------------------------------

def test_it_counts_the_older_half_through_the_same_filters():
    """**THE FILTERS ARE UNIVERSAL**, at the user's request: "now that my
    filters are in the settings i think you should probably have the vibe
    that it is universal.. so for these metrics i want those filters to
    apply.... not only for present to 3 months but for 3 months to 6
    mopnths for that exampl;e".

    Both halves go through the one `shape` call with the one set of
    options, so there is no second place for a filter to be forgotten.
    Without it the delta would compare a ranked, turbo-free sample
    against everything the account has played and report a change that is
    entirely the filters.
    """
    rows = [a_row(200, win=True) for _ in range(3)]
    rows.append(a_row(250, win=False))
    rows.append({**a_row(210), "game_mode": 23})          # turbo
    rows.append({**a_row(220), "lobby_type": 0})          # unranked
    strict = runner.measure_before(
        rows, Options(window="6m", no_turbo=True, ranked_only=True), HEROES)
    loose = runner.measure_before(
        rows, Options(window="6m", no_turbo=False, ranked_only=False), HEROES)
    assert strict == Before(matches=4, wins=3)
    assert loose.matches == 6


def test_the_cap_is_the_one_setting_that_does_not_reach_the_older_half():
    """AND THAT IS THE HONEST WAY ROUND, not an oversight.

    The cap is "at most N matches to MEASURE", so it belongs to the
    window's own sample. Applying it to the older half as well would cut
    that half to its newest N and leave the two covering different
    amounts of TIME — which is the unfairness the whole `clipped` guard
    exists to refuse. So the older half is counted whole, and if the cap
    ever bites on the WINDOW the delta is not drawn at all (see
    `test_a_window_trimmed_to_the_cap_is_refused`).
    """
    rows = [a_row(200) for _ in range(30)]
    got = runner.measure_before(rows, Options(window="6m", cap=5), HEROES)
    assert got == Before(matches=30, wins=30), (
        "the cap was applied to the stretch before")
    # And the window's own half IS cut to it.
    recent, _earlier = runner.split_window(
        [a_row(1) for _ in range(30)], 182, cap=5, now=NOW)
    assert len(recent) == 5


def test_a_clipped_fetch_is_refused():
    """**THE CASE THE GUARD EXISTS FOR.** A limit keeps the most RECENT
    rows, so the half that gets lost is exactly the half being measured.
    """
    options = Options(window="6m", cap=20)
    # Spanning the whole doubled window, so the SECOND guard (a server
    # cap we cannot see) has nothing to say and this is only about the
    # count.
    rows = [a_row(n * 9) for n in range(40)]
    assert runner.clipped(rows, options, limit=40, now=NOW) is True
    assert runner.measure_before(rows, options, HEROES, clipped=True) is None
    # One row short of the limit and it is trusted again.
    assert runner.clipped(rows[:-1], options, limit=40, now=NOW) is False


def test_a_server_side_cap_we_cannot_see_is_caught_too():
    """OpenDota does not document a ceiling on `limit` and could apply
    one silently, which the count test would sail straight past. A fetch
    that came back substantial and STILL did not reach behind the window
    was cut off by something."""
    options = Options(window="6m", cap=100)
    rows = [a_row(n / 10) for n in range(150)]        # all inside 15 days
    assert runner.clipped(rows, options, limit=200, now=NOW) is True


def test_an_account_younger_than_the_window_is_not_a_clipped_fetch():
    """Its `earlier` is empty because it was not playing, which is a real
    answer — and the games delta should say so rather than going blank."""
    options = Options(window="6m", cap=1000)
    rows = [a_row(n) for n in (1, 20, 60)]
    assert runner.clipped(rows, options, limit=2000, now=NOW) is False
    assert runner.measure_before([], options, HEROES) == Before()


def test_a_window_trimmed_to_the_cap_is_refused(monkeypatch):
    """**THE SUBTLER UNFAIRNESS, and the one that prompted this.** A
    window cut to its newest `cap` matches covers LESS TIME than the
    stretch behind it, so the delta would be comparing four months
    against six while saying it compared six against six.
    """
    rows = ([a_row(n / 10) for n in range(30)]        # 30 inside the window
            + [a_row(200) for _ in range(5)])
    recent, earlier = runner.split_window(rows, 182, cap=10, now=NOW)
    assert len(recent) == 10
    trimmed = len(recent) < len(rows) - len(earlier)
    assert trimmed is True
    assert runner.measure_before(earlier, Options(window="6m", cap=10),
                                 HEROES, clipped=trimmed) is None


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
