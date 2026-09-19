"""The one file the user double-clicks, checked for Windows correctness.

Nothing here can RUN the launcher — this is Linux, and cmd.exe is the
whole point of the file — so these read it instead. That is worth doing
because its failures land on somebody else's machine on their first run,
where there is no traceback and no way to ask them for one, and because
the app it starts is the only thing they can see when it does not work.
"""

from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
LAUNCHER = REPO_ROOT / "Dota Draft Assist.bat"


def scripts() -> list[Path]:
    return sorted(p for p in REPO_ROOT.glob("*.bat")
                  if ".venv" not in p.parts)


def test_there_is_exactly_one_launcher():
    """Every maintenance action is a menu item inside the app; do not add
    new .bat files."""
    assert scripts() == [LAUNCHER]


@pytest.mark.parametrize("script", scripts(), ids=lambda p: p.name)
def test_no_batch_file_redirects_the_unix_way(script):
    """`>/dev/null` is a PATH to cmd.exe. It cannot find it, so it prints
    "The system cannot find the path specified." and carries on — which
    is what a first run looked like on a default Windows install, before
    the setup had done anything at all.

    This shipped in the two `where` lines that pick the Python command,
    which is the worst place for it: they run before anything else, so
    the error was the first thing a new user ever saw.
    """
    text = script.read_text(encoding="utf-8", errors="replace")
    assert "/dev/null" not in text, (
        f"{script.name} redirects the Unix way; cmd.exe wants >nul")


def probes(line: str) -> bool:
    """Does this line RUN `where`, as opposed to mentioning it?

    The first version asked whether the string "where " appeared
    anywhere, which is true of any English sentence using the word — and
    `echo ... picks up where it left off` is not a probe. A guard that
    fires on prose is one the next person edits around rather than
    obeys, so this looks at the COMMAND: the first word of the line, or
    of anything cmd.exe would start a new command at.
    """
    if line.strip().lower().startswith("rem "):
        return False
    run = line
    for joiner in ("&&", "||", "&", "|", "("):
        run = run.replace(joiner, "\n")
    return any(part.strip().lower().startswith("where ")
               for part in run.split("\n"))


@pytest.mark.parametrize("script", scripts(), ids=lambda p: p.name)
def test_every_probe_swallows_both_streams(script):
    """`where` writes to stderr when it finds nothing, so a probe that
    redirects only stdout still prints "INFO: Could not find files..." at
    the user. Both streams or neither."""
    found = 0
    for number, line in enumerate(
            script.read_text(encoding="utf-8").splitlines(), start=1):
        if not probes(line):
            continue
        found += 1
        assert ">nul 2>&1" in line, (
            f"{script.name}:{number} probes without silencing stderr: "
            f"{line.strip()}")
    assert found, f"{script.name} has no `where` probe left to check"


def test_the_probe_guard_still_catches_a_bare_where():
    """The narrowing above must not have narrowed it into uselessness."""
    assert probes("where py >nul 2>&1 && set PYCMD=py")
    assert probes("    where winget >nul 2>&1 || exit /b 0")
    assert probes("if x==y (where git) else echo no")
    assert not probes("echo it picks up where it left off")
    assert not probes("rem where this came from")


@pytest.mark.parametrize("script", scripts(), ids=lambda p: p.name)
def test_the_launcher_does_not_ask_for_the_key_itself(script):
    """It used to copy .env.example over and open it in Notepad, so a new
    user was asked for a Stratz key TWICE: once by a text editor before
    the app had opened, and again by the first-run wizard inside it.

    The wizard is the better of the two — it checks the key against
    Stratz before accepting it, and takes the rank brackets in the same
    pass — so the script builds the environment and starts the app, and
    nothing else. It writes .env itself when it needs to.
    """
    text = script.read_text(encoding="utf-8")
    body = "\n".join(line for line in text.splitlines()
                     if not line.strip().lower().startswith("rem "))
    assert "notepad" not in body.lower(), (
        "the app asks for the key, in a dialog that verifies it")
    assert ".env.example" not in body, (
        "a .env full of the placeholder is not a setup step")


def test_the_venv_guard_tests_pyvenv_cfg_not_the_interpreter():
    """`pythonw.exe` is a COPY that happens to sit in `Scripts\\`;
    `pyvenv.cfg` is what makes the folder a virtual environment at all.

    Guarded on the interpreter, a .venv that had lost its pyvenv.cfg
    went straight to :launch and Windows answered "failed to locate
    pyvenv.cfg: The system cannot find the file specified." in a dialog
    with nothing behind it. The launcher could not repair what it had
    not noticed, so it failed the same way on every double-click — the
    one failure mode this file exists to keep off somebody else's
    machine.
    """
    text = LAUNCHER.read_text(encoding="utf-8")
    assert "pyvenv.cfg" in text, "the guard cannot see a gutted .venv"
    jump = text.index("goto :launch")
    assert text.index('if exist ".venv\\pyvenv.cfg"') < jump, (
        "pyvenv.cfg must be checked before the launch shortcut is taken")


def test_a_broken_venv_is_rebuilt_rather_than_reported():
    """The app's standing rule: do the thing rather than name it.

    Telling somebody to delete a folder is the answer this launcher
    exists to avoid, and `python -m venv` on an existing directory
    repairs it in place — so nothing of theirs is deleted to fix it.
    """
    text = LAUNCHER.read_text(encoding="utf-8")
    assert "rmdir" not in text, "a repair must not delete the user's folder"
    assert ":firstrun" in text and ":setup" in text, (
        "the repair path must reach the same environment build")


