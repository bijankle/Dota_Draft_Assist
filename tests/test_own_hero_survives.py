"""Your own hero must not vanish when the screen starts reading.

Reported from a real draft, match 8996474799. The user was first pick:

     5.6s  HERO_SELECTION  none    allies=Rubick
    17.3s  HERO_SELECTION  screen  allies=Disruptor        <- Rubick GONE
    33.3s  HERO_SELECTION  screen  allies=Disruptor, Rubick

"I was first pick, it showed me, and then after the 2nd pick on our team
it disappeared." Rubick came back sixteen seconds later, when recognition
happened to see the portrait too — a quarter of the draft with the user's
own hero missing from the board the app exists to show.

During HERO_SELECTION the feed names exactly ONE hero, yours, and that is
not a line-up — so `lineup_source` is empty, the "the game told us
outright" guard does not fire, and the screen's partial reading replaced
it wholesale.
"""

import sys
import types
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from draft_assist.ui import providers

RUBICK, DISRUPTOR, GRIMSTROKE, EARTHSHAKER = 86, 87, 121, 7


def a_read(radiant, dire):
    """Just enough DraftRead for the screen path."""
    return types.SimpleNamespace(
        team_ids=lambda team: list(radiant if team == "radiant" else dire),
        unknown_count=lambda: 10 - len(radiant) - len(dire),
        slots=[])


def a_screen(radiant, dire):
    return types.SimpleNamespace(
        read=a_read(radiant, dire), read_raw=None, frame=None,
        gate_score=0.4, stalled=False, frames_arrived=1, warning="",
        mode="draft")


@pytest.fixture()
def hybrid():
    hub = providers.HybridProvider.__new__(providers.HybridProvider)
    hub.forced = False
    hub.manual = providers.ManualDraft()
    import threading
    hub._search_lock = threading.Lock()
    hub._search_running = None
    hub._search_at = 0.0
    hub.vision = object()
    return hub


def a_snapshot(left, right, my_team="radiant"):
    return providers.Snapshot(
        left=list(left), right=list(right), my_team=my_team,
        sides_known=True, lineup_source="",
        game_state="DOTA_GAMERULES_STATE_HERO_SELECTION")


def read_with_screen(hybrid, snap, radiant, dire):
    """Run just the screen half of `poll` against a prepared snapshot."""
    return hybrid._add_screen(snap, a_screen(radiant, dire))


def test_the_reported_bug_does_not_happen(hybrid):
    """The exact sequence, with the heroes from that draft."""
    # 5.6s — the game has named you and the screen has seen nothing.
    snap = a_snapshot([RUBICK], [])
    out = read_with_screen(hybrid, snap, [], [])
    assert out.left == [RUBICK], "lost before the screen even read"

    # 17.3s — the screen sees the SECOND pick and not yours.
    snap = a_snapshot([RUBICK], [])
    out = read_with_screen(hybrid, snap, [DISRUPTOR], [])
    assert RUBICK in out.left, "your own hero vanished when a team-mate picked"
    assert DISRUPTOR in out.left

    # 33.3s — the screen catches up. No duplicate.
    snap = a_snapshot([RUBICK], [])
    out = read_with_screen(hybrid, snap, [DISRUPTOR, RUBICK], [])
    assert sorted(out.left) == sorted([RUBICK, DISRUPTOR])


def test_the_game_comes_FIRST_then_the_screen(hybrid):
    """The order `merge` already uses, one source deeper."""
    snap = a_snapshot([RUBICK], [])
    out = read_with_screen(hybrid, snap, [DISRUPTOR], [GRIMSTROKE])
    assert out.left[0] == RUBICK
    assert out.right == [GRIMSTROKE]


def test_a_hero_the_game_calls_yours_is_never_on_the_other_side(hybrid):
    """Recognition can put a portrait in the wrong bank; the feed saying
    which hero is YOURS cannot be wrong about that. So the enemy list
    gives way rather than the board showing one hero twice."""
    snap = a_snapshot([RUBICK], [])
    out = read_with_screen(hybrid, snap, [DISRUPTOR], [RUBICK, GRIMSTROKE])
    assert RUBICK in out.left
    assert RUBICK not in out.right, "the same hero on both teams"
    assert GRIMSTROKE in out.right


def test_the_screen_alone_still_works(hybrid):
    """With nothing from the game — vision-only, or before you lock in —
    the screen is the whole answer and says so."""
    snap = a_snapshot([], [])
    out = read_with_screen(hybrid, snap, [DISRUPTOR], [GRIMSTROKE])
    assert out.left == [DISRUPTOR]
    assert out.right == [GRIMSTROKE]
    assert out.lineup_source == "screen"


def test_the_source_says_both_were_used(hybrid):
    """A reading built from two sources must not claim to be one: the
    status line is how a wrong pick is traced to what produced it."""
    snap = a_snapshot([RUBICK], [])
    out = read_with_screen(hybrid, snap, [DISRUPTOR], [])
    assert out.lineup_source == "game data + screen"


def test_a_complete_game_lineup_still_wins_outright(hybrid):
    """The "never blended" rule is untouched where it applies: two
    COMPLETE answers disagreeing must not be averaged into a third."""
    snap = a_snapshot([1, 2, 3, 4, 5], [6, 7, 8, 9, 10])
    snap.lineup_source = "minimap"
    snap.sides_certain = True
    out = read_with_screen(hybrid, snap, [99], [98])
    assert out.left == [1, 2, 3, 4, 5]
    assert 99 not in out.left


# --------------------------------------------------------------------
# A RECIPE IS NOT A CANDIDATE FOR AN ITEM ICON.
#
# "Why is there no picture for Eul's? Is there any other item that
# doesn't have an image?" Valve publishes the scroll that builds an item
# as an item of its own, so "Eul's Scepter" is a prefix of BOTH "Eul's
# Scepter of Divinity" and "Eul's Scepter Recipe" - two matches, refused
# as ambiguous, which is the resolver working as designed and still
# drawing no icon. Checked against the whole rules file: it was the only
# one of the 24 items named that could not resolve.


def test_a_recipe_never_wins_or_blocks_an_item_icon(monkeypatch):
    from draft_assist.ui import item_icons
    monkeypatch.setattr(item_icons, "_slugs", lambda: {
        item_icons.slug("Eul's Scepter of Divinity"),
        item_icons.slug("Eul's Scepter Recipe"),
        item_icons.slug("Black King Bar"),
    })
    got = item_icons._resolve("Eul's Scepter")
    assert got == item_icons.slug("Eul's Scepter of Divinity"), got


def test_two_REAL_items_are_still_refused(monkeypatch):
    """The guard this is narrowing must survive: "Boots" would otherwise
    silently draw Boots of Travel, and drawing the wrong item is worse
    than drawing the name."""
    from draft_assist.ui import item_icons
    monkeypatch.setattr(item_icons, "_slugs", lambda: {
        item_icons.slug("Boots of Speed"),
        item_icons.slug("Boots of Travel"),
    })
    assert item_icons._resolve("Boots") is None


def test_an_exact_name_still_wins_outright(monkeypatch):
    from draft_assist.ui import item_icons
    monkeypatch.setattr(item_icons, "_slugs", lambda: {
        item_icons.slug("Black King Bar"),
        item_icons.slug("Black King Bar Recipe"),
    })
    assert item_icons._resolve("Black King Bar") == item_icons.slug(
        "Black King Bar")
