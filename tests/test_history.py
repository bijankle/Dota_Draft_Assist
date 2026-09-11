"""The match history analyser: ids, shaping, statistics and the workbook.

Every one of these is arithmetic over synthetic matches, so none of them
touches the network. The one thing that does — `history/opendota.py` — is
exercised by having its callers use a stub, because a test that needs
OpenDota to be up is a test that fails for reasons nobody can fix.
"""

import json
import math
import time

import pytest

from draft_assist.history import account, analyse, shape, store, workbook
from draft_assist.history.report import Options, Report

HEROES = {1: "Anti-Mage", 2: "Axe", 3: "Bane"}


def rows_for(count=60, *, hero=1, win_rate=0.5, start=None, duration=1800,
             gap=1200, **extra):
    """`count` matches on one hero, `win_rate` of them won."""
    start = start or (time.time() - count * gap - 86400)
    out = []
    for index in range(count):
        won = index < round(count * win_rate)
        slot = 0 if index % 2 else 128
        row = dict(match_id=1000 + index, player_slot=slot,
                   radiant_win=(slot < 128) == won, duration=duration,
                   start_time=int(start + index * gap), hero_id=hero,
                   kills=5, deaths=5, assists=10, hero_damage=15000,
                   party_size=1, lobby_type=7, game_mode=22)
        row.update(extra)
        out.append(row)
    return out


# ---------------------------------------------------------------- ids ----

def test_every_id_form_lands_on_the_same_account():
    """A friend ID, a 64 bit Steam ID, a steamID3, a classic STEAM_0 and a
    profile URL are five spellings of one number, and the field takes all
    of them because the user has no reason to know which they have."""
    for text in ("195286385", "76561198155552113", "[U:1:195286385]",
                 "STEAM_0:1:97643192",
                 "https://www.dotabuff.com/players/195286385",
                 "https://www.opendota.com/players/195286385"):
        parsed = account.parse(text)
        assert parsed.ok, text
        assert parsed.account_id == 195286385, text
        assert parsed.how


def test_a_steam_id_below_the_individual_range_is_refused():
    """Converting it would give an account id that is not one."""
    parsed = account.parse("76561197960265700")
    assert not parsed.ok
    assert "individual account range" in parsed.error


def test_a_vanity_url_is_a_name_and_says_so():
    """Resolving one needs the Steam Web API — a key AND a server, since
    Steam sends no CORS headers. So it is a name, and named as one."""
    parsed = account.parse("https://steamcommunity.com/id/dendi")
    assert parsed.account_id is None
    assert parsed.name == "dendi"
    assert "name" in parsed.how


# ------------------------------------------------------------ shaping ----

def test_an_abandon_is_not_a_game_whose_result_means_anything():
    rows = rows_for(12)
    rows[0]["duration"] = 240           # under five minutes
    shaped = shape.shape(rows, HEROES)
    assert len(shaped.matches) == 11
    assert shaped.dropped["short"] == 1


def test_a_row_missing_any_of_the_four_facts_is_dropped_not_guessed():
    """Slot, result, duration and start time are what a match IS here.
    Nothing is inferred to fill a gap: a guess dressed as a measurement is
    the one thing an instrument must not do."""
    rows = rows_for(6)
    rows[0].pop("radiant_win")
    rows[1]["duration"] = None
    shaped = shape.shape(rows, HEROES)
    assert len(shaped.matches) == 4
    assert shaped.dropped["malformed"] == 2


def test_the_side_decides_the_result():
    """`player_slot < 128` is Radiant, and a win is that agreeing with
    `radiant_win`. Getting this backwards would invert every number."""
    shaped = shape.shape([
        dict(match_id=1, player_slot=0, radiant_win=True, duration=1800,
             start_time=1_700_000_000, hero_id=1),
        dict(match_id=2, player_slot=128, radiant_win=True, duration=1800,
             start_time=1_700_004_000, hero_id=1)], HEROES)
    first, second = shaped.matches
    assert first.radiant and first.win
    assert not second.radiant and not second.win


def test_three_hours_of_silence_opens_a_new_session():
    rows = rows_for(4, gap=1200)
    rows[2]["start_time"] += 4 * 3600
    rows[3]["start_time"] += 4 * 3600
    shaped = shape.shape(rows, HEROES)
    assert shaped.sessions == 2
    assert [m.position for m in shaped.matches] == [1, 2, 1, 2]


