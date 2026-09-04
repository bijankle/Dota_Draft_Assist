"""Synthetic Game State Integration payloads, for testing without Dota.

This drives the REAL ingestion path — HTTP listener, auth check, parser,
provider, UI — rather than injecting state into the UI directly, which is
what `--demo` does. Every bug in this area so far (auth token mismatch, port
sharing, a stale status bar) lived in that plumbing, so a test that skips it
would have caught none of them.

Two fidelities, and the difference matters:

  MODELLED (all_pick_scenario) — payloads shaped the way this codebase
  believes Dota's look. Useful and repeatable, but it is our own belief
  echoed back, so it cannot discover that a real field is named or
  structured differently.

  RECORDED (replay_scenario) — real payloads archived by tools/probe_gsi.py
  and replayed verbatim. Strictly better evidence, and the only kind that
  can contradict us. Prefer it once any exist.
"""

import json
from dataclasses import dataclass, field
from pathlib import Path

from . import state as gsi_state

# Fallback hero ids/classes used when no dataset has been downloaded, so the
# simulator still works on a fresh install.
FALLBACK_HEROES = [
    (1, "npc_dota_hero_antimage"), (2, "npc_dota_hero_axe"),
    (5, "npc_dota_hero_crystal_maiden"), (8, "npc_dota_hero_juggernaut"),
    (11, "npc_dota_hero_nevermore"), (14, "npc_dota_hero_pudge"),
    (22, "npc_dota_hero_zuus"), (25, "npc_dota_hero_lina"),
    (26, "npc_dota_hero_lion"), (41, "npc_dota_hero_faceless_void"),
]


def describe_payload(payload: dict) -> str:
    """Describe what a payload ACTUALLY contains.

    Labels are derived here rather than written by the scenario builder,
    because a label that describes intent instead of content is worse than
    no label: an earlier version announced "picking (4 allies, 4 enemies)"
    while sending payloads with no draft block at all, which made a correct
    app look broken and sent the reader hunting a bug that did not exist.
    """
    state = (payload.get("map") or {}).get("game_state", "")
    parts = [state.replace("DOTA_GAMERULES_STATE_", "").replace("_", " ").title()
             or "no game state"]

    hero = payload.get("hero")
    parts.append(f"your hero: {hero.get('name', '?')}"
                 if isinstance(hero, dict) and hero.get("name")
                 else "your hero: none yet")

    draft = payload.get("draft")
    if isinstance(draft, dict):
        counted = {}
        for key, side in (("team2", "radiant"), ("team3", "dire")):
            block = draft.get(key) or {}
            counted[side] = sum(
                1 for slot in range(5)
                if block.get(f"pick{slot}_id") or block.get(f"pick{slot}_class"))
        parts.append(f"draft block: {counted['radiant']} radiant, "
                     f"{counted['dire']} dire")
    else:
        parts.append("no draft block (as a player's own feed behaves)")
    return " · ".join(parts)


@dataclass
class Step:
    delay: float          # seconds to wait before sending this payload
    payload: dict
    label: str


