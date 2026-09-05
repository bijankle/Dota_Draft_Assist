"""Read both line-ups out of GSI's minimap block.

The `draft` block is empty in every payload ever recorded, and during
HERO_SELECTION the feed names no hero but your own. From STRATEGY_TIME the
minimap carries all ten, in a shape two recorded matches agree on
(`tests/fixtures/gsi/`):

  * Some objects sit at the origin, (0,0). They are always duplicates of the
    player's own hero — three of them in both recordings — and carry no
    information. They are dropped first, before anything is counted.
  * What remains is exactly ten objects in object order (`o3`…`o12` in one
    match, `o0`…`o12` minus the origin in the other), one per player, and
    they arrive as **two runs of five**.
  * Which run is yours is decided by **where your own hero is**. Nothing
    else identifies it.

Two things that look like signal and are not:

  * **The `team` field.** Every object in both recordings said `team 2`,
    once while the player was on Dire and once on Radiant. It is constant,
    so it distinguishes nothing.
  * **The lane positions.** An earlier version verified the split by
    pairing heroes across the five xpos/ypos values, and reported "5 of 5
    confirm". That was a coincidence of the first match: in the second,
    (176,-370) holds pudge AND axe, both from the same run, because a lane
    can hold two heroes from one team. Positions are lane assignments, not
    ally/enemy pairs, and the check has been removed rather than left to
    reject good data.

So the guards are the ones that hold in both recordings: exactly ten
non-origin objects, exactly ten distinct heroes, all resolvable, and the
player's own hero in exactly one run. A failed check yields NOTHING rather
than a guess.
"""

from dataclasses import dataclass, field

HERO_PREFIX = "npc_dota_hero_"
TEAM_SIZE = 5
ORIGIN = (0, 0)


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
    """(object index, hero internal name) in object order.

    Origin entries are dropped by default: they are duplicates of your own
    hero and counting them makes ten objects look like thirteen.
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
        if drop_origin and (obj.get("xpos"), obj.get("ypos")) == ORIGIN:
            continue
        entries.append((_index(key), name))
    entries.sort()
    return entries


def read_lineups(payload: dict, name_to_id: dict[str, int],
                 my_hero_id: int | None) -> Lineups:
    """Both teams from the minimap, or nothing with a reason why not."""
    out = Lineups()
    names = [name for _index, name in hero_entries(payload)]
    if not names:
        return out

    if len(names) != 2 * TEAM_SIZE:
        out.notes.append(
            f"minimap carried {len(names)} placed heroes, not ten — too "
            "early in the phase, or not the shape this reads")
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
        out.allies, out.enemies = first, second
    elif my_hero_id in second:
        out.allies, out.enemies = second, first
    else:
        out.notes.append(
            "minimap named ten heroes but not the one the feed says is "
            "yours — refusing to guess which five are your team")
        return out
    out.notes.append("line-ups read from the minimap")
    return out
