"""Draft state providers: the UI polls one of these on a timer and doesn't
care whether the state comes from live capture (Windows), replayed frames on
disk, or the scripted demo — which is what keeps the whole interface
iterable with no game running.
"""

import time
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from ..data.store import Dataset
from ..vision.recognize import DraftRead
from .demo import DemoDraft


@dataclass
class Snapshot:
    left: list[int] = field(default_factory=list)    # left bank hero ids
    right: list[int] = field(default_factory=list)   # right bank hero ids
    unknown: int = 0
    mode: str = "idle"          # idle | draft | forced | demo | replay
    frame: np.ndarray | None = None
    read: DraftRead | None = None            # stabilised
    read_raw: DraftRead | None = None        # per-frame, for the debug view
    gate_score: float = float("inf")
    stalled: bool = False
    frames_arrived: int = 0
    source: str = ""
    warning: str = ""


class DemoProvider:
    def __init__(self, ds: Dataset):
        self.ds = ds
        self.draft = DemoDraft(ds)

    def start(self) -> str:
        return "demo draft (restarts when it completes)"

    def stop(self) -> None:
        pass

    def set_forced(self, forced: bool) -> None:
        pass

    def poll(self) -> Snapshot:
        left, right, unknown = self.draft.current()
        if len(left) == 5 and len(right) + unknown == 5:
            if time.monotonic() - self.draft.started > 60:
                self.draft = DemoDraft(self.ds)
        return Snapshot(left=left, right=right, unknown=unknown,
                        mode="demo", source="demo")


class SessionProvider:
    """Shared logic for live capture and replay: both run a CaptureSession,
    one fed by Windows Graphics Capture, the other by frames from disk."""

    def __init__(self, session):
        self.session = session

    def set_forced(self, forced: bool) -> None:
        self.session.set_forced(forced)

    def stop(self) -> None:
        self.session.stop()

    def poll(self) -> Snapshot:
        state = self.session.tick()
        read = state.last_read
        snap = Snapshot(
            mode=("forced" if state.forced else
                  "draft" if state.mode == "active" else "idle"),
            frame=state.last_frame, read=read,
            read_raw=state.last_read_raw,
            gate_score=state.gate_score, stalled=state.stalled,
            frames_arrived=state.frames_arrived)
        if read is not None:
            snap.left = read.team_ids("radiant")
            snap.right = read.team_ids("dire")
            snap.unknown = read.unknown_count()
        return snap


class LiveProvider(SessionProvider):
    """Live Windows Graphics Capture, bound to a chosen window.

    Binding failure is NOT fatal: the app opens anyway with the capture
    source unbound so the user can pick a window from the Debug tab. Dying
    at startup hides the one fact that explains most apparent recognition
    failures — which window is actually being captured.
    """

    def __init__(self, session, title: str | None = None):
        super().__init__(session)
        self.requested_title = title
        self.error = ""

    def start(self) -> str:
        return self.rebind(self.requested_title)

    def rebind(self, title: str | None) -> str:
        """(Re)bind capture; title None means 'find the Dota client'.
        Never raises — the message it returns is shown in the UI."""
        try:
            bound = self.session.start(title)
            self.error = ""
            return f"capturing window '{bound}'"
        except Exception as exc:  # binding failure must not kill the app
            self.error = str(exc)
            first_line = str(exc).splitlines()[0]
            return f"capture not bound — {first_line}"

    def available_sources(self) -> list[str]:
        from ..capture.window import DOTA_TITLE, list_window_titles
        titles = list_window_titles()
        # Surface the Dota client first when present; it is the only one
        # that is ever bound without the user asking.
        return ([DOTA_TITLE] if DOTA_TITLE in titles else []) + \
            [t for t in titles if t != DOTA_TITLE]

    def poll(self) -> Snapshot:
        snap = super().poll()
        title = self.session.capture_title
        if title:
            snap.source = f"capturing '{title}'"
            if title != "Dota 2":
                snap.warning = (f"captured window is '{title}', NOT the Dota "
                                "client — recognition results are meaningless")
        else:
            snap.source = "no capture source bound"
            snap.warning = ("no window bound — choose one in the Debug tab's "
                            "capture source picker")
        return snap


class ReplayProvider(SessionProvider):
    def __init__(self, session, frames_dir: Path, period: float = 1.0):
        super().__init__(session)
        self.paths = (sorted(frames_dir.glob("*.png"))
                      + sorted(frames_dir.glob("*.jpg")))
        if not self.paths:
            raise SystemExit(f"no frames in {frames_dir}")
        self.i = 0
        self.period = period
        self._next = 0.0

    def start(self) -> str:
        return f"replaying {len(self.paths)} frames"

    def poll(self) -> Snapshot:
        import cv2
        now = time.monotonic()
        if now >= self._next:
            self._next = now + self.period
            frame = cv2.imread(str(self.paths[self.i]), cv2.IMREAD_COLOR)
            self.i = (self.i + 1) % len(self.paths)
            if frame is not None:
                self.session.inject_frame(frame)
        snap = super().poll()
        snap.source = self.paths[(self.i - 1) % len(self.paths)].name
        return snap
