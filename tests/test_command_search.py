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

def test_enter_takes_the_top_match_and_clicking_takes_that_one(qapp):
    """Both, at the user's request: Enter for the top match, and any
    result clickable. A box that only obeys Enter makes the list a
    display rather than a control, and the list is the part that answers
    "what else is there"."""
    from draft_assist.ui.search_dialog import SearchDialog
    from draft_assist.ui.commands import Command

    fired = []
    entries = [
        Command("First thing", "File", "", ("alpha",),
                lambda: fired.append("first")),
        Command("Second thing", "View", "", ("alpha",),
                lambda: fired.append("second")),
    ]
    dialog = SearchDialog(entries)
    dialog.box.setText("alpha")
    assert dialog.results.count() == 2
    dialog._take_top()
    assert fired == ["first"]

    dialog = SearchDialog(entries)
    dialog.box.setText("alpha")
    dialog._take(dialog.results.item(1))
    assert fired == ["first", "second"]


def test_an_empty_box_shows_what_there_is(qapp):
    """Half of searching is finding out what the app can do at all, and a
    blank list answers that with nothing."""
    from draft_assist.ui.search_dialog import SearchDialog
    from draft_assist.ui.commands import Command

    entries = [Command(f"Thing {n}", "File", run=lambda: None)
               for n in range(3)]
    dialog = SearchDialog(entries)
    assert dialog.results.count() == 3


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
