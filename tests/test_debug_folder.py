"""Everything you would send somebody lives under one folder.

"i want you to make sure that all error debugging, etc is all part of 1
parent folder and easy to find within the folder structure... make it
organized intuitively but all bundled in a common error or debugging
folder".
"""

import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from draft_assist import crashlog, debugdir                   # noqa: E402

ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture(autouse=True)
def _own_folder(tmp_path, monkeypatch):
    monkeypatch.setattr(debugdir, "ROOT", tmp_path)


def test_one_parent_holds_every_kind():
    kinds = set(debugdir.KINDS)
    assert kinds == {"startup", "crashes", "reports", "recordings",
                     "scratch"}
    for kind in kinds:
        assert debugdir.folder(kind).parent == debugdir.root()


def test_the_path_is_resolved_at_call_time(tmp_path, monkeypatch):
    """A default argument is evaluated once at import, which is how a
    test that repointed a path still wrote into the real repository."""
    monkeypatch.setattr(debugdir, "ROOT", tmp_path / "elsewhere")
    assert debugdir.root() == tmp_path / "elsewhere" / "debug"


def test_a_startup_run_keeps_only_the_last_three(tmp_path):
    """The owner's rule, verbatim: "only keep the last 3 logs (on the
    4th youd create a new one and delete the first log)"."""
    made = []
    for i in range(6):
        folder = debugdir.new_run("startup", when=1_700_000_000 + i * 3600)
        (folder / "setup-log.txt").write_text(f"run {i}\n")
        made.append(folder.name)
        assert len(debugdir.runs("startup")) <= 3, (
            "a fourth run must delete the first, not sit beside it")
    kept = [p.name for p in debugdir.runs("startup")]
    assert kept == made[-3:]


def test_what_the_user_owns_is_never_pruned():
    """A recording is their evidence and a report is what they sent;
    only the two that write on EVERY run have a ceiling."""
    assert debugdir.KINDS["recordings"] is None
    assert debugdir.KINDS["reports"] is None
    assert debugdir.KINDS["startup"] == 3


def test_two_runs_in_one_second_do_not_collide():
    """A crash loop is not rare, and losing the second traceback to a
    name clash loses exactly the one worth reading."""
    first = debugdir.new_run("crashes", when=1_700_000_000)
    second = debugdir.new_run("crashes", when=1_700_000_000)
    assert first != second and second.is_dir()


def test_a_folder_that_cannot_be_deleted_does_not_stop_anything(
        monkeypatch):
    """The whole point of this module is to be the thing that still
    works when something else has not."""
    for i in range(3):
        debugdir.new_run("startup", when=1_700_000_000 + i * 3600)

    def refuse(*a, **k):
        raise OSError("held open by a text editor")

    monkeypatch.setattr(debugdir.shutil, "rmtree", refuse)
    assert debugdir.prune("startup", 1) == 0        # no raise
    assert debugdir.new_run("startup").is_dir()


def test_the_old_folders_move_in_once(tmp_path):
    (tmp_path / "recordings" / "2026-01-01_120000").mkdir(parents=True)
    (tmp_path / "debug_out").mkdir()
    assert sorted(debugdir.migrate()) == ["recordings", "scratch"]
    assert (debugdir.folder("recordings") / "2026-01-01_120000").is_dir()
    assert debugdir.folder("scratch").is_dir()
    assert not (tmp_path / "recordings").exists()
    assert debugdir.migrate() == [], "migrating twice must do nothing"


def test_a_migration_never_merges(tmp_path):
    """Gigabytes of somebody's own evidence: if both exist, leave the
    old one alone for a person to look at rather than guess."""
    (tmp_path / "recordings" / "old").mkdir(parents=True)
    (debugdir.folder("recordings") / "new").mkdir(parents=True)
    assert "recordings" not in debugdir.migrate()
    assert (tmp_path / "recordings" / "old").is_dir()


def test_a_traceback_gets_its_own_dated_folder():
    try:
        raise ValueError("boom")
    except ValueError as exc:
        written = crashlog.save(exc)
    assert written is not None and written.name == "traceback.txt"
    assert written.parent.parent == debugdir.folder("crashes")
    assert "boom" in written.read_text(encoding="utf-8")


def test_a_hard_crash_is_filed_on_the_next_run():
    """Qt ABORTS rather than raising, so faulthandler's file is all
    there is - and nothing of ours runs after the signal, which is why
    it is filed one launch late."""
    crashlog.arm()
    assert crashlog.hard_crash_file().is_file()
    assert debugdir.runs("crashes") == [], "a clean run files nothing"
    crashlog.hard_crash_file().write_text("Windows fatal exception\n")
    filed = crashlog.file_away_last_crash()
    assert filed is not None
    assert (filed / "faulthandler.txt").read_text().startswith("Windows")
    assert (filed / "what-happened.txt").is_file()


