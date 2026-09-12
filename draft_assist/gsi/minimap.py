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

**The pairing is corroborated; the TIE-BREAK is not, and is known wrong at
least once.** In one recording the screen resolved the same ten
independently (`vision/lineup.py`) and its split took exactly one hero
from each lane pair — the first confirmation of the pairing from a source
that knows nothing about it. But it disagreed with the index tie-break on
four of the five pairs: the screen put the player with the HIGHER-indexed
half of each pair, while an older recording has the player with the LOWER
half. Object index does not decide it, and no rule found so far does.

So for THAT case the halves are a coin flip that must be labelled:
`sides_certain` stays False, the note says which rule produced the split,
and the drag correction stays. What the pairing still buys is that the
teams come out 5-5 with one hero from each lane whichever way the coin
lands, so the app can no longer show a 4-1 team. **The screen settles it
outright when vision has a frame**; this is the fallback for when it does
not.

**AND ONE CASE IS NOW SETTLED OUTRIGHT** (`_split_by_strategy_slots`,
`tests/test_minimap_strategy_slots.py`), which is the first thing in this
module decided by evidence rather than offered. It came from a match whose
real teams the user named after seeing the app get them wrong: the ten
placed heroes were NOT two to a slot, so the reading fell back to object
order and swapped Hoodwink and Riki. FIVE of them stood on the canonical
lane slots, one each; the other five stood at real world coordinates,
clustered together — and the five on the slots were the player's team
exactly.

The mechanism is why this one can be asserted. The strategy screen draws
YOUR OWN team at the lanes your team chose, and has nothing to draw the
enemy from unless you predicted them, so they arrive at their positions in
the world. Predict them and the slots hold two apiece, which is every
earlier recording and which this rule declines, leaving that case to the
pairs unchanged. And it cannot invert — the fault every other rule here
has had — because the player's own hero must be among the five on the
slots, and a contradiction declines rather than handing back the halves
the other way round.

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
# THE FIVE STRATEGY-MAP LANE SLOTS, the same coordinates in every
# recording: the positions the strategy screen draws a chosen lane at.
# They are a coordinate space of their own - three-figure numbers, where a
# real world position runs to four - which is why a hero standing on one
# can be told from a hero standing where it actually is.
LANE_SLOTS = frozenset({(176, -370), (176, 370),
                        (752, -144), (752, 144), (1088, 0)})


@dataclass
class Lineups:
    allies: list[int] = field(default_factory=list)
    enemies: list[int] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    # WHICH ten heroes is solid. WHICH FIVE ARE YOURS depends on the rule
    # that produced the split: "strategy slots" is decided and sets this
    # True, and the other two are offered and labelled, never asserted,
    # because a real match came out inverted under object order.
    sides_certain: bool = False
    # "strategy slots", "lane pairs" or "object order" — which rule
    # produced the split, so the session report can grade them against
    # each other.
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
    # THE STRATEGY SLOTS FIRST, because that one is decided rather than
    # offered. See `_split_by_strategy_slots`.
    split = _split_by_strategy_slots(entries, by_id, my_hero_id)
    how = "strategy slots"
    if split is None:
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
    if how == "strategy slots":
        out.sides_certain = True
        out.notes.append(
            "ten heroes read from the minimap, split by the strategy map — "
            "five stand on its lane slots and five at their own world "
            "positions, and the five on the slots are yours")
    elif how == "lane pairs":
        out.notes.append(
            "ten heroes read from the minimap, split by the five strategy-"
            "map lane slots — each holds one of yours and one of theirs, "
            "so the teams cannot come out 4-1. WHICH half of each pair is "
            "yours is a coin flip this cannot call: check the top row and "
            "drag heroes across if it is reversed")
    else:
        out.notes.append(
            "ten heroes read from the minimap, but they did not fall into "
            "five lane pairs, so the split fell back to object order — "
            "that has come out INVERTED on a real match, so check it and "
            "drag heroes across if it is wrong")
    return out


def _split_by_strategy_slots(entries, by_id: dict[str, int],
                             my_hero_id: int
                             ) -> tuple[list[int], list[int]] | None:
    """Your five and theirs, when the strategy map drew only your own.

    THIS IS THE ONE RULE HERE THAT IS DECIDED RATHER THAN OFFERED, and it
    came from a match whose real teams the user named. The ten placed
    heroes were NOT two to a lane slot, which is what `_split_by_lane_
    pairs` needs, so the reading fell back to object order and put
    Hoodwink and Riki on the wrong sides. The positions say why:

        axe          (1088,    0)     riki           (3968, -2885)
        storm_spirit ( 176, -370)     grimstroke     (3740, -2972)
        juggernaut   ( 752, -144)     snapfire       (3865, -3513)
        rubick       ( 176,  370)     nyx_assassin   (3917, -3175)
        hoodwink     ( 752,  144)     winter_wyvern  (3634, -2526)

    Five stand on the canonical lane slots, one each; five stand at real
    world coordinates, clustered where they actually are. The left column
    is the player's team exactly — Rubick, their own hero, among them —
    and the right column is the enemy.

    The mechanism is what makes this safe to assert where the pairs
    cannot be. The strategy screen draws YOUR OWN team at the lanes your
    team chose; it has nothing to draw the enemy from unless you predicted
    them, so they come through at their positions in the world. When you
    DO predict them the slots hold two apiece and this declines, leaving
    that case to `_split_by_lane_pairs` exactly as before.

    And it cannot invert, which is the fault every earlier rule here had.
    If the halves were the other way round the player's own hero would be
    in the off-slot five — so that is checked, and a contradiction
    declines rather than asserting the opposite.
    """
    on_slots, off_slots = [], []
    for index, name, position in entries:
        where = on_slots if tuple(position) in LANE_SLOTS else off_slots
        where.append((index, by_id[name]))
    if len(on_slots) != TEAM_SIZE or len(off_slots) != TEAM_SIZE:
        return None
    mine = [hid for _i, hid in on_slots]
    if my_hero_id not in mine:
        return None                      # the premise is wrong; do not guess
    return (mine, [hid for _i, hid in off_slots])


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
