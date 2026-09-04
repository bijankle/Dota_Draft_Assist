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
from .manual import ManualDraft, merge


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
    # GSI-specific: what the game itself reported, and what it could not.
    game_state: str = ""
    # True when left/right already MEAN ally/enemy (game data or manual
    # entry), so the user must never be asked which side they are on.
    sides_known: bool = False
    player_name: str = ""
    my_team: str = ""
    gsi_live: bool = False
    gsi_notes: list[str] = field(default_factory=list)
    gsi_capabilities: dict = field(default_factory=dict)
    needs_manual: bool = False


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


class GsiProvider:
    """Draft state from Dota's own Game State Integration feed.

    This is the sanctioned data path: Dota volunteers JSON to a local port
    because a config file asks it to. Nothing is injected, no memory is
    read, no pixels are interpreted, and there is no per-frame compute.

    What the feed carries is discovered, not assumed. Whatever GSI reports
    is used; whatever it omits is filled from manually entered slots, and
    the Snapshot says which is which so the UI can be honest about it.
    """

    def __init__(self, dataset: Dataset, server, manual: ManualDraft | None = None,
                 install_hint: str = ""):
        self.ds = dataset
        self.server = server
        self.manual = manual if manual is not None else ManualDraft()
        self.install_hint = install_hint
        self.last_state = None
        # A failed bind must be sticky, not a status message that scrolls
        # away: an unbound listener looks exactly like Dota being silent.
        self.bind_error = ""

    def start(self) -> str:
        try:
            self.server.start()
            self.bind_error = ""
        except OSError as exc:
            self.bind_error = (
                f"port {self.server.port} is already in use — another copy "
                "of this app is probably already running. Close the other "
                "one, then use Capture > Use game data (GSI).")
            return f"could not open the GSI port {self.server.port}: {exc}"
        return f"listening for Dota game data on 127.0.0.1:{self.server.port}"

    def stop(self) -> None:
        self.server.stop()

    def set_forced(self, forced: bool) -> None:
        """No gate to override: the game tells us when a draft is happening."""

    def poll(self) -> Snapshot:
        from ..gsi import state as gsi_state

        reception = self.server.snapshot()
        snap = Snapshot(mode="idle", source="game data (GSI)")
        snap.frames_arrived = reception.count
        snap.gsi_live = reception.live

        if self.bind_error:
            snap.warning = self.bind_error
            snap.needs_manual = True
            snap.sides_known = True
            snap.left = merge([], self.manual.entered("ally"))
            snap.right = merge([], self.manual.entered("enemy"))
            snap.mode = "manual" if not self.manual.is_empty else "idle"
            return snap

        if reception.payload is None:
            snap.sides_known = True
            snap.warning = (
                "no data from Dota yet — "
                + (self.install_hint or
                   "install GSI from the Capture menu and add "
                   "-gamestateintegration to Dota's launch options"))
            snap.needs_manual = True
            snap.left = merge([], self.manual.entered("ally"))
            snap.right = merge([], self.manual.entered("enemy"))
            snap.mode = "manual" if not self.manual.is_empty else "idle"
            return snap

        parsed = gsi_state.parse(reception.payload, self.ds)
        self.last_state = parsed
        snap.game_state = parsed.game_state
        snap.sides_known = True
        snap.player_name = parsed.my_name
        snap.my_team = parsed.my_team
        snap.gsi_notes = parsed.notes
        snap.gsi_capabilities = parsed.capabilities
        snap.source = f"game data (GSI) · {parsed.summary()}"

        snap.left = merge(parsed.allies, self.manual.entered("ally"))
        snap.right = merge(parsed.enemies, self.manual.entered("enemy"))
        snap.needs_manual = not parsed.has_full_draft
        snap.mode = "draft" if parsed.drafting else (
            "manual" if not self.manual.is_empty else "idle")

        if not reception.live:
            snap.warning = ("Dota has stopped sending data (game closed, or "
                            "the -gamestateintegration launch option is "
                            "missing)")
        elif reception.rejected and not reception.count:
            snap.warning = reception.last_error
        return snap


class ManualProvider:
    """Draft entered entirely by hand — no game connection at all. Useful
    for planning a draft away from the client, and as the guaranteed
    fallback."""

    def __init__(self, manual: ManualDraft | None = None):
        self.manual = manual if manual is not None else ManualDraft()

    def start(self) -> str:
        return "manual entry — click the draft slots to fill them in"

    def stop(self) -> None:
        pass

    def set_forced(self, forced: bool) -> None:
        pass

    def poll(self) -> Snapshot:
        return Snapshot(left=self.manual.entered("ally"),
                        right=self.manual.entered("enemy"),
                        mode="manual", source="manual entry",
                        needs_manual=True, sides_known=True)
