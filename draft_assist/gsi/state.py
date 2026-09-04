"""Turn a raw GSI payload into draft state.

WHAT GSI ACTUALLY PROVIDES IS NOT ASSUMED HERE. Valve documents GSI thinly,
and the components a payload carries differ between playing and spectating:
a player's own feed reliably carries provider/map/player/hero/items, while
`draft` (and buildings, minimap, roshan, couriers) are understood to be
spectator/observer components. That means GSI most likely CANNOT see the
enemy team's picks in an ordinary ranked All Pick game.

So this parser extracts what is present, records what is missing, and never
invents a value. `GsiState.capabilities` reports exactly which blocks the
live game sent, `tools/probe_gsi.py` archives real payloads, and the UI
shows the verdict — the question is settled with evidence, not memory.

Hero identity is resolved through the dataset's own internal names
("npc_dota_hero_antimage"), never a hardcoded table.
"""

import time
from dataclasses import dataclass, field

# Game states Dota reports; the draft happens in HERO_SELECTION.
STATE_HERO_SELECTION = "DOTA_GAMERULES_STATE_HERO_SELECTION"
STATE_STRATEGY = "DOTA_GAMERULES_STATE_STRATEGY_TIME"
STATE_PREGAME = "DOTA_GAMERULES_STATE_PRE_GAME"
STATE_IN_PROGRESS = "DOTA_GAMERULES_STATE_GAME_IN_PROGRESS"
DRAFTING_STATES = {STATE_HERO_SELECTION, STATE_STRATEGY}

# Components a player's own feed is expected to carry; anything else is
# reported as spectator-only when absent, rather than treated as an error.
PLAYER_COMPONENTS = ("provider", "map", "player", "hero")
SPECTATOR_COMPONENTS = ("draft", "buildings", "minimap", "roshan",
                        "couriers", "neutralitems")


def _hero_id_by_internal_name(dataset) -> dict[str, int]:
    return {info.get("internal_name", ""): hid
            for hid, info in dataset.heroes.items()
            if info.get("internal_name")}


@dataclass
class GsiState:
    received_at: float = 0.0
    game_state: str = ""
    match_id: str = ""
    my_team: str = ""                  # "radiant" | "dire" | ""
    my_name: str = ""                  # Steam persona, as the game reports it
    my_hero_id: int | None = None
    my_hero_name: str = ""
    allies: list[int] = field(default_factory=list)
    enemies: list[int] = field(default_factory=list)
    capabilities: dict[str, bool] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)

    @property
    def drafting(self) -> bool:
        return self.game_state in DRAFTING_STATES

    @property
    def in_game(self) -> bool:
        return bool(self.game_state)

    @property
    def has_full_draft(self) -> bool:
        """True only when GSI really did hand us both line-ups. Until a real
        payload proves otherwise this is expected to be False for a player's
        own match."""
        return len(self.allies) + len(self.enemies) >= 9

    def summary(self) -> str:
        if not self.game_state:
            return "connected, no match in progress"
        bits = [self.game_state.replace("DOTA_GAMERULES_STATE_", "")]
        if self.my_name:
            bits.append(self.my_name)
        if self.my_hero_name:
            bits.append(f"you: {self.my_hero_name}")
        if self.my_team:
            bits.append(self.my_team)
        picks = len(self.allies) + len(self.enemies)
        bits.append(f"{picks} picks visible")
        return " · ".join(bits)


def describe_capabilities(payload: dict) -> dict[str, bool]:
    keys = set(payload or {})
    return {name: name in keys
            for name in PLAYER_COMPONENTS + SPECTATOR_COMPONENTS}


def _team_of(player_block: dict) -> str:
    name = str(player_block.get("team_name", "")).lower()
    return name if name in ("radiant", "dire") else ""


def _collect_draft_picks(draft: dict, name_to_id: dict[str, int],
                         notes: list[str]) -> dict[str, list[int]]:
    """Pull picks out of the spectator `draft` block if it is present.

    Its shape is team2/team3 (Dota's internal team numbers: 2 = Radiant,
    3 = Dire) with pick0_id/pick0_class entries. Both id and class are read,
    because which of them is populated has varied.
    """
    out: dict[str, list[int]] = {"radiant": [], "dire": []}
    for key, side in (("team2", "radiant"), ("team3", "dire")):
        block = draft.get(key)
        if not isinstance(block, dict):
            continue
        for slot in range(5):
            hero_id = block.get(f"pick{slot}_id")
            hero_class = block.get(f"pick{slot}_class")
            resolved = None
            if isinstance(hero_id, int) and hero_id > 0:
                resolved = hero_id
            elif isinstance(hero_class, str) and hero_class:
                resolved = name_to_id.get(hero_class)
                if resolved is None:
                    notes.append(f"unknown hero class {hero_class!r} in draft "
                                 f"{key} slot {slot}")
            if resolved is not None:
                out[side].append(resolved)
    return out


def parse(payload: dict, dataset) -> GsiState:
    """Extract everything the payload genuinely contains. Missing data is
    recorded in notes, never fabricated."""
    state = GsiState(received_at=time.monotonic())
    if not isinstance(payload, dict):
        state.notes.append("payload was not an object")
        return state

    state.capabilities = describe_capabilities(payload)
    name_to_id = _hero_id_by_internal_name(dataset)

    map_block = payload.get("map")
    if isinstance(map_block, dict):
        state.game_state = str(map_block.get("game_state", ""))
        state.match_id = str(map_block.get("matchid", ""))

    player_block = payload.get("player")
    # Spectating gives player/hero keyed by team and slot; playing gives a
    # single object. Handle the flat case and note the nested one.
    if isinstance(player_block, dict):
        name = player_block.get("name")
        if isinstance(name, str):
            state.my_name = name
        if _team_of(player_block):
            state.my_team = _team_of(player_block)
        elif any(k.startswith("team") for k in player_block):
            state.notes.append(
                "player block is keyed by team (spectator feed)")

    hero_block = payload.get("hero")
    if isinstance(hero_block, dict) and "id" in hero_block:
        hero_id = hero_block.get("id")
        if isinstance(hero_id, int) and hero_id > 0:
            state.my_hero_id = hero_id
            state.my_hero_name = dataset.name(hero_id)
        elif isinstance(hero_block.get("name"), str):
            resolved = name_to_id.get(hero_block["name"])
            if resolved:
                state.my_hero_id = resolved
                state.my_hero_name = dataset.name(resolved)

    draft_block = payload.get("draft")
    if isinstance(draft_block, dict):
        picks = _collect_draft_picks(draft_block, name_to_id, state.notes)
        side = state.my_team or "radiant"
        other = "dire" if side == "radiant" else "radiant"
        state.allies = picks[side]
        state.enemies = picks[other]
        if not state.my_team and (picks["radiant"] or picks["dire"]):
            state.notes.append(
                "team unknown, assuming Radiant is your side — set it in "
                "the app if the sides are swapped")
    else:
        state.notes.append(
            "no 'draft' block in this payload: GSI is not reporting the "
            "line-ups (expected for a player's own match — the draft block "
            "is a spectator component)")

    # Your own locked hero is a pick even when no draft block exists.
    if state.my_hero_id and state.my_hero_id not in state.allies:
        state.allies = [state.my_hero_id] + state.allies

    return state
