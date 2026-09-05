"""Draft state providers: the UI polls one of these on a timer and doesn't
care whether the state comes from live capture (Windows), replayed frames on
disk, or the scripted demo — which is what keeps the whole interface
iterable with no game running.
"""

import time
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from ..capture.window import DOTA_TITLE
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
    # Which part of the feed the line-ups came out of, so the
    # UI can say so rather than leave it looking like magic.
    lineup_source: str = ""
    # The ten heroes are known but the split between them is
    # inferred; the UI offers a swap rather than asserting it.
    sides_certain: bool = True
    match_id: str = ""
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

    # How often to look for the Dota window again when not bound to it.
    REBIND_EVERY = 3.0

    def __init__(self, session, title: str | None = None):
        super().__init__(session)
        self.requested_title = title
        self.error = ""
        self._last_rebind = 0.0

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
        from ..capture.window import list_window_titles
        titles = list_window_titles()
        # Surface the Dota client first when present; it is the only one
        # that is ever bound without the user asking.
        return ([DOTA_TITLE] if DOTA_TITLE in titles else []) + \
            [t for t in titles if t != DOTA_TITLE]

    def poll(self) -> Snapshot:
        self._rebind_to_dota_if_possible()
        snap = super().poll()
        title = self.session.capture_title
        if title:
            snap.source = f"capturing '{title}'"
            if title != DOTA_TITLE:
                snap.warning = (f"captured window is '{title}', NOT the Dota "
                                "client — recognition results are meaningless")
        else:
            snap.source = "waiting for the Dota window"
            snap.warning = ("Dota is not running, or not in borderless "
                            "windowed mode — capture binds itself as soon "
                            "as its window appears")
        return snap

    def _rebind_to_dota_if_possible(self) -> None:
        """Bind to Dota the moment its window exists.

        A real session spent a whole draft bound to a File Explorer window
        called "Dota_Draft_Assist" and captured nothing useful, because
        binding happened once at startup — before Dota was running — and
        never again. The user should never have to pick a window: Dota's
        title is exact, so when it appears it is unambiguous.
        """
        if self.requested_title is not None:
            return                      # the user asked for a specific one
        if self.session.capture_title == DOTA_TITLE:
            return
        now = time.monotonic()
        if now - self._last_rebind < self.REBIND_EVERY:
            return
        self._last_rebind = now
        from ..capture.window import find_dota_window_title
        try:
            if find_dota_window_title() is None:
                return
        except Exception:
            return                      # not Windows, or enumeration failed
        self.rebind(None)


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
        # A complete minimap line-up is kept for the rest of the match. One
        # recorded session read a correct split at 16s and a scrambled one
        # at 43s from the same game: after strategy time the minimap holds
        # real units, so the first good reading is the one to trust.
        self.latched: tuple[list[int], list[int]] | None = None
        self.latched_match = ""
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
                   "run Setup ▸ Set up game data (GSI), add "
                   "-gamestateintegration to Dota's launch options, and "
                   "restart Dota"))
            snap.needs_manual = True
            snap.left = merge([], self.manual.entered("ally"))
            snap.right = merge([], self.manual.entered("enemy"))
            snap.mode = "manual" if not self.manual.is_empty else "idle"
            return snap

        parsed = gsi_state.parse(reception.payload, self.ds)
        self.last_state = parsed
        snap.game_state = parsed.game_state
        snap.match_id = parsed.match_id
        snap.sides_known = True
        snap.player_name = parsed.my_name
        snap.my_team = parsed.my_team
        snap.gsi_notes = parsed.notes
        snap.gsi_capabilities = parsed.capabilities
        snap.source = f"game data (GSI) · {parsed.summary()}"

        allies, enemies = parsed.allies, parsed.enemies
        source = parsed.lineup_source
        if parsed.game_state.endswith("HERO_SELECTION") or (
                parsed.match_id and parsed.match_id != self.latched_match):
            self.latched, self.latched_match = None, parsed.match_id
        if source == "minimap" and len(allies) + len(enemies) >= 10:
            self.latched = (list(allies), list(enemies))
            self.latched_match = parsed.match_id
        elif self.latched is not None:
            allies, enemies = self.latched
            source = "minimap"
            # parsed.summary() counts what THIS payload carried, which is
            # your own hero and nothing else once strategy time has passed.
            # Printing that beside "(held)" read as "1 pick, held" when ten
            # are being held.
            held = len(allies) + len(enemies)
            snap.source = (f"game data (GSI) · {parsed.short_summary()} · "
                           f"{held} picks held from the draft")

        snap.lineup_source = source
        snap.sides_certain = (parsed.sides_certain if source != "minimap"
                              else False)
        snap.left = merge(allies, self.manual.entered("ally"))
        snap.right = merge(enemies, self.manual.entered("enemy"))
        snap.needs_manual = len(snap.left) + len(snap.right) < 9
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


