"""Read both line-ups out of GSI's minimap block.

The `draft` block is empty in every payload ever recorded, and during
HERO_SELECTION the feed names no hero but your own. From STRATEGY_TIME the
minimap carries all ten, in a shape two recorded matches agree on
(`tests/fixtures/gsi/`):

  * Some objects sit at the origin, (0,0). Three of them are duplicates of
    the player's own hero, which also appears in its lane. But an origin
    entry is NOT always a duplicate: recording 4 has Sven there, in no
    other slot, because no lane had been chosen for it yet. Dropping every
    origin entry lost Sven and left nine heroes, so only origin entries
    whose hero appears elsewhere are dropped.
  * What remains is exactly ten objects in object order (`o3`…`o12` in one
    match, `o0`…`o12` minus the origin in the other), one per player, and
    they arrive as **two runs of five**.
  * Which run is yours is decided by **where your own hero is**. Nothing
    else identifies it.

**The `team` field is not usable.** Every object in every recording says
`team 2`, with the player on Dire in one and Radiant in another. Constant,
so it distinguishes nothing.

**The lane positions are NOT a check, and two attempts at using them as one
were wrong.** They are where each hero sits on the strategy map: your five
in the lanes you chose, theirs in the lanes you predicted. Nothing stops
two heroes from the same team sharing a lane, and recordings 2 and 4 both
do exactly that — pudge with axe, dragon knight with juggernaut. Requiring
the five slots to pair one-from-each-run passed on recordings 1 and 3 by
coincidence and refused 2 and 4 outright. It is gone for good.

What remains is the run split anchored on your own hero. It matches the
strategy screen itself, which has exactly two panels of five: CHOOSE YOUR
LANE and PREDICT ENEMY LANES. The guards are structural — ten heroes, all
distinct, all known, yours among them — and the session report prints the
reading so a wrong one is visible rather than silent.

Only STRATEGY_TIME is read. In TEAM_SHOWCASE and later the minimap holds
real units rather than strategy-map slots, and the object order means
something else: one recorded session produced a correct split at 16s and a
scrambled one at 43s from the same match. The caller latches the first
complete reading so a later payload cannot overwrite it.
"""

from dataclasses import dataclass, field

HERO_PREFIX = "npc_dota_hero_"
TEAM_SIZE = 5
ORIGIN = (0, 0)
STRATEGY_STATE = "STRATEGY_TIME"


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


def hero_entries(payload: dict, drop_origin: bool = True):
    """(object index, hero internal name, position) in object order.

    Origin entries whose hero is ALSO placed somewhere else are duplicates
    and are dropped — counting them makes ten heroes look like thirteen.
    An origin entry for a hero placed nowhere else is a real player with no
    lane chosen yet, and is kept: dropping it left one recording with nine.
    """
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
        entries.append((_index(key), name,
                        (obj.get("xpos"), obj.get("ypos"))))
    entries.sort()
    if not drop_origin:
        return entries
    placed = {name for _i, name, position in entries if position != ORIGIN}
    kept, seen = [], set()
    for index, name, position in entries:
        if position == ORIGIN and name in placed:
            continue                      # a duplicate of a placed hero
        if name in seen:
            continue                      # same hero at two origin slots
        seen.add(name)
        kept.append((index, name, position))
    return kept


def read_lineups(payload: dict, name_to_id: dict[str, int],
                 my_hero_id: int | None, game_state: str = "") -> Lineups:
    """Both teams from the minimap, or nothing with a reason why not."""
    out = Lineups()
    if STRATEGY_STATE not in str(game_state or ""):
        return out                       # only the strategy map is readable

    entries = hero_entries(payload)
    if not entries:
        return out
    names = [name for _i, name, _p in entries]
    positions = {name: position for _i, name, position in entries}

    if len(names) != 2 * TEAM_SIZE:
        out.notes.append(
            f"minimap carried {len(names)} placed heroes, not ten — too "
            "early in the phase for a full line-up")
        return out
    if len(set(names)) != len(names):
        out.notes.append(
            "minimap named the same hero twice among the ten placed — "
            "cannot tell the runs apart")
        return out

    ids = [name_to_id.get(name) for name in names]
    unknown = [name for name, hid in zip(names, ids) if hid is None]
    if unknown:
        out.notes.append("minimap named heroes this dataset does not know: "
                         + ", ".join(unknown))
        return out

    if my_hero_id is None:
        out.notes.append(
            "minimap has both line-ups but the feed has not said which hero "
            "is yours, so which five are your team is unknown")
        return out

    first, second = ids[:TEAM_SIZE], ids[TEAM_SIZE:]
    if my_hero_id in first:
        allies, enemies = first, second
    elif my_hero_id in second:
        allies, enemies = second, first
    else:
        out.notes.append(
            "minimap named ten heroes but not the one the feed says is "
            "yours — refusing to guess which five are your team")
        return out

    out.allies, out.enemies = allies, enemies
    out.notes.append("line-ups read from the minimap")
    return out
