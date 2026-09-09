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


@pytest.mark.parametrize("script", scripts(), ids=lambda p: p.name)
def test_every_probe_swallows_both_streams(script):
    """`where` writes to stderr when it finds nothing, so a probe that
    redirects only stdout still prints "INFO: Could not find files..." at
    the user. Both streams or neither."""
    for number, line in enumerate(
            script.read_text(encoding="utf-8").splitlines(), start=1):
        stripped = line.strip()
        if stripped.lower().startswith("rem ") or "where " not in stripped:
            continue
        assert ">nul 2>&1" in stripped, (
            f"{script.name}:{number} probes without silencing stderr: "
            f"{stripped}")


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
