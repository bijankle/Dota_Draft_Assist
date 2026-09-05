"""One recording: game data, screen frames and the app's own reading.

Recording used to be three unrelated things — a GSI archive toggle, a
separate capture probe, and Ctrl+S snapshots — living in three menus and
three folders, which meant the evidence for any one game was scattered and
usually incomplete. A session is now one folder holding all of it:

    recordings/2026-09-05_2031/
        meta.json          when it started and stopped, and the totals
        gsi/gsi_00001.json every payload Dota sent, verbatim
        frames/00001.png   the Dota window during the draft
        state.jsonl        one line per tick: what the app concluded and
                           WHICH SOURCE it came from

The third file is the one that makes the other two worth keeping. A payload
says what the game sent and a frame says what was on screen, but only the
state log says what the app made of them, so a wrong pick can be traced to
the source that produced it rather than guessed at.

Frames are the expensive part, so they are rate-limited and capped, and
only taken while the game says a draft is happening — the rest of a match
is thousands of images that answer nothing.
"""

import json
import time
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

# One frame every couple of seconds is plenty to see what recognition was
# looking at, and the cap is a hard stop so a session left running cannot
# fill the disk. Frames start at the button press, not at the draft: the
# queue and the loading screen are where a capture-binding fault shows up,
# and by the time hero selection starts it is too late to notice.
FRAME_INTERVAL = 2.0
MAX_FRAMES = 600
DRAFT_STATES = ("HERO_SELECTION", "STRATEGY_TIME")


def is_drafting(game_state: str) -> bool:
    return any(name in str(game_state or "") for name in DRAFT_STATES)
# Stop by itself a minute after the draft ends. Nothing after that answers
# a question, and the alternative is remembering to press Stop mid-game.
POST_DRAFT_GRACE = 60.0
# And stop regardless after this long, so a press with no game behind it
# does not run until the disk fills.
MAX_SESSION = 1800.0