# ---- the prerequisites --------------------------------------------------

def body() -> str:
    """The launcher with its commentary removed. Every rule below is
    about what the script DOES; a `rem` explaining a past bug must not
    satisfy a test looking for the fix."""
    return "\n".join(
        line for line in LAUNCHER.read_text(encoding="utf-8").splitlines()
        if not line.strip().lower().startswith("rem "))


def test_a_missing_python_offers_to_install_it():
    """"make sure that if the user doesnt have pyton... that it
    autoamtically downloads / installs wwith the users permission, or as
    a minimum has a step to downlaod it and givcfes the website link."
    Both halves: winget where it exists, the link where it does not."""
    text = body()
    assert "winget install" in text, "no automatic route"
    assert "Python.Python" in text, "winget needs the package id"
    assert "choice /c YN" in text, "nothing may be installed unasked"
    assert "https://www.python.org/downloads/" in text, "no manual route"


def test_nothing_is_installed_without_being_asked():
    """Every `winget install` in the file sits after a prompt."""
    lines = body().splitlines()
    for number, line in enumerate(lines):
        if "winget install" not in line:
            continue
        before = "\n".join(lines[max(0, number - 12):number])
        assert "choice /c YN" in before, (
            f"line {number + 1} installs without asking first")


def test_pip_is_offered_and_guarded():
    """A real user was turned around here: the upgrade was hidden by a
    redirect, had no failure guard, and was never offered. He saw an
    error he did not read, "press any key", and the window closing."""
    text = body()
    upgrades = [ln for ln in text.splitlines()
                if "pip install --upgrade pip" in ln]
    assert upgrades, "the pip upgrade has gone"
    for line in upgrades:
        assert ">nul" not in line, (
            "a silent upgrade reads as a frozen window: " + line.strip())
        assert "||" in line, (
            "an upgrade that fails must not fall through to the next "
            "step, where the error names neither pip nor the upgrade")


def test_every_long_step_says_it_is_working():
    """Minutes of silence is the frozen-application fault this project
    has a standing rule about."""
    text = body()
    for step in ("-m venv .venv", "-r requirements.txt"):
        assert step in text, f"{step} has gone"
    assert "takes a few minutes" in text


def test_the_setup_never_sends_anybody_to_a_download_for_python():
    """The link is the FALLBACK for a PC with no winget, and it has to
    stay reachable - but it must not be the first thing offered."""
    text = body()
    winget = text.index("winget install")
    link = text.index("https://www.python.org/downloads/")
    assert winget < link, "the automatic route comes first"


def test_a_version_floor_is_actually_checked():
    """"Python 3.11 or newer is required" was printed and never tested,
    so an older Python, and the Microsoft Store stub that ships on PATH,
    both got through and failed later where the error names neither."""
    text = body()
    assert "version_info >= (3, 11)" in text, (
        "the floor is asserted in prose and not in code")


def test_failure_puts_the_thing_to_do_last():
    """He pressed a key without reading a page of text above it."""
    text = body()
    tail = text[text.index(":failed"):]
    do_it = tail.rindex("RUN THIS FILE AGAIN")
    prompt = tail.rindex("pause")
    assert do_it < prompt, "the advice must sit next to the prompt"


# ---- the packages live in the folder ------------------------------------

def test_the_packages_are_installed_from_the_folder_before_the_network():
    """"i also want you to store as much on the application as possible
    in the program folder itself to save setup hassle / time, for example
    any python packages that it relies on."

    A stocked cache makes a repaired .venv free, a second install
    instant, and a COPY of this folder work on another PC with no
    download at all."""
    text = body()
    offline = text.index("--no-index --find-links wheels -r requirements")
    online = text.index("pip download -r requirements")
    assert offline < online, "the folder has to be tried first"


def test_the_network_is_still_reachable_when_the_cache_cannot_serve():
    """`--no-index` on the fallback would turn a half-stocked folder
    into a setup that cannot finish at all."""
    text = body()
    fallback = [ln for ln in text.splitlines()
                if "pip install --find-links wheels -r" in ln]
    assert fallback, "no online fallback"
    for line in fallback:
        assert "--no-index" not in line, (
            "the fallback must be allowed to reach pypi.org: " + line)


def test_pip_itself_is_taken_from_the_folder_first():
    """An old pip is the commonest way a first run fails, and upgrading
    it was a download of its own."""
    text = body()
    assert "--find-links wheels --upgrade pip" in text


def test_the_wheels_folder_is_never_committed():
    """The ZIP updater fetches every TRACKED file, so 181 MB of wheels
    in the repository is 181 MB on every press of Update - against the
    owner's own standing rule that the update is the code and nothing
    else. Git also keeps every version for ever, so each refresh would
    add another 181 MB to every clone."""
    import subprocess

    ignored = (LAUNCHER.parent / ".gitignore").read_text(encoding="utf-8")
    assert "wheels/" in ignored.splitlines(), "wheels/ is not gitignored"
    tracked = subprocess.run(
        ["git", "ls-files", "wheels"], cwd=LAUNCHER.parent,
        capture_output=True, text=True).stdout.strip()
    assert not tracked, f"wheels are committed: {tracked.splitlines()[:3]}"
