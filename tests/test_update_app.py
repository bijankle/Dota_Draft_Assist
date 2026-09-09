"""The update step, against real git repositories in a temp directory.

The bug this covers was reported from a real machine: the Update button
ran `git pull --rebase --autostash` and got

    There is no tracking information for the current branch.

so these build the checkout that produces that — a branch with no
upstream, against a remote that carries no `main` or `master` — and run
the real thing at it. A test of the resolution ladder alone would not
have caught a wrong git invocation, which is the half that actually
failed.
"""

import json
import shutil
import subprocess

import pytest

from tools import update_app

pytestmark = pytest.mark.skipif(shutil.which("git") is None,
                                reason="git is not installed here")


def git(where, *args, check=True):
    return subprocess.run(["git", "-C", str(where), *args], check=check,
                          capture_output=True, text=True).stdout.strip()


def a_remote(tmp_path, branch="claude/work"):
    """A bare repo carrying ONE branch, which is this app's own shape."""
    origin = tmp_path / "dota_draft_assist.git"
    seed = tmp_path / "seed"
    subprocess.run(["git", "init", "--bare", "-q", str(origin)], check=True)
    subprocess.run(["git", "clone", "-q", str(origin), str(seed)], check=True)
    git(seed, "config", "user.email", "t@example.com")
    git(seed, "config", "user.name", "Test")
    git(seed, "checkout", "-q", "-b", branch)
    (seed / "app.py").write_text("first\n", encoding="utf-8")
    git(seed, "add", "-A")
    git(seed, "commit", "-qm", "first")
    git(seed, "push", "-q", "origin", branch)
    # The bare repo's HEAD still names the branch `git init` invented, which
    # does not exist — clone that and you get no working tree at all. Point
    # it at the branch that IS there, which is what GitHub does.
    git(origin, "symbolic-ref", "HEAD", f"refs/heads/{branch}")
    return origin, seed


def a_checkout(tmp_path, origin, *, branch="master", track=False):
    """A clone sitting on a branch that does NOT track anything."""
    work = tmp_path / "work"
    subprocess.run(["git", "clone", "-q", str(origin), str(work)], check=True)
    git(work, "config", "user.email", "t@example.com")
    git(work, "config", "user.name", "Test")
    if not track:
        # A local branch made by hand: no upstream, and a name the remote
        # does not carry. This is the reported checkout.
        git(work, "checkout", "-q", "-b", branch)
    return work


def new_commit(seed, branch, text="second"):
    (seed / "app.py").write_text(text + "\n", encoding="utf-8")
    git(seed, "add", "-A")
    git(seed, "commit", "-qm", text)
    git(seed, "push", "-q", "origin", branch)


# ------------------------------------------------------- the ladder ----

def test_an_upstream_is_used_when_the_branch_has_one():
    target, why = update_app.choose_target(
        "main", "origin/main", ["main", "other"], "main")
    assert target == "origin/main"
    assert "tracking" in why


def test_a_branch_of_the_same_name_is_next():
    target, why = update_app.choose_target(
        "claude/work", "", ["main", "claude/work"], "main")
    assert target == "origin/claude/work"


def test_then_the_release_branch_whatever_the_default_says():
    """`main` is what a stranger's copy follows, so once the remote has one
    a checkout with nothing better to go on lands there — even if the
    repository's default branch has been pointed somewhere else."""
    target, why = update_app.choose_target("master", "", ["main", "dev"],
                                           "dev")
    assert target == "origin/main"
    assert "release branch" in why


def test_then_the_remotes_default_branch():
    target, why = update_app.choose_target("master", "", ["stable", "dev"],
                                           "stable")
    assert target == "origin/stable"
    assert "default" in why


def test_and_finally_a_remote_with_exactly_one_branch():
    """Which is this repository today: no `main`, no `master`, one branch.
    A checkout sitting on `master` has nothing to track and nothing to
    guess from — but with one branch on the remote there is no ambiguity
    to protect anybody from."""
    target, why = update_app.choose_target("master", "", ["claude/work"], "")
    assert target == "origin/claude/work"
    assert "only branch" in why


def test_several_branches_and_no_match_is_refused_not_guessed():
    """Pulling somebody's half-finished branch into their working copy
    because it sorted first is worse than saying so."""
    target, why = update_app.choose_target("master", "", ["dev", "spike"], "")
    assert target is None
    assert "git pull --rebase origin <branch>" in why


