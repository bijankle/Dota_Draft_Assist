"""Did this draft go wrong, and what to send back if it did.

THE DETECTION ALREADY EXISTED; NOTHING WAS LISTENING. Three things in
this app already know when the screen reading has failed, and all three
said so where only the owner would ever look:

  * `Snapshot.crop_boxes_wrong` - at strategy time the GAME names the ten
    heroes on screen, `lineup.read_placed` scores the ten calibrated crop
    boxes against exactly those, and fewer than a bank's worth landing
    proves the boxes are not on portraits. It is a verdict rather than a
    guess, which is what makes it safe to act on.
  * `record.compare_sources` - grades what the screen read against the
    minimap's line-up from the same match, and already separates a WRONG
    hero (advice given against a hero not in the game) from a MISSED one,
    and both from SWAPPED sides, which is a mapping fault rather than a
    recognition one.
  * `Lineups.sides_certain` - the app knows when the teams were a coin
    flip.

So this module is a reader rather than a new pipeline: it grades a
finished recording and says whether a stranger's copy of this app just
had a bad draft.

REPAIR COMES FIRST AND REPORTING SECOND. For the commonest fault the app
already knows the cure - re-run the portrait search and save the
calibration it measures - so a `Fault` carries `repairable` and the
caller tries that before asking anybody to send anything. A stranger's
app fixing itself is worth more than a ticket.

GRADED ONCE PER DRAFT, NEVER PER TICK. A draft is the unit that means
something: a single tick reading nothing is the app between frames, and
the same tick repeated eighty times is the fault this exists to catch.
"""

import json
import shutil
import zipfile
from dataclasses import dataclass, field
from pathlib import Path

from . import record as record_mod

# A HERO-SELECTION TICK WITH A FRAME AND NO HERO IS ORDINARY; a run of
# them is the app blind through the one screen it exists for. Measured
# against the real fault this is drawn from: a ranked game that read two
# of ten slots for eighty seconds.
BLIND_SECONDS = 25.0
# How many of the ten the screen may miss before it is worth reporting.
# One is a hero in a persona the library has no picture of, which is
# normal and is what `harvest` exists to learn; half the board is not.
MISSED_FLOOR = 4

# WHAT MAY GO IN THE POST. A mail server usually refuses at 25MB, so the
# budget is well under it: the zip is built to a ceiling and says what it
# left out rather than being written and then found to be too big.
SIZE_CAP = 18 * 1024 * 1024
# Frames are the expensive part - a 3440x1440 PNG is about five
# megabytes - so they are downscaled and counted. Four is enough to show
# a draft filling up under boxes that are or are not landing.
FRAMES_SENT = 4
FRAME_WIDTH = 1600


@dataclass(frozen=True)
class Fault:
    """One thing that went wrong, in words the person can read."""

    key: str
    title: str                      # one line, for the banner
    detail: str                     # a sentence or two, for the report
    repairable: bool = False        # the app knows the cure for this one


@dataclass
class Verdict:
    faults: list[Fault] = field(default_factory=list)
    # What was measured, whether or not it produced a fault - a report
    # saying only what failed cannot be read against a healthy one.
    notes: list[str] = field(default_factory=list)

    @property
    def bad(self) -> bool:
        return bool(self.faults)

    @property
    def repairable(self) -> bool:
        """True when EVERY fault is one the app can fix by itself.

        Deliberately `all` rather than `any`: repairing the boxes and
        then staying quiet about a second fault nothing addresses would
        lose exactly the reports worth having.
        """
        return bool(self.faults) and all(f.repairable for f in self.faults)

    def headline(self) -> str:
        if not self.faults:
            return "nothing looked wrong with this draft"
        first = self.faults[0].title
        if len(self.faults) == 1:
            return first
        return f"{first} (and {len(self.faults) - 1} more)"


def _drafting(row: dict) -> bool:
    return record_mod.is_drafting(str(row.get("game_state") or ""))


