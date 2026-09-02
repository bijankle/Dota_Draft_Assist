"""Live capture session: binds the Dota window via Windows Graphics Capture
and runs the idle/active state machine.

- IDLE: the gate checks a downscaled frame at ~1 Hz.
- ACTIVE: full slot recognition at ~2 Hz while the gate keeps tripping (with
  hysteresis so one noisy frame doesn't flap the state).
- Manual override forces ACTIVE regardless of the gate.

The session is UI-framework agnostic: the owner (the PyQt app, or a test)
calls tick() on its own timer; the capture callback thread only stores the
newest frame. Recognition confirming a draft screen auto-saves a gate
reference, which is how the gate bootstraps from zero references.

Windows-only imports happen inside start(), so every other module imports
this file fine on Linux.
"""

import threading
import time
from dataclasses import dataclass, field

import numpy as np

from ..vision.layout import DraftLayout
from ..vision.library import Library, RecognitionParams
from ..vision.recognize import DraftRead, SlotRead, read_draft
from . import gate

IDLE_PERIOD = 1.0      # gate cadence
ACTIVE_PERIOD = 0.5    # recognition cadence
# Hysteresis: consecutive gate results needed to switch state.
TRIPS_TO_ACTIVATE = 2
MISSES_TO_DEACTIVATE = 4
# Recognition confirming this many resolved slots marks the frame as a real
# draft screen (feeds gate references).
CONFIRM_SLOTS = 6
STALL_AFTER = 5.0      # no frames for this long -> "stalled" flag


@dataclass
class SessionState:
    mode: str = "idle"              # idle | active
    forced: bool = False            # manual override
    gate_score: float = float("inf")
    frames_arrived: int = 0
    stalled: bool = False
    last_read: DraftRead | None = None       # STABILISED — what consumers use
    last_read_raw: DraftRead | None = None   # per-frame — what debug shows
    last_frame: np.ndarray | None = None


# Consecutive identical reads required before a slot's published value
# changes. At the 2 Hz active cadence this is ~1.5 s of latency against a
# ~30 s pick timer — cheap insurance against flicker.
STABLE_CONFIRMS = 3


class SlotStabilizer:
    """Recognition can flicker frame-to-frame (hover overlays, animations,
    a wrong window being captured). Published slot values are therefore
    debounced: a slot changes only after the same NEW value is seen
    STABLE_CONFIRMS times in a row, and unknown never overwrites a resolved
    value — picks don't un-pick during a draft. Reset when the draft screen
    goes away."""

    def __init__(self, n_slots: int = 10, confirms: int = STABLE_CONFIRMS):
        self.confirms = confirms
        self.stable: list[int | None] = [None] * n_slots
        self._candidate: list[int | None] = [None] * n_slots
        self._count = [0] * n_slots

    def reset(self) -> None:
        n = len(self.stable)
        self.stable = [None] * n
        self._candidate = [None] * n
        self._count = [0] * n

    def update(self, read: DraftRead) -> DraftRead:
        out = []
        for i, s in enumerate(read.slots):
            v = s.hero_id
            if v is not None and v != self.stable[i]:
                if v == self._candidate[i]:
                    self._count[i] += 1
                else:
                    self._candidate[i], self._count[i] = v, 1
                if self._count[i] >= self.confirms:
                    self.stable[i] = v
                    self._candidate[i], self._count[i] = None, 0
            elif v == self.stable[i]:
                self._candidate[i], self._count[i] = None, 0
            out.append(SlotRead(rect=s.rect, hero_id=self.stable[i],
                                best_label=s.best_label, distance=s.distance,
                                margin=s.margin, crop=s.crop))
        return DraftRead(slots=out)