def test_the_tilt_check_does_not_charge_a_loss_you_slept_on():
    """The previous result only counts INSIDE a session. Otherwise the
    first game of a morning is measured against last night's last."""
    rows = rows_for(3, win_rate=0.0, gap=1200)
    rows[2]["start_time"] += 5 * 3600
    shaped = shape.shape(rows, HEROES)
    assert [m.previous for m in shaped.matches] == [
        "First of session", "After a loss", "First of session"]


def test_turbo_and_unranked_are_dropped_only_when_asked():
    rows = rows_for(4)
    rows[0]["game_mode"] = 23           # Turbo
    rows[1]["lobby_type"] = 0           # unranked
    assert len(shape.shape(rows, HEROES).matches) == 4
    assert len(shape.shape(rows, HEROES, no_turbo=True).matches) == 3
    assert len(shape.shape(rows, HEROES, ranked_only=True).matches) == 3


def test_a_deathless_game_stays_a_number():
    """Deaths are floored at one, so the KDA of a game with none is its own
    kill contribution rather than infinity taking the mean with it."""
    shaped = shape.shape(rows_for(1, deaths=0, kills=10, assists=10), HEROES)
    assert shaped.matches[0].kda == pytest.approx(13.0)


# --------------------------------------------------------- statistics ----

def test_the_datum_is_the_players_own_rate_and_sigma_is_measured_off_it():
    """sqrt(p(1-p)/k) is the standard error on a proportion. The sigma is
    how many of those the bucket sits from the player's own rate — not
    from 50%, and not from anybody else's."""
    matches = shape.shape(rows_for(100, win_rate=0.5), HEROES).matches
    for index, match in enumerate(matches):
        match.hero = "Axe" if index < 20 else "Bane"
        match.win = index < 16 or (20 <= index < 54)
    baseline = sum(1 for m in matches if m.win) / len(matches)
    rows = analyse.categorical(matches, baseline, lambda m: m.hero, "count")
    axe = next(r for r in rows if r.key == "Axe")
    assert axe.n == 20 and axe.wins == 16
    assert axe.rate == pytest.approx(0.8)
    assert axe.se == pytest.approx(
        math.sqrt(baseline * (1 - baseline) / 20))
    assert axe.sigma == pytest.approx((0.8 - baseline) / axe.se)


def test_a_thin_bucket_is_measured_but_never_written_up():
    """Below `MIN_BUCKET` a bucket appears, muted, so what was measured is
    visible — and produces no finding however far off it sits."""
    matches = shape.shape(rows_for(60, win_rate=0.5), HEROES).matches
    for index, match in enumerate(matches):
        match.hero = "Axe" if index < 4 else "Bane"
        match.win = index < 4 or index >= 32
    baseline = sum(1 for m in matches if m.win) / len(matches)
    rows = analyse.categorical(matches, baseline, lambda m: m.hero, "count")
    axe = next(r for r in rows if r.key == "Axe")
    assert axe.n == 4 and axe.rate == 1.0
    assert not axe.eligible
    assert abs(axe.sigma) >= analyse.SIGMA_CAT, "it IS far off"
    assert not [f for f in analyse.cat_findings(rows, "hero")
                if f.key == "Axe"]


def test_a_two_sided_split_reports_one_fact_not_two():
    """Radiant and Dire are one fact: the unfavourable half is the mirror
    of the favourable one and says nothing new."""
    matches = shape.shape(rows_for(80, win_rate=0.5), HEROES).matches
    for index, match in enumerate(matches):
        match.radiant = index < 40
        match.win = index < 28 or index >= 68
    baseline = sum(1 for m in matches if m.win) / len(matches)
    rows = analyse.categorical(
        matches, baseline, lambda m: "Radiant" if m.radiant else "Dire",
        ["Radiant", "Dire"])
    findings = analyse.cat_findings(rows, "side")
    assert len(findings) == 1
    assert findings[0].sigma > 0