def _blind_run(states: list[dict]) -> float:
    """The longest stretch of hero selection with a frame and no hero.

    A FRAME IS REQUIRED, which is what separates this from the app not
    being bound to Dota at all: capture failing and recognition failing
    are different bugs and want different fixes, and the recorder logs
    them apart for exactly that reason.
    """
    longest = started = 0.0
    running = False
    for row in states:
        picking = "HERO_SELECTION" in str(row.get("game_state") or "")
        blind = (picking and row.get("has_frame")
                 and not row.get("read_heroes"))
        at = float(row.get("at") or 0.0)
        if blind and not running:
            running, started = True, at
        elif not blind and running:
            running = False
            longest = max(longest, at - started)
        elif blind:
            longest = max(longest, at - started)
    return longest


def grade(folder: Path, dataset=None) -> Verdict:
    """Read one finished recording and say whether it went wrong."""
    out = Verdict()
    states = record_mod.read_states(folder)
    if not states:
        out.notes.append("no state log - nothing to grade")
        return out
    drafting = [row for row in states if _drafting(row)]
    out.notes.append(f"{len(states)} ticks, {len(drafting)} of them in a draft")
    if not drafting:
        out.notes.append("this session never reached a draft")
        return out

    # 1. THE BOXES, which is the one verdict rather than an inference.
    if any(row.get("crop_boxes_wrong") for row in drafting):
        out.faults.append(Fault(
            "crop_boxes",
            "the app could not find the hero portraits on screen",
            "At strategy time the game named all ten heroes and the "
            "app's crop boxes matched too few of them to be sitting on "
            "portraits. This is the fault that makes the app blind for "
            "a whole draft.",
            repairable=True))

    # 2. BLIND WHILE PICKING - the screen the app exists for.
    blind = _blind_run(drafting)
    out.notes.append(f"longest blind stretch while picking: {blind:.0f}s")
    if blind >= BLIND_SECONDS:
        out.faults.append(Fault(
            "blind",
            f"nothing was read for {blind:.0f}s of hero selection",
            f"The game reported hero selection and the app had a picture "
            f"of the screen, but resolved no hero for {blind:.0f} "
            "continuous seconds. Either the crop boxes are wrong for "
            "this display or recognition is failing on this artwork.",
            repairable=True))

    # 3. WHAT THE SCREEN READ AGAINST WHAT THE GAME SAID. The grader is
    #    `record.compare_sources`, which has always run for the session
    #    report and has never been read by anything that could act.
    check = record_mod.compare_sources(states)
    if not check.get("comparable"):
        out.notes.append(f"screen vs game: {check.get('reason', 'not graded')}")
    else:
        wrong, missed = check["wrong"], check["missed"]
        out.notes.append(
            f"screen vs game: {check['correct']} right, {wrong} wrong, "
            f"{missed} missed" + (", SIDES SWAPPED" if check["swapped"] else ""))
        if wrong:
            out.faults.append(Fault(
                "wrong_heroes",
                f"{wrong} hero(es) were read that were not in the game",
                "The screen resolved a hero the game's own line-up does "
                "not contain, so advice was given about a hero nobody "
                "picked. A recognition fault rather than a geometry one."))
        if missed >= MISSED_FLOOR:
            out.faults.append(Fault(
                "missed_heroes",
                f"{missed} of the ten were never read from the screen",
                "The game named ten heroes and the screen resolved too "
                "few of them. One missing is a hero in artwork the "
                "library has not learned yet, which is normal; this is "
                "more than that."))
        if check["swapped"]:
            out.faults.append(Fault(
                "swapped_sides",
                "the two teams came out the wrong way round",
                "What the screen read matched the OTHER team better than "
                "its own. That is a side-mapping fault rather than a "
                "recognition one, and the two want different fixes."))

    # 4. THE TEAMS WERE A GUESS. Last, and never on its own evidence
    #    alone: the app SAYS it is guessing and offers the drag, so this
    #    is only worth reporting beside something that actually broke.
    if any(row.get("sides_certain") is False for row in drafting):
        out.notes.append("the teams were split by a rule that can invert")
    return out


