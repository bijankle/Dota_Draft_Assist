"""Two faults, from twelve reported drafts.

THE SIDE READING WAS REFUSED BY A GAP COUNT. Across those twelve the
screen failed to settle the sides seven times, and in three of them the
boxes were provably ON the bar - "9 of the ten matched in the calibrated
boxes, so the boxes are on the pick bar" and then "2 gaps look like the
split between banks; this frame is probably not a pick bar". A missed
portrait leaves a hole, the boundary between banks is a bigger one, and
`split_banks` refused whenever BOTH cleared its threshold. Which of them
is the boundary is not a matter of degree: only one cuts the bar into
banks of five.

AND THE COIN FLIP OVERWROTE A GOOD SCREEN READING. Reported as:
"sometimes at the end when drafting phase is over and everyone is locked
in, the app gets 1 person on each team and switches them to the other
team." On 2026-10-10 the screen had allies Snapfire, Pudge, Mars,
Phantom Lancer, Crystal Maiden at 22.4s; the minimap replaced them with
Snapfire, Queen of Pain, Juggernaut, Necrophos, Undying at 35.0s.
"""

from dataclasses import dataclass

import pytest

from draft_assist.vision.lineup import TEAM_SIZE, split_banks


@dataclass
class Found:
    x: int
    hero_id: int


def bar(xs):
    return [Found(x=x, hero_id=i + 1) for i, x in enumerate(xs)]


# A measured 16:9 pick bar: pitch 166px, the banks 4.87 pitches apart.
PITCH = 166
GAP = int(4.87 * PITCH)


def full_bar(missing=None):
    xs, x = [], 0
    for slot in range(2 * TEAM_SIZE):
        if slot == TEAM_SIZE:
            x += GAP
        elif slot:
            x += PITCH
        if slot != missing:
            xs.append(x)
    return bar(xs)


# ---- the gap rule ----------------------------------------------------

def test_a_complete_bar_splits_five_a_side():
    split, why = split_banks(full_bar())
    assert why == "" and split == TEAM_SIZE


@pytest.mark.parametrize("missing", range(10))
def test_one_missed_portrait_still_splits(missing):
    """THE BUG. A hole and the bank boundary are both "wide"; only one of
    them gives five a side. Refusing on the count threw the frame away."""
    split, why = split_banks(full_bar(missing))
    assert why == "", f"missing slot {missing}: {why}"
    expected = TEAM_SIZE - 1 if missing < TEAM_SIZE else TEAM_SIZE
    assert split == expected


def test_a_bar_that_cannot_be_five_a_side_is_still_refused():
    """The 2/7 split a real recording reported. Nothing here cuts the bar
    into banks the pick bar could have, so it is refused as before."""
    xs = [0, PITCH, PITCH + GAP]
    xs += [xs[-1] + PITCH * (i + 1) for i in range(6)]
    split, why = split_banks(bar(xs))
    assert split == -1
    assert "five a side" in why


def test_two_gaps_that_would_both_work_are_refused():
    """Genuine ambiguity still declines rather than inventing a boundary.

    It takes NINE portraits to build: with ten, only one cut can be five
    a side, so the shape itself resolves it. With nine, 4/5 and 5/4 are
    both possible bars and nothing here can choose."""
    xs = [0, PITCH, 2 * PITCH, 3 * PITCH]
    xs.append(xs[-1] + GAP)
    xs.append(xs[-1] + GAP)
    xs += [xs[-1] + PITCH * (i + 1) for i in range(3)]
    split, why = split_banks(bar(xs))
    assert split == -1, why
    assert "five a side" in why


def test_a_bar_with_no_wide_gap_is_refused():
    split, why = split_banks(bar([i * PITCH for i in range(10)]))
    assert split == -1 and "cannot be told apart" in why


# ---- the coin flip that overwrote the screen -------------------------

from types import SimpleNamespace                            # noqa: E402

from draft_assist.ui.providers import GsiProvider, HybridProvider  # noqa: E402
from draft_assist.data import store                          # noqa: E402

