"""Valve's own role ratings, and the sums this app builds on them.

The data is the game's: `npc_heroes.txt` carries a "Role" list and a
parallel "Rolelevels" list of 0-to-3 scores per hero, which is what the
hero-selection UI draws its bars from. Nothing in this app rates a hero.

TWO THINGS WERE SETTLED BY MEASURING RATHER THAN REMEMBERING, and both
are held here because both are easy to get wrong from memory:

* **There are EIGHT roles, not nine.** Every list anybody writes down
  includes Jungler. Valve's data does not: it appears zero times in the
  whole hero file, and OpenDota's `constants/heroes`, built independently
  from the same source, lists the same eight. The role survives only as
  leftover strings in the client's filter UI (with Lane Support, Offlaner
  and Solo Mid, which were never scored either).
* **Every hero is rated.** A first parse said 109 of 127 and that was a
  bug in the parse, not a hole in the data - it found the first mention
  of a hero's name rather than its own block, and heroes refer to each
  other in fields like "LastHitChallengeRival", so Lion's roles were read
  out of Bane's block.
"""

import json

import pytest

from draft_assist.model import roles


def test_every_hero_the_app_can_draft_has_a_rating():
    table = json.loads(roles.BUNDLED.read_text(encoding="utf-8"))
    assert len(table) == 127, (
        f"{len(table)} heroes rated; a partial table is usually a parse "
        "that read one hero's roles out of another hero's block")
    for hid, levels in table.items():
        assert int(hid) > 0
        assert levels, f"hero {hid} has an empty rating"


def test_there_are_eight_roles_and_jungler_is_not_one():
    assert len(roles.ROLES) == 8
    assert "Jungler" not in roles.ROLES
    # Valve's own column order, which is what the card reads down.
    assert roles.ROLES == ("Carry", "Support", "Nuker", "Disabler",
                           "Durable", "Escape", "Pusher", "Initiator")


def test_no_rating_is_outside_valves_scale():
    table = json.loads(roles.BUNDLED.read_text(encoding="utf-8"))
    for hid, levels in table.items():
        for role, level in levels.items():
            assert role in roles.ROLES, f"hero {hid} rated on {role!r}"
            assert 1 <= level <= roles.MAX_LEVEL, (hid, role, level)


def test_a_known_hero_reads_back_the_games_own_figures():
    # Lion, from the hero file: Support 2, Disabler 3, Nuker 3, Initiator 2.
    lion = roles.levels_for(26)
    assert lion["Support"] == 2 and lion["Disabler"] == 3
    assert lion["Nuker"] == 3 and lion["Initiator"] == 2
    # Unrated roles come back as a zero rather than absent, so a caller
    # never has to ask whether a key is missing or the score is nought.
    assert lion["Carry"] == 0
    assert set(lion) == set(roles.ROLES)


# ---- the sums ----------------------------------------------------------

def test_the_denominator_is_three_per_pick():
    """After two picks a role can hold at most 6, after five 15."""
    two = roles.team_scores([1, 26])
    assert all(score.possible == 6 for score in two)
    five = roles.team_scores([1, 26, 8, 2, 5])
    assert all(score.possible == 15 for score in five)


def test_the_share_makes_a_part_drafted_team_comparable():
    """Three picks scoring 6 of 9 and five scoring 10 of 15 are the same
    team so far as this card is concerned - which is the whole reason the
    raw sums are not drawn."""
    small = roles.RoleScore("Carry", scored=6, possible=9, rated=3)
    big = roles.RoleScore("Carry", scored=10, possible=15, rated=5)
    assert small.share == pytest.approx(big.share)
    assert small.pills == big.pills


def test_pills_are_the_share_rounded_to_the_nearest_one():
    assert roles.RoleScore("Carry", 0, 9, 3).pills == 0
    assert roles.RoleScore("Carry", 9, 9, 3).pills == roles.PILLS
    # 5/9 is 0.556, which is 2.8 pills and rounds to 3.
    assert roles.RoleScore("Carry", 5, 9, 3).pills == 3


def test_an_empty_side_scores_nothing_rather_than_dividing_by_zero():
    for score in roles.team_scores([]):
        assert score.possible == 0 and score.share == 0.0
        assert score.pills == 0


def test_a_hero_with_no_rating_is_left_out_of_BOTH_halves():
    """Counting it as a zero in the numerator while it still raised the
    denominator would report a team as WORSE at every role for having
    picked a hero this file has not been cut for yet."""
    alone = roles.team_scores([1])
    with_ghost = roles.team_scores([1, 10_000_000])
    assert [s.possible for s in alone] == [s.possible for s in with_ghost]
    assert [s.scored for s in alone] == [s.scored for s in with_ghost]
    assert all(s.rated == 1 for s in with_ghost)


# ---- who leads ---------------------------------------------------------

def test_compare_reads_from_the_first_sides_point_of_view():
    ours = [roles.RoleScore(r, 9, 9, 3) for r in roles.ROLES]
    theirs = [roles.RoleScore(r, 0, 9, 3) for r in roles.ROLES]
    assert roles.compare(ours, theirs) == [1] * len(roles.ROLES)
    assert roles.compare(theirs, ours) == [-1] * len(roles.ROLES)


def test_equal_shares_are_level_rather_than_a_win_for_either():
    ours = [roles.RoleScore(r, 6, 9, 3) for r in roles.ROLES]
    theirs = [roles.RoleScore(r, 10, 15, 5) for r in roles.ROLES]
    assert roles.compare(ours, theirs) == [0] * len(roles.ROLES)


def test_a_side_with_nothing_rated_leads_nothing_and_trails_nothing():
    """Otherwise whoever picked first sweeps every role, which says
    something about the clock rather than about the drafts."""
    ours = roles.team_scores([1, 26])
    theirs = roles.team_scores([])
    assert roles.compare(ours, theirs) == [0] * len(roles.ROLES)
    assert roles.compare(theirs, ours) == [0] * len(roles.ROLES)
