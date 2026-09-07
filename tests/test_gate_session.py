"""Gate and capture-session state machine, exercised entirely with injected
synthetic frames — no Windows, no Dota."""

import time

import numpy as np
import pytest

from draft_assist.capture import gate
from draft_assist.capture import session as session_mod
from draft_assist.capture.session import (CaptureSession, MISSES_TO_DEACTIVATE,
                                          STABLE_CONFIRMS, TRIPS_TO_ACTIVATE)
from draft_assist.proving.evaluate import build_library_from_images
from draft_assist.proving.synth import (Distortions, empty_slot_image,
                                        generate_case,
                                        procedural_portrait_set)
from draft_assist.vision.layout import DraftLayout
from draft_assist.vision.library import EMPTY_SLOT, RecognitionParams


@pytest.fixture(scope="module")
def draft_frame():
    portraits = procedural_portrait_set(126)
    layout = DraftLayout()
    rng = np.random.default_rng(21)
    case = generate_case(portraits, layout, rng, resolution=(1920, 1080),
                         distort=Distortions(jitter_frac=0.0, dim_chance=0),
                         fill_range=(10, 10))
    return case.frame


@pytest.fixture()
def menu_frame():
    rng = np.random.default_rng(4)
    return rng.integers(60, 200, (1080, 1920, 3), dtype=np.uint8)


def make_session():
    portraits = procedural_portrait_set(126)
    lib = build_library_from_images(
        portraits, 8, extra={EMPTY_SLOT: [empty_slot_image()]})
    return CaptureSession(DraftLayout(),
                          lib, RecognitionParams(8, 0.30, 0.04))


def tick_now(session):
    session._next_tick = 0.0
    return session.tick()


def test_gate_separates_draft_from_menu(draft_frame, menu_frame):
    refs = [gate.signature(draft_frame)]
    assert gate.score(draft_frame, refs) < 0.02
    assert gate.score(menu_frame, refs) > gate.DEFAULT_THRESHOLD
    assert gate.is_draft_screen(draft_frame, refs)
    assert not gate.is_draft_screen(menu_frame, refs)


def test_gate_reference_roundtrip(tmp_path, draft_frame):
    assert gate.load_references(tmp_path) == []
    assert gate.save_reference(draft_frame, tmp_path) is not None
    refs = gate.load_references(tmp_path)
    assert len(refs) == 1
    assert gate.score(draft_frame, refs) < 0.05
    # Near duplicate is not stored twice.
    assert gate.save_reference(draft_frame, tmp_path) is None


def test_session_activates_and_reads(draft_frame, menu_frame):
    session = make_session()
    session._refs = [gate.signature(draft_frame)]
    session.inject_frame(draft_frame)
    for _ in range(TRIPS_TO_ACTIVATE):
        state = tick_now(session)
    assert state.mode == "active"
    # Raw read resolves on the first recognised frame; the published read
    # needs STABLE_CONFIRMS agreeing frames before it follows.
    state = tick_now(session)
    assert state.last_read_raw is not None
    assert 10 - state.last_read_raw.unknown_count() >= 8
    for _ in range(STABLE_CONFIRMS):
        state = tick_now(session)
    assert 10 - state.last_read.unknown_count() >= 8

    session.inject_frame(menu_frame)
    for _ in range(MISSES_TO_DEACTIVATE):
        state = tick_now(session)
    assert state.mode == "idle"
    # The reading SURVIVES the drop to idle. Four missed gate checks is
    # four seconds, and a pick does not un-pick in four seconds — wiping it
    # here is what deleted every hero the app had read mid-draft.
    assert state.last_read is not None
    assert 10 - state.last_read.unknown_count() >= 8


