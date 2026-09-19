"""Record what the launcher does, so a failure can be read afterwards.

    python tools/setup_log.py start
    python tools/setup_log.py run  <label> -- <command...>
    python tools/setup_log.py note <text>
    python tools/setup_log.py finish

WHY THIS EXISTS. A user answered Y to the pip prompt, a step failed, and
the message was gone before it could be read - because the launcher's
last act is `start` followed by `exit`, so cmd.exe closes the console
the moment the app appears. On the path where everything WORKED. The
guards were fine; there was simply no record.

IT TEES RATHER THAN REDIRECTING, and that distinction is the whole
design. `>nul` is what hid the original fault and made minutes of
downloading read as a frozen window; `>file` would fix the record and
bring the frozen window back. Every byte goes to both.

A PROGRESS BAR IS ONE LINE, NOT A THOUSAND. pip draws its bar by
returning the carriage and overwriting, so the console gets the bytes
exactly as pip wrote them - the bar animates - while the log keeps only
what the line said when it ended. Straight through, a captured bar is
several hundred lines of junk around the one line that matters.

WHICH FOLDER IS IN A POINTER FILE rather than a cmd.exe variable. This
app's own folder is called "Dota Draft Assist", so every path it hands
about has spaces in it, and `for /f` round a path with spaces is the
kind of quoting that works until somebody unzips it somewhere else.
"""

import argparse
import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from draft_assist import console, debugdir                   # noqa: E402

# Names the folder in use, so `run` and `finish` find what `start` made.
POINTER = "current.txt"
LOG = "setup-log.txt"
SUMMARY = "summary.txt"


def pointer() -> Path:
    return debugdir.folder("startup") / POINTER


def current() -> Path | None:
    """The folder this run is writing to, or None when `start` never ran
    (or its folder has been deleted underneath us)."""
    try:
        name = pointer().read_text(encoding="utf-8").strip()
    except OSError:
        return None
    if not name:
        return None
    where = debugdir.folder("startup") / name
    return where if where.is_dir() else None


def note(line: str) -> None:
    """Append one line to this run's log. Never fatal: a setup that
    cannot write its diary must still install the app."""
    where = current()
    if where is None:
        return
    try:
        with (where / LOG).open("a", encoding="utf-8",
                                errors="replace") as log:
            log.write(line.rstrip("\n") + "\n")
    except OSError:
        pass


def start() -> int:
    """Open a fresh folder for this run and say where it is."""
    debugdir.migrate()
    where = debugdir.new_run("startup")
    try:
        pointer().write_text(where.name, encoding="utf-8")
    except OSError:
        pass
    note(f"Dota Draft Assist setup - {time.strftime('%Y-%m-%d %H:%M:%S')}")
    note(f"folder   {ROOT}")
    note(f"platform {sys.platform}")
    note("")
    print(f"A log of this setup is being kept in {where}")
    print()
    return 0


def tee(command: list[str], out) -> int:
    """Run `command`, copying its output to the console AND to `out`.

    Bytes rather than text, deliberately. A Windows console is cp1252
    and pip prints whatever it likes; decoding here would raise inside
    the thing that exists to record a failure, which is the fault
    `console.plain_output` was written for one layer down.
    """
    env = dict(os.environ, PYTHONIOENCODING="utf-8:replace")
    try:
        # NO CONSOLE OF ITS OWN. Its output is on a PIPE and comes back
        # out of ours, so the child needs no window - and this file may
        # be run from the windowless launcher shortcut, where one would
        # flash. The app-wide rule, through the one helper.
        running = subprocess.Popen(command, stdout=subprocess.PIPE,
                                   stderr=subprocess.STDOUT, env=env,
                                   **console.no_window())
    except OSError as exc:
        message = f"could not run {command[0]}: {exc}"
        print(message)
        out.write(message + "\n")
        return 127
    line = bytearray()
    assert running.stdout is not None
    while True:
        chunk = running.stdout.read(1)
        if not chunk:
            break
        try:
            sys.stdout.buffer.write(chunk)
            sys.stdout.buffer.flush()
        except (OSError, ValueError, AttributeError):
            pass                       # no console: the log still gets it
        if chunk == b"\n":
            out.write(line.decode("utf-8", "replace") + "\n")
            line.clear()
        elif chunk == b"\r":
            line.clear()               # a redrawn progress bar
        else:
            line += chunk
    if line:
        out.write(line.decode("utf-8", "replace") + "\n")
    return running.wait()


def run(label: str, command: list[str]) -> int:
    """One step of the setup, recorded and reported."""
    where = current()
    if where is None:                  # `start` never ran: do the work
        return subprocess.call(command, **console.no_window())
    with (where / LOG).open("a", encoding="utf-8", errors="replace") as out:
        out.write(f"--- {label} ---\n")
        out.write("    " + " ".join(command) + "\n")
        code = tee(command, out)
        out.write(f"--- {label}: exit {code} ---\n\n")
    return code


def to_clipboard(text: str) -> bool:
    """Put the log where it can be pasted. `clip` ships with Windows.

    THIS IS THE HALF THE USER ASKED FOR. Reading an error off a console
    is not the problem; getting it out of one is - cmd.exe wants
    QuickEdit, a drag and a right-click, and the window had gone anyway.
    """
    if sys.platform != "win32":
        return False
    try:
        clip = subprocess.Popen(["clip"], stdin=subprocess.PIPE,
                                **console.no_window())
        clip.communicate(text.encode("utf-16-le"))
        return clip.returncode == 0
    except Exception:
        return False


def finish(ok: bool, step: str) -> int:
    """Write the verdict, and on a bad run hand the log over."""
    where = current()
    if where is None:
        return 0
    verdict = "SETUP OK" if ok else f"SETUP FAILED at: {step}"
    note("")
    note(verdict)
    try:
        (where / SUMMARY).write_text(
            "\n".join([verdict,
                       f"when   {time.strftime('%Y-%m-%d %H:%M:%S')}",
                       f"folder {ROOT}",
                       f"log    {where / LOG}"]) + "\n",
            encoding="utf-8")
    except OSError:
        pass
    if ok:
        return 0
    try:
        text = (where / LOG).read_text(encoding="utf-8", errors="replace")
    except OSError:
        text = verdict
    print()
    print("The full log of this setup was saved to:")
    print(f"    {where / LOG}")
    if to_clipboard(text):
        print()
        print("It is also ON YOUR CLIPBOARD - paste it wherever you are")
        print("reporting this and the whole thing goes with it.")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    subs = parser.add_subparsers(dest="action", required=True)
    subs.add_parser("start")
    said = subs.add_parser("note")
    said.add_argument("text", nargs="+")
    step = subs.add_parser("run")
    step.add_argument("label")
    step.add_argument("command", nargs=argparse.REMAINDER)
    done = subs.add_parser("finish")
    done.add_argument("--failed", default="", metavar="STEP")
    args = parser.parse_args(argv)

    if args.action == "start":
        return start()
    if args.action == "note":
        # WHAT THE USER WAS ASKED AND WHAT THEY ANSWERED. A log of
        # commands alone cannot say why the online path was taken, and
        # "he said yes but then something failed" is exactly the report
        # this has to be able to answer.
        note(" ".join(args.text))
        return 0
    if args.action == "run":
        command = args.command
        if command and command[0] == "--":
            command = command[1:]
        if not command:
            return 2
        return run(args.label, command)
    return finish(not args.failed, args.failed)


if __name__ == "__main__":
    raise SystemExit(main())
