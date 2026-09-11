"""Help ▸ Search — the way back to everything the menu bar stopped listing.

The bar is File | View | Help now and the rest is tabs in Settings, which
is a better place to keep a control and a worse place to find one. These
check the property that makes the search worth having: that it answers
the words a PERSON reaches for, not only the words the app printed.
"""

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication                      # noqa: E402

from draft_assist.config import RULES_FILE                    # noqa: E402
from draft_assist.model import items as items_mod             # noqa: E402
from draft_assist.ui.app import MainWindow                    # noqa: E402
from draft_assist.ui.commands import Command, score, search   # noqa: E402
from draft_assist.ui.demo import demo_dataset                 # noqa: E402
from draft_assist.ui.providers import DemoProvider            # noqa: E402


@pytest.fixture(scope="module")
def qapp():
    yield QApplication.instance() or QApplication([])


@pytest.fixture()
def window(qapp):
    ds = demo_dataset()
    provider = DemoProvider(ds)
    provider.draft.started -= 45
    rules, meta = items_mod.load_rules(RULES_FILE)
    win = MainWindow(ds, provider, rules, meta)
    win.timer.stop()
    yield win
    win.close()


def _cmd(label, where="", detail="", words=()):
    return Command(label=label, where=where, detail=detail, words=words,
                   run=lambda: None)


CATALOGUE = [
    _cmd("All artwork…", "Settings ▸ Downloads",
         "Every hero portrait and item icon — no API key needed.",
         ("pictures", "portraits", "images", "icons", "artwork")),
    _cmd("Item icons…", "Settings ▸ Downloads",
         "Just the item pictures, with the reason if it fails.",
         ("items", "pictures", "icons")),
    _cmd("Diagnose game data…", "Settings ▸ Game data",
         "Check every requirement and name the one that is failing.",
         ("gsi", "broken", "problem", "nothing", "silent")),
    _cmd("Statistics bracket…", "Settings ▸ Downloads",
         "Which ranks the statistics are drawn from.",
         ("rank", "ranks", "mmr")),
    _cmd("Transparency", "View", "How see-through the window is.",
         ("opacity", "seethrough")),
    _cmd("Update application…", "Help",
         "Pull the latest code, then reopen the app.",
         ("upgrade", "version", "new")),
]


@pytest.mark.parametrize("query,expected", [
    # The app's own words still work, and beat a broader match.
    ("item icons", "Item icons…"),
    ("artwork", "All artwork…"),
    # THE POINT: what a person calls it. None of these words is in the
    # label of the thing they find.
    ("pictures", "All artwork…"),
    ("my mmr", "Statistics bracket…"),
    ("rank", "Statistics bracket…"),
    ("its broken", "Diagnose game data…"),
    ("nothing from dota", "Diagnose game data…"),
    ("see through", "Transparency"),
    ("opacity", "Transparency"),
    ("new version", "Update application…"),
])
def test_the_top_match_is_what_a_person_meant(query, expected):
    hits = search(query, CATALOGUE)
    assert hits, f"{query!r} found nothing"
    assert hits[0].label == expected, \
        f"{query!r} -> {[h.label for h in hits][:3]}"


def test_a_term_nothing_answers_sinks_the_whole_entry():
    """A search that always has an answer is one where the top match means
    nothing. Every term has to hit something, or the entry is out."""
    assert search("zzzz", CATALOGUE) == []
    # "item" matches two entries; "icons" narrows it. "item lizard" must
    # not fall back to the "item" half.
    assert search("item lizard", CATALOGUE) == []


def test_the_more_specific_answer_wins_on_the_same_terms():
    """Both of these declare themselves findable by "pictures", and one is
    about item pictures specifically."""
    hits = search("item pictures", CATALOGUE)
    assert hits[0].label == "Item icons…"


def test_a_menu_mnemonic_is_not_part_of_a_word():
    """`&Update` must match "update" — an ampersand that survives into the
    word is a label nothing can ever find."""
    assert score("update", _cmd("&Update application…")) > 0


def test_an_entry_that_does_nothing_is_never_offered():
    """A heading carries no `run`, and offering something unpressable is
    worse than not listing it."""
    heading = Command(label="Downloads", where="Settings", run=None)
    assert search("downloads", [heading]) == []


def test_the_where_is_carried_so_the_answer_teaches_the_way_back():
    hits = search("mmr", CATALOGUE)
    assert hits[0].title == "Settings ▸ Downloads ▸ Statistics bracket…"


# ---- the dialog ------------------------------------------------------

def _a_menu(entries, qapp):
    """A Help menu with its own items and the search attached, exactly
    the way `MainWindow` builds it."""
    from PyQt6.QtWidgets import QMenu
    from draft_assist.ui.menusearch import MenuSearch

    menu = QMenu("&Help")
    own = [menu.addAction(name) for name in ("User manual", "About")]
    return menu, own, MenuSearch(menu, lambda: entries)


def _type(qapp, menu, text):
    """Press each key AT THE MENU, which is where an open menu's keyboard
    grab sends them — not at the box, which never has focus."""
    from PyQt6.QtCore import QEvent, Qt
    from PyQt6.QtGui import QKeyEvent

    for ch in text:
        qapp.sendEvent(menu, QKeyEvent(QEvent.Type.KeyPress, 0,
                                       Qt.KeyboardModifier.NoModifier, ch))