def test_a_reading_is_forgotten_once_the_screen_is_long_gone(draft_frame,
                                                             menu_frame):
    """Kept across a wobble, dropped when it is a different game.

    Thirty seconds of not-the-draft-screen is not a draft any more, so the
    reading has to expire — otherwise last game's picks greet the next one.
    """
    session = make_session()
    session._refs = [gate.signature(draft_frame)]
    session.inject_frame(draft_frame)
    for _ in range(TRIPS_TO_ACTIVATE + STABLE_CONFIRMS + 1):
        tick_now(session)
    assert session.state.last_read is not None

    session.inject_frame(menu_frame)
    for _ in range(MISSES_TO_DEACTIVATE):
        tick_now(session)
    assert session.state.mode == "idle"
    session.set_required(False)         # the game says no, so no probing
    session._idle_since = time.monotonic() - session_mod.FORGET_AFTER - 1
    state = tick_now(session)
    assert state.last_read is None and state.last_read_raw is None


def test_manual_override_forces_recognition_without_gate(draft_frame):
    session = make_session()   # no gate references at all
    # The game says no draft is on, which switches the probe off — this is
    # about the manual override beating the gate, nothing else.
    session.set_required(False)
    session.inject_frame(draft_frame)
    state = tick_now(session)
    assert state.mode == "idle" and state.last_read is None
    session.set_forced(True)
    state = tick_now(session)
    assert state.last_read is not None  # recognition ran despite failed gate


def test_confirmed_draft_bootstraps_gate_reference(tmp_path, monkeypatch,
                                                   draft_frame):
    monkeypatch.setattr(gate, "GATE_DIR", tmp_path)
    session = make_session()
    session.set_forced(True)
    session.inject_frame(draft_frame)
    tick_now(session)
    # Recognition resolved the frame, so a gate reference now exists and the
    # gate can work on its own next draft.
    refs = gate.load_references(tmp_path)
    assert refs and gate.is_draft_screen(draft_frame, refs)


def make_read(values):
    from draft_assist.vision.layout import DraftLayout
    from draft_assist.vision.recognize import DraftRead, SlotRead
    rects = DraftLayout().slots()
    return DraftRead(slots=[
        SlotRead(rect=r, hero_id=v, best_label="t", distance=5, margin=10)
        for r, v in zip(rects, values)])


def test_stabilizer_debounces_flicker():
    from draft_assist.capture.session import SlotStabilizer
    st = SlotStabilizer(confirms=3)
    base = [None] * 10
    # A single-frame phantom must never surface.
    seq = [7] + [None] * 5
    for v in seq:
        out = st.update(make_read([v] + base[1:]))
    assert out.slots[0].hero_id is None
    # Three consecutive identical reads publish the value.
    for _ in range(3):
        out = st.update(make_read([7] + base[1:]))
    assert out.slots[0].hero_id == 7
    # Later unknowns (hover overlay) never un-pick it.
    out = st.update(make_read([None] + base[1:]))
    assert out.slots[0].hero_id == 7
    # Alternating values never accumulate confirmations.
    for _ in range(6):
        st.update(make_read([1] + base[1:]))
        out = st.update(make_read([2] + base[1:]))
    assert out.slots[0].hero_id == 7


def test_stabilizer_allows_stable_correction():
    from draft_assist.capture.session import SlotStabilizer
    st = SlotStabilizer(confirms=3)
    base = [None] * 10
    for _ in range(3):
        st.update(make_read([7] + base[1:]))
    # A persistent different value (real correction) does replace it.
    for _ in range(3):
        out = st.update(make_read([9] + base[1:]))
    assert out.slots[0].hero_id == 9


def test_session_publishes_stable_read_and_raw_read(draft_frame):
    session = make_session()
    session.set_forced(True)
    session.inject_frame(draft_frame)
    state = tick_now(session)
    # Raw read resolves immediately; stabilised read needs confirmations.
    assert state.last_read_raw is not None
    resolved_raw = 10 - state.last_read_raw.unknown_count()
    assert resolved_raw >= 8
    assert state.last_read.unknown_count() == 10  # not yet confirmed
    for _ in range(2):
        state = tick_now(session)
    assert 10 - state.last_read.unknown_count() == resolved_raw