@dataclass
class Recorder:
    root: Path
    folder: Path | None = None
    started_at: float = 0.0
    frames: int = 0
    states: int = 0
    saw_draft: bool = False
    left_draft_at: float = 0.0
    stop_reason: str = ""
    _last_frame: float = 0.0
    _errors: list[str] = field(default_factory=list)

    @property
    def active(self) -> bool:
        return self.folder is not None

    @property
    def gsi_dir(self) -> Path | None:
        return self.folder / "gsi" if self.folder else None

    @property
    def elapsed(self) -> float:
        return time.monotonic() - self.started_at if self.active else 0.0

    # -- lifecycle -------------------------------------------------------

    def start(self) -> Path:
        """Begin a session in its own folder. Never appends to an earlier
        one: pooling two matches made every count in the report meaningless
        and was the thing that most confused reading the evidence."""
        stamp = time.strftime("%Y-%m-%d_%H%M%S")
        folder = self.root / stamp
        suffix = 2
        while folder.exists():
            folder = self.root / f"{stamp}_{suffix}"
            suffix += 1
        (folder / "gsi").mkdir(parents=True)
        (folder / "frames").mkdir()
        self.folder = folder
        self.started_at = time.monotonic()
        self.frames = self.states = 0
        self.saw_draft = False
        self.left_draft_at = 0.0
        self._last_frame = 0.0
        self._errors = []
        self._write_meta(finished=False)
        return folder

    def stop(self, reason: str = "") -> Path | None:
        self.stop_reason = reason
        folder = self.folder
        if folder is not None:
            self._write_meta(finished=True)
            # The report is written now rather than on demand so the folder
            # is self-contained: it can be zipped, moved or pasted without
            # needing the app that produced it.
            self._safe(lambda: (folder / "report.txt").write_text(
                format_session_report(folder), encoding="utf-8"))
        self.folder = None
        return folder

    def _write_meta(self, finished: bool) -> None:
        if self.folder is None:
            return
        payloads = len(list((self.folder / "gsi").glob("gsi_*.json")))
        self._safe(lambda: (self.folder / "meta.json").write_text(
            json.dumps({
                "started": time.strftime("%Y-%m-%d %H:%M:%S"),
                "finished": finished,
                "seconds": round(self.elapsed, 1),
                "payloads": payloads,
                "frames": self.frames,
                "states": self.states,
                "stopped": self.stop_reason or "stopped by hand",
                "errors": self._errors[:20],
            }, indent=2), encoding="utf-8"))

    # -- per-tick capture ------------------------------------------------

    def wants_frame(self) -> bool:
        """From the button press onward, no faster than the interval."""
        if not self.active or self.frames >= MAX_FRAMES:
            return False
        return time.monotonic() - self._last_frame >= FRAME_INTERVAL

    def observe(self, game_state: str) -> str:
        """Watch the phase and say when the session should end itself.

        Returns a reason to stop, or "" to keep going. The draft is what
        the session is for, so once the game has left it and a grace period
        has passed there is nothing more to record — and pressing Stop is
        one more thing to remember at exactly the moment the game starts.
        """
        if not self.active:
            return ""
        if self.elapsed >= MAX_SESSION:
            return (f"stopped automatically after "
                    f"{MAX_SESSION / 60:.0f} minutes")
        state = str(game_state or "")
        if is_drafting(state):
            self.saw_draft = True
            self.left_draft_at = 0.0
            return ""
        if not state or not self.saw_draft:
            # A blank state is Dota going quiet for a moment, not the draft
            # ending; and before a draft has been seen there is nothing to
            # have left.
            return ""
        now = time.monotonic()
        if not self.left_draft_at:
            self.left_draft_at = now
            return ""
        if now - self.left_draft_at >= POST_DRAFT_GRACE:
            return (f"stopped automatically {POST_DRAFT_GRACE:.0f}s after "
                    "the draft ended")
        return ""

    @property
    def auto_stop_in(self) -> float:
        """Seconds until the session ends itself, or 0 when not counting."""
        if not self.active or not self.left_draft_at:
            return 0.0
        return max(0.0, POST_DRAFT_GRACE
                   - (time.monotonic() - self.left_draft_at))

    def save_frame(self, frame) -> Path | None:
        if not self.active or frame is None:
            return None
        import cv2

        self.frames += 1
        self._last_frame = time.monotonic()
        path = self.folder / "frames" / f"{self.frames:05d}.png"
        if not self._safe(lambda: cv2.imwrite(str(path), frame)):
            return None
        return path

    def log_state(self, record: dict) -> None:
        """One JSON line per tick. Appended, never rewritten, so a crash
        mid-session still leaves everything up to that point readable."""
        if not self.active:
            return
        record = dict(record, at=round(self.elapsed, 2))
        self.states += 1
        path = self.folder / "state.jsonl"

        def write():
            with path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(record, default=str) + "\n")
        self._safe(write)

    def _safe(self, action) -> bool:
        """A failed write must never take the draft window down mid-game."""
        try:
            action()
            return True
        except Exception as exc:                     # disk full, locked file
            message = f"{type(exc).__name__}: {exc}"
            if message not in self._errors:
                self._errors.append(message)
            return False


def _heroes_in(read) -> int:
    if read is None:
        return 0
    try:
        return len(read.team_ids("radiant")) + len(read.team_ids("dire"))
    except Exception:
        return 0


def snapshot_record(snap, allies, enemies, dataset) -> dict:
    """What the app concluded this tick, in names a human can read back.

    The notes matter as much as the picks. A session where every tick says
    source "none" is unreadable without them: the reason the minimap
    declined, or the screen never recognised anything, is exactly what has
    to come back — otherwise the log records the failure without recording
    why.
    """
    return {
        "notes": list(getattr(snap, "gsi_notes", []) or []),
        "capture": getattr(snap, "source", ""),
        "has_frame": getattr(snap, "frame", None) is not None,
        # Whether the pipeline RAN is a different fact from whether it
        # found anything. A session logged "106 of 206 recognised
        # something" beside "the screen never read a pick", which is both
        # true and useless.
        "ran_recognition": getattr(snap, "read", None) is not None,
        "read_heroes": _heroes_in(getattr(snap, "read", None)),
        "game_state": getattr(snap, "game_state", ""),
        "source": getattr(snap, "lineup_source", "") or "none",
        "mode": getattr(snap, "mode", ""),
        "player": getattr(snap, "player_name", ""),
        "my_team": getattr(snap, "my_team", ""),
        "sides_known": bool(getattr(snap, "sides_known", False)),
        "allies": [dataset.name(h) for h in allies],
        "enemies": [dataset.name(h) for h in enemies],
        "unknown": getattr(snap, "unknown", 0),
        "payloads": getattr(snap, "frames_arrived", 0),
        "warning": getattr(snap, "warning", ""),
    }


# ---- reading a session back --------------------------------------------