def _heroes(dataset, count: int = 10) -> list[tuple[int, str]]:
    """(hero_id, internal_name) pairs, from real data when available."""
    if dataset is not None and not dataset.is_empty:
        pairs = [(hid, dataset.heroes[hid].get("internal_name", ""))
                 for hid in dataset.hero_ids
                 if dataset.heroes[hid].get("internal_name")]
        if len(pairs) >= count:
            step = max(1, len(pairs) // count)
            return pairs[::step][:count]
    return FALLBACK_HEROES[:count]


def _base(game_state: str, my_hero: tuple[int, str] | None,
          match_id: str = "8123456789", token: str | None = None) -> dict:
    payload: dict = {
        "provider": {"name": "Dota 2", "appid": 570, "version": 47,
                     "timestamp": 1700000000},
        "map": {"name": "start", "matchid": match_id,
                "game_time": 0, "clock_time": 0, "daytime": True,
                "game_state": game_state, "win_team": "none"},
        "player": {"steamid": "76561190000000000", "name": "tester",
                   "activity": "playing", "team_name": "radiant",
                   "kills": 0, "deaths": 0, "assists": 0},
    }
    if my_hero is not None:
        payload["hero"] = {"id": my_hero[0], "name": my_hero[1],
                           "level": 1, "alive": True, "health_percent": 100}
    if token:
        payload["auth"] = {"token": token}
    return payload


def all_pick_scenario(dataset=None, token: str | None = None,
                      include_draft_block: bool = False,
                      speed: float = 1.0) -> list[Step]:
    """A ranked All Pick match, menu through to running.

    include_draft_block adds the spectator-style `draft` component, which a
    player's own feed is NOT expected to carry. Turn it on to rehearse what
    the app does IF that turns out to be wrong; leave it off for the
    behaviour we actually expect.
    """
    heroes = _heroes(dataset, 10)
    mine, allies, enemies = heroes[0], heroes[1:5], heroes[5:10]

    def scaled(seconds: float) -> float:
        return seconds / max(speed, 0.01)

    steps: list[Step] = []

    def add(delay, game_state, hero, picked_allies=(), picked_enemies=()):
        payload = _base(game_state, hero, token=token)
        if include_draft_block:
            payload["draft"] = {
                "activeteam": 2, "pick": True,
                "team2": {f"pick{i}_id": h[0]
                          for i, h in enumerate(picked_allies)},
                "team3": {f"pick{i}_id": h[0]
                          for i, h in enumerate(picked_enemies)},
            }
        steps.append(Step(scaled(delay), payload, describe_payload(payload)))

    # Hero selection: picks land one at a time, ours partway through.
    add(0.0, gsi_state.STATE_HERO_SELECTION, None)
    for i in range(1, 5):
        add(2.0, gsi_state.STATE_HERO_SELECTION, None,
            picked_allies=allies[:i], picked_enemies=enemies[:i])
    add(2.0, gsi_state.STATE_HERO_SELECTION, mine,
        picked_allies=[mine] + allies, picked_enemies=enemies)

    add(3.0, gsi_state.STATE_STRATEGY, mine,
        picked_allies=[mine] + allies, picked_enemies=enemies)
    add(3.0, gsi_state.STATE_PREGAME, mine,
        picked_allies=[mine] + allies, picked_enemies=enemies)

    # The running payload must carry the same draft block as the rest, or
    # the line-up would vanish the moment the game starts — the flag has to
    # mean the same thing for every step it produces.
    add(4.0, gsi_state.STATE_IN_PROGRESS, mine,
        picked_allies=[mine] + allies, picked_enemies=enemies)
    running = steps[-1].payload
    running["map"]["clock_time"] = 120
    running["items"] = {"slot0": {"name": "item_tango", "can_cast": True}}
    steps[-1] = Step(steps[-1].delay, running, describe_payload(running))
    return steps


def replay_scenario(directory: Path, token: str | None = None,
                    delay: float = 0.5) -> list[Step]:
    """Real payloads archived by tools/probe_gsi.py, replayed in order.

    The auth token is rewritten to the current one, since the archive was
    recorded under whatever token was installed at the time.
    """
    paths = sorted(Path(directory).glob("gsi_*.json"))
    if not paths:
        raise FileNotFoundError(
            f"no archived payloads in {directory} — record some first with "
            "Game > Record game data")
    steps = []
    for path in paths:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(payload, dict):
            continue
        if token:
            payload["auth"] = {"token": token}
        elif "auth" in payload:
            payload.pop("auth")
        steps.append(Step(delay, payload,
                          f"{path.name} · {describe_payload(payload)}"))
    if not steps:
        raise ValueError(f"no readable payloads in {directory}")
    return steps