class FakeSession:
    """Stands in for CaptureSession without Windows Graphics Capture."""

    def __init__(self, works=("Dota 2",)):
        self.works = set(works)
        self.capture_title = None
        self.state = None
        self.forced = False

    def start(self, title=None):
        if title is None:
            title = "Dota 2" if "Dota 2" in self.works else None
        if title is None:
            raise RuntimeError("No window titled exactly 'Dota 2' is open\n"
                               "Visible windows:\n  Firefox")
        if title not in self.works:
            raise RuntimeError(f"cannot capture '{title}'")
        self.capture_title = title
        return title

    def stop(self):
        pass

    def set_forced(self, forced):
        self.forced = forced

    def tick(self):
        from draft_assist.capture.session import SessionState
        return SessionState()


def test_live_provider_survives_missing_dota_window():
    from draft_assist.ui.providers import LiveProvider
    prov = LiveProvider(FakeSession(works=()))
    message = prov.start()          # must not raise
    assert "not bound" in message
    assert prov.error
    snap = prov.poll()
    assert "waiting for the Dota window" in snap.source
    assert snap.warning


def test_live_provider_rebinds_to_chosen_window():
    from draft_assist.ui.providers import LiveProvider
    prov = LiveProvider(FakeSession(works=("Dota 2", "OBS")))
    assert "Dota 2" in prov.start()
    msg = prov.rebind("OBS")
    assert "OBS" in msg and not prov.error
    # Capturing anything other than the client is loudly flagged, because a
    # wrong source looks exactly like broken recognition.
    snap = prov.poll()
    assert "NOT the Dota client" in snap.warning


def test_live_provider_reports_failed_rebind_without_raising():
    from draft_assist.ui.providers import LiveProvider
    prov = LiveProvider(FakeSession(works=("Dota 2",)))
    prov.start()
    msg = prov.rebind("Some Other Window")
    assert "not bound" in msg and prov.error


def test_find_dota_window_never_guesses_a_lookalike(monkeypatch):
    from draft_assist.capture import window
    monkeypatch.setattr(window, "list_window_titles",
                        lambda: ["Dota 2 draft guide - YouTube — Firefox"])
    # A browser tab is NOT the client: binding it silently is what made
    # recognition look broken.
    assert window.find_dota_window_title() is None
    assert window.dota_like_titles() == [
        "Dota 2 draft guide - YouTube — Firefox"]
    monkeypatch.setattr(window, "list_window_titles",
                        lambda: ["Firefox", "Dota 2"])
    assert window.find_dota_window_title() == "Dota 2"


def test_maintenance_tasks_are_well_formed():
    """Each menu task must name real scripts and resolve {py} to this venv."""
    import sys
    from pathlib import Path

    from draft_assist.config import REPO_ROOT
    from draft_assist.ui.tasks import PY, TASKS, Task, TaskWorker

    for key, task in TASKS.items():
        assert isinstance(task, Task) and task.key == key
        assert task.steps and task.blurb
        worker = TaskWorker(task)
        for step in task.steps:
            argv = worker._argv(step)
            assert PY not in argv           # placeholder fully resolved
            if argv[0] == sys.executable and argv[1] not in ("-m", "-u"):
                assert (REPO_ROOT / argv[1]).exists(), argv[1]


# ---- the game outranks the gate ----------------------------------------

def test_a_wrong_gate_no_longer_blocks_recognition(draft_frame, menu_frame):
    """The gate is a guess about pixels, and its references are harvested
    from whichever screen confirmed first. One real session sat at 0.707
    against a 0.50 threshold for the whole of hero selection and recognised
    nothing until every pick was already in — while GSI was reporting
    HERO_SELECTION the entire time."""
    session = make_session()
    # References that do NOT describe this screen: the gate will refuse.
    session._refs = [gate.signature(menu_frame)]
    session.set_required(False)          # the game says no: the gate rules
    session.inject_frame(draft_frame)
    state = tick_now(session)
    assert state.gate_score > gate.DEFAULT_THRESHOLD
    assert state.mode == "idle"
    assert state.last_read is None, "the gate should have refused this"

    # The game says a draft is happening, so the guess does not get a vote.
    session.set_required(True)
    state = tick_now(session)
    assert state.last_read_raw is not None
    assert 10 - state.last_read_raw.unknown_count() >= 8


