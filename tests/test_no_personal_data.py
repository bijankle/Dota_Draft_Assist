"""Nothing in this repository identifies its owner.

"I dont want random users seeing my steam account." The owner's Dota
friend ID, their persona and the ids of matches they actually played were
all committed — in CLAUDE.md, in the GSI fixtures and across a dozen
tests — and a match id is a ONE-CLICK route to the account: anyone can
open `opendota.com/matches/<id>` and read the ten players off it.

The repository being private is not the answer. It was private by luck,
and the reason the Stratz key and Valve's artwork have never been
committed is precisely that it should be safe to make public. This check
keeps that true, because the way it comes back is one careless paste.
"""

import re
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent

# The owner's own identifiers, in every spelling the app parses.
THEIRS = (
    "195286385",            # friend ID
    "76561198155552113",    # the same account as a 64-bit Steam ID
    "97643192",             # and the Z half of its STEAM_0 form
    "Bijson",               # the persona
    # Matches they actually played. Each one lists all ten players.
    "8996568678", "8995290135", "8983179556",
    "8983145525", "8981992551", "8996474799",
)


def tracked() -> list[Path]:
    """Every file git actually carries — the ones a clone would hand over.

    Asked of git rather than walked, so anything gitignored (the key, the
    settings, the downloaded artwork, the recordings) is out of scope by
    construction rather than by a list somebody has to maintain.
    """
    out = subprocess.run(["git", "ls-files"], cwd=ROOT,
                         capture_output=True, text=True, check=True)
    return [ROOT / name for name in out.stdout.split() if name]


@pytest.mark.parametrize("secret", THEIRS)
def test_no_tracked_file_carries_the_owners_identifiers(secret):
    found = []
    for path in tracked():
        if path.name == Path(__file__).name:
            continue                      # this file names them on purpose
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue                      # binary, and none of these fit
        if secret in text:
            found.append(str(path.relative_to(ROOT)))
    assert not found, (
        f"{secret!r} is committed in {found}. Use the example account "
        "instead — see `tests/test_example_account_is_not_a_real_one`.")


def test_the_env_file_is_not_tracked():
    """The key has been gitignored since the first commit. Still checked:
    it is the one file here that would matter immediately."""
    names = {path.name for path in tracked()}
    assert ".env" not in names
    assert ".env.example" in names, "the documentation for it should stay"


def test_no_tracked_file_carries_a_real_looking_key():
    """`.env.example` names the variable and gives a placeholder. Anything
    that looks like an actual value is the thing this catches."""
    real = re.compile(r"STRATZ_API_KEY\s*=\s*(?!your-)[A-Za-z0-9._-]{20,}")
    for path in tracked():
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        if path.name == Path(__file__).name:
            continue
        assert not real.search(text), f"{path} looks like it carries a key"


def test_the_example_account_is_not_a_real_one():
    """WHY 4242424242 AND NOT SOMETHING STARTING WITH 9.

    A number beginning with 9 cannot be a friend ID at all — a 10-digit
    one is at least nine billion and the 32-bit account space stops at
    4294967295, so the app's own parser refuses it — and a NINE-digit one
    starting with 9 is only ~987 million, well inside the range Steam has
    already handed out, so it could be somebody's real account.

    The safe band is inside 32 bits and past what has been allocated.
    Steam has created roughly two billion accounts, so 4.24 billion is
    about twice the frontier: it still parses, it converts to a
    real-shaped 17-digit Steam64, and the repeated digits read as an
    example on sight.
    """
    from draft_assist.history import account

    example = 4242424242
    assert example <= account.MAX_ACCOUNT_ID, "the app would refuse it"
    assert example > 2_500_000_000, "inside the range Steam has allocated"
    parsed = account.parse(str(example))
    assert parsed.ok and parsed.account_id == example
    # And the 64-bit spelling is the shape a real one has: 17 digits.
    steam64 = account.STEAM64_BASE + example
    assert len(str(steam64)) == 17
    assert account.parse(str(steam64)).account_id == example


def test_every_artwork_folder_is_ignored():
    """VALVE'S AND BLIZZARD'S ARTWORK NEVER ENTERS THIS REPOSITORY, and a
    folder that is missing from `.gitignore` is how that rule gets broken
    by accident rather than by decision.

    `assets/screenshots/` was the one that was missing. It is where the
    resolution sweep is pointed, so it fills with full-screen captures of
    the draft — and a game frame carries more than the artwork: it shows
    whatever else was on screen and the names of the nine other players.
    Every sibling folder was listed and this one was not, which is
    exactly the shape of an omission nobody notices until a `git add -A`.
    """
    import subprocess

    root = Path(__file__).resolve().parent.parent
    for folder in ("portraits", "items", "synth", "gate", "role_icons",
                   "screenshots"):
        probe = f"assets/{folder}/probe.png"
        done = subprocess.run(["git", "check-ignore", "-q", probe],
                              cwd=root, capture_output=True)
        assert done.returncode == 0, (
            f"{probe} is NOT gitignored — artwork could be committed")


def test_no_screenshot_of_the_game_is_tracked():
    """The rule, checked against what git actually holds rather than
    against what `.gitignore` says it should."""
    import subprocess

    root = Path(__file__).resolve().parent.parent
    listed = subprocess.run(["git", "ls-files"], cwd=root,
                            capture_output=True, text=True).stdout.split()
    art = [f for f in listed
           if f.startswith("assets/")
           and f.rsplit(".", 1)[-1].lower() in {"png", "jpg", "jpeg", "bmp"}
           and not f.startswith("assets/app-default.")]
    assert not art, f"artwork is committed: {art}"
