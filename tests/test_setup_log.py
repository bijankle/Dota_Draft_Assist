"""The setup log has to keep what it was written to keep.

Every line of every setup log written on Windows came out BLANK, for
the whole life of the module. pip ends its lines "\r\n"; the
progress-bar rule read that "\r" as a redraw and cleared the line one
byte before the "\n" could write it. It could not be seen from here -
on Linux a line ends with a bare "\n" - so these drive the loop with
the bytes Windows actually produces.
"""

import subprocess
import sys

from tools import setup_log


def tee_of(raw: bytes) -> list[str]:
    """Run a child that writes exactly `raw`, and return the logged lines."""
    class Sink:
        def __init__(self) -> None:
            self.lines: list[str] = []

        def write(self, text: str) -> None:
            self.lines.append(text.rstrip("\n"))

    sink = Sink()
    code = setup_log.tee(
        [sys.executable, "-c",
         "import sys; sys.stdout.buffer.write(%r); sys.stdout.buffer.flush()"
         % raw],
        sink)
    assert code == 0
    return sink.lines


def test_windows_line_endings_survive():
    """THE BUG. Two CRLF-terminated lines must arrive as two lines."""
    assert tee_of(b"ERROR: no matching distribution\r\nSETUP OK\r\n") == [
        "ERROR: no matching distribution", "SETUP OK"]


def test_unix_line_endings_still_survive():
    assert tee_of(b"one\ntwo\n") == ["one", "two"]


def test_a_redrawn_progress_bar_is_still_one_line():
    """The rule this was guarding is real and must keep working: a bar
    drawn by returning the carriage keeps only what it last said."""
    assert tee_of(b"10%\r45%\r100% done\n") == ["100% done"]


def test_a_bar_followed_by_a_real_line_keeps_both():
    assert tee_of(b"50%\r100%\r\nInstalling\r\n") == ["100%", "Installing"]


def test_a_last_line_with_no_terminator_is_kept():
    assert tee_of(b"no newline at the end") == ["no newline at the end"]


def test_the_header_records_which_python():
    """The bundle carries one numpy per Python version, so the version
    is what decides whether the offline install can work at all - and
    no log had ever said it."""
    source = (setup_log.ROOT / "tools" / "setup_log.py").read_text()
    assert 'note(f"python   {sys.version.split()[0]}")' in source


def test_an_attempt_says_it_was_allowed_to_fail(tmp_path, monkeypatch):
    """A step with a fallback behind it must not read as breakage."""
    monkeypatch.setattr(setup_log, "current", lambda: tmp_path)
    out = subprocess.run(
        [sys.executable, "-c",
         "import sys; sys.path.insert(0, %r); from tools import setup_log;"
         "setup_log.current = lambda: None;"
         "raise SystemExit(setup_log.attempt('x', [sys.executable, '-c',"
         "'raise SystemExit(1)']))" % str(setup_log.ROOT)],
        capture_output=True, text=True)
    assert out.returncode == 1
    assert "NOT a fault" in out.stdout
    assert "fallback" in out.stdout


def test_the_launcher_lets_the_offline_install_fail():
    """`try`, not `run`: --no-index cannot serve a Python the bundle was
    not built for, and the download below is the designed fallback."""
    text = (setup_log.ROOT / "Dota Draft Assist.bat").read_text(
        encoding="ascii")
    offline = [line for line in text.splitlines()
               if "--no-index" in line and "requirements.txt" in line]
    assert offline, "the offline install step has gone"
    for line in offline:
        assert '"tools\\setup_log.py" try ' in line, line