def test_a_silent_feed_probes_past_a_wrong_gate(draft_frame, menu_frame):
    """With GSI down the gate is the only vote, so it must not be the last.

    Its references are harvested from frames recognition confirmed, which
    makes a wrong gate self-sustaining: it never runs the recognition that
    would correct it. One real ranked game read four heroes in two seconds,
    missed four gate checks, went idle, and never looked again for the
    remaining twenty — with the draft still on screen. A probe every few
    seconds is the way out, and the library disagreeing with the gate
    inside the calibrated boxes is better evidence than the gate.
    """
    session = make_session()
    session._refs = [gate.signature(menu_frame)]
    assert session.state.required is None, "silence is the default"
    session.inject_frame(draft_frame)
    state = tick_now(session)
    assert state.gate_score > gate.DEFAULT_THRESHOLD, "the gate said no"
    assert state.last_read_raw is not None, "and the probe went anyway"
    assert 10 - state.last_read_raw.unknown_count() >= 8
    assert state.mode == "active", "the library outvoted the gate"


def test_a_probe_is_occasional_not_every_tick(draft_frame, menu_frame):
    """It is the expensive path, so it runs once per PROBE_PERIOD."""
    session = make_session()
    session._refs = [gate.signature(draft_frame)]   # gate agrees: no probe
    session.inject_frame(menu_frame)
    tick_now(session)                               # spends the first probe
    before = session._next_probe
    assert before > time.monotonic()
    tick_now(session)
    assert session._next_probe == before, "a second probe came too soon"


def test_the_frame_is_published_even_while_idle(menu_frame):
    """It used to be set only when recognition ran, so a session that never
    tripped the gate reported `frame=none` and the debug view had nothing
    to show — exactly when a picture is what you need to see why."""
    session = make_session()
    session.inject_frame(menu_frame)
    state = tick_now(session)
    assert state.mode == "idle"
    assert state.last_frame is not None


def test_the_gate_still_works_when_nothing_is_required(draft_frame,
                                                       menu_frame):
    """It is an economiser and it still earns its keep — with the game feed
    off or silent, the pixels are all there is."""
    session = make_session()
    session._refs = [gate.signature(draft_frame)]
    session.set_required(False)     # the GAME says no, which is an answer
    session.inject_frame(menu_frame)
    for _ in range(MISSES_TO_DEACTIVATE + 1):
        tick_now(session)
    assert session.state.mode == "idle"
    assert session.state.last_read is None


def test_the_game_state_drives_it(monkeypatch):
    """HERO_SELECTION and STRATEGY_TIME are the two states a draft is in;
    anything else and the gate is back in charge."""
    from draft_assist.gsi import state as gsi_state
    from draft_assist.ui.manual import ManualDraft
    from draft_assist.ui.providers import HybridProvider, Snapshot

    asked = []

    class FakeGsi:
        game_state = ""

        def poll(self):
            return Snapshot(game_state=self.game_state)

    class FakeVision:
        session = None

        def set_required(self, required):
            asked.append(required)

        def poll(self):
            return Snapshot()

    gsi = FakeGsi()
    gsi.manual = ManualDraft()
    provider = HybridProvider(gsi, FakeVision())

    # A blank state is the feed saying NOTHING, which is not the feed
    # saying no: it asks for None so the session can probe past a wrong
    # gate. Reporting it as False is what put the gate back in sole charge.
    for state, expected in ((gsi_state.STATE_HERO_SELECTION, True),
                            (gsi_state.STATE_STRATEGY, True),
                            (gsi_state.STATE_IN_PROGRESS, False),
                            ("", None)):
        gsi.game_state = state
        provider.poll()
        assert asked[-1] is expected, f"{state} asked for {asked[-1]}"