def test_a_metric_split_uses_the_overall_spread_not_the_buckets_own():
    """A thin bucket must not be able to manufacture a tight interval for
    itself, which is exactly what its own standard deviation would do."""
    matches = shape.shape(rows_for(40), HEROES).matches
    for index, match in enumerate(matches):
        match.hero = "Axe" if index < 8 else "Bane"
        match.hero_damage = (30000 if index < 8 else 15000)
    datum, spread, rows, covered, total = analyse.metric_split(
        matches, lambda m: m.hero, lambda m: m.damage_per_min)
    axe = next(r for r in rows if r.key == "Axe")
    assert covered == total == 40
    assert axe.se == pytest.approx(spread / math.sqrt(axe.n))
    assert axe.sigma > analyse.SIGMA_CAT


def test_every_figure_is_two_significant_figures():
    """At the user's request. SIGNIFICANT FIGURES rather than decimal
    places because these blocks span four orders of magnitude — gold in
    the hundreds, CS in single figures, denies in hundredths — so one
    decimal setting cannot serve them all."""
    assert analyse.sig(614.67) == "610"
    assert analyse.sig(5.6) == "5.6"
    assert analyse.sig(0.48) == "0.48"
    assert analyse.sig(0.0483) == "0.048"
    assert analyse.sig(2.345) == "2.3"
    assert analyse.sig(-3.47) == "-3.5"
    # NO TRAILING ".0", at the user's request — a whole number is written
    # as one. It must not reach inside the decimals, though: 0.30 is not
    # a whole number and keeps the second figure it is drawn at.
    assert analyse.sig(3.04) == "3"
    assert analyse.sig(2.98) == "3"
    assert analyse.sig(0.30) == "0.30"
    assert not any(analyse.sig(v).endswith(".0")
                   for v in (3.04, 2.98, 5.02, 9.99, 10.23, 100.0))
    # Rounding that crosses a power of ten must not print a third figure.
    assert analyse.sig(9.99) == "10"
    assert analyse.sig(0.0999) == "0.10"
    # Nothing measured is nothing written, never "0.00".
    assert analyse.sig(None) == ""
    assert analyse.sig(0) == "0"
    # NEVER an exponent: "6.1e+02" is the right number, unreadably.
    assert "e" not in analyse.sig(614.67) and "e" not in analyse.sig(0.00012)


def test_denies_is_counted_per_game_and_a_long_game_does_not_dilute_it():
    """The one figure in the contribution family that is NOT a rate, at
    the user's request and on its own merits. Denying is a laning stage
    act, so a 25 minute game and a 50 minute game hold about the same
    number — per minute would make the long game read as worse denying
    with nothing about the laning changed. Per minute also could not give
    the whole numbers asked for: denies run at tenths of one a minute, so
    rounding those to integers prints 0 for every hero."""
    matches = shape.shape(rows_for(40), HEROES).matches
    for index, match in enumerate(matches):
        match.hero = "Axe" if index < 20 else "Bane"
        match.denies = 24 if index < 20 else 6
        # Axe's games run twice as long. Per minute that would halve his
        # figure; per game it must not move it at all.
        match.duration = 3600 if index < 20 else 1800
    blocks = analyse.build_blocks(matches, 0.5, picked=dict(analyse.DEFAULT_ON))
    block = next(b for b in blocks if b.id == "denies")
    figures = {r.key: analyse.format_figure(block, r.mean) for r in block.shown}
    assert figures == {"Axe": "24", "Bane": "6"}
    assert not any("." in f for f in figures.values()), "whole numbers"
    assert analyse.METRICS["denies"]["field"] == "denies", "the raw count"


def test_a_rate_is_per_minute_so_a_long_game_cannot_out_farm_a_short_one():
    """Raw CS measures how long the game ran at least as much as how well
    it was farmed, which is the whole reason these are rates."""
    long_game = shape.shape(rows_for(1, duration=3600, last_hits=300),
                            HEROES).matches[0]
    short_game = shape.shape(rows_for(1, duration=1800, last_hits=300),
                             HEROES).matches[0]
    assert long_game.last_hits == short_game.last_hits == 300
    assert long_game.cs_per_min == pytest.approx(5.0)
    assert short_game.cs_per_min == pytest.approx(10.0)
    assert short_game.cs_per_min > long_game.cs_per_min