def test_a_remote_with_no_branches_says_so():
    target, why = update_app.choose_target("master", "", [], "")
    assert target is None
    assert "no branches" in why


# ------------------------------------------------- only this repo ----

def test_it_refuses_a_remote_that_is_not_this_app():
    """The match history analyser was folded in from another repository
    and nothing may reach back to it."""
    with pytest.raises(update_app.Refused) as refused:
        update_app.check_remote("https://github.com/bijankle/"
                                "DotaGameHistoryAnalyser")
    assert "not this app" in str(refused.value)
    assert "DotaGameHistoryAnalyser" in str(refused.value)


def test_a_checkout_with_no_origin_is_told_what_happened():
    with pytest.raises(update_app.Refused) as refused:
        update_app.check_remote("")
    assert "no 'origin' remote" in str(refused.value)


def test_this_repositorys_own_remote_passes():
    for url in ("https://github.com/bijankle/Dota_Draft_Assist",
                "git@github.com:bijankle/Dota_Draft_Assist.git",
                "https://github.com/BIJANKLE/dota_draft_assist.git"):
        update_app.check_remote(url)         # no exception


# ------------------------------------------------- against real git ----

def test_it_updates_a_branch_that_tracks_nothing(tmp_path, monkeypatch,
                                                 capsys):
    """The reported failure, end to end: local `master`, no upstream, and a
    remote with no `master` on it at all."""
    origin, seed = a_remote(tmp_path)
    work = a_checkout(tmp_path, origin)
    monkeypatch.setattr(update_app, "REPO_ROOT", work)
    assert git(work, "rev-parse", "--abbrev-ref", "HEAD") == "master"

    new_commit(seed, "claude/work")
    update_app.main()

    assert (work / "app.py").read_text(encoding="utf-8").strip() == "second"
    # And the tracking is set, so the next update is an ordinary pull.
    assert git(work, "rev-parse", "--abbrev-ref", "--symbolic-full-name",
               "@{upstream}") == "origin/claude/work"
    assert "claude/work" in capsys.readouterr().out


def test_it_updates_when_the_remote_names_no_default_branch(tmp_path,
                                                            monkeypatch,
                                                            capsys):
    """`origin/HEAD` can name a branch that is no longer there — a default
    branch that was renamed or deleted leaves it dangling, and this
    repository's remote HEAD still names a `master` it does not carry.
    With one branch on the remote there is no ambiguity to resolve."""
    origin, seed = a_remote(tmp_path)
    work = a_checkout(tmp_path, origin)
    # Point both HEADs at a branch that does not exist.
    git(origin, "symbolic-ref", "HEAD", "refs/heads/master")
    git(work, "symbolic-ref", "refs/remotes/origin/HEAD",
        "refs/remotes/origin/master")
    monkeypatch.setattr(update_app, "REPO_ROOT", work)

    new_commit(seed, "claude/work")
    update_app.main()

    assert (work / "app.py").read_text(encoding="utf-8").strip() == "second"
    assert "only branch" in capsys.readouterr().out


def test_local_edits_survive_the_update(tmp_path, monkeypatch):
    """`--autostash` is the whole reason the item rules can be edited by
    hand: an update must never be a reason to lose them."""
    origin, seed = a_remote(tmp_path)
    work = a_checkout(tmp_path, origin)
    monkeypatch.setattr(update_app, "REPO_ROOT", work)
    (work / "rules.yaml").write_text("mine\n", encoding="utf-8")
    git(work, "add", "-A")
    git(work, "commit", "-qm", "my rules")
    (work / "rules.yaml").write_text("mine, edited\n", encoding="utf-8")

    new_commit(seed, "claude/work")
    update_app.main()

    assert (work / "rules.yaml").read_text(encoding="utf-8") == "mine, edited\n"
    assert (work / "app.py").read_text(encoding="utf-8").strip() == "second"


def test_a_second_update_is_an_ordinary_pull(tmp_path, monkeypatch, capsys):
    origin, seed = a_remote(tmp_path)
    work = a_checkout(tmp_path, origin)
    monkeypatch.setattr(update_app, "REPO_ROOT", work)
    new_commit(seed, "claude/work")
    update_app.main()
    capsys.readouterr()

    new_commit(seed, "claude/work", "third")
    update_app.main()
    assert (work / "app.py").read_text(encoding="utf-8").strip() == "third"
    assert "tracking origin/claude/work" in capsys.readouterr().out