class CaptureSession:
    def __init__(self, layout: DraftLayout, lib: Library,
                 params: RecognitionParams):
        self.layout, self.lib, self.params = layout, lib, params
        self.state = SessionState()
        self._lock = threading.Lock()
        self._latest: np.ndarray | None = None
        self._arrived_at = 0.0
        self._count = 0
        self._trips = 0
        self._misses = 0
        self._next_tick = 0.0
        # gate.GATE_DIR is read at call time (not bound as a default) so
        # tests can repoint it.
        self._refs = gate.load_references(gate.GATE_DIR)
        self._control = None
        self._stabilizer = SlotStabilizer()
        self.capture_title: str | None = None

    # -- capture binding (Windows only) --------------------------------
    def start(self, title: str | None = None) -> str:
        """Bind capture to `title`, or to the Dota client when omitted.

        Raises RuntimeError naming the visible windows if nothing matches —
        the caller (the UI) offers a picker rather than dying, because
        "which window am I capturing" is the question behind most apparent
        recognition failures.
        """
        from windows_capture import WindowsCapture

        from .window import find_dota_window_title, list_window_titles
        if title is None:
            title = find_dota_window_title()
        if title is None:
            visible = list_window_titles()
            raise RuntimeError(
                "No window titled exactly 'Dota 2' is open — start Dota in "
                "borderless windowed mode, or pick a capture source in the "
                "app's Debug tab.\nVisible windows:\n  "
                + "\n  ".join(visible[:40] or ["(none)"]))
        self.stop()
        self._stabilizer.reset()
        with self._lock:
            self._latest = None
            self._count = 0
        capture = WindowsCapture(cursor_capture=False, draw_border=False,
                                 window_name=title)

        @capture.event
        def on_frame_arrived(frame, capture_control):  # noqa: ANN001
            with self._lock:
                self._latest = frame.frame_buffer.copy()
                self._arrived_at = time.monotonic()
                self._count += 1

        @capture.event
        def on_closed():
            pass

        self._control = capture.start_free_threaded()
        self.capture_title = title
        return title

    def stop(self) -> None:
        if self._control is not None:
            self._control.stop()
            self._control = None

    # -- for replay/tests: inject frames instead of start() -------------
    def inject_frame(self, frame_bgr: np.ndarray) -> None:
        with self._lock:
            self._latest = frame_bgr
            self._arrived_at = time.monotonic()
            self._count += 1

    def set_forced(self, forced: bool) -> None:
        self.state.forced = forced

    # -- state machine ---------------------------------------------------
    def tick(self) -> SessionState:
        """Call frequently (e.g. every 250 ms); internally rate-limits to the
        current mode's cadence. Mutates and returns self.state."""
        now = time.monotonic()
        with self._lock:
            frame = self._latest
            self.state.frames_arrived = self._count
            arrived_at = self._arrived_at
        self.state.stalled = bool(frame is not None
                                  and now - arrived_at > STALL_AFTER)
        if frame is None or now < self._next_tick:
            return self.state

        if frame.ndim == 3 and frame.shape[2] == 4:
            frame = frame[:, :, :3]

        active = self.state.forced or self.state.mode == "active"
        self._next_tick = now + (ACTIVE_PERIOD if active else IDLE_PERIOD)

        self.state.gate_score = gate.score(frame, self._refs)
        tripped = gate.is_draft_screen(frame, self._refs)
        if tripped:
            self._trips, self._misses = self._trips + 1, 0
        else:
            self._trips, self._misses = 0, self._misses + 1
        if self.state.mode == "idle" and self._trips >= TRIPS_TO_ACTIVATE:
            self.state.mode = "active"
        elif (self.state.mode == "active"
              and self._misses >= MISSES_TO_DEACTIVATE
              and not self.state.forced):
            self.state.mode = "idle"
            self.state.last_read = None
            self.state.last_read_raw = None
            self._stabilizer.reset()

        if self.state.mode == "active" or self.state.forced:
            raw = read_draft(frame, self.layout, self.lib, self.params)
            self.state.last_read_raw = raw
            self.state.last_read = self._stabilizer.update(raw)
            self.state.last_frame = frame
            # A frame the recogniser itself resolves is the draft screen;
            # judge that on the raw read so gate bootstrap isn't delayed.
            if 10 - raw.unknown_count() >= CONFIRM_SLOTS:
                if gate.save_reference(frame, gate.GATE_DIR) is not None:
                    self._refs = gate.load_references(gate.GATE_DIR)
        return self.state