def test_gold_and_xp_are_taken_as_the_rates_they_already_are():
    """OpenDota reports `gold_per_min` and `xp_per_min` PER MINUTE itself.
    Dividing either by the duration a second time would quietly report a
    number nobody measured, and it would look plausible."""
    matches = shape.shape(rows_for(20, duration=3000, gold_per_min=500,
                                   xp_per_min=600), HEROES).matches
    blocks = analyse.build_blocks(matches, 0.5, picked=dict(analyse.DEFAULT_ON))
    gold = next(b for b in blocks if b.id == "gold")
    experience = next(b for b in blocks if b.id == "xp")
    assert gold.datum == pytest.approx(500)
    assert experience.datum == pytest.approx(600)


def test_a_field_that_never_arrives_is_unmeasured_rather_than_nought():
    """The four farm fields are the ones most at risk of coming back empty
    — a projection OpenDota does not accept is dropped SILENTLY. An absent
    field must read as "not measured" and produce no finding, never as a
    hero who farms nothing, which is a measurement nobody made."""
    matches = shape.shape(rows_for(30), HEROES).matches      # no CS in the row
    assert all(m.last_hits is None and m.cs_per_min is None for m in matches)
    blocks = analyse.build_blocks(matches, 0.5, picked=dict(analyse.DEFAULT_ON))
    cs = next(b for b in blocks if b.id == "cs")
    assert cs.datum is None
    assert cs.findings == []
    assert cs.covered == 0


def test_the_farm_four_are_contributions_and_not_win_rate_splits():
    """They belong in the Impact card with the other caveated rankings:
    every one of them ranks a ROLE before it ranks the player."""
    matches = shape.shape(rows_for(40, last_hits=200, denies=20,
                                   gold_per_min=500, xp_per_min=600),
                          HEROES).matches
    # TWO heroes, because a section needs two eligible buckets to have a
    # best and a worst — one bucket is a figure, not a spread.
    for index, match in enumerate(matches):
        carry = index < 20
        match.hero = "Axe" if carry else "Bane"
        match.last_hits = 400 if carry else 60
        match.denies = 24 if carry else 4
        match.gold_per_min = 620 if carry else 280
        match.xp_per_min = 700 if carry else 340
    blocks = analyse.build_blocks(matches, 0.5, picked=dict(analyse.DEFAULT_ON))
    farm = {b.id: b for b in blocks if b.id in ("gold", "xp", "cs", "denies")}
    assert set(farm) == {"gold", "xp", "cs", "denies"}
    assert all(b.kind == "metric" for b in farm.values())
    assert all(b.caveat for b in farm.values())
    # Distinct fields, or two sections would draw the same figure twice.
    assert len({analyse.METRICS[k]["field"] for k in farm}) == 4

    report = Report(options=Options(), how="test", name="", matches=matches,
                    blocks=blocks, dropped={}, sessions=1,
                    returned=len(matches))
    _rates, contributions = report.split_findings()
    rate_rows, impact_rows = report.summary_rows()
    impact = {block.name for block, *_ in impact_rows}
    assert {"Gold/min", "XP/min", "CS/min", "Denies/game"} <= impact
    assert not {"Gold/min", "XP/min", "CS/min", "Denies/game"} & {
        block.name for block, *_ in rate_rows}


def test_an_item_is_measured_against_that_heros_own_rate():
    """Comparing a Pudge item against an overall rate dominated by other
    heroes would measure the hero, not the item."""
    rows = rows_for(40, hero=2, win_rate=0.5, item_0=29)
    for index in range(0, 20):
        rows[index]["item_1"] = 63           # on the twenty won games
    matches = shape.shape(rows, HEROES).matches
    block = analyse.item_analysis(matches, {29: "Boots", 63: "Treads"})
    group = block.groups[0]
    assert group.hero == "Axe"
    assert group.baseline == pytest.approx(0.5)
    treads = next(r for r in group.rows if r.key == "Treads")
    assert treads.rate == pytest.approx(1.0)
    assert treads.sigma > analyse.SIGMA_CAT
    assert any("Treads" in f.text and "on Axe" in f.text
               for f in block.findings)


def test_the_report_headlines_the_two_families_apart():
    """Contribution metrics separate far harder than win-rate splits —
    they are partly structural — so one merged ranking by sigma would be
    nothing but damage rows with every behavioural finding under them."""
    matches = shape.shape(rows_for(60, win_rate=0.5), HEROES).matches
    for index, match in enumerate(matches):
        match.hero = "Axe" if index < 30 else "Bane"
        match.win = index < 24 or index >= 54
        match.hero_damage = 40000 if index < 30 else 8000
    baseline = sum(1 for m in matches if m.win) / len(matches)
    picked = dict(analyse.DEFAULT_ON)
    blocks = analyse.build_blocks(matches, baseline, picked, {})
    report = Report(options=Options(account_id=1), how="", name="",
                    matches=matches, blocks=blocks, dropped={}, sessions=1,
                    returned=60)
    rates, contributions = report.split_findings()
    assert rates and contributions
    assert all(block.kind != "metric" for block, _ in rates)
    assert all(block.kind == "metric" for block, _ in contributions)