def read_states(folder: Path) -> list[dict]:
    path = folder / "state.jsonl"
    if not path.is_file():
        return []
    states = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            record = json.loads(line)
        except ValueError:
            continue                      # a torn last line after a crash
        if isinstance(record, dict):
            states.append(record)
    return states


def compare_sources(states: list[dict]) -> dict:
    """Score what the SCREEN read during the draft against what the GAME
    reported afterwards.

    This is the only ground truth available. During hero selection GSI
    names no hero, so recognition cannot be checked at the time; but from
    strategy time the minimap carries all ten, and it is the same match.
    The last screen reading before the game took over is therefore
    gradeable, hero by hero, without anyone having to eyeball a screenshot.
    """
    truth = next((s for s in states if s.get("source") == "minimap"), None)
    screen = None
    for state in states:
        if state.get("source") == "minimap":
            break
        if state.get("source") == "screen":
            screen = state
    if truth is None or screen is None:
        reached = any("STRATEGY_TIME" in str(s.get("game_state", ""))
                      for s in states)
        if truth is None and reached:
            reason = ("the game DID reach strategy time but no line-up was "
                      "read from the minimap — see the notes below, which "
                      "say why it declined")
        elif truth is None:
            reason = ("no minimap line-up: the session never reached "
                      "strategy time")
        else:
            reason = "the screen never read a pick in this session"
        return {"comparable": False, "reason": reason}

    out = {"comparable": True, "swapped": False}
    truth_sides = {"allies": set(truth.get("allies", [])),
                   "enemies": set(truth.get("enemies", []))}
    screen_sides = {"allies": set(screen.get("allies", [])),
                    "enemies": set(screen.get("enemies", []))}
    # A screen reading that matches the other side better than its own is a
    # side-mapping bug, not a recognition failure, and the two want very
    # different fixes — so say which it is.
    straight = (len(screen_sides["allies"] & truth_sides["allies"])
                + len(screen_sides["enemies"] & truth_sides["enemies"]))
    crossed = (len(screen_sides["allies"] & truth_sides["enemies"])
               + len(screen_sides["enemies"] & truth_sides["allies"]))
    if crossed > straight:
        out["swapped"] = True
        screen_sides = {"allies": screen_sides["enemies"],
                        "enemies": screen_sides["allies"]}

    for side in ("allies", "enemies"):
        got, want = screen_sides[side], truth_sides[side]
        out[side] = {
            "correct": sorted(got & want),
            "missed": sorted(want - got),
            "wrong": sorted(got - want),
        }
    out["correct"] = len(out["allies"]["correct"]) + len(
        out["enemies"]["correct"])
    out["wrong"] = len(out["allies"]["wrong"]) + len(out["enemies"]["wrong"])
    out["missed"] = len(out["allies"]["missed"]) + len(
        out["enemies"]["missed"])
    return out


