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

**The `team` field is not usable.** Every object in every recording says
`team 2`, with the player on Dire in one and Radiant in another. Constant,
so it distinguishes nothing.

**The lane positions ARE the check, and refusing is the point.** The five
xpos/ypos values are strategy-map lane slots, and each holds exactly one
hero from each run — one of yours, one of theirs. A third recording has all
five pairs consistent; the second has two positions holding both heroes
from the SAME run, which cannot happen if the runs are teams. This was
briefly read as "positions are lane assignments, so drop the check". That
was backwards: the contradiction is the data saying the run split is wrong
for that payload, and the honest response is to produce nothing. A wrong
line-up is worse than none, because the app then advises against heroes on
your own team.

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
        entries.append((_index(key), name,
                        (obj.get("xpos"), obj.get("ypos"))))
    entries.sort()
    return entries


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

    matched, contradicted = _lane_pairs(names[:TEAM_SIZE], positions)
    if contradicted or matched != TEAM_SIZE:
        # The lane slots disagree with the run split. Whatever the runs
        # mean in this payload, they are not the two teams, and a wrong
        # line-up is worse than none: the app would advise against heroes
        # on the user's own side.
        out.notes.append(
            f"minimap line-up REFUSED: {matched} of {TEAM_SIZE} lane slots "
            f"back the split and {contradicted} contradict it, so these ten "
            "heroes cannot be split into teams from this payload")
        return out

    out.allies, out.enemies = allies, enemies
    out.notes.append("line-ups read from the minimap "
                     f"({matched} of {TEAM_SIZE} lane slots agree)")
    return out


def _lane_pairs(first_run: list[str],
                positions: dict[str, tuple]) -> tuple[int, int]:
    """(lane slots backing the run split, slots contradicting it).

    Each strategy-map slot should hold one hero from each run — one of
    yours and one of theirs. A slot holding two from the SAME run says the
    runs are not the teams, and outweighs any number of slots that agree.
    """
    run_one = set(first_run)
    slots: dict[tuple, list[str]] = {}
    for name, position in positions.items():
        if position in (None, ORIGIN, (None, None)):
            continue
        slots.setdefault(position, []).append(name)
    matched = contradicted = 0
    for names in slots.values():
        if len(names) != 2:
            contradicted += 1            # not a pair at all
        elif len({name in run_one for name in names}) == 2:
            matched += 1
        else:
            contradicted += 1
    return matched, contradicted