# ------------------------------------------------------------- export ----

def _report():
    matches = shape.shape(rows_for(30, win_rate=0.6), HEROES).matches
    baseline = sum(1 for m in matches if m.win) / len(matches)
    blocks = analyse.build_blocks(matches, baseline,
                                  dict(analyse.DEFAULT_ON), {})
    return Report(options=Options(account_id=195286385, window="12m",
                                  cap=1000),
                  how="read as a 32 bit friend ID", name="Bijson",
                  matches=matches, blocks=blocks,
                  dropped={"short": 0, "window": 0, "turbo": 0,
                           "unranked": 0, "malformed": 0},
                  sessions=1, returned=30)


def test_the_workbook_is_two_sheets_the_raw_table_and_the_analysis(tmp_path):
    """At the user's request: one tab you sort and pivot yourself, one tab
    with the whole report. Thirteen tabs is a worse way to read it."""
    openpyxl = pytest.importorskip("openpyxl")
    report = _report()
    path = tmp_path / "report.xlsx"
    workbook.write(report, path)
    book = openpyxl.load_workbook(path)
    assert book.sheetnames == ["Raw matches", "Analysis"]
    raw = book["Raw matches"]
    assert raw.max_row == report.n + 1          # a header and every match
    assert raw.auto_filter.ref, "the raw sheet is meant to be filtered"
    analysis = [row[0] for row in book["Analysis"].iter_rows(values_only=True)]
    assert "Dota deviation report" in analysis
    assert "FINDINGS" in analysis
    for block in report.blocks:
        assert block.name.upper() in analysis


def test_the_workbook_carries_the_buckets_the_screen_hides(tmp_path):
    """The screen is protecting the reader from noise; the workbook is the
    record, so a single-game bucket is in it."""
    pytest.importorskip("openpyxl")
    rows = rows_for(30, hero=2, win_rate=0.5)
    rows[0]["hero_id"] = 3                      # one game on Bane
    matches = shape.shape(rows, HEROES).matches
    baseline = sum(1 for m in matches if m.win) / len(matches)
    blocks = analyse.build_blocks(matches, baseline, {"hero": True}, {})
    hero_block = blocks[0]
    assert [r.key for r in hero_block.shown] == ["Axe"]
    assert hero_block.hidden == 1
    text = " ".join(str(cell) for row in workbook.analysis_rows(
        Report(options=Options(account_id=1), how="", name="",
               matches=matches, blocks=blocks, dropped={}, sessions=1,
               returned=30)) for cell in row)
    assert "Bane" in text


# -------------------------------------------------------------- store ----

def test_the_remembered_accounts_are_local_only(tmp_path):
    """Gitignored, like the settings file and the API key: sending someone
    a copy of this app must not send them your match history."""
    import pathlib
    ignored = pathlib.Path("/home/user/Dota_Draft_Assist/.gitignore")
    assert "history_accounts.json" in ignored.read_text(encoding="utf-8")

    path = tmp_path / "accounts.json"
    store.remember(195286385, "Bijson", when="2026-09-08 21:14", matches=412,
                   wins=211, options={"window": "6m"}, path=path)
    store.remember(42, "Mate", when="2026-09-09 10:00", matches=88, wins=40,
                   path=path)
    rows = store.load(path)
    assert [row["account_id"] for row in rows] == [42, 195286385]
    assert rows[1]["name"] == "Bijson"
    assert rows[1]["options"] == {"window": "6m"}
    assert store.label(rows[1]) == "195286385 (Bijson)"


def test_an_account_with_no_resolved_name_is_just_its_number():
    """Empty brackets after a number say a lookup failed, which is not
    something the dropdown should be reporting."""
    assert store.label({"account_id": 42, "name": ""}) == "42"
    assert store.label({"account_id": 42}) == "42"


# ------------------------------------------------------- the name -------

