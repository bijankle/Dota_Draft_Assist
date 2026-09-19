"""The zip that carries the app AND every package it runs on.

"can you package all of the requirements within the app itself? the app
requirements num py open cv etc they can jsut be kept static forever...
so the user never needs to preinstall them".
"""

import sys
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from tools import make_release, stock_wheels                  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent


def test_the_manifest_is_gits_own_tracked_list():
    """The same manifest the ZIP updater installs, so what a stranger
    unzips is what an update would give them, plus the packages."""
    names = make_release.tracked()
    assert "Dota Draft Assist.bat" in names
    assert "draft_assist/ui/app.py" in names
    assert not any(name.startswith("wheels/") for name in names), (
        "the wheels are not tracked, which is the whole arrangement")


def test_nothing_personal_is_ever_packed():
    """Belt and braces over git's own list, for the day somebody commits
    a .env by accident - the same list `update_app.NEVER_WRITE` keeps."""
    for name in (".env", "ui_settings.json", "preferences.json",
                 "history_accounts.json", "calibration_local.json"):
        assert not make_release.wanted(name), name
        assert not make_release.wanted(f"some/where/{name}"), name
    assert make_release.wanted("draft_assist/ui/app.py")


def test_it_builds_the_app_without_any_packages(tmp_path):
    out = tmp_path / "app.zip"
    count, size = make_release.build(out, wheels=False)
    assert count > 100 and size > 0.5
    with zipfile.ZipFile(out) as zf:
        names = zf.namelist()
    assert "Dota Draft Assist.bat" in names
    assert not any(n.startswith("wheels/") for n in names)


def test_the_packages_go_in_beside_the_launcher(tmp_path, monkeypatch):
    """`wheels/` is exactly where the launcher's `--find-links` looks, so
    an unzipped bundle installs offline with nothing else done to it."""
    fake = tmp_path / "wheels"
    fake.mkdir()
    (fake / "numpy-2.5.3-cp312-cp312-win_amd64.whl").write_bytes(b"z" * 2048)
    monkeypatch.setattr(stock_wheels, "stocked",
                        lambda: sorted(fake.iterdir()))
    out = tmp_path / "bundle.zip"
    make_release.build(out)
    with zipfile.ZipFile(out) as zf:
        names = zf.namelist()
    assert "wheels/numpy-2.5.3-cp312-cp312-win_amd64.whl" in names
    launcher = (ROOT / "Dota Draft Assist.bat").read_text(encoding="utf-8")
    assert f"--find-links {stock_wheels.WHEEL_DIR}" in launcher


def test_a_wheel_is_stored_rather_than_recompressed(tmp_path, monkeypatch):
    """A wheel is already a zip. Deflating 240 MB of them again costs
    minutes and saves nothing."""
    fake = tmp_path / "wheels"
    fake.mkdir()
    (fake / "big-1.0-py3-none-any.whl").write_bytes(b"a" * 100_000)
    monkeypatch.setattr(stock_wheels, "stocked",
                        lambda: sorted(fake.iterdir()))
    out = tmp_path / "bundle.zip"
    make_release.build(out)
    with zipfile.ZipFile(out) as zf:
        info = zf.getinfo("wheels/big-1.0-py3-none-any.whl")
        source = zf.getinfo("Dota Draft Assist.bat")
    assert info.compress_type == zipfile.ZIP_STORED
    assert source.compress_type == zipfile.ZIP_DEFLATED, (
        "the source is text and is worth compressing")


def test_an_empty_cache_says_so_rather_than_shipping_a_lie(tmp_path,
                                                           monkeypatch,
                                                           capsys):
    """A zip that claims to carry the packages and does not is the worst
    of the three outcomes - it fails on somebody else's machine."""
    monkeypatch.setattr(stock_wheels, "stocked", list)
    make_release.build(tmp_path / "bundle.zip")
    said = capsys.readouterr().out
    assert "no packages" in said.lower()
    assert "stock_wheels.py --windows" in said


def test_the_bundle_is_never_committed():
    """The ZIP updater fetches every TRACKED file. 240 MB in the
    repository is 240 MB on every press of Update, for ever."""
    ignored = (ROOT / ".gitignore").read_text(encoding="utf-8").splitlines()
    assert "dist/" in ignored
    assert "wheels/" in ignored


def test_it_covers_more_than_one_python_version():
    """numpy and pywin32 are built per version; everything else here is
    abi3 or pure, so covering three costs about 50 MB rather than three
    times the whole set. A bundle pinned to one version is one that
    fails on the next machine."""
    assert len(stock_wheels.PY_VERSIONS) >= 3
    assert stock_wheels.PLATFORM == "win_amd64"


def test_every_line_it_prints_is_ascii():
    text = (ROOT / "tools" / "make_release.py").read_text(encoding="utf-8")
    bad = [c for c in text if ord(c) > 127]
    assert not bad, f"non-ASCII in the tool: {sorted(set(bad))}"


def test_a_copy_that_was_unzipped_can_still_build_one(tmp_path,
                                                      monkeypatch):
    """There are two kinds of install and the owner may be on either.

    A clone asks git; a copy unzipped from GitHub has no .git and may
    have no git installed - and telling somebody to install git to
    build a zip whose whole point is that nobody installs anything is
    the joke this tool exists to avoid.
    """
    monkeypatch.setattr(make_release, "ROOT", tmp_path)
    monkeypatch.setattr(make_release, "from_git", list)
    (tmp_path / "installed_version.json").write_text(
        '{"branch": "main", "sha": "abc", '
        '"files": ["Dota Draft Assist.bat", "draft_assist/ui/app.py"]}',
        encoding="utf-8")
    assert make_release.tracked() == ["Dota Draft Assist.bat",
                                      "draft_assist/ui/app.py"]


def test_neither_route_says_what_to_do(tmp_path, monkeypatch):
    """Doing nothing silently is indistinguishable from being broken."""
    import pytest
    monkeypatch.setattr(make_release, "ROOT", tmp_path)
    monkeypatch.setattr(make_release, "from_git", list)
    with pytest.raises(SystemExit) as stop:
        make_release.tracked()
    assert "Update application" in str(stop.value)
