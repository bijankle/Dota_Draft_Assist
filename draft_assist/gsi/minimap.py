"""Read both line-ups out of GSI's minimap block.

The `draft` block is empty in every payload ever recorded from a player's
own match, and during HERO_SELECTION the feed names no hero at all — not
even your own. But once the game reaches STRATEGY_TIME the minimap carries
all ten heroes, and a real payload (`tests/fixtures/gsi/`) shows they arrive
in two runs of five in object order, with your own hero in one of them:

    o0 silencer  o1..o4 rubick  o5 windrunner  o6 abaddon  o7 gyrocopter
    o8 nevermore o9 viper       o10 zuus       o11 sniper  o12 marci

    distinct, in order: silencer rubick windrunner abaddon gyrocopter |
                        nevermore viper zuus sniper marci

The `team` field is NOT usable: every object in that payload says team 2
while the player was on Dire. The positions are, though — the five distinct
xpos/ypos values each hold exactly one hero from each run, which is what a
lane-by-lane strategy map looks like. So the grouping is checked against the
positions before it is believed.

This is inference from observed structure, not something Valve documents, so
every assumption is verified per payload and a failed check yields NOTHING
rather than a guess. Which run is yours is decided by where your own hero
is — never assumed.
"""

from dataclasses import dataclass, field

HERO_PREFIX = "npc_dota_hero_"
TEAM_SIZE = 5
# Lane positions that must back the run-of-five split before it is
# believed. Not all five: the player's own hero can sit unplaced at
# the origin, and a lane can be unassigned.
MIN_CONFIRMING_POSITIONS = 3


@dataclass
class Lineups:
    allies: list[int] = field(default_factory=list)
    enemies: list[int] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    @property
    def complete(self) -> bool:
        return len(self.allies) == TEAM_SIZE and len(self.enemies) == TEAM_SIZE


def _index(key: str) -> int:
    """'o10' -> 10, so o2 sorts before o10 rather than after it."""
    digits = "".join(c for c in key if c.isdigit())
    return int(digits) if digits else -1


def hero_entries(payload: dict) -> list[tuple[int, str, tuple]]:
    """(object index, hero internal name, position) in object order."""
    block = payload.get("minimap")
    if not isinstance(block, dict):
        return []
    entries = []
    for key, obj in block.items():
        if not isinstance(obj, dict):
            continue
        name = obj.get("unitname") or obj.get("name")
        if not isinstance(name, str) or not name.startswith(HERO_PREFIX):
            continue
        entries.append((_index(key), name, (obj.get("xpos"), obj.get("ypos"))))
    entries.sort()
    return entries


def read_lineups(payload: dict, name_to_id: dict[str, int],
                 my_hero_id: int | None) -> Lineups:
    """Both teams from the minimap, or nothing with a reason why not."""
    out = Lineups()
    entries = hero_entries(payload)
    if not entries:
        return out

    order: list[str] = []
    positions: dict[str, tuple] = {}
    for _i, name, position in entries:
        if name not in order:
            order.append(name)
        # Prefer a real position over the origin, where unplaced entries
        # sit: the player's own hero appears at (0,0) three times before it
        # appears in its lane, and taking the first would lose the one
        # pairing that proves the split.
        if positions.get(name) in (None, (0, 0), (None, None)):
            positions[name] = position

    if len(order) != 2 * TEAM_SIZE:
        out.notes.append(
            f"minimap named {len(order)} distinct heroes, not ten — not "
            "enough to read a line-up from")
        return out

    ids = [name_to_id.get(name) for name in order]
    unknown = [name for name, hid in zip(order, ids) if hid is None]
    if unknown:
        out.notes.append("minimap named heroes this dataset does not know: "
                         + ", ".join(unknown))
        return out
    if len(set(ids)) != len(ids):
        out.notes.append("minimap named the same hero twice — cannot split")
        return out

    first, second = ids[:TEAM_SIZE], ids[TEAM_SIZE:]
    if my_hero_id is None:
        out.notes.append(
            "minimap has both line-ups but the feed has not said which hero "
            "is yours, so which five are your team is unknown")
        return out
    if my_hero_id in first:
        out.allies, out.enemies = first, second
    elif my_hero_id in second:
        out.allies, out.enemies = second, first
    else:
        out.notes.append(
            "minimap named ten heroes but not the one the feed says is "
            "yours — refusing to guess which five are your team")
        return out

    # The two runs should pair off across five lane positions. If they do
    # not, the run-of-five reading is not what this payload is doing.
    paired, contradicted = _pairs_across(order, positions)
    if contradicted == 0 and paired >= MIN_CONFIRMING_POSITIONS:
        out.notes.append(f"line-ups read from the minimap ({paired} of "
                         f"{TEAM_SIZE} lane positions confirm the split)")
    else:
        out.allies, out.enemies = [], []
        out.notes.append(
            f"minimap named ten heroes but only {paired} lane positions "
            f"back the split and {contradicted} contradict it, so which "
            "five are your team is unclear — enter them by hand")
    return out


def _pairs_across(order: list[str],
                  positions: dict[str, tuple]) -> tuple[int, int]:
    """(positions backing the split, positions contradicting it).

    A lane position should hold one hero from each run of five. A position
    holding two heroes from the SAME run says the runs are not teams, which
    is worth more than any number of positions that merely agree — so both
    are counted and a single contradiction is disqualifying.

    Heroes parked at the origin are ignored: that is where unplaced entries
    sit in the recorded payload.
    """
    first = set(order[:TEAM_SIZE])
    buckets: dict[tuple, list[str]] = {}
    for name in order:
        position = positions.get(name)
        if position in (None, (0, 0), (None, None)):
            continue
        buckets.setdefault(position, []).append(name)
    matched = contradicted = 0
    for names in buckets.values():
        if len(names) != 2:
            continue
        if len({name in first for name in names}) == 2:
            matched += 1
        else:
            contradicted += 1
    return matched, contradicted