def test_it_refuses_to_update_from_another_repository(tmp_path, monkeypatch):
    """An origin that is not this app is named rather than pulled from."""
    origin, _seed = a_remote(tmp_path)
    work = a_checkout(tmp_path, origin)
    elsewhere = tmp_path / "someoneelse.git"
    subprocess.run(["git", "init", "--bare", "-q", str(elsewhere)], check=True)
    git(work, "remote", "set-url", "origin", str(elsewhere))
    monkeypatch.setattr(update_app, "REPO_ROOT", work)
    with pytest.raises(update_app.Refused) as refused:
        update_app.main()
    assert "not this app" in str(refused.value)


# ------------------------------------------------- when git is absent ----

def test_a_machine_without_git_is_told_in_one_sentence(tmp_path, monkeypatch):
    """The app runs, reads the draft and analyses match history without
    git. Update is the one thing that needs it, so that is what it says —
    not a traceback about a missing executable."""
    work = tmp_path / "work"
    (work / ".git").mkdir(parents=True)
    monkeypatch.setattr(update_app, "REPO_ROOT", work)

    real = subprocess.run

    def no_git(argv, *args, **kwargs):
        if argv and argv[0] == "git":
            raise FileNotFoundError(2, "No such file or directory: 'git'")
        return real(argv, *args, **kwargs)

    monkeypatch.setattr(subprocess, "run", no_git)
    with pytest.raises(update_app.Refused) as refused:
        update_app.main()
    message = str(refused.value)
    assert "git is not installed" in message
    assert "git-scm.com" in message
    # And it names the way out that needs nothing installed: without .git
    # this same button downloads the new version instead.
    assert "delete the .git folder" in message


# ------------------------------------------------ a downloaded copy ----
#
# No .git at all is what GitHub's "Download ZIP" leaves behind, and it is
# what almost anybody handed this app will have — installing git is where
# most people stop. It used to be refused with instructions to clone.


def an_archive(tmp_path, files, name="release.zip", root="Dota-main"):
    """A GitHub-shaped archive: everything under one top-level folder."""
    import zipfile
    path = tmp_path / name
    with zipfile.ZipFile(path, "w") as zf:
        for relative, text in files.items():
            zf.writestr(f"{root}/{relative}", text)
    return path


def a_copy(tmp_path, monkeypatch, files=(), sha=""):
    """An install with no .git, holding the user's own untracked files."""
    work = tmp_path / "copied"
    work.mkdir()
    for relative, text in dict(files).items():
        target = work / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")
    monkeypatch.setattr(update_app, "REPO_ROOT", work)
    monkeypatch.setattr(update_app, "head_sha", lambda *a, **k: sha)
    return work


def serve(monkeypatch, archive):
    monkeypatch.setattr(update_app, "download",
                        lambda branch, into: archive)


def test_a_downloaded_copy_updates_without_git(tmp_path, monkeypatch, capsys):
    """The whole point: a stranger who never installed git presses Update
    and gets the new version."""
    work = a_copy(tmp_path, monkeypatch,
                  {"app.py": "old\n"}, sha="a" * 40)
    serve(monkeypatch, an_archive(tmp_path, {"app.py": "new\n",
                                             "rules/items.yaml": "rules\n"}))
    update_app.main()
    assert (work / "app.py").read_text(encoding="utf-8") == "new\n"
    assert (work / "rules" / "items.yaml").exists()
    assert "Updated to main" in capsys.readouterr().out

    recorded = json.loads(
        (work / "installed_version.json").read_text(encoding="utf-8"))
    assert recorded["sha"] == "a" * 40
    assert sorted(recorded["files"]) == ["app.py", "rules/items.yaml"]


def test_the_users_key_and_settings_are_never_written_over(tmp_path,
                                                           monkeypatch):
    """The archive carries only tracked files, so a gitignored one cannot
    be in it — and if one ever is, it still must not land on the key."""
    work = a_copy(tmp_path, monkeypatch, {
        ".env": "STRATZ_API_KEY=mine\n",
        "ui_settings.json": '{"window_locked": true}\n',
        "history_accounts.json": "[]\n",
        "data_cache/heroes.json": "{}\n",
        "assets/portraits/base/1.png": "art",
    }, sha="b" * 40)
    serve(monkeypatch, an_archive(tmp_path, {
        "app.py": "new\n",
        ".env": "STRATZ_API_KEY=THEIRS\n",     # must never be applied
    }))
    update_app.main()
    assert (work / ".env").read_text(encoding="utf-8") == "STRATZ_API_KEY=mine\n"
    assert (work / "ui_settings.json").exists()
    assert (work / "history_accounts.json").exists()
    assert (work / "data_cache" / "heroes.json").exists()
    assert (work / "assets" / "portraits" / "base" / "1.png").exists()


