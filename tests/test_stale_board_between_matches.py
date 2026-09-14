"""The previous match's ten heroes, on screen for nine seconds of a new draft.

Reported from a real session: at 0.0s of the recording for match
8000000001 the board carried a full ten from the game before it, and held
them for nine seconds - which is the first pick of the new draft, made
against advice about a board that no longer existed.

The screen's picks live on the capture session, which forgets them after
FORGET_AFTER (30s) of not-the-draft-screen. That timer says in its own
comment what it is a proxy for - "thirty seconds of not-the-draft-screen
is a different game" - and the match id is that answer outright. So the
provider forgets the reading when the id changes, and the timer stays as
the answer for when there is no game feed to say so.
"""

import pytest

from draft_assist.ui.providers import HybridProvider, Snapshot
from draft_assist.vision.recognize import DraftRead


class Session:
    """Only the half `forget_reading` touches."""

    def __init__(self):
        self.forgotten = 0
        self.layout = None

    def forget_reading(self):
        self.forgotten += 1


class Vision:
    def __init__(self):
        self.session = Session()
        self.next = Snapshot()

    def set_required(self, required):
        pass

    def poll(self):
        return self.next


class Gsi:
    def __init__(self, manual):
        self.manual = manual
        self.next = Snapshot()

    def poll(self):
        return self.next


@pytest.fixture
def provider():
    from draft_assist.ui.manual import ManualDraft
    gsi = Gsi(ManualDraft())
    return HybridProvider(gsi, Vision())


def tick(provider, match_id, game_state="DOTA_GAMERULES_STATE_HERO_SELECTION"):
    provider.gsi.next = Snapshot(match_id=match_id, game_state=game_state)
    return provider.poll()


def test_the_first_match_of_a_session_forgets_nothing(provider):
    tick(provider, "8000000001")
    tick(provider, "8000000001")
    assert provider.vision.session.forgotten == 0, (
        "there is no previous board to be stale")


def test_a_new_match_forgets_the_previous_boards_picks(provider):
    tick(provider, "8000000002")
    assert provider.vision.session.forgotten == 0
    tick(provider, "8000000001")
    assert provider.vision.session.forgotten == 1


def test_it_happens_once_per_match_not_once_per_tick(provider):
    tick(provider, "8000000002")
    for _ in range(20):
        tick(provider, "8000000001")
    assert provider.vision.session.forgotten == 1, (
        "forgetting on every tick would delete a reading as fast as it "
        "was made")


def test_dotas_zero_is_not_a_match(provider):
    """Dota reports matchid 0 outside a match; `summary` already filters
    it. Treating it as a new match would wipe the board between every
    payload that arrived in a menu."""
    tick(provider, "8000000002")
    tick(provider, "0", game_state="DOTA_GAMERULES_STATE_POST_GAME")
    tick(provider, "8000000002")
    assert provider.vision.session.forgotten == 0


def test_a_blank_id_is_dota_saying_nothing(provider):
    tick(provider, "8000000002")
    tick(provider, "", game_state="")
    tick(provider, "8000000002")
    assert provider.vision.session.forgotten == 0


def test_a_session_with_no_forget_reading_does_not_raise(provider):
    """The vision half is optional and is duck-typed everywhere else here."""
    provider.vision.session = object()
    tick(provider, "8000000002")
    tick(provider, "8000000001")


def test_the_capture_session_really_drops_the_read():
    """The provider's half is wired to something that does the work."""
    from draft_assist.capture.session import CaptureSession
    session = CaptureSession.__new__(CaptureSession)
    session.state = type("S", (), {})()
    session.state.last_read = DraftRead(slots=[])
    session.state.last_read_raw = DraftRead(slots=[])
    session._stabilizer = type("Z", (), {"reset": lambda self: None})()
    session.forget_reading()
    assert session.state.last_read is None
    assert session.state.last_read_raw is None