def test_config_points_into_the_folder():
    """The whole app reads these two names; what moved is where they
    point, so nothing else had to change."""
    from draft_assist import config
    assert config.RECORDINGS_DIR.parent.name == debugdir.FOLDER
    assert config.DEBUG_OUT.parent.name == debugdir.FOLDER


def test_nothing_here_reaches_qt():
    """Both modules run before the QApplication exists - the crash hook
    is armed ahead of it and the launcher's steps run before the app is
    installed at all.

    THE SCAN READS THE CODE, NOT THE PROSE. `crashlog`'s own docstring
    has to NAME the QApplication to say why it must not touch one, and
    a search over raw text would fail on the sentence explaining the
    rule it is enforcing - the same trap `single.py`'s guard carries.
    """
    import ast
    for name in ("debugdir.py", "crashlog.py"):
        tree = ast.parse((ROOT / "draft_assist" / name).read_text(
            encoding="utf-8"))
        imported = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported += [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom):
                imported.append(node.module or "")
        assert not [m for m in imported if "Qt" in m or "qt" in m], name


def test_the_setup_logger_is_ascii():
    """A Windows console is cp1252, and argparse prints __doc__ for
    --help - so the docstring counts as output too."""
    text = (ROOT / "tools" / "setup_log.py").read_text(encoding="utf-8")
    bad = [c for c in text if ord(c) > 127]
    assert not bad, f"non-ASCII in the tool: {sorted(set(bad))}"


def test_a_failing_step_is_recorded_and_its_exit_code_survives(tmp_path):
    """The launcher decides what to do next from the step's own exit
    code, so the tee must pass it through rather than swallow it - and
    what the step PRINTED has to reach the log, which is the whole
    point: the console closes and this is what is left."""
    sys.path.insert(0, str(ROOT / "tools"))
    import setup_log

    assert setup_log.main(["start"]) == 0
    code = setup_log.main(["run", "a step", "--", sys.executable, "-c",
                           "import sys; print('working'); sys.exit(3)"])
    assert code == 3, "the step's own exit code must survive the tee"
    setup_log.main(["finish", "--failed", "a step"])

    logs = list((tmp_path / "debug" / "startup").glob("*/setup-log.txt"))
    assert len(logs) == 1, logs
    written = logs[0].read_text(encoding="utf-8")
    assert "working" in written, "what the step printed is in the log"
    assert "exit 3" in written and "SETUP FAILED at: a step" in written
    assert (logs[0].parent / "summary.txt").is_file()


def test_a_prompt_and_its_answer_are_recorded(tmp_path):
    """"he said yes but then something failed" is exactly the report
    this has to be able to answer, and a list of commands cannot."""
    sys.path.insert(0, str(ROOT / "tools"))
    import setup_log

    setup_log.main(["start"])
    setup_log.main(["note", "offered to update pip: answered YES"])
    setup_log.main(["finish"])
    log = next((tmp_path / "debug" / "startup").glob("*/setup-log.txt"))
    text = log.read_text(encoding="utf-8")
    assert "answered YES" in text and "SETUP OK" in text


def test_the_launcher_records_every_step_it_runs():
    """A step that is not tee'd is a step whose failure vanishes with
    the console - which is the fault this was all built for."""
    launcher = (ROOT / "Dota Draft Assist.bat").read_text(encoding="utf-8")
    for step in ("-m venv .venv", "-m pip install", "-m pip download"):
        for line in launcher.splitlines():
            if step in line and not line.strip().startswith("rem "):
                assert "setup_log.py" in line, (
                    f"this step is not recorded: {line.strip()}")
    assert 'setup_log.py" start' in launcher
    assert 'setup_log.py" finish' in launcher


def test_the_launcher_no_longer_hides_a_pip_failure():
    """`2>nul` on the offline upgrade is what left the last report
    unexplained: it failed silently and the online path took over."""
    launcher = (ROOT / "Dota Draft Assist.bat").read_text(encoding="utf-8")
    for line in launcher.splitlines():
        if "pip install" in line and not line.strip().startswith("rem "):
            assert "2>nul" not in line, line.strip()


def test_a_bundled_copy_is_never_pushed_onto_the_network_for_pip():
    """The prompt exists because the upgrade is a DOWNLOAD. A release
    zip already has pip in `wheels\\`, so asking - and on a miss
    sending them to pypi.org - was the one step that reached for the
    internet inside a bundle whose whole point is that it need not."""
    launcher = (ROOT / "Dota Draft Assist.bat").read_text(encoding="utf-8")
    offline = launcher.index("wheels\\pip-*.whl")
    prompt = launcher.index("Update pip now?")
    assert offline < prompt, "the folder is tried before anybody is asked"
    assert launcher.index("if defined PIPDONE goto :deps") < prompt
