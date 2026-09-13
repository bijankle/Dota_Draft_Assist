"""A hero already in the draft is SHOWN and refused, never deleted.

Reported from a real session: "I typed in his name to manually add him
and I couldn't find [him]" - about Mars, who was on the board at the time
(the app's own report for that match lists him). The duplicate rule is
right and stays; what was wrong is that it was enforced by leaving the
hero out of the list, and an absence explains nothing. An empty list is
indistinguishable from the app never having heard of that hero, which is
exactly how it was read.
"""

import os

import pytest

pytest.importorskip("PyQt6")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import Qt                                  # noqa: E402
from PyQt6.QtWidgets import QApplication                     # noqa: E402

from draft_assist.ui import hero_picker                      # noqa: E402
from draft_assist.ui.hero_picker import HeroPickerDialog     # noqa: E402

MARS, MARCI, AXE, LION = 129, 136, 2, 26


class Dataset:
    hero_ids = (MARS, MARCI, AXE, LION)
    is_empty = False
    _names = {MARS: "Mars", MARCI: "Marci", AXE: "Axe", LION: "Lion"}

    def name(self, hero_id):
        return self._names[hero_id]


@pytest.fixture(scope="module")
def qapp():
    yield QApplication.instance() or QApplication([])


@pytest.fixture
def picker(qapp):
    made = []

    def build(taken=frozenset(), current=None):
        dialog = HeroPickerDialog(Dataset(), taken=taken, current=current)
        made.append(dialog)
        return dialog
    yield build
    for dialog in made:
        dialog.deleteLater()


def rows(dialog):
    return [dialog.list.item(i) for i in range(dialog.list.count())]


def visible(dialog):
    return [item for item in rows(dialog) if not item.isHidden()]


def named(dialog, hero_id):
    for item in rows(dialog):
        if item.data(Qt.ItemDataRole.UserRole) == hero_id:
            return item
    return None


def test_a_drafted_hero_is_still_in_the_list(picker):
    """THE BUG: Mars was removed outright, so typing his name found
    nothing at all."""
    dialog = picker(taken={MARS: "already on your team"})
    assert named(dialog, MARS) is not None


def test_and_the_row_says_which_team_has_him(picker):
    dialog = picker(taken={MARS: "already on your team"})
    assert named(dialog, MARS).text() == "Mars — already on your team"


def test_typing_his_name_finds_him(picker):
    dialog = picker(taken={MARS: "already on your team"})
    dialog.filter_box.setText("mars")
    assert [item.data(Qt.ItemDataRole.UserRole)
            for item in visible(dialog)] == [MARS]


def test_and_the_dialog_says_what_to_do_about_it(picker):
    dialog = picker(taken={MARS: "already on your team"})
    dialog.filter_box.setText("mars")
    assert not dialog.note.isHidden()
    assert "Already in this draft" in dialog.note.text()
    assert "right-click" in dialog.note.text().lower()


def test_but_he_still_cannot_be_picked(picker):
    """The duplicate rule is the point; only its silence was the bug."""
    dialog = picker(taken={MARS: "already on your team"})
    dialog.filter_box.setText("mars")
    dialog._accept_current()
    assert dialog.selected is None
    dialog.filter_box.returnPressed.emit()
    assert dialog.selected is None


def test_enter_skips_a_refused_row_and_takes_the_next_real_one(picker):
    """A prefix hitting both must not leave Enter on the one that
    cannot be chosen. "mar" is Marci and Mars, and Mars sorts second -
    so before this, Enter on "mar" quietly did nothing."""
    dialog = picker(taken={MARS: "already on your team"})
    dialog.filter_box.setText("mar")
    assert sorted(item.data(Qt.ItemDataRole.UserRole)
                  for item in visible(dialog)) == sorted([MARCI, MARS])
    dialog._accept_current()
    assert dialog.selected == MARCI


def test_the_hero_in_this_very_slot_is_selectable(picker):
    """`current` is the slot being edited, so it is not a duplicate of
    itself - it must keep its plain name and stay pickable."""
    dialog = picker(taken={MARS: "already on your team"}, current=MARS)
    assert named(dialog, MARS).text() == "Mars"
    dialog.filter_box.setText("mars")
    dialog._accept_current()
    assert dialog.selected == MARS


def test_a_filter_matching_nothing_says_so(picker):
    dialog = picker()
    dialog.filter_box.setText("zzzz")
    assert visible(dialog) == []
    assert not dialog.note.isHidden()
    assert "No hero matches" in dialog.note.text()


def test_an_ordinary_filter_says_nothing(picker):
    dialog = picker()
    dialog.filter_box.setText("li")
    assert dialog.note.isHidden()


def test_an_empty_box_says_nothing(picker):
    dialog = picker(taken={MARS: "already on your team"})
    dialog.filter_box.setText("mars")
    dialog.filter_box.setText("")
    assert dialog.note.isHidden()


def test_the_suffix_is_not_something_anybody_has_to_type(picker):
    """Filtering on the drawn text would make "team" match half the list
    and would put the reason in the way of the name."""
    dialog = picker(taken={MARS: "already on your team",
                           AXE: "already on the enemy team"})
    dialog.filter_box.setText("team")
    assert visible(dialog) == []


def test_a_plain_set_still_works(picker):
    """Every other caller hands it a set; the map is the new part."""
    dialog = picker(taken={MARS})
    assert named(dialog, MARS).text() == f"Mars — {hero_picker.IN_DRAFT}"
    assert named(dialog, MARS).flags() == Qt.ItemFlag.NoItemFlags


def test_nothing_taken_leaves_every_row_plain_and_pickable(picker):
    dialog = picker()
    assert [item.text() for item in rows(dialog)] == [
        "Axe", "Lion", "Marci", "Mars"]
    assert all(dialog._selectable(item) for item in rows(dialog))
