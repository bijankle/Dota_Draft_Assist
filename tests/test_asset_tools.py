"""The artwork download: what it needs, and that it can always say so.

Two faults met on the user's first Windows install and this file holds
both shut. The alternative-portraits step wanted the STATISTICS dataset
for nothing but hero names, so skipping the Stratz key at setup made it
raise; and the handler that caught the raise then died printing it,
because the message carried a character a Windows console cannot encode.
The second is the worse of the two: it turned a reported failure into an
unreported one, and the user never saw the actual cause.
"""

import io
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from draft_assist import console                       # noqa: E402
from tools import fetch_assets, fetch_custom_portraits  # noqa: E402

CONSOLE_TOOLS = (Path("tools/fetch_assets.py"),
                 Path("tools/fetch_custom_portraits.py"))


def cp1252_stream() -> io.TextIOWrapper:
    """A Windows console, as far as anything printing to it can tell."""
    return io.TextIOWrapper(io.BytesIO(), encoding="cp1252", newline="")


def test_a_failure_is_reported_even_on_a_windows_console(monkeypatch):
    """The bug exactly: the handler must not die reporting the error.

    The original message said "Setup <U+25B8> Download", which cp1252
    cannot encode, so `run` raised UnicodeEncodeError from inside its own
    `except` — and the FileNotFoundError it had caught was never printed.
    """
    out = cp1252_stream()
    monkeypatch.setattr(sys, "stdout", out)

    def explode():
        raise FileNotFoundError(r"No dataset cache at C:\x\dataset.npz")

    assert fetch_assets.run("Alternative hero portraits", explode) is False

    out.flush()
    printed = out.buffer.getvalue().decode("cp1252")
    assert "did not finish" in printed
    assert "No dataset cache" in printed          # the CAUSE, not just a name
    assert "Settings > Downloads" in printed      # and the way to retry


def test_a_step_that_works_says_so_and_does_not_report_a_failure(monkeypatch):
    out = cp1252_stream()
    monkeypatch.setattr(sys, "stdout", out)
    assert fetch_assets.run("Hero portraits and item icons", lambda: None)
    out.flush()
    assert "did not finish" not in out.buffer.getvalue().decode("cp1252")


def test_a_keyboard_interrupt_is_still_a_keyboard_interrupt(monkeypatch):
    """`except BaseException` must not swallow the user's Ctrl-C."""
    monkeypatch.setattr(sys, "stdout", cp1252_stream())

    def interrupted():
        raise KeyboardInterrupt

    with pytest.raises(KeyboardInterrupt):
        fetch_assets.run("Hero portraits and item icons", interrupted)


@pytest.mark.parametrize("path", CONSOLE_TOOLS, ids=lambda p: p.name)
def test_console_tools_print_nothing_a_windows_console_cannot_encode(path):
    """Not just the one arrow that was found: the whole file.

    Comments and docstrings are exempt only in the sense that they are
    not printed — this checks every line, because the failure mode is a
    character reaching `print`, and the cheapest way to be sure is for
    the file not to contain one at all.
    """
    offenders = []
    for number, line in enumerate(path.read_text(encoding="utf-8")
                                  .splitlines(), start=1):
        if line.lstrip().startswith("#"):
            continue
        for char in line:
            try:
                char.encode("cp1252")
            except UnicodeEncodeError:
                offenders.append(f"{path}:{number}: {char!r} (U+{ord(char):04X})")
    assert not offenders, (
        "cp1252 cannot encode these, and a Windows console is cp1252:\n  "
        + "\n  ".join(offenders))


def test_say_survives_a_stream_that_refuses_the_character(monkeypatch):
    """The last resort, for when the stream cannot be reconfigured."""
    out = cp1252_stream()
    monkeypatch.setattr(sys, "stdout", out)
    console.say("Settings \u25b8 Downloads")           # would raise on print
    out.flush()
    assert "Settings ? Downloads" in out.buffer.getvalue().decode("cp1252")


def test_plain_output_makes_the_stream_stop_raising(monkeypatch):
    out = cp1252_stream()
    monkeypatch.setattr(sys, "stdout", out)
    console.plain_output()
    print("a \u25b8 b")                                 # plain print, no helper
    sys.stdout.flush()
    assert "a ? b" in out.buffer.getvalue().decode("cp1252")


def test_plain_output_survives_having_no_streams_at_all(monkeypatch):
    """pythonw.exe: `sys.stdout` is None, and this must not be the crash."""
    monkeypatch.setattr(sys, "stdout", None)
    monkeypatch.setattr(sys, "stderr", None)
    console.plain_output()


def test_hero_names_need_no_stratz_key(monkeypatch):
    """The root cause: names came from the statistics dataset.

    With no dataset on disk it must fall back to OpenDota's public
    constants — the same keyless source the base portraits come from —
    rather than raising and taking the whole artwork run down.
    """
    def no_dataset(*_a, **_k):
        raise FileNotFoundError("No dataset cache at /nowhere/dataset.npz")

    monkeypatch.setattr(fetch_custom_portraits.store, "load", no_dataset)
    monkeypatch.setattr(fetch_custom_portraits.opendota, "fetch_heroes",
                        lambda: {14: {"name": "Pudge"}, 22: {"name": "Zeus"}})
    assert fetch_custom_portraits.hero_names() == {14: "Pudge", 22: "Zeus"}


def test_hero_names_prefer_the_dataset_when_there_is_one(monkeypatch):
    """Free and offline: no request when the answer is already on disk."""
    class Ds:
        hero_ids = [14]

        def name(self, _hid):
            return "Pudge"

    def must_not_be_called():
        raise AssertionError("asked OpenDota with a dataset already on disk")

    monkeypatch.setattr(fetch_custom_portraits.store, "load", lambda: Ds())
    monkeypatch.setattr(fetch_custom_portraits.opendota, "fetch_heroes",
                        must_not_be_called)
    assert fetch_custom_portraits.hero_names() == {14: "Pudge"}


def test_a_missing_expected_hero_is_named(capsys):
    got = set(fetch_custom_portraits.EXPECTED) - {"Pudge", "Zeus"}
    fetch_custom_portraits.report_missing(got)
    printed = capsys.readouterr().out
    assert "Pudge" in printed and "Zeus" in printed


def test_a_full_house_says_nothing(capsys):
    """Silence is the good answer, and the first real run gave it."""
    fetch_custom_portraits.report_missing(set(fetch_custom_portraits.EXPECTED))
    assert capsys.readouterr().out == ""


def test_the_task_runner_declares_one_encoding_at_both_ends():
    """The other half of the same bug: the pipe the app spawns tools on.

    `text=True` alone decodes by the machine's locale, and the child
    encodes by it too — cp1252 on Windows, which is where the crash
    happened. Both ends say UTF-8 or a tool's output is at the mercy of
    a codepage nobody set deliberately.
    """
    source = Path("draft_assist/ui/tasks.py").read_text(encoding="utf-8")
    assert 'PYTHONIOENCODING' in source          # what the child writes
    assert 'encoding="utf-8"' in source          # what we read
    assert 'errors="replace"' in source          # and neither may raise
