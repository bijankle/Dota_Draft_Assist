"""Four tick boxes in View cut the Draft tab down, and the picks stay.

At the user's request: "i want to be able to tick on/off all the
subheaders, except for the top 5 / 5 portraits - as that is the main
part of the app... so the role attributes (scores out of 5), the
sugegsted picks, the items, all in the view dropdown menu with tick
boxes... they are on by default, the only oen off by defautl are the
matrices... and if the user unticks them the headers should hide away
just like was done for the matrices".

THE HEADING GOES WITH THE CARD. "I dont want the header to even show if
its unticked" — so what is hidden is the whole block, not its contents,
and nothing is left behind saying where a card used to be.
"""

import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

pytest.importorskip("PyQt6")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication                  # noqa: E402

from draft_assist.config import RULES_FILE                # noqa: E402
from draft_assist.model import items as items_mod         # noqa: E402
from draft_assist.ui import settings as ui_settings       # noqa: E402
from draft_assist.ui.app import MainWindow                # noqa: E402
from draft_assist.ui.demo import demo_dataset             # noqa: E402
from draft_assist.ui.providers import DemoProvider        # noqa: E402


@pytest.fixture
def window(qapp):
    ds = demo_dataset()
    rules, meta = items_mod.load_rules(RULES_FILE)
    win = MainWindow(ds, DemoProvider(ds), rules, meta)
    win.timer.stop()
    win.show()
    QApplication.processEvents()
    yield win
    win.close()


@pytest.fixture
def qapp():
    yield QApplication.instance() or QApplication([])


def _settle():
    for _ in range(3):
        QApplication.processEvents()


# --- the settings ------------------------------------------------------

def test_every_section_has_a_setting_of_its_own():
    keys = {key for key, _label, _attr in MainWindow.SECTIONS}
    assert keys <= set(ui_settings.DEFAULTS), keys - set(ui_settings.DEFAULTS)


def test_only_the_matrices_start_off():
    """"they are on by default, the only oen off by defautl are the
    matrices"."""
    off = {key for key, _l, _a in MainWindow.SECTIONS
           if not ui_settings.DEFAULTS[key]}
    assert off == {"show_matrices"}


def test_the_ten_picks_are_not_one_of_the_sections():
    """The board is what the app IS; everything on this list is advice
    ABOUT the board. A tick box that empties the window is not something
    to be able to find by accident."""
    attrs = {attr for _k, _l, attr in MainWindow.SECTIONS}
    assert "team_panels" not in attrs
    assert not any("team" in attr or "pick_tile" in attr for attr in attrs)


# --- what the window does with them ------------------------------------

def test_a_fresh_window_draws_three_of_the_four(window):
    for key, label, attr in MainWindow.SECTIONS:
        block = getattr(window, attr)
        assert block.isVisible() == ui_settings.DEFAULTS[key], label


def test_the_matrices_are_gone_rather_than_empty(window):
    """Not an empty card where a grid was — the heading goes too."""
    assert not window.grids_block.isVisible()
    assert not window.synergy_card.isVisible()
    assert not window.matchup_card.isVisible()


def test_ticking_one_on_draws_it_and_remembers(window):
    window.section_actions["show_matrices"].setChecked(True)
    _settle()
    assert window.grids_block.isVisible()
    assert window.settings["show_matrices"] is True


def test_unticking_hides_the_block_and_its_heading(window):
    window.section_actions["show_items"].setChecked(False)
    _settle()
    assert not window.items_card.isVisible()
    assert window.settings["show_items"] is False


def test_the_picks_survive_every_box_being_off(window):
    """The one thing that cannot be turned off."""
    for key, _label, _attr in MainWindow.SECTIONS:
        window.section_actions[key].setChecked(False)
    _settle()
    for side in ("ally", "enemy"):
        assert window.team_panels[side].isVisible(), side


def test_a_hidden_section_leaves_no_gap_behind(window):
    """A LAYOUT whose children are all hidden still takes the spacing
    either side of it, which is why each row is wrapped in a block that
    can be hidden whole. Turning three off must shorten the page."""
    # THE TAB IS A QScrollArea, so its own sizeHint is the viewport's
    # and never moves. The PAGE inside it is what shortens.
    page = window.tabs.widget(0)
    page = page.widget() if hasattr(page, "widget") else page
    _settle()
    tall = page.sizeHint().height()
    for key in ("show_roles", "show_suggestions", "show_items"):
        window.section_actions[key].setChecked(False)
    _settle()
    assert page.sizeHint().height() < tall


def test_the_setting_is_what_the_tick_follows_rather_than_the_reverse(
        window):
    """A file edited by hand, or restored from another machine, must
    arrive where a click would — `_apply_sections` is the one path and
    it corrects the tick without writing the file back."""
    window.settings["show_roles"] = False
    window._apply_sections()
    _settle()
    assert not window.roles_block.isVisible()
    assert not window.section_actions["show_roles"].isChecked()
    # And correcting a tick is not the user pressing it.
    assert window.settings["show_roles"] is False


# --- the size sliders --------------------------------------------------

def test_the_sliders_are_centred_on_a_hundred_percent():
    """"redefine what 100% is and rejig the min / max percentage to be
    relative to this and jsut make it 25% to 175%".

    They ran 50 to 200 with the default at 100, so the MIDDLE of the
    travel was 125: the handle sat a third of the way along and dragging
    right reached twice as far as dragging left.
    """
    from draft_assist.ui import teams, tilekit

    for module in (teams, tilekit):
        low, high = module.SCALE_MIN, module.SCALE_MAX
        assert (low, high) == (0.25, 1.75), module.__name__
        assert (low + high) / 2 == pytest.approx(1.0), (
            f"{module.__name__} is not centred on 100%")


def test_both_sliders_offer_exactly_what_the_code_will_accept(window):
    """A slider that can be dragged to a value the module clamps away is
    a control that lies about what it does."""
    from draft_assist.ui import teams

    for slider in window.size_sliders.values():
        assert slider.minimum() == round(teams.SCALE_MIN * 100)
        assert slider.maximum() == round(teams.SCALE_MAX * 100)


def test_a_setting_saved_outside_the_new_range_is_clamped(qapp):
    """The range narrowed at the top, so a machine that had turned the
    portraits up to 200% must come back inside it rather than keeping a
    size the slider can no longer show."""
    from draft_assist.ui import teams

    teams.set_scale(2.0)
    assert teams.SCALE == teams.SCALE_MAX
    teams.set_scale(0.1)
    assert teams.SCALE == teams.SCALE_MIN
    teams.set_scale(1.0)