def _frames_worth_sending(folder: Path) -> list[Path]:
    """A spread across the draft rather than the first few.

    The first frames of a session are the queue and the loading screen,
    which answer nothing about recognition; what is worth having is the
    bar filling up, so they are taken evenly across whatever was saved.
    """
    frames = sorted((folder / "frames").glob("*.png"))
    if len(frames) <= FRAMES_SENT:
        return frames
    step = len(frames) / FRAMES_SENT
    return [frames[min(len(frames) - 1, int(i * step))]
            for i in range(FRAMES_SENT)]


def _shrunk(path: Path, into: Path) -> Path | None:
    """A frame narrow enough to post. Returns the written file."""
    import cv2
    import numpy as np

    try:
        data = np.frombuffer(path.read_bytes(), dtype=np.uint8)
        image = cv2.imdecode(data, cv2.IMREAD_COLOR) if data.size else None
    except OSError:
        return None
    if image is None:
        return None
    height, width = image.shape[:2]
    if width > FRAME_WIDTH:
        scale = FRAME_WIDTH / width
        image = cv2.resize(image, (FRAME_WIDTH, max(1, int(height * scale))),
                           interpolation=cv2.INTER_AREA)
    ok, buffer = cv2.imencode(".jpg", image, [cv2.IMWRITE_JPEG_QUALITY, 82])
    if not ok:
        return None
    out = into / f"{path.stem}.jpg"
    out.write_bytes(buffer.tobytes())
    return out


