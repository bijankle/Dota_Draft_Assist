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
from dataclasses import dataclass, field
from pathlib import Path

# A draft lasts a minute or two; one frame every couple of seconds is
# plenty to see what recognition was looking at, and 600 is a hard stop so
# a session left running overnight cannot fill the disk.
FRAME_INTERVAL = 2.0
MAX_FRAMES = 600
DRAFT_STATES = ("HERO_SELECTION", "STRATEGY_TIME")


@dataclass
class Recorder:
    root: Path
    folder: Path | None = None
    started_at: float = 0.0
    frames: int = 0
    states: int = 0
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
        self._last_frame = 0.0
        self._errors = []
        self._write_meta(finished=False)
        return folder

    def stop(self) -> Path | None:
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
                "errors": self._errors[:20],
            }, indent=2), encoding="utf-8"))

    # -- per-tick capture ------------------------------------------------

    def wants_frame(self, game_state: str) -> bool:
        """Frames only while drafting, and not faster than the interval."""
        if not self.active or self.frames >= MAX_FRAMES:
            return False
        if not any(state in game_state for state in DRAFT_STATES):
            return False
        return time.monotonic() - self._last_frame >= FRAME_INTERVAL

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


def snapshot_record(snap, allies, enemies, dataset) -> dict:
    """What the app concluded this tick, in names a human can read back."""
    return {
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
        return {"comparable": False,
                "reason": ("no minimap line-up in this session — the game "
                           "never reached strategy time"
                           if truth is None else
                           "the screen never read a pick in this session")}

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


def format_session_report(folder: Path) -> str:
    """A whole session as text a human can read and paste back."""
    lines = [f"RECORDING  {folder.name}", "=" * 64]
    meta_path = folder / "meta.json"
    if meta_path.is_file():
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
        except ValueError:
            meta = {}
        for key in ("started", "seconds", "payloads", "frames", "states",
                    "finished"):
            if key in meta:
                lines.append(f"{key + ':':<12}{meta[key]}")
        for error in meta.get("errors", []):
            lines.append(f"WRITE ERROR: {error}")

    states = read_states(folder)
    if not states:
        lines += ["", "No state log — nothing was recorded."]
        return "\n".join(lines)

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

    lines += ["", "SCREEN vs GAME", "-" * 64]
    comparison = compare_sources(states)
    if not comparison["comparable"]:
        lines.append(f"Not comparable: {comparison['reason']}")
        return "\n".join(lines)

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
    return "\n".join(lines)


def sessions(root: Path) -> list[Path]:
    """Recording folders, newest first."""
    if not root.is_dir():
        return []
    return sorted((p for p in root.iterdir()
                   if p.is_dir() and ((p / "state.jsonl").exists()
                                      or (p / "meta.json").exists())),
                  key=lambda p: p.name, reverse=True)