def test_the_display_name_is_read_off_the_profile(monkeypatch):
    """A friend ID is nine digits nobody recognises a fortnight later, so
    the run resolves the name that goes in brackets beside it."""
    from draft_assist.history import opendota
    seen = []
    monkeypatch.setattr(opendota, "_get", lambda url, **k: seen.append(url)
                        or {"profile": {"personaname": " Bijson "}})
    who = opendota.profile(195286385)
    assert (who.name, who.known) == ("Bijson", True)
    assert seen == ["https://api.opendota.com/api/players/195286385"]


def test_a_name_that_cannot_be_had_is_not_a_fault(monkeypatch):
    """A private profile answers 200 with a null profile, and a rate limit
    answers with an error — neither may stop a run that is about matches."""
    from draft_assist.history import opendota

    monkeypatch.setattr(opendota, "_get", lambda url, **k: {"profile": None})
    assert opendota.profile(1) == opendota.Profile(name="", known=False)

    def refuse(url, **kwargs):
        raise opendota.ApiError("rate", "slow down")
    monkeypatch.setattr(opendota, "_get", refuse)
    # ASKED AND NOT ANSWERED is not the same as answered "no": known stays
    # None, or a rate limit would tell somebody their ID was wrong.
    assert opendota.profile(1) == opendota.Profile(name="", known=None)


def test_an_empty_match_list_says_which_of_the_three_it_is(monkeypatch):
    """A private history, a wrong ID and an unanswerable lookup all return
    no matches, and the user can only fix the first two if told apart."""
    from draft_assist.history import opendota, runner

    def answering(profile):
        def fake(url, **kwargs):
            if "/matches?" in url:
                return []                   # nothing, whatever the reason
            if "/players/" in url:
                if isinstance(profile, Exception):
                    raise profile
                return {"profile": profile}
            return []
        return fake

    options = Options(account_id=1, window="all", cap=100)

    monkeypatch.setattr(opendota, "_get", answering({"personaname": "Bij"}))
    with pytest.raises(runner.Refused) as caught:
        runner.run(options)
    assert str(caught.value) == runner.PRIVATE
    assert "Expose Public Match Data" in runner.PRIVATE

    monkeypatch.setattr(opendota, "_get", answering(None))
    with pytest.raises(runner.Refused) as caught:
        runner.run(options)
    assert str(caught.value) == runner.UNKNOWN_ACCOUNT

    monkeypatch.setattr(opendota, "_get",
                        answering(opendota.ApiError("rate", "slow down")))
    with pytest.raises(runner.Refused) as caught:
        runner.run(options)
    assert str(caught.value) == runner.NO_MATCHES


def test_a_run_carries_the_name_through_to_the_remembered_list(
        tmp_path, monkeypatch):
    """The run is the one moment the name can be resolved without the tab
    making a network call of its own, so it is where it happens."""
    from draft_assist.history import opendota, runner

    def fake(url, **kwargs):
        if "/matches?" in url:
            return rows_for(40)
        if "/players/" in url:
            return {"profile": {"personaname": "Bijson"}}
        return []                                   # the hero list

    monkeypatch.setattr(opendota, "_get", fake)
    report = runner.run(Options(account_id=195286385, window="all", cap=100))
    assert report.name == "Bijson"

    path = tmp_path / "accounts.json"
    rows = store.remember(report.options.account_id, report.name,
                          when="2026-09-09 10:00", matches=report.n,
                          wins=report.wins, path=path)
    assert store.label(rows[0]) == "195286385 (Bijson)"


def test_running_an_account_again_keeps_what_it_knew(tmp_path):
    """An id typed straight in has no name attached, and must not wipe the
    one a previous run resolved."""
    path = tmp_path / "accounts.json"
    store.remember(7, "Bijson", when="2026-01-01 00:00", matches=100, wins=50,
                   path=path)
    store.remember(7, "", when="2026-02-02 00:00", matches=120, wins=61,
                   path=path)
    row = store.load(path)[0]
    assert row["name"] == "Bijson"
    assert row["last_run"] == "2026-02-02 00:00"
    assert (row["matches"], row["wins"]) == (120, 61)


def test_a_store_that_cannot_be_read_is_empty_not_a_crash(tmp_path):
    path = tmp_path / "accounts.json"
    path.write_text("{ not json", encoding="utf-8")
    assert store.load(path) == []