def format_session_report(folder: Path, dataset=None) -> str:
    """A whole session as one report.

    Recording starts the screen and the game feed together, so the account
    of it is one document: what the app concluded tick by tick, why it
    declined when it declined, how the screen's reading scored against the
    game's, and what the raw payloads contained. Splitting those across two
    tools meant neither answered a question on its own.
    """
    lines = [f"RECORDING  {folder.name}", "=" * 64]
    meta_path = folder / "meta.json"
    if meta_path.is_file():
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
        except ValueError:
            meta = {}
        for key in ("started", "seconds", "payloads", "frames", "states",
                    "finished", "stopped"):
            if key in meta:
                lines.append(f"{key + ':':<12}{meta[key]}")
        for error in meta.get("errors", []):
            lines.append(f"WRITE ERROR: {error}")

    states = read_states(folder)
    if not states:
        lines += ["", "No state log — nothing was recorded."]
        return "\n".join(lines) + _payload_section(folder, dataset)

    lines += ["", "TIMELINE (only where the reading changed)", "-" * 64]
    previous = None
    for state in states:
        key = (state.get("game_state"), state.get("source"),
               tuple(state.get("allies", [])),
               tuple(state.get("enemies", [])))
        if key == previous:
            continue
        previous = key
        phase = str(state.get("game_state", "")).replace(
            "DOTA_GAMERULES_STATE_", "") or "—"
        lines.append(
            f"{state.get('at', 0):7.1f}s  {phase:<18s} "
            f"{str(state.get('source', '')):<8s} "
            f"allies={', '.join(state.get('allies', [])) or '—'} | "
            f"enemies={', '.join(state.get('enemies', [])) or '—'}")

    lines += ["", "WHERE EACH READING CAME FROM", "-" * 64]
    sources = Counter(str(s.get("source", "")) or "none" for s in states)
    for name, count in sources.most_common():
        lines.append(f"  {count:6d} ticks  {name}")
    framed = sum(1 for s in states if s.get("has_frame"))
    ran = sum(1 for s in states if s.get("ran_recognition"))
    found = sum(1 for s in states if s.get("read_heroes"))
    best = max((s.get("read_heroes", 0) for s in states), default=0)
    lines.append(f"  {framed:6d} ticks captured a frame")
    lines.append(f"  {ran:6d} ticks ran recognition on one")
    lines.append(f"  {found:6d} ticks found at least one hero "
                 f"(best: {best} of 10)")
    if not framed:
        lines.append("  No frame was ever captured: screen reading was off, "
                     "unbound, or bound to the wrong window.")
    elif not ran:
        lines.append("  Frames arrived but recognition never ran — the "
                     "draft gate never opened.")
    elif not found:
        lines.append("  Recognition ran on every frame and found no hero at "
                     "all. That is the crop boxes or the portrait library, "
                     "not capture.")
    elif best < 10:
        lines.append(f"  Recognition never saw more than {best} of the ten "
                     "slots — check the Debug tab's crop boxes against the "
                     "pick screen.")

    notes = Counter()
    for state in states:
        notes.update(state.get("notes", []) or [])
        if state.get("warning"):
            notes[f"WARNING: {state['warning']}"] += 1
    if notes:
        lines += ["", "WHAT THE APP SAID ABOUT ITS OWN READING", "-" * 64]
        for note, count in notes.most_common(15):
            lines.append(f"  {count:6d}x  {note}")

    lines += ["", "SCREEN vs GAME", "-" * 64]
    comparison = compare_sources(states)
    if not comparison["comparable"]:
        lines.append(f"Not comparable: {comparison['reason']}")
        return "\n".join(lines) + _payload_section(folder, dataset)

    if comparison["swapped"]:
        lines.append("SIDES WERE SWAPPED: the screen reading matches the "
                     "other team better than its own. That is a "
                     "side-mapping fault, not a recognition one.")
        lines.append("(scored below after un-swapping)")
    for side in ("allies", "enemies"):
        detail = comparison[side]
        lines.append(f"{side}:")
        lines.append(f"  correct : {', '.join(detail['correct']) or '—'}")
        lines.append(f"  missed  : {', '.join(detail['missed']) or '—'}"
                     "   (the game had them, the screen did not)")
        lines.append(f"  wrong   : {', '.join(detail['wrong']) or '—'}"
                     "   (the screen had them, the game did not)")
    total = comparison["correct"] + comparison["wrong"] + comparison["missed"]
    lines.append("")
    lines.append(f"{comparison['correct']}/10 heroes read correctly "
                 f"({comparison['wrong']} wrong, {comparison['missed']} "
                 f"missed, {total} judged)")
    if comparison["wrong"]:
        lines.append("A WRONG hero is the serious one: the app advised "
                     "against a hero that was never in the game.")
    return "\n".join(lines) + _payload_section(folder, dataset)


def _payload_section(folder: Path, dataset) -> str:
    """The raw game feed, analysed, appended to the same report.

    This used to be a separate tool over a separate archive. Recording
    starts both sources at once, so the account of them belongs together.
    """
    gsi_dir = folder / "gsi"
    if not gsi_dir.is_dir():
        return ""
    from .data import store
    from .gsi import summary as gsi_summary

    if dataset is None:
        dataset = store.load_or_empty()
    try:
        report = gsi_summary.from_directory(gsi_dir, dataset)
    except OSError as exc:
        return f"\n\nCould not read {gsi_dir}: {exc}"
    if not report.payloads:
        return "\n\nNo game-data payloads in this session."
    return ("\n\n" + "=" * 64 + "\nWHAT DOTA ACTUALLY SENT\n"
            + gsi_summary.format_report(report, gsi_dir))


def sessions(root: Path) -> list[Path]:
    """Recording folders, newest first."""
    if not root.is_dir():
        return []
    return sorted((p for p in root.iterdir()
                   if p.is_dir() and ((p / "state.jsonl").exists()
                                      or (p / "meta.json").exists())),
                  key=lambda p: p.name, reverse=True)