class HybridProvider:
    """Game data for the phase and your identity; the screen for the picks.

    This is the shape the evidence forces. Recordings of real matches show
    that during HERO_SELECTION the GSI feed names no hero anywhere at all —
    so a GSI-only app is blind for the whole of the draft, which is the
    only moment the advice is worth anything. Reading the screen is the one
    remaining source, and it is what the vision pipeline was built for.

    GSI does not become useless; it removes the two hardest parts of the
    vision problem:

    * WHEN. `game_state` says a draft is happening, so nothing has to be
      inferred from pixels about whether the pick screen is up. The gate
      stops being a guess.
    * WHOSE. `player.team_name` says which side you are on, so the left and
      right banks map to ally and enemy without ever asking the user.

    Precedence is strict, and never a blend: what the game reports outright
    (minimap line-ups) wins; the screen fills what the game did not report;
    hand-entered slots fill what the screen could not read. Whatever is
    still unknown stays unknown.
    """

    def __init__(self, gsi: "GsiProvider", vision: SessionProvider | None):
        self.gsi = gsi
        self.vision = vision
        self.manual = gsi.manual
        self.forced = False

    # The Debug tab and the capture menu reach for these.
    @property
    def session(self):
        return getattr(self.vision, "session", None)

    def start(self) -> str:
        message = self.gsi.start()
        if self.vision is not None:
            bound = self.vision.start()
            return f"{message}; {bound}"
        return message

    def stop(self) -> None:
        self.gsi.stop()
        if self.vision is not None:
            self.vision.stop()

    def set_forced(self, forced: bool) -> None:
        self.forced = forced
        if self.vision is not None:
            self.vision.set_forced(forced)

    def rebind(self, title: str | None) -> str:
        if self.vision is None or not hasattr(self.vision, "rebind"):
            return "screen capture is not available"
        return self.vision.rebind(title)

    def available_sources(self) -> list[str]:
        if self.vision is None or not hasattr(self.vision, "available_sources"):
            return []
        return self.vision.available_sources()

    def poll(self) -> Snapshot:
        snap = self.gsi.poll()
        if self.vision is None:
            return snap

        screen = self.vision.poll()
        # Always carry the frame and the read: the Debug tab is how a
        # recognition problem gets diagnosed, and it must show what the app
        # is looking at even when the picks came from somewhere else.
        snap.frame = screen.frame
        snap.read = screen.read
        snap.read_raw = screen.read_raw
        snap.gate_score = screen.gate_score
        snap.stalled = screen.stalled
        snap.frames_arrived = max(snap.frames_arrived, screen.frames_arrived)
        if screen.warning and not snap.warning:
            snap.warning = screen.warning

        if snap.lineup_source:
            return snap                      # the game told us outright

        read = screen.read
        if read is None:
            return snap

        radiant, dire = read.team_ids("radiant"), read.team_ids("dire")
        if not radiant and not dire:
            return snap
        # my_team is what makes the banks mean ally and enemy. Without it
        # the sides are still a question, so say so rather than pick one.
        if snap.my_team == "dire":
            allies, enemies = dire, radiant
        elif snap.my_team == "radiant":
            allies, enemies = radiant, dire
        else:
            snap.sides_known = False
            allies, enemies = radiant, dire

        snap.left = merge(allies, self.manual.entered("ally"))
        snap.right = merge(enemies, self.manual.entered("enemy"))
        snap.unknown = read.unknown_count()
        snap.lineup_source = "screen"
        snap.needs_manual = len(snap.left) + len(snap.right) < 9
        snap.mode = "forced" if self.forced else (
            "draft" if snap.game_state or snap.left or snap.right else "idle")
        return snap
