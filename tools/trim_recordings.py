"""Delete the frames in old recordings that were never worth keeping.

    python tools/trim_recordings.py            delete all-but-the-draft
    python tools/trim_recordings.py --check    say what would go, delete nothing
    python tools/trim_recordings.py --all      delete every frame

WHY THIS EXISTS. "can you delete all the images that have been created
fro mthese old recordings... if its easy to fgilter can you keep the key
snaps of the draft menus? if not jjsut delete all those recording
capture photos".

It IS easy to filter, so the default keeps the draft. A recording used
to save a frame every second from the moment the session started, which
is the queue, the loading screen, the menu and - once Dota was closed
with a session still running - the desktop, for as long as
`MAX_SESSION`. `Recorder.wants_frame` now saves a frame only while the
pick bar could be on the screen, so this is a one-off tidy of the
recordings taken before that: a 3440x1440 PNG is about five megabytes
and a session of them is most of a gigabyte.

WHAT DECIDES. `state.jsonl` names the game state on every tick, and
`measure_recording.state_at` reads a frame's own state out of it by
file time - the same function, because two ways of answering "what was
on screen in this picture" is one of them going stale. A frame whose
state is in `BAR_IS_UP` is the draft and is kept; everything else goes.

WHAT IT NEVER TOUCHES. `state.jsonl` and the payloads: they are
kilobytes, they are what every report and every measurement is built
from, and a session with its frames gone is still readable. This
removes pictures and nothing else.

A SESSION WITH NO STATE LOG IS LEFT ALONE unless `--all` is passed. Not
knowing which frames are the draft is a reason to keep them, not a
reason to guess - the same rule the app follows everywhere about an
unresolved slot.
"""

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from draft_assist import console, record                      # noqa: E402
from draft_assist.gsi import state as gsi_state               # noqa: E402

# The states with a pick bar on the screen, DERIVED from the app's own
# set rather than typed out again - `timeline` strips the
# `DOTA_GAMERULES_STATE_` prefix, so the comparison has to be against
# the short spelling.
BAR_IS_UP = {name.replace("DOTA_GAMERULES_STATE_", "")
             for name in gsi_state.DRAFTING_STATES}


def reader():
    """`measure_recording`'s state helpers, imported at CALL time.

    NOT AT MODULE SCOPE, and the reason is not style. That module pulls
    in `autocal` and `lineup`, which pull in cv2 - and cv2 ships its own
    copy of Qt's platform plugins. Imported into a process that is also
    running this app's Qt, it changes which plugin Qt resolves, which is
    exactly what "This plugin does not support propagateSizeHints()"
    means. The whole test suite shares one QApplication, so importing
    this tool at the top of a test file was enough to fail an unrelated
    window test several files later.

    The helpers themselves are shared rather than copied: two ways of
    answering "what was on screen in this picture" is one of them going
    stale.
    """
    from tools.measure_recording import (frame_seconds, state_at,
                                         timeline)
    return frame_seconds, state_at, timeline


def recordings_dir() -> Path:
    """Resolved at CALL time, never as a default argument - a default is
    evaluated once at import, which is how a test that repointed a path
    still wrote into the real repository."""
    return ROOT / "recordings"


def frames_of(folder: Path) -> list[Path]:
    where = folder / "frames"
    if not where.is_dir():
        return []
    return sorted(p for p in where.iterdir()
                  if p.suffix.lower() in (".png", ".jpg", ".jpeg"))


def marks_of(folder: Path) -> list[tuple[float, str]]:
    """The state timeline, or an empty list when there is no log."""
    _, _, timeline = reader()
    try:
        states = record.read_states(folder)
    except Exception:
        return []
    return timeline(states)


def sort_frames(folder: Path, everything: bool = False
                ) -> tuple[list[Path], list[Path]]:
    """(keep, drop) for one session's frames.

    With no state log, nothing is dropped unless `everything` is set:
    not knowing which pictures are the draft is a reason to keep them.
    """
    frames = frames_of(folder)
    if everything:
        return [], frames
    marks = marks_of(folder)
    if not marks:
        return frames, []
    frame_seconds, state_at, _ = reader()
    seconds = frame_seconds(frames)
    keep, drop = [], []
    for path in frames:
        state = state_at(marks, seconds.get(path))
        (keep if state in BAR_IS_UP else drop).append(path)
    return keep, drop


def megabytes(paths: list[Path]) -> float:
    total = 0
    for path in paths:
        try:
            total += path.stat().st_size
        except OSError:
            pass
    return total / 1e6


def trim(root: Path, everything: bool = False, dry_run: bool = False
         ) -> tuple[int, float]:
    """Walk every session under `root`. Returns (files gone, MB freed).

    NEVER FATAL. A file held open by a picture viewer is a file this
    cannot delete, and one refusal must not cost the rest of the tidy -
    so it is counted, named once, and the walk carries on.
    """
    folders = record.sessions(root)
    if not folders:
        print("No recordings on this machine - nothing to tidy.")
        return 0, 0.0

    gone, freed, refused = 0, 0.0, 0
    for number, folder in enumerate(folders, start=1):
        console.progress(number / (len(folders) + 1), "checking recordings")
        keep, drop = sort_frames(folder, everything)
        if not drop:
            if keep:
                print(f"  {folder.name}: {len(keep)} frame(s), all draft")
            continue
        size = megabytes(drop)
        print(f"  {folder.name}: {len(drop)} to go, {len(keep)} kept "
              f"({size:.0f} MB)")
        if dry_run:
            gone += len(drop)
            freed += size
            continue
        for path in drop:
            try:
                path.unlink()
                gone += 1
                freed += path_size(path, size, len(drop))
            except OSError:
                refused += 1
    console.progress(1.0, "done")
    if refused:
        print(f"\n{refused} file(s) could not be deleted - something else "
              "has them open.")
    return gone, freed


def path_size(path: Path, total: float, count: int) -> float:
    """A deleted file cannot be measured, so its share is the average of
    the batch it was in. Close enough for a sentence saying how much
    room was freed, and it cannot raise after the unlink."""
    return total / count if count else 0.0


def main(argv: list[str] | None = None) -> int:
    console.plain_output()
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--check", action="store_true",
                        help="report what would go and delete nothing")
    parser.add_argument("--all", action="store_true", dest="everything",
                        help="delete every frame, draft or not")
    args = parser.parse_args(argv)

    root = recordings_dir()
    if args.everything:
        print("Deleting EVERY saved frame, draft or not.\n")
    else:
        print("Deleting the frames taken outside the draft. The pick bar "
              "frames stay.\n")
    gone, freed = trim(root, everything=args.everything,
                       dry_run=args.check)
    print()
    if not gone:
        print("Nothing to delete - these recordings are already just "
              "the draft.")
    elif args.check:
        print(f"Would delete {gone} frame(s), freeing about {freed:.0f} MB. "
              "Nothing was removed.")
    else:
        print(f"Deleted {gone} frame(s), freeing about {freed:.0f} MB. "
              "Every payload and state log is untouched.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