def write_zip(folder: Path, verdict: Verdict, out_dir: Path,
              extra_text: str = "", dataset=None) -> tuple[Path, list[str]]:
    """Build the file the user posts. Returns (zip path, what went in).

    BUILT TO A CEILING RATHER THAN CHECKED AFTERWARDS. A mail server
    refuses a big attachment outright, and a report that cannot be sent
    is a report nobody sends - so each picture is added only while the
    budget holds, and the manifest says what was left out.
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    target = out_dir / f"bug-{folder.name}.zip"
    packed: list[str] = []

    lines = [f"=== {folder.name} ===", ""]
    lines.append("WHAT LOOKED WRONG")
    for fault in verdict.faults:
        lines.append(f"  * {fault.title}")
        lines.append(f"      {fault.detail}")
    if not verdict.faults:
        lines.append("  nothing - this report was sent by hand")
    lines += ["", "WHAT WAS MEASURED"]
    lines += [f"  {note}" for note in verdict.notes]
    if extra_text:
        lines += ["", "THE APP AT THE TIME", extra_text]
    try:
        lines += ["", "THE SESSION REPORT", "",
                  record_mod.format_session_report(folder, dataset)]
    except (OSError, ValueError, KeyError) as exc:      # noqa: BLE001
        lines += ["", f"(the session report could not be built: {exc})"]

    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as zipped:
        zipped.writestr("report.txt", "\n".join(lines))
        packed.append("report.txt")
        state = folder / "state.jsonl"
        if state.is_file():
            zipped.write(state, "state.jsonl")
            packed.append("state.jsonl")
        # ONE PAYLOAD, NOT ALL OF THEM. A session holds hundreds and they
        # are nearly identical; what answers a question is the fullest
        # one, which is what the session report already picks out.
        fullest = _fullest_payload(folder)
        if fullest is not None:
            zipped.writestr("payload.json", json.dumps(fullest, indent=1))
            packed.append("payload.json")

        scratch = out_dir / "_frames"
        scratch.mkdir(parents=True, exist_ok=True)
        try:
            for frame in _frames_worth_sending(folder):
                if target.stat().st_size > SIZE_CAP:
                    packed.append(f"(stopped at the {SIZE_CAP // 1048576}MB "
                                  "ceiling; some frames left out)")
                    break
                small = _shrunk(frame, scratch)
                if small is None:
                    continue
                zipped.write(small, f"frames/{small.name}")
                packed.append(f"frames/{small.name}")
        finally:
            shutil.rmtree(scratch, ignore_errors=True)
    return target, packed


def _fullest_payload(folder: Path):
    """The strategy-time payload carrying the most heroes, or None."""
    best, most = None, 0
    for path in sorted((folder / "gsi").glob("gsi_*.json")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        block = payload.get("minimap")
        count = len(block) if isinstance(block, dict) else 0
        if count > most:
            best, most = payload, count
    return best


# ---- repairing rather than reporting ------------------------------------

def repair(folder: Path, dataset) -> str:
    """Measure the crop boxes off this recording and save them. A note.

    THE APP ALREADY KNOWS THE CURE FOR THE COMMONEST FAULT, and until
    now it could only apply it DURING a draft, from the banner, off a
    live frame. By the time a draft has been graded the pick bar is off
    the screen - so the frame to measure from is one of the recording's
    own, which is the same trick `tools/measure_recording.py` uses: the
    minimap names all ten heroes at strategy time, and those are the ten
    that were on the bar.

    So a stranger's FIRST bad draft fixes the boxes for every draft
    after it, with nobody pressing anything. That is worth more than the
    report it replaces.

    ALL TEN OR NOTHING. `autocal.layout_from` reads a bank's origin off
    the first portrait IN it, so a miss at the start of a bank shifts
    that whole bank one pitch and every box after it - and this writes a
    calibration a fresh install then inherits. Nine portraits answer
    which side a hero is on; it takes ten to say where the boxes go.
    """
    from .vision import autocal
    from .vision import layout as layout_mod

    ten = _ten_from(folder, dataset)
    if not ten:
        return "no strategy-time payload named ten heroes to measure against"
    art = autocal.base_portraits(ten)
    if len(art) < len(ten):
        return "this machine has no downloaded portrait for some of the ten"

    frames = sorted((folder / "frames").glob("*.png"))
    if not frames:
        return "this recording saved no frames"
    # NEWEST FIRST. The bar is fullest at the end of the draft, and a
    # frame from the first seconds of hero selection has nothing on it
    # to find - which is the same reason the two hero-selection
    # screenshots in the old sample located nothing and were right to.
    for path in reversed(frames[-_REPAIR_FRAMES:]):
        frame = _read(path)
        if frame is None:
            continue
        height, width = frame.shape[:2]
        found = autocal.locate(frame, art)
        if len(found) < 2 * _TEAM:
            continue
        fitted = autocal.layout_from(found, width, height)
        if not fitted.ok:
            continue
        layout_mod.save_calibration(fitted.layout)
        return (f"measured the crop boxes off {path.name} and saved them "
                f"({fitted.note})")
    return ("could not locate all ten portraits in any frame, so nothing "
            "was written - the boxes are unchanged")


_REPAIR_FRAMES = 12          # how far back from the end to try
_TEAM = 5


def _read(path: Path):
    import cv2
    import numpy as np

    try:
        data = np.frombuffer(path.read_bytes(), dtype=np.uint8)
    except OSError:
        return None
    return cv2.imdecode(data, cv2.IMREAD_COLOR) if data.size else None


def _ten_from(folder: Path, dataset) -> list[int]:
    """The ten hero ids the game named at strategy time, or []."""
    from .gsi import minimap as minimap_mod
    from .gsi import state as gsi_state

    payload = _fullest_payload(folder)
    if payload is None or dataset is None:
        return []
    try:
        names = gsi_state._hero_id_by_internal_name(dataset)
    except (AttributeError, TypeError):
        return []
    ids = [names.get(name)
           for _i, name, _p in minimap_mod.hero_entries(payload)]
    ids = [hid for hid in ids if hid is not None]
    return ids if len(ids) == 2 * _TEAM else []
