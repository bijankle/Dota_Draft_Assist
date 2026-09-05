"""Read both line-ups out of GSI's minimap block.

The `draft` block is empty in every payload ever recorded, and during
HERO_SELECTION the feed names no hero but your own. From STRATEGY_TIME the
minimap carries all ten, in a shape two recorded matches agree on
(`tests/fixtures/gsi/`):

  * The heroes that matter are the ones PLACED in a lane slot. Ten placed
    is the whole line-up and the origin is then ignored entirely.
  * Objects at the origin, (0,0), are a mixed bag and must not be trusted:
    duplicates of the player's own hero, and — in recording 6 — Faceless
    Void, which was in no lane and not in the match at all (a hovered pick,
    or a leftover). Keeping every origin entry that was not placed
    elsewhere gave ELEVEN heroes and refused a perfectly good line-up.
  * They are only drawn on when fewer than ten are placed, which happens
    when a player has chosen no lane (recording 4's Sven, nine placed).
    Then origin-only heroes are added in object order until exactly ten,
    and if that cannot land on exactly ten the reading is refused.
  * What remains is exactly ten objects in object order (`o3`…`o12` in one
    match, `o0`…`o12` minus the origin in the other), one per player, and
    they arrive as **two runs of five**.
  * Which run is yours is decided by **where your own hero is**. Nothing
    else identifies it.

**The `team` field is not usable.** Every object in every recording says
`team 2`, with the player on Dire in one and Radiant in another. Constant,
so it distinguishes nothing.

**The lane positions ARE structure, which reverses an earlier conclusion in
this file.** Across all five recordings the placed heroes occupy exactly
five distinct positions — `(176,-370)`, `(176,370)`, `(752,-144)`,
`(752,144)`, `(1088,0)` — and each holds exactly TWO heroes. That is the
strategy map: your five in the lanes you chose, theirs in the lanes you
predicted, so a slot holds one of yours and one of theirs.

An earlier attempt tested this as "the pairs must straddle the run
boundary", and it failed on recordings 2 and 4. Both failures are now
explained without the pairing being wrong: recording 4 had only NINE placed
(one player chose no lane), so one slot held a single hero and no pairing
could straddle anything; and recording 2's pairs disagree with the RUN
split, which is evidence against the runs, not against the pairs. The note
above about "pudge with axe, dragon knight with juggernaut" being
team-mates was read off the run split — the very thing in question — so it
never was evidence.

**So the split is now taken from the pairs**: group the ten by position,
order each pair by object index, and the set holding the player's own hero
is the player's team. Two things this buys that the runs never could — it
cannot produce a 4-1 team, since every slot contributes exactly one hero
to each side, and it degrades honestly, falling back to the runs when the
positions do not pair cleanly.

**It is still NOT verified against a labelled match.** The pairing itself
is solid across five recordings; which HALF of each pair is yours rests on
object-index order being consistent between slots, and nothing has proved
that. So `Lineups.sides_certain` stays False, the note says which rule
produced the split, and the UI keeps the drag correction. A wrong line-up
asserted silently is the worst outcome available, because the app then
advises against the user's own team. The screen settles it outright when
vision has a frame (`vision/lineup.py`); this is the fallback for when it
does not.

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
    # WHICH ten heroes is solid. WHICH FIVE ARE YOURS IS NOT: a real match
    # came out inverted — the run holding the player's own hero was the
    # other team. Until a signal is found that settles it, the split is
    # offered and labelled, never asserted, and the UI can flip it.
    sides_certain: bool = False
    # "lane pairs" or "object order" — which rule produced the split, so
    # the session report can grade one against the other.
    split_rule: str = ""

    @property
    def complete(self) -> bool:
        return len(self.allies) == TEAM_SIZE and len(self.enemies) == TEAM_SIZE


def _index(key: str) -> int:
    """'o10' -> 10, so o2 sorts before o10 rather than after it."""
    digits = "".join(c for c in key if c.isdigit())
    return int(digits) if digits else -1


def hero_entries(payload: dict, drop_origin: bool = True):
    """(object index, hero internal name, position) in object order.

    Placed heroes first, in object order. Origin entries are drawn on only
    to make up a short line-up: they hold duplicates of your own hero AND,
    in one recording, a hero that was not in the match, so trusting them
    when ten heroes are already placed turned a good reading into eleven.
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

    kept, seen = [], set()
    for index, name, position in entries:
        if position == ORIGIN or name in seen:
            continue
        seen.add(name)
        kept.append((index, name, position))
    if len(kept) >= 2 * TEAM_SIZE:
        return kept
    # Short: a player with no lane chosen sits at the origin. Take those in
    # object order, but only enough to reach ten -- the origin also holds
    # heroes that are not in the match.
    for index, name, position in entries:
        if position != ORIGIN or name in seen:
            continue
        seen.add(name)
        kept.append((index, name, position))
        if len(kept) == 2 * TEAM_SIZE:
            break
    kept.sort()
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

    by_id = dict(zip(names, ids))
    split = _split_by_lane_pairs(entries, by_id)
    how = "lane pairs"
    if split is None:
        split = (ids[:TEAM_SIZE], ids[TEAM_SIZE:])
        how = "object order"

    first, second = split
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
    out.split_rule = how
    if how == "lane pairs":
        out.notes.append(
            "ten heroes read from the minimap, split by the five strategy-"
            "map lane slots — each slot holds one of yours and one of "
            "theirs, so the teams cannot come out 4-1. Which half of each "
            "pair is yours is not yet verified against a known match: "
            "check it once and drag a hero across if it is wrong")
    else:
        out.notes.append(
            "ten heroes read from the minimap, but they did not fall into "
            "five lane pairs, so the split fell back to object order — "
            "that has come out INVERTED on a real match, so check it and "
            "drag heroes across if it is wrong")
    return out


def _split_by_lane_pairs(entries, by_id: dict[str, int]
                         ) -> tuple[list[int], list[int]] | None:
    """Two candidate teams from the strategy map's lane slots.

    Ten heroes standing in exactly five positions, two to a position, is
    the strategy map: your five where you put them, theirs where you
    predicted. Ordering each pair by object index and taking one from each
    gives two sets of five that cannot be 4-1 whatever else is wrong.

    Returns None — not a guess — when the positions do not pair cleanly,
    which is what a short line-up looks like (one recording had nine placed
    because a player chose no lane).
    """
    slots: dict[tuple, list[tuple[int, str]]] = {}
    for index, name, position in entries:
        slots.setdefault(position, []).append((index, name))
    if len(slots) != TEAM_SIZE:
        return None
    if any(len(members) != 2 for members in slots.values()):
        return None
    lower, upper = [], []
    for members in slots.values():
        members.sort()
        lower.append((members[0][0], by_id[members[0][1]]))
        upper.append((members[1][0], by_id[members[1][1]]))
    # Each side back into object order. The slots are a set, so iterating
    # them would order the teams by whichever lane happened to be seen
    # first — object order at least matches what every other reading here
    # uses, and it is what the screen will overwrite anyway.
    lower.sort()
    upper.sort()
    return ([hid for _i, hid in lower], [hid for _i, hid in upper])