def test_already_up_to_date_is_not_an_error(tmp_path, monkeypatch, capsys):
    """Pressing Update when there is nothing to get is a successful
    outcome, and it must not download or look like a failure."""
    work = a_copy(tmp_path, monkeypatch, sha="c" * 40)
    (work / "installed_version.json").write_text(
        json.dumps({"branch": "main", "sha": "c" * 40, "files": []}),
        encoding="utf-8")

    def refuse(*args, **kwargs):
        raise AssertionError("it downloaded when it had nothing to get")
    monkeypatch.setattr(update_app, "download", refuse)

    update_app.main()                      # no exception is the assertion
    assert "Already up to date" in capsys.readouterr().out


def test_a_file_dropped_from_a_release_is_removed(tmp_path, monkeypatch):
    """A stale module left on disk is not inert — it is importable."""
    work = a_copy(tmp_path, monkeypatch,
                  {"app.py": "old\n", "gone.py": "removed upstream\n",
                   "mine.txt": "the user's own file\n"}, sha="d" * 40)
    (work / "installed_version.json").write_text(
        json.dumps({"branch": "main", "sha": "old",
                    "files": ["app.py", "gone.py"]}), encoding="utf-8")
    serve(monkeypatch, an_archive(tmp_path, {"app.py": "new\n"}))
    update_app.main()
    assert not (work / "gone.py").exists()
    # Only what THIS tool wrote. A file the user put here is theirs.
    assert (work / "mine.txt").exists()


def test_an_archive_that_climbs_out_of_its_folder_is_refused(tmp_path,
                                                             monkeypatch):
    """A path that escapes the extraction folder is how an archive writes
    files it was never meant to reach."""
    work = a_copy(tmp_path, monkeypatch, sha="e" * 40)
    serve(monkeypatch, an_archive(tmp_path,
                                  {"app.py": "fine\n", "../../evil.py": "no"}))
    with pytest.raises(update_app.Refused) as refused:
        update_app.main()
    assert "unsafe path" in str(refused.value)
    assert not (work / "app.py").exists(), "nothing may be written"


def test_the_install_file_is_resolved_at_call_time(tmp_path, monkeypatch):
    """A module constant is evaluated once at import, so a test that
    repoints REPO_ROOT would still write into the real repository — which
    has already happened once here, with the calibration file."""
    monkeypatch.setattr(update_app, "REPO_ROOT", tmp_path)
    assert update_app.install_file() == tmp_path / "installed_version.json"


def test_the_update_does_not_fetch_the_artwork():
    """REVERSED AT THE USER'S REQUEST, and because of what it looked like.

    The update used to end by fetching artwork, on the reasoning that
    nobody handed this app should be left short of a picture. In practice
    that made Update sit for minutes pulling 126 portraits, every item
    icon and the community's alternative portraits — behind a progress
    box that reads as a frozen application, on a press whose whole point
    is "get the new code and reopen".

    So Update is the CODE and its dependencies. Nothing about the
    artwork is lost: `fetch_assets` is still its own task, the first-run
    wizard still runs it, the recurring statistics job still tops it up,
    and the banner at the top of the window flags anything missing with
    a button that fetches it. What changed is that none of that happens
    inside a press that was meant to take seconds.
    """
    from draft_assist.ui.tasks import TASKS
    steps = [" ".join(step) for step in TASKS["update_app"].steps]
    assert not any("fetch_assets" in step for step in steps)
    assert not any("pull_data" in step for step in steps)
    # Still reachable every other way it was before.
    assert "fetch_assets" in TASKS
    assert any("fetch_assets" in " ".join(step)
               for step in TASKS["update_data"].steps)


def test_the_update_task_runs_the_tool_rather_than_bare_git():
    """A bare `git pull` was the whole step, and it fails on a branch with
    no upstream — which is the state this app's own remote produces."""
    from draft_assist.ui.tasks import TASKS
    steps = TASKS["update_app"].steps
    assert steps[0][1] == "tools/update_app.py"
    assert not any(step[0] == "git" for step in steps)