# ------------------------------------------------------------- cache ----

def test_the_last_run_comes_back_off_disk_without_a_fetch(tmp_path,
                                                          monkeypatch):
    """Seeing last week's answer used to mean measuring it again over a
    free API, with the tab blank until it finished."""
    from draft_assist.history import cache, opendota, runner

    def fake(url, **kwargs):
        if "/matches?" in url:
            return rows_for(40)
        if "/players/" in url:
            return {"profile": {"personaname": "Bijson"}}
        return []

    monkeypatch.setattr(opendota, "_get", fake)
    monkeypatch.setattr(cache, "CACHE_DIR", tmp_path / "cache")
    report = runner.run(Options(account_id=195286385, window="all", cap=100))
    assert cache.save(report)

    monkeypatch.setattr(opendota, "_get", lambda *a, **k: pytest.fail(
        "reading the cache asked OpenDota for something"))
    back = cache.load(195286385)
    assert back is not None
    assert back.n == report.n and back.wins == report.wins
    assert back.name == "Bijson"
    assert back.ran_at == report.ran_at
    # The RAW MATCHES survive, which is what lets the workbook's first
    # sheet be written with no network at all.
    assert [m.match_id for m in back.matches] == \
        [m.match_id for m in report.matches]


def test_the_findings_are_recomputed_rather_than_stored(tmp_path,
                                                        monkeypatch):
    """Storing the blocks would let a cached run show numbers produced by
    a version of the analysis that is no longer in the app."""
    from draft_assist.history import cache

    monkeypatch.setattr(cache, "CACHE_DIR", tmp_path / "cache")
    matches = shape.shape(rows_for(40), HEROES).matches
    report = Report(options=Options(account_id=7, picked={"hero": True}),
                    how="", name="", matches=matches, blocks=[],
                    dropped={}, sessions=1, returned=40)
    cache.save(report)

    raw = json.loads((tmp_path / "cache" / "7.json").read_text("utf-8"))
    assert "matches" in raw and "blocks" not in raw

    # And which analyses are drawn follows what is ticked NOW, not what
    # was ticked when the run happened.
    assert len(cache.load(7, {"hero": True}).blocks) == 1
    assert cache.load(7, {"hero": False}).blocks == []


def test_a_cache_that_cannot_be_read_is_no_cache_rather_than_a_crash(
        tmp_path, monkeypatch):
    """The file is written by older versions of the app as often as by
    this one, so an unreadable row degrades rather than taking the tab
    down with it."""
    from draft_assist.history import cache
    folder = tmp_path / "cache"
    folder.mkdir()
    monkeypatch.setattr(cache, "CACHE_DIR", folder)

    assert cache.load(1) is None                       # nothing there
    (folder / "2.json").write_text("{ not json", encoding="utf-8")
    assert cache.load(2) is None
    (folder / "3.json").write_text('{"matches": [{"junk": 1}]}', "utf-8")
    assert cache.load(3) is None


def test_the_cached_runs_are_local_only(tmp_path):
    """Gitignored beside history_accounts.json and the API key: sending
    somebody a copy of this app sends them none of your matches."""
    import pathlib
    ignored = pathlib.Path("/home/user/Dota_Draft_Assist/.gitignore")
    assert "history_cache/" in ignored.read_text(encoding="utf-8")


def test_the_item_name_map_is_not_a_run_and_is_never_pruned(tmp_path,
                                                            monkeypatch):
    """`NAMES_FILE` lives beside the runs, and a `*.json` glob sweeps it
    up. That went wrong in both directions: `_prune` counted it towards
    KEEP and would DELETE it once there were that many accounts, and a
    reader that assumed every file here was a run raised KeyError on it.
    Losing the map is the "Item 63" bug from a fourth cause."""
    from draft_assist.history import cache as cache_mod
    monkeypatch.setattr(cache_mod, "CACHE_DIR", tmp_path)
    monkeypatch.setattr(cache_mod, "KEEP", 2)
    assert cache_mod.save_item_names({63: "Power Treads"}, tmp_path)
    names = tmp_path / cache_mod.NAMES_FILE
    assert names.exists()

    for account in (111, 222, 333, 444):
        (tmp_path / f"{account}.json").write_text("{}", encoding="utf-8")
    cache_mod._prune(tmp_path)

    # The map survives however many accounts there are...
    assert names.exists(), "the item name map was pruned as though a run"
    assert cache_mod.item_names().get(63) == "Power Treads"
    # ...and it never counted towards the runs kept.
    kept = cache_mod.run_files(tmp_path)
    assert len(kept) == 2
    assert names not in kept
    assert all(p.stem.isdigit() for p in kept)


