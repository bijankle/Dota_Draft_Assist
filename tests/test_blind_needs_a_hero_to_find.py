"""Hero selection opens with an EMPTY pick bar.

Reading no hero then is the correct answer, not a fault - this
repository's own notes say exactly that about two screenshots that
"failed to locate": their bar was empty, "so locating nothing is the
CORRECT answer". `_blind_run` charged it as blindness anyway, so the
quiet opening of a slow draft read as the app being broken and raised
a bug-report banner over a draft that had gone fine.

Reported as: "ive got a feeling it is nuisance tripping ... it
shouldn't think this is a problem that needs flagging."
"""

from draft_assist import bugreport


def ticks(rows):
    """`at`, `game_state`, `has_frame`, `allies`, `read_heroes`."""
    out = []
    for at, allies, read in rows:
        out.append({"at": at,
                    "game_state": "DOTA_GAMERULES_STATE_HERO_SELECTION",
                    "has_frame": True,
                    "allies": list(allies),
                    "enemies": [],
                    "read_heroes": read})
    return out


def test_an_empty_bar_is_not_blindness():
    """Sixty seconds of hero selection before anybody has locked in."""
    quiet = ticks([(float(t), [], 0) for t in range(0, 61)])
    assert bugreport._blind_run(quiet) == 0.0


def test_a_bar_with_your_own_hero_on_it_and_nothing_read_is():
    """You have locked in, so a portrait is certainly on the bar."""
    blind = ticks([(float(t), ["Tiny"], 0) for t in range(0, 61)])
    assert bugreport._blind_run(blind) >= bugreport.BLIND_SECONDS


def test_the_quiet_opening_is_not_charged_to_the_stretch_after_it():
    """The empty opening must not be glued onto a real blind run - it is
    the difference between 'over the floor' and 'well under it'."""
    rows = [(float(t), [], 0) for t in range(0, 40)]          # empty bar
    rows += [(float(t), ["Tiny"], 0) for t in range(40, 50)]  # 10s blind
    run = bugreport._blind_run(ticks(rows))
    assert run < bugreport.BLIND_SECONDS, run
    assert 8 <= run <= 11, run


def test_reading_a_hero_ends_the_stretch():
    rows = [(float(t), ["Tiny"], 0) for t in range(0, 10)]
    rows += [(float(t), ["Tiny"], 3) for t in range(10, 60)]
    assert bugreport._blind_run(ticks(rows)) < bugreport.BLIND_SECONDS


def test_no_frame_is_still_not_blindness():
    """Capture failing and recognition failing are different bugs."""
    rows = ticks([(float(t), ["Tiny"], 0) for t in range(0, 61)])
    for row in rows:
        row["has_frame"] = False
    assert bugreport._blind_run(rows) == 0.0


def test_a_real_draft_that_went_wrong_still_reports():
    """The fault this exists for: a ranked game that read two of ten
    slots for eighty seconds, with the player's hero long since locked."""
    rows = ticks([(float(t), ["Tiny"], 0) for t in range(0, 81)])
    assert bugreport._blind_run(rows) >= 79
