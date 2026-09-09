"""Pull the latest code — for THIS repository, and no other.

`git pull --rebase --autostash` on its own was the whole update step, and
it fails outright on a checkout whose branch has no upstream:

    There is no tracking information for the current branch.

Which is not an exotic state. A branch made locally has no upstream until
something sets one, and this repository's remote has never carried a
`main` or a `master` at all — so a checkout sitting on `master` has
nothing to track and nothing to guess from either. The button said
"Update application"; it must not answer with a git tutorial.

So the target is RESOLVED rather than assumed, in this order:

1. the current branch's own upstream, if it has one;
2. `origin/<the current branch's name>`, if the remote carries it;
3. the remote's default branch, if `origin/HEAD` names one;
4. the remote's ONLY branch, when it has exactly one — which is this
   repository today, and is unambiguous whenever it holds.

Then the upstream is SET, so the next update is an ordinary pull and this
whole ladder is skipped.

**It only ever updates this repository.** The remote is checked against
the app's own name before anything is fetched: the match history analyser
was folded in from another repository and nothing may reach back to it,
so an origin that is not this app is refused with the URL it found rather
than pulled from.
"""

import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from draft_assist.config import REPO_ROOT  # noqa: E402

# The app's own repository, lower-cased for comparison. A fork or a rename
# is a legitimate reason for this to fail; the message names what it found
# so that is obvious rather than mysterious.
THIS_REPO = "dota_draft_assist"


class Refused(Exception):
    """The update cannot honestly be done. The message says why."""


NO_GIT = (
    "Git is not installed on this machine, and Update is the one thing in "
    "this app that needs it.\n\n"
    "Install Git for Windows from https://git-scm.com/download/win (or run "
    "`winget install --id Git.Git`), close the app and open it again. "
    "Nothing else here needs git: the app itself runs, reads the draft and "
    "analyses your match history without it.\n\n"
    "Update needs it because it is the only thing that can bring down new "
    "code while keeping the edits you have made to your own files. Copying "
    "a fresh download over the top would take your item rules with it.")

NOT_A_CHECKOUT = (
    "This folder is a copy of the app rather than a clone of it: there is "
    "no .git directory in it, so there is no way to tell what has changed "
    "since it was downloaded.\n\n"
    "That is what a ZIP from GitHub's 'Download code' button leaves you "
    "with. Install git, then clone the repository properly:\n\n"
    "    git clone https://github.com/bijankle/Dota_Draft_Assist\n\n"
    "Your settings and any downloaded portraits live in files this "
    "repository does not carry, so copy them across and nothing is lost.")


def git(*args, check=True) -> str:
    try:
        result = subprocess.run(["git", "-C", str(REPO_ROOT), *args],
                                capture_output=True, text=True)
    except FileNotFoundError:
        # Not an exotic state: the app is run from a folder, and nothing
        # else about it needs git. It has to say so in one sentence rather
        # than as a traceback about a missing executable.
        raise Refused(NO_GIT)
    if check and result.returncode != 0:
        raise Refused((result.stderr or result.stdout).strip()
                      or f"git {' '.join(args)} failed")
    return (result.stdout or "").strip()


def check_remote(url: str) -> None:
    """Refuse an origin that is not this app.

    The match history analyser came from a separate repository and is now
    wholly inside this one. Updating must never reach back to it, and the
    cheapest way to be sure is to look at where origin points.
    """
    if not url:
        raise Refused(
            "This checkout has no 'origin' remote, so there is nowhere to "
            "update from. It was probably copied rather than cloned; clone "
            "it from GitHub instead and your settings will carry over.")
    if THIS_REPO not in url.lower():
        raise Refused(
            f"'origin' points at {url}, which is not this app. Update only "
            "ever pulls Dota Draft Assist — nothing here updates from any "
            "other repository.")


def choose_target(branch: str, upstream: str, remote_branches, head: str):
    """What to pull, and why. Returns (ref, reason) or (None, why not).

    Pure, so the ladder can be tested without a git repository to hand.
    `remote_branches` are short names as `origin/x` gives them: "main",
    "claude/thing". `head` is what `origin/HEAD` resolves to, or "".
    """
    branches = [b for b in remote_branches if b]
    if upstream:
        return upstream, f"tracking {upstream}"
    if branch and branch in branches:
        return f"origin/{branch}", f"the remote's own {branch}"
    if head and head in branches:
        return f"origin/{head}", f"the remote's default branch, {head}"
    if len(branches) == 1:
        return (f"origin/{branches[0]}",
                f"the remote's only branch, {branches[0]}")
    if not branches:
        return None, "the remote has no branches to pull from"
    return None, ("the remote has several branches and none of them matches "
                  f"'{branch}', so which one to pull is not this tool's "
                  "guess to make. Run: git pull --rebase origin <branch>")


def main() -> None:
    print(f"Repository: {REPO_ROOT}")
    if not (REPO_ROOT / ".git").exists():
        # Checked BEFORE running git, because "not a git repository" is a
        # true answer to the wrong question: the useful thing to say is
        # that this was downloaded rather than cloned.
        raise Refused(NOT_A_CHECKOUT)
    url = git("remote", "get-url", "origin", check=False)
    check_remote(url)
    print(f"origin:     {url}")

    branch = git("rev-parse", "--abbrev-ref", "HEAD", check=False)
    if branch == "HEAD":
        raise Refused(
            "This checkout is on a detached HEAD rather than a branch, so "
            "there is nothing to update. Run: git checkout <branch>")
    print(f"branch:     {branch}")

    print("\nFetching…")
    print(git("fetch", "--prune", "origin", check=False) or "  (up to date)")

    upstream = git("rev-parse", "--abbrev-ref", "--symbolic-full-name",
                   "@{upstream}", check=False)
    remote_branches = [line.strip().removeprefix("origin/")
                       for line in git("for-each-ref", "--format=%(refname:short)",
                                       "refs/remotes/origin", check=False
                                       ).splitlines()
                       if line.strip() and "->" not in line]
    head = git("symbolic-ref", "--short", "refs/remotes/origin/HEAD",
               check=False).removeprefix("origin/")

    target, reason = choose_target(branch, upstream, remote_branches, head)
    if target is None:
        raise Refused(f"Nothing to pull: {reason}.")
    print(f"Pulling from {target} — {reason}.\n")

    remote_branch = target.removeprefix("origin/")
    result = subprocess.run(
        ["git", "-C", str(REPO_ROOT), "pull", "--rebase", "--autostash",
         "origin", remote_branch],
        text=True)
    if result.returncode != 0:
        raise Refused(
            "The pull did not finish. Your own edits are safe — nothing was "
            "discarded. If it stopped in a rebase, `git rebase --abort` puts "
            "the checkout back exactly as it was.")

    # SET THE UPSTREAM, so the next update is an ordinary pull rather than
    # this whole ladder again — and so `git status` starts saying how far
    # ahead or behind the checkout is.
    if not upstream:
        git("branch", f"--set-upstream-to=origin/{remote_branch}", branch,
            check=False)
        print(f"\nTracking set: {branch} follows origin/{remote_branch}.")
    print("\nUpdated.")


if __name__ == "__main__":
    try:
        main()
    except Refused as refused:
        print(f"\n{refused}")
        raise SystemExit(1)