def test_only_the_newest_runs_are_kept(tmp_path, monkeypatch):
    from draft_assist.history import cache
    folder = tmp_path / "cache"
    monkeypatch.setattr(cache, "CACHE_DIR", folder)
    matches = shape.shape(rows_for(12), HEROES).matches
    for account in range(1, cache.KEEP + 4):
        cache.save(Report(options=Options(account_id=account), how="",
                          name="", matches=matches, blocks=[], dropped={},
                          sessions=1, returned=12))
    assert len(list(folder.glob("*.json"))) == cache.KEEP


def test_a_cached_run_still_knows_its_items_by_name(tmp_path, monkeypatch):
    """"Items are listed as numbers instead of names."

    The item block keys its buckets by OpenDota's numeric item id and
    turns them into words with a map fetched from `/constants/items`.
    `cache.rebuild` recomputes every block on the way back in and was
    handed an EMPTY map, so the names were right exactly once — on the
    run that fetched them — and every later opening of that same run,
    which is the path the tab takes whenever you do not re-run, printed
    "Item 1", "Item 63" down the whole block.
    """
    from draft_assist.history import cache

    folder = tmp_path / "cache"
    monkeypatch.setattr(cache, "CACHE_DIR", folder)
    cache.save_item_names({1: "Blink Dagger", 63: "Power Treads"})
    # Read back as INTS, because that is what the buckets are keyed by —
    # a map keyed by strings misses every one of them silently, which is
    # the same numbers on screen from a different cause. The saved file
    # sits OVER the bundled map rather than replacing it.
    names = cache.item_names()
    assert names[1] == "Blink Dagger" and names[63] == "Power Treads"
    assert len(names) > 100, "the bundled map is not underneath" 

    matches = shape.shape(rows_for(40), HEROES).matches
    for index, match in enumerate(matches):
        match.items = [1, 63] if index % 2 else [1]
    report = Report(options=Options(account_id=9, picked={"items": True}),
                    how="", name="", matches=matches, blocks=[],
                    dropped={}, sessions=1, returned=40)
    cache.save(report)

    back = cache.load(9, {"items": True})
    assert back is not None
    keys = [row.key for block in back.blocks if block.kind == "items"
            for group in block.groups for row in group.rows]
    assert keys, "the item block came back empty"
    assert not any(k.startswith("Item ") for k in keys), keys
    assert "Blink Dagger" in keys


def test_the_bundled_map_names_items_with_no_run_and_no_network(tmp_path,
                                                                monkeypatch):
    """The saved file only exists after a run has written one, so an
    install that updated without re-measuring went on printing ids until
    Update was pressed — and it "fixed itself" with nothing having been
    done differently. Worse, the fetch it depends on fails SILENTLY:
    `opendota.item_names` answers {} on any ApiError.

    So the map SHIPS. A fresh install with no run, a cold cache and a
    dead connection all still name their items, and a saved file only
    ever adds to it.
    """
    from draft_assist.history import cache
    folder = tmp_path / "cache"
    folder.mkdir()
    monkeypatch.setattr(cache, "CACHE_DIR", folder)

    bundled = cache.bundled_item_names()
    assert len(bundled) > 400, "the bundled map is missing or short"
    assert bundled[1] == "Blink Dagger"
    # Nothing saved at all — a fresh install.
    assert cache.item_names() == bundled
    # And a file that cannot be read degrades to it rather than to
    # nothing, which is what put numbers on screen in the first place.
    for junk in ("{ not json", '{"nope": "x"}', "[]"):
        (folder / cache.NAMES_FILE).write_text(junk, encoding="utf-8")
        assert cache.item_names() == bundled, junk
    assert cache.save_item_names({}) is False

    # It is the real map, not a stub: every id the screenshot showed.
    for hero_item in (41, 63, 110, 116, 141, 178, 259, 277):
        assert bundled.get(hero_item), hero_item
    assert not any(str(v).startswith("Item ") for v in bundled.values())
