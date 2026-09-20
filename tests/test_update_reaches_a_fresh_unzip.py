"""A shareable zip goes stale the moment the release branch moves.

"i foudn that when i use the zip version of the file i need to hit the
'update application' to get the core function of portrait recognition to
owrk properyl... i think it would be ideal that as part of the setup that
the program runs an app update... but if you cant do that then just have
it as a banner that the user is alerted to click on".

Both halves are here: the stamp that lets a fresh unzip know which build
it is at all, the automatic update before the wizard, and the banner rung
for a copy that has sat for a month.
"""

import json
import sys
import zipfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from draft_assist import config, version            # noqa: E402

ROOT = Path(__file__).resolve().parent.parent


def test_the_repository_and_branch_are_spelled_once():
    """The app checks one place and the updater downloads from another
    the moment these disagree."""
    sys.path.insert(0, str(ROOT / "tools"))
    import update_app
    assert update_app.OWNER == config.GITHUB_OWNER
    assert update_app.REPO == config.GITHUB_REPO
    assert update_app.RELEASE_BRANCH == config.RELEASE_BRANCH
    assert update_app.INSTALL_NAME == config.INSTALL_RECORD


def test_a_clone_is_never_told_it_is_out_of_date(monkeypatch):
    """A clone follows whatever branch it is tracking, so comparing it
    against `main` would put a banner over the author's own window every
    time they worked on a branch."""
    monkeypatch.setattr(version, "is_a_clone", lambda: True)
    called = []
    monkeypatch.setattr(version, "installed_sha",
                        lambda: called.append(1) or "abc")
    assert version.newer_release() == ""
    assert not called, "a clone must not even look"


def test_an_unstamped_copy_claims_nothing(monkeypatch, tmp_path):
    """No record means it cannot be compared. It is not claimed to be
    behind - `zip_update` still downloads when ASKED, which is where
    "unknown means fetch" belongs."""
    monkeypatch.setattr(version, "is_a_clone", lambda: False)
    monkeypatch.setattr(version, "ROOT", tmp_path)
    assert version.installed_sha() == ""
    assert version.newer_release() == ""


def test_the_check_answers_empty_for_every_way_of_not_knowing(monkeypatch,
                                                              tmp_path):
    """"" covers clone, no network, rate limit AND already-current.
    None of them is a fault and none should put anything on screen."""
    monkeypatch.setattr(version, "is_a_clone", lambda: False)
    monkeypatch.setattr(version, "installed_sha", lambda: "a" * 40)

    class Boom:
        def get(self, *a, **k):
            raise OSError("no network")
    monkeypatch.setitem(sys.modules, "requests", Boom())
    assert version.newer_release() == ""


def test_the_stamp_names_the_build_and_the_files(tmp_path, monkeypatch):
    """A zip that does not know which build it is cannot be told it is
    out of date, which is what sent a real user round the houses."""
    from tools import make_release
    raw = json.loads(make_release.stamp(["a.py", "b.py"]))
    assert raw["branch"] == config.RELEASE_BRANCH
    assert len(raw["sha"]) == 40, raw["sha"]
    # the FILE list too, so the first update from a shareable zip can
    # also remove files that went away rather than leaving them
    # importable - the same shape `update_app` writes.
    assert raw["files"] == ["a.py", "b.py"]


def test_a_built_zip_carries_its_own_version_record(tmp_path):
    """End to end: the thing a stranger unzips knows its own sha."""
    from tools import make_release
    out = tmp_path / "copy.zip"
    make_release.build(out, wheels=False)
    with zipfile.ZipFile(out) as zf:
        assert config.INSTALL_RECORD in zf.namelist()
        raw = json.loads(zf.read(config.INSTALL_RECORD))
    assert len(raw["sha"]) == 40
    assert raw["files"], "the record has to carry the manifest"
    # and it must never ship the key or anybody's settings
    for never in make_release.NEVER_SHIP:
        assert never not in raw["files"]


def test_the_banner_rung_reads_a_flag_and_never_the_network():
    """`_update_first_run_banner` runs four times a second. A network
    call in it would be an HTTP request per tick."""
    import ast
    tree = ast.parse((ROOT / "draft_assist" / "ui" / "app.py").read_text(
        encoding="utf-8"))
    banner = next(n for n in ast.walk(tree)
                  if isinstance(n, ast.FunctionDef)
                  and n.name == "_update_first_run_banner")
    names = {n.attr for n in ast.walk(banner) if isinstance(n, ast.Attribute)}
    assert "_newer_build" in names, "the rung must read the cached flag"
    assert "newer_release" not in names, (
        "the banner must not ask the network on the refresh loop")


def test_setup_updates_before_it_asks_anything():
    """The code first, then the questions: every step of setup then runs
    on current code, and nothing has been typed yet so the relaunch costs
    the user nothing."""
    import ast
    tree = ast.parse((ROOT / "draft_assist" / "ui" / "app.py").read_text(
        encoding="utf-8"))
    offer = next(n for n in ast.walk(tree)
                 if isinstance(n, ast.FunctionDef) and n.name == "offer_setup")
    body = ast.dump(offer)
    assert "_update_before_setup" in body
    assert body.index("_update_before_setup") < body.index("_run_setup"), (
        "the update has to come before the wizard, not after it")
