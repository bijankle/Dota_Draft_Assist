"""The app must never send anybody to a menu that does not exist.

"Game ▸ Start a fresh recording --- i dont have this option." They were
right: the menu bar is File | View | Help, and everything that lived
under Setup and Game became a tab in Settings — but fourteen strings
across the GSI code and the console tools were still naming the old
trails, and RECORDING stopped being a menu item at all. It is the red
dot on the tab row.

This is the same family as the `fetch_assets` message that named
"Setup ▸ Download", two menus that no longer exist: a sentence that is
about the app's own past, printed at somebody trying to use it now.
Prose goes stale silently, so this is checked rather than remembered.
"""

import ast
import io
import re
import sys
import tokenize
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# Menus that no longer exist. Setup and Game were folded into Settings;
# CAPTURE went when the source stopped being a mode and became two tick
# boxes, and six sentences were still sending people to it — including
# one inside a method nothing had called since the menu item went.
# `>` is what a console tool prints and `▸` is what the Qt widgets do,
# and both are trails.
GONE = re.compile(r"\b(Game|Setup|Capture)\s*(?:>|▸)\s*[A-Z]")

# Whole items that were deleted rather than moved, wherever they are
# named as somewhere to go. Two families here and they went for
# different reasons: the hand-drawn crop boxes, because the geometry is
# measured now and "my plan now is to have the automatic detection work
# so the user never needs to draw out these vision boxes"; and the
# recognition checks, because they were instruments for refining the
# recogniser and "once its done i dont nteed them".
DELETED_ITEMS = re.compile(
    r"(?:>|▸)\s*(?:Calibrate pick boxes|Recognition checks|"
    r"Tune recognition|Run capture probe|Game data status|"
    r"Check item icons|Make a pinnable shortcut|Simulate a draft)")

FILES = sorted(
    list((ROOT / "draft_assist").rglob("*.py"))
    + list((ROOT / "tools").rglob("*.py")))


def strings_in(path: Path):
    """Every STRING LITERAL in the file, with its line.

    Strings are what gets printed. Comments are excluded deliberately:
    a comment recording that a message once said "Setup > Download" is
    this project explaining itself, not the app misdirecting anybody.
    """
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except (OSError, SyntaxError):          # pragma: no cover
        return
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            yield node.lineno, node.value


@pytest.mark.parametrize("path", FILES, ids=lambda p: p.name)
def test_no_string_names_a_menu_that_was_deleted(path):
    bad = [(line, text.strip()[:70])
           for line, text in strings_in(path) if GONE.search(text)]
    assert not bad, (
        f"{path.relative_to(ROOT)} sends the reader to a menu that no "
        f"longer exists: {bad}")


def test_the_check_would_actually_catch_one(tmp_path):
    """A guard that cannot fail is not a guard."""
    sample = tmp_path / "stale.py"
    sample.write_text('print("Run Game > Set up game data (GSI).")',
                      encoding="utf-8")
    assert any(GONE.search(text) for _line, text in strings_in(sample))


def test_a_comment_about_the_old_menus_is_not_flagged(tmp_path):
    """This project's own history is written down on purpose."""
    sample = tmp_path / "history.py"
    sample.write_text(
        "# It named Setup > Download, two menus that no longer exist.\n"
        'print("all good")\n', encoding="utf-8")
    assert not any(GONE.search(text) for _line, text in strings_in(sample))


def test_recording_is_not_offered_as_a_menu_item_anywhere():
    """It is the red dot on the tab row, and has been since the menu bar
    was cut to File | View | Help."""
    # The ACTION, not the list: `Settings ▸ Debug ▸ Recordings` is a
    # real place and must not be caught by a rule about a control that
    # moved onto the tab row.
    wrong = re.compile(
        r"(?:>|▸)\s*(?:Start a fresh recording|Record game data)")
    for path in FILES:
        for line, text in strings_in(path):
            assert not wrong.search(text), f"{path.name}:{line}: {text[:60]}"


def test_no_string_offers_a_menu_item_that_was_deleted():
    """An item that went entirely is worse to name than one that moved:
    there is nowhere to send somebody who goes looking."""
    for path in FILES:
        for line, text in strings_in(path):
            assert not DELETED_ITEMS.search(text), (
                f"{path.name}:{line}: {text[:70]}")


def test_that_check_would_actually_catch_one(tmp_path):
    sample = tmp_path / "stale.py"
    sample.write_text('print("Use File > Calibrate pick boxes to fix it.")',
                      encoding="utf-8")
    assert any(DELETED_ITEMS.search(text)
               for _line, text in strings_in(sample))