def test_typing_at_the_menu_lands_in_the_box(qapp):
    """"When I hit help and start typing I should see it being entered
    into a text box which sits on the help dropdown list."

    An open QMenu holds a keyboard GRAB, so every key goes to the menu
    whatever has focus. The box therefore never asks for focus: the keys
    are forwarded to it. This is the assertion that the whole design
    exists to make true.
    """
    from draft_assist.ui.commands import Command

    entries = [Command("Diagnose game data", "Settings ▸ Game data", "",
                       ("broken",), lambda: None)]
    menu, own, search = _a_menu(entries, qapp)
    menu.aboutToShow.emit()
    assert search.edit.text() == "", "a fresh box every time it opens"

    _type(qapp, menu, "broken")
    assert search.edit.text() == "broken"
    assert [a.text() for a in search._results] == [
        "Settings ▸ Game data ▸ Diagnose game data"], "the trail, not just the name"
    assert all(not a.isVisible() for a in own), "own items give way"


def test_the_menu_keeps_the_keys_a_menu_is_driven_by(qapp):
    """Arrows, Enter and Escape stay the MENU's. Swallowing them for the
    box would take the keyboard navigation away from a menu to give it a
    text field nobody is looking at."""
    from PyQt6.QtCore import QEvent, Qt
    from PyQt6.QtGui import QKeyEvent
    from draft_assist.ui.commands import Command

    entries = [Command("First", "File", "", ("alpha",), lambda: None)]
    menu, _own, search = _a_menu(entries, qapp)
    menu.aboutToShow.emit()
    _type(qapp, menu, "alpha")
    before = search.edit.text()

    # NAVIGATION only. Return and Escape are deliberately not in here:
    # they also belong to the menu, but they ACT — Return takes the
    # highlighted result, which clears the box on purpose.
    for key in (Qt.Key.Key_Down, Qt.Key.Key_Up, Qt.Key.Key_Left,
                Qt.Key.Key_Right, Qt.Key.Key_Home, Qt.Key.Key_End):
        qapp.sendEvent(menu, QKeyEvent(QEvent.Type.KeyPress, key,
                                       Qt.KeyboardModifier.NoModifier, ""))
    assert search.edit.text() == before, "navigation keys are not typing"

    # Backspace IS the box's, or a typo could only be fixed by starting
    # the whole query again.
    qapp.sendEvent(menu, QKeyEvent(QEvent.Type.KeyPress,
                                   Qt.Key.Key_Backspace,
                                   Qt.KeyboardModifier.NoModifier, ""))
    assert search.edit.text() == "alph"


def test_enter_takes_the_top_match_and_any_result_is_clickable(qapp):
    """Both, at the user's request. A QMenu activates NOTHING until an
    arrow is pressed, so without highlighting the top result you could
    type a setting's exact name, press Enter, and watch the menu sit
    there doing nothing."""
    from draft_assist.ui.commands import Command

    fired = []
    entries = [
        Command("First thing", "File", "", ("alpha",),
                lambda: fired.append("first")),
        Command("Second thing", "View", "", ("alpha",),
                lambda: fired.append("second")),
    ]
    menu, _own, search = _a_menu(entries, qapp)
    menu.aboutToShow.emit()
    _type(qapp, menu, "alpha")

    assert len(search._results) == 2
    assert menu.activeAction() is search._results[0], "Enter has a target"
    # Held BEFORE triggering: taking a result clears the box, which
    # clears the results with it — so `_results` is empty a line later,
    # which is the behaviour rather than a bug.
    first, second = search._results
    first.trigger()
    assert fired == ["first"]
    assert search.edit.text() == "" and search._results == [], (
        "taking a result puts the menu back to its resting state")

    second.trigger()
    assert fired == ["first", "second"]


def test_an_empty_box_shows_the_menus_own_items(qapp):
    """This REVERSES what the dialog did — it listed every command when
    empty. At the user's request the menu shows "top 8 matches, nothing
    when empty", because a menu that listed thirty commands before a key
    was pressed is a page rather than a menu."""
    from draft_assist.ui.commands import Command

    entries = [Command(f"Thing {n}", "File", "", ("alpha",), lambda: None)
               for n in range(12)]
    menu, own, search = _a_menu(entries, qapp)
    menu.aboutToShow.emit()
    assert search._results == [] and all(a.isVisible() for a in own)

    _type(qapp, menu, "alpha")
    from draft_assist.ui.menusearch import CAP
    assert len(search._results) == CAP, "a menu is not a scrolling list"

    # And clearing it puts the menu back the way it was found.
    search.edit.setText("")
    assert search._results == [] and all(a.isVisible() for a in own)


def test_a_query_with_no_answer_says_so(qapp):
    """Silently showing nothing reads as the search having broken."""
    from draft_assist.ui.commands import Command
    from draft_assist.ui.menusearch import NOTHING

    menu, _own, search = _a_menu(
        [Command("First", "File", "", ("alpha",), lambda: None)], qapp)
    menu.aboutToShow.emit()
    _type(qapp, menu, "zzzznope")
    assert [a.text() for a in search._results] == [NOTHING]
    assert not search._results[0].isEnabled()


def test_every_command_the_app_offers_can_be_found_by_its_own_name(window):
    """The registry builds the Settings tabs AND feeds the search, so an
    entry nobody can search for is one the menu bar also stopped
    listing — findable nowhere at all."""
    from draft_assist.ui.commands import search

    catalogue = window._all_commands()
    for command in catalogue:
        plain = command.label.replace("…", "").strip()
        hits = search(plain, catalogue)
        assert command.label in [h.label for h in hits], \
            f"{command.label!r} cannot be found by its own name"
