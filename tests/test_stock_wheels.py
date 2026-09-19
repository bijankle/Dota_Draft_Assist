"""The app's packages live in the app's folder.

"i also want you to store as much on the application as possible in the
program folder itself to save setup hassle / time, for example any python
packages that it relies on.... and id want this to be updated every so
often" — and "right now when the user starts they need to download and
update a bunch of python packages and stuff liek that... pip".
"""

import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from tools import stock_wheels                                # noqa: E402

ROOT = Path(__file__).resolve().parent.parent


def test_the_cache_sits_beside_the_app():
    assert stock_wheels.wheel_dir() == ROOT / "wheels"


def test_the_path_is_resolved_at_call_time(monkeypatch, tmp_path):
    """A default argument is evaluated once at import, which is how a
    test that repointed a path still wrote into the real repository."""
    monkeypatch.setattr(stock_wheels, "ROOT", tmp_path)
    assert stock_wheels.wheel_dir() == tmp_path / "wheels"


def test_pip_itself_is_stocked():
    """An old pip is the commonest way a first run fails, and upgrading
    it was a download of its own."""
    assert "pip" in stock_wheels.ALSO


def test_it_describes_an_empty_folder_without_pretending(tmp_path,
                                                         monkeypatch):
    monkeypatch.setattr(stock_wheels, "ROOT", tmp_path)
    said = stock_wheels.describe()
    assert "empty" in said and "download" in said


def test_it_counts_and_sizes_what_is_there(tmp_path, monkeypatch):
    monkeypatch.setattr(stock_wheels, "ROOT", tmp_path)
    folder = tmp_path / "wheels"
    folder.mkdir()
    (folder / "numpy-2.0-cp312-win_amd64.whl").write_bytes(b"x" * 2_000_000)
    (folder / "pip-24.0-py3-none-any.whl").write_bytes(b"y" * 1_000_000)
    said = stock_wheels.describe()
    assert "2 package file(s)" in said and "3 MB" in said


def test_a_partial_download_is_kept_rather_than_discarded(tmp_path,
                                                          monkeypatch):
    """Off Windows the second requirements file cannot resolve at all,
    and on Windows one package may 404. What DID come down is still
    worth keeping."""
    calls = []

    class Result:
        def __init__(self, code):
            self.returncode = code

    def fake_run(argv, **kw):
        calls.append(argv)
        return Result(1 if "requirements-windows.txt" in " ".join(argv)
                      else 0)

    assert any(p.name == "requirements-windows.txt"
               for p in stock_wheels.requirement_files()), (
        "the premise: there is a file here that cannot resolve off Windows")

    monkeypatch.setattr(subprocess, "run", fake_run)
    code = stock_wheels.download(tmp_path / "wheels")
    assert code != 0, "the failure is reported"
    assert (tmp_path / "wheels").is_dir(), "the folder is still made"
    assert any("pip" in " ".join(c) for c in calls), "pip is still fetched"


def test_every_line_it_prints_is_ascii():
    """A Windows console is cp1252 and cannot encode a fancy arrow;
    argparse prints __doc__ for --help, so the docstring counts too."""
    text = (ROOT / "tools" / "stock_wheels.py").read_text(encoding="utf-8")
    bad = [c for c in text if ord(c) > 127]
    assert not bad, f"non-ASCII in the tool: {sorted(set(bad))}"


def test_check_writes_nothing(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(stock_wheels, "ROOT", tmp_path)
    monkeypatch.setattr(stock_wheels, "download",
                        lambda *a, **k: pytest.fail("--check wrote"))
    assert stock_wheels.main(["--check"]) == 0
    assert not (tmp_path / "wheels").exists()


def test_the_launcher_and_the_tool_name_the_same_folder():
    """Three places have to agree: this tool, the launcher and
    .gitignore. Two spellings is one of them going stale."""
    launcher = (ROOT / "Dota Draft Assist.bat").read_text(encoding="utf-8")
    assert f"--find-links {stock_wheels.WHEEL_DIR}" in launcher
    ignored = (ROOT / ".gitignore").read_text(encoding="utf-8").splitlines()
    assert f"{stock_wheels.WHEEL_DIR}/" in ignored