# 2026-10-10_130922, by hero id (the ids themselves do not matter, only
# which side each ends up on).
SNAPFIRE, QOP, JUGG, NECRO, UNDYING = 1, 2, 3, 4, 5
AA, PUDGE, PL, CM, MARS = 6, 7, 8, 9, 10

SCREEN_ALLIES = [SNAPFIRE, PUDGE, MARS, PL, CM]      # read at 22.4s
SCREEN_ENEMIES = [NECRO, AA, JUGG, UNDYING]
MINIMAP_ALLIES = [SNAPFIRE, QOP, JUGG, NECRO, UNDYING]   # the coin flip, 35.0s
MINIMAP_ENEMIES = [AA, PUDGE, PL, CM, MARS]


def a_hybrid():
    gsi = GsiProvider(store.empty_dataset(), server=None)
    return HybridProvider(gsi, vision=None)


def a_snap(**over):
    snap = SimpleNamespace(
        left=list(MINIMAP_ALLIES), right=list(MINIMAP_ENEMIES),
        lineup_source="minimap", sides_certain=False, my_team="radiant",
        my_hero_id=SNAPFIRE, match_id="9037542115", source="", gsi_notes=[])
    for key, value in over.items():
        setattr(snap, key, value)
    return snap


def remembering(hybrid):
    for hero in SCREEN_ALLIES:
        hybrid._screen_side[hero] = "ally"
    for hero in SCREEN_ENEMIES:
        hybrid._screen_side[hero] = "enemy"
    return hybrid


def test_the_screen_beats_the_coin_flip():
    """THE REPORTED FAULT. Four of five heroes moved to the enemy team
    when strategy time arrived, over a screen reading that had them
    right."""
    hybrid = remembering(a_hybrid())
    snap = a_snap()
    hybrid._orient_by_memory(snap)
    assert sorted(snap.left) == sorted(SCREEN_ALLIES)
    assert snap.sides_certain is True
    assert snap.lineup_source == "minimap+screen"


def test_the_hero_the_screen_never_saw_fills_the_gap():
    """Queen of Pain was picked after the screen stopped reading, so she
    is the one hero the memory cannot place - and the only seat left is
    on the enemy team."""
    hybrid = remembering(a_hybrid())
    snap = a_snap()
    hybrid._orient_by_memory(snap)
    assert QOP in snap.right


def test_nothing_happens_without_a_memory():
    hybrid = a_hybrid()
    snap = a_snap()
    hybrid._orient_by_memory(snap)
    assert snap.left == MINIMAP_ALLIES
    assert snap.sides_certain is False


def test_it_declines_rather_than_moving_your_own_hero():
    """A hero the GAME calls yours is never on the other side - that
    outranks the screen, as it does everywhere else."""
    hybrid = a_hybrid()
    for hero in SCREEN_ALLIES:
        hybrid._screen_side[hero] = "enemy"
    for hero in SCREEN_ENEMIES:
        hybrid._screen_side[hero] = "ally"
    snap = a_snap()
    hybrid._orient_by_memory(snap)
    assert SNAPFIRE in snap.left


def test_it_declines_when_the_screen_contradicts_itself():
    hybrid = a_hybrid()
    for hero in MINIMAP_ALLIES + MINIMAP_ENEMIES[:1]:
        hybrid._screen_side[hero] = "ally"       # six allies: impossible
    snap = a_snap()
    hybrid._orient_by_memory(snap)
    assert snap.left == MINIMAP_ALLIES
    assert snap.sides_certain is False


def test_it_says_nothing_when_the_minimap_already_agreed():
    """No note, no source change, when there was nothing to correct."""
    hybrid = a_hybrid()
    for hero in MINIMAP_ALLIES:
        hybrid._screen_side[hero] = "ally"
    for hero in MINIMAP_ENEMIES:
        hybrid._screen_side[hero] = "enemy"
    snap = a_snap()
    hybrid._orient_by_memory(snap)
    assert snap.lineup_source == "minimap"
    assert snap.gsi_notes == []


def test_a_new_match_forgets_the_last_draft():
    hybrid = remembering(a_hybrid())
    hybrid._match = "9037542115"
    hybrid._new_match(SimpleNamespace(match_id="9037542116"))
    assert hybrid._screen_side == {}
