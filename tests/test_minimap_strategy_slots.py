"""The split that a real match's ground truth settled.

The user played match 8995290135, the app put Hoodwink on the enemy team
and Riki on theirs, and they said which way round it really was. Their
recording's fullest strategy-time payload is the fixture here, so the one
case that has ever been checked against a person's own knowledge of the
game cannot regress silently.
"""

import json
from pathlib import Path

import pytest

from draft_assist.gsi import minimap

FIXTURE = (Path(__file__).parent / "fixtures" / "gsi"
           / "strategy_slots_8995290135.json")

# The ten heroes, numbered however this test likes: `read_lineups` maps
# names to ids through whatever dictionary it is handed.
IDS = {f"npc_dota_hero_{name}": number for number, name in enumerate(
    ["axe", "storm_spirit", "juggernaut", "rubick", "hoodwink",
     "riki", "grimstroke", "snapfire", "nyx_assassin", "winter_wyvern"], 1)}
RUBICK = IDS["npc_dota_hero_rubick"]


@pytest.fixture
def payload():
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def read(payload):
    return minimap.read_lineups(
        payload, IDS, RUBICK,
        game_state="DOTA_GAMERULES_STATE_STRATEGY_TIME")


def test_the_teams_are_the_ones_the_user_named(payload):
    out = read(payload)
    assert sorted(out.allies) == sorted(
        IDS[f"npc_dota_hero_{n}"] for n in
        ("axe", "storm_spirit", "juggernaut", "rubick", "hoodwink"))
    assert sorted(out.enemies) == sorted(
        IDS[f"npc_dota_hero_{n}"] for n in
        ("riki", "grimstroke", "snapfire", "nyx_assassin", "winter_wyvern"))


def test_hoodwink_is_an_ally_and_riki_is_not(payload):
    """The exact swap that was reported, named so a failure says which."""
    out = read(payload)
    assert IDS["npc_dota_hero_hoodwink"] in out.allies
    assert IDS["npc_dota_hero_riki"] in out.enemies


def test_object_order_would_have_got_it_wrong(payload):
    """The rule this replaces, so the fixture is known to be a hard case.

    If object order ever agreed with the truth here, this fixture would
    stop testing anything.
    """
    entries = minimap.hero_entries(payload)
    names = [name for _i, name, _p in entries]
    assert names[:minimap.TEAM_SIZE][-1] == "npc_dota_hero_riki"
    assert "npc_dota_hero_hoodwink" in names[minimap.TEAM_SIZE:]


def test_the_split_is_asserted_rather_than_offered(payload):
    out = read(payload)
    assert out.split_rule == "strategy slots"
    assert out.sides_certain is True


def test_it_declines_rather_than_inverting(payload):
    """The player's own hero must be among the five on the slots.

    That is the whole guard against the fault every earlier rule here
    had. Tell it the player is Riki - who stands at a world position -
    and the premise is contradicted, so it must fall back rather than
    hand back the two halves the other way round.
    """
    out = minimap.read_lineups(
        payload, IDS, IDS["npc_dota_hero_riki"],
        game_state="DOTA_GAMERULES_STATE_STRATEGY_TIME")
    assert out.split_rule != "strategy slots"
    assert out.sides_certain is False


def test_predicted_enemy_lanes_still_go_to_the_pairs(payload):
    """Two heroes to a slot is the case this rule must NOT take.

    When you predict the enemy lanes as well, all ten stand on the five
    slots - which is every earlier recording, and what
    `_split_by_lane_pairs` was built for.
    """
    slots = sorted(minimap.LANE_SLOTS)
    for number, key in enumerate(["o7", "o8", "o10", "o11", "o12"]):
        payload["minimap"][key]["xpos"] = slots[number][0]
        payload["minimap"][key]["ypos"] = slots[number][1]
    out = read(payload)
    assert out.split_rule == "lane pairs"
    assert out.complete
