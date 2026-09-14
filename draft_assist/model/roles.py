"""Valve's own role ratings, summed per team.

**THE NUMBERS ARE THE GAME'S, NOT OURS.** Dota's `npc_heroes.txt` scores
every hero 0 to 3 on each role — the same figures the hero-selection UI
draws its bars from — as two parallel fields:

    "Role"          "Support,Disabler,Nuker,Initiator"
    "Rolelevels"    "2,3,3,2"

That is the whole datum. Nothing here rates a hero; this module adds up
what the game already says and normalises it so two half-drafted teams can
be compared.

**EIGHT ROLES, NOT NINE, and that is measured rather than assumed.**
JUNGLER is in every list of Dota's roles anybody writes down and it is
**not in Valve's data**: it appears ZERO times across the whole of
`npc_heroes.txt`, and OpenDota's `constants/heroes`, which is built
independently, lists the same eight. The jungle role was removed from the
game and the metadata went with it. A ninth column would be a permanent
run of zeros under a heading, which says "no hero in Dota junglse" rather
than "Valve stopped scoring this".

**THE SHARE IS OUT OF WHAT COULD HAVE BEEN PICKED**, which is what makes
a 2v5 board readable: three picks can score at most 9 on any one role, so
a team on 6 of 9 reads the same as a full team on 10 of 15. Comparing the
raw sums instead would say the team with more picks is better at
everything, which is true and useless.

**A HERO WITH NO ROLE DATA IS LEFT OUT OF BOTH HALVES.** It is the rule
unknown slots already follow — silent about one hero beats wrong about
one hero — and the alternative is worse than it looks: counting a hero we
have no figures for as a zero in the numerator while it still raises the
denominator reports a team as WORSE at every role for having picked it.
A hero added in a patch before this file is next cut is exactly that case.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

# Valve's own column order, minus the role Valve no longer scores.
ROLES: tuple[str, ...] = ("Carry", "Support", "Nuker", "Disabler",
                          "Durable", "Escape", "Pusher", "Initiator")

# The top of Valve's scale. A pick can contribute at most this to one role.
MAX_LEVEL = 3

# How many pills a share is drawn as. Five, at the user's request.
PILLS = 5

BUNDLED = Path(__file__).with_name("hero_roles.json")

_levels: dict[int, dict[str, int]] | None = None


def _load() -> dict[int, dict[str, int]]:
    """Read the bundled table once.

    Keys come back as INTS. The file is JSON, so its keys are strings,
    and every caller here holds a hero id as a number — a map keyed by
    strings would miss every lookup silently and the table would draw
    empty with nothing anywhere saying why. Same trap as the item names.
    """
    global _levels
    if _levels is None:
        try:
            raw = json.loads(BUNDLED.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            raw = {}
        _levels = {int(k): {r: int(v) for r, v in levels.items() if r in ROLES}
                   for k, levels in raw.items()}
    return _levels


def levels_for(hero_id: int) -> dict[str, int]:
    """This hero's rating on each of the eight roles, 0 where unrated."""
    have = _load().get(int(hero_id))
    if have is None:
        return {}
    return {role: int(have.get(role, 0)) for role in ROLES}


def known(hero_id: int) -> bool:
    return int(hero_id) in _load()


@dataclass(frozen=True)
class RoleScore:
    """One role, for one team."""
    role: str
    scored: int          # the levels this team's picks actually carry
    possible: int        # MAX_LEVEL per rated pick
    rated: int           # how many of the picks had figures at all

    @property
    def share(self) -> float:
        return self.scored / self.possible if self.possible else 0.0

    @property
    def pills(self) -> int:
        """The share as whole pills, rounded to the nearest one."""
        return int(round(self.share * PILLS))


def team_scores(hero_ids) -> list[RoleScore]:
    """Every role for one side, in Valve's column order."""
    rated = [hid for hid in hero_ids if known(hid)]
    possible = MAX_LEVEL * len(rated)
    out = []
    for role in ROLES:
        scored = sum(levels_for(hid).get(role, 0) for hid in rated)
        out.append(RoleScore(role=role, scored=scored, possible=possible,
                             rated=len(rated)))
    return out


def compare(ours: list[RoleScore],
            theirs: list[RoleScore]) -> list[int]:
    """+1 where the first side leads that role, -1 where it trails, 0 level.

    A side with nothing rated has no share to compare, so every role is
    level rather than a clean sweep for whoever picked first.
    """
    out = []
    for mine, yours in zip(ours, theirs):
        if not mine.possible or not yours.possible:
            out.append(0)
            continue
        gap = mine.share - yours.share
        out.append(0 if abs(gap) < 1e-9 else (1 if gap > 0 else -1))
    return out
