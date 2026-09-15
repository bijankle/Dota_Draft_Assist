"""What a clicked hero is made of, in a box pointing down at it.

At the user's request: "when i click on a hero in addition to the gold
border i want to see the stats show up above in a callout above the
hero.... with the same pill look at the one for the team, but more
ocmpact (there is too much space between carry and durable, support and
escape, etc".

The gold ring says WHICH hero the whole board is being measured against;
this says what that hero IS, which is the one thing the board around it
cannot.
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

from PyQt6.QtCore import QRect                              # noqa: E402
from PyQt6.QtWidgets import QApplication, QWidget           # noqa: E402

from draft_assist.config import RULES_FILE                  # noqa: E402
from draft_assist.model import items as items_mod           # noqa: E402
from draft_assist.model import roles as roles_mod           # noqa: E402
from draft_assist.ui import rolebar, theme                  # noqa: E402
from draft_assist.ui.app import MainWindow                  # noqa: E402
from draft_assist.ui.demo import demo_dataset               # noqa: E402
from draft_assist.ui.manual import ManualDraft              # noqa: E402
from draft_assist.ui.providers import ManualProvider        # noqa: E402


@pytest.fixture(scope="module")
def qapp():
    yield QApplication.instance() or QApplication([])


@pytest.fixture
def styled(qapp):
    from draft_assist.ui import fonts
    fonts.load_bundled()
    qapp.setStyleSheet(theme.STYLESHEET)
    yield
    qapp.setStyleSheet("")


@pytest.fixture
def window(qapp, styled):
    ds = demo_dataset()
    hand = ManualDraft()
    rules, meta = items_mod.load_rules(RULES_FILE)
    win = MainWindow(ds, ManualProvider(hand), rules, meta, hand)
    win.timer.stop()
    win.resize(1180, 1000)
    win.show()
    win._demo_draft()
    win.refresh()
    for _ in range(6):
        QApplication.processEvents()
    yield win
    win.close()


def _settle(times=6):
    for _ in range(times):
        QApplication.processEvents()


def a_rated_hero() -> int:
    return next(iter(roles_mod._load()))


def a_rated_tile(window):
    """A pick whose hero the bundled table actually rates.

    `_demo_draft` takes TEN AT RANDOM, so a tile picked by position is a
    hero the table may never have heard of — and an unrated hero draws no
    callout at all, by design. Asserting on a random one is a test that
    fails about as often as the roster leaves it out.
    """
    for tile in window.team_panels["ally"].slots:
        hero = tile.property("hero_id")
        if hero is not None and roles_mod.known(int(hero)):
            return tile
    pytest.skip("the demo draft rated none of its own picks")


# ---- what it says ------------------------------------------------------

def test_it_draws_valves_own_scale_rather_than_a_share(qapp, styled):
    """The Roles card under the board asks how much of what a SIDE could
    have scored it scored — a fraction, drawn across five pills. One hero
    has no fraction to take: it has the rating the game publishes, so it
    gets `MAX_LEVEL` pills and each one is a level. Three levels spread
    over five pills would invent a precision Valve does not publish."""
    block = rolebar.HeroRoles()
    hero = a_rated_hero()
    assert block.set_hero(hero) is True
    levels = roles_mod.levels_for(hero)
    for role in roles_mod.ROLES:
        assert block.rating(role) == levels[role], role
        assert block._cells[role][1].count == roles_mod.MAX_LEVEL
    block.deleteLater()


def test_all_eight_roles_always_even_the_zeros(qapp, styled):
    """A list cut to what a hero scores would change shape from hero to
    hero, and "no initiation at all" is exactly the answer somebody
    clicks a portrait to get."""
    block = rolebar.HeroRoles()
    block.set_hero(a_rated_hero())
    assert set(block._cells) == set(roles_mod.ROLES)
    assert len(block._cells) == 8
    block.deleteLater()


def test_a_hero_the_table_has_never_heard_of_draws_nothing(qapp, styled):
    """Unknown is a real state here as everywhere else: eight empty rows
    would read as a hero that is good at none of them."""
    block = rolebar.HeroRoles()
    assert block.set_hero(999_999) is False
    block.deleteLater()

    callout = rolebar.RoleCallout()
    assert callout.show_hero(999_999, "Nobody") is False
    assert not callout.isVisible()
    callout.deleteLater()


def test_the_columns_are_a_fixed_gap_apart_rather_than_spread(qapp, styled):
    """"more ocmpact (there is too much space between carry and durable,
    support and escape".

    The Roles CARD spreads its slack between its two columns on purpose —
    right for a block as wide as the board, wrong for a box hanging over
    one portrait, where that gap would be most of the width. So this grid
    has a fixed separator and no stretch at all.
    """
    block = rolebar.HeroRoles()
    grid = block.layout()
    assert grid.columnMinimumWidth(2) == rolebar.CALLOUT_GAP
    for column in range(grid.columnCount()):
        assert grid.columnStretch(column) == 0, column
    block.deleteLater()


def test_it_carries_no_name_of_its_own(qapp, styled):
    """The tile it points at is an inch below with that hero's portrait
    on it — and where there is no artwork, that tile draws the name. The
    profile callout's lesson, and the two rows it saves are what decide
    whether this fits ABOVE the tile."""
    from PyQt6.QtWidgets import QLabel

    callout = rolebar.RoleCallout()
    callout.show_hero(a_rated_hero(), "Anti-Mage")
    words = {label.text() for label in callout.findChildren(QLabel)}
    assert words == set(roles_mod.ROLES), words
    callout.deleteLater()


# ---- where it goes -----------------------------------------------------

def test_it_is_never_a_window_of_its_own(qapp, styled):
    """A parentless QWidget is a WINDOW the moment anything shows it, and
    this app has opened a stray second "Dota Draft Assist" that way three
    times."""
    host = QWidget()
    callout = rolebar.RoleCallout(host)
    callout.show_hero(a_rated_hero(), "")
    callout.setVisible(True)
    assert callout.parentWidget() is host
    assert not callout.isWindow()
    host.deleteLater()


def test_it_sits_above_the_tile_and_points_down_at_it(qapp, styled):
    host = QWidget()
    host.resize(800, 600)
    callout = rolebar.RoleCallout(host)
    callout.show_hero(a_rated_hero(), "")
    target = QRect(300, 400, 120, 68)
    callout.point_at(target, host.rect())
    assert callout._below is False
    assert callout.geometry().bottom() <= target.top() + 1
    # The pointer is aimed at the tile's middle, not the box's.
    middle = callout.geometry().left() + callout._point_at * callout.width()
    assert abs(middle - target.center().x()) <= 2
    host.deleteLater()


def test_with_no_room_above_it_flips_under(qapp, styled):
    """Above is where it was asked for, and on a short window there is no
    above — so it goes under rather than over the tile it is about."""
    host = QWidget()
    host.resize(800, 600)
    callout = rolebar.RoleCallout(host)
    callout.show_hero(a_rated_hero(), "")
    target = QRect(300, 4, 120, 68)
    callout.point_at(target, host.rect())
    assert callout._below is True
    assert callout.geometry().top() >= target.bottom()
    host.deleteLater()


def test_it_is_clamped_sideways_but_the_pointer_is_not(qapp, styled):
    """A callout pushed sideways to stay on screen still has to name the
    portrait it is about, which is the whole job of the pointer."""
    host = QWidget()
    host.resize(400, 600)
    callout = rolebar.RoleCallout(host)
    callout.show_hero(a_rated_hero(), "")
    target = QRect(360, 400, 40, 68)
    callout.point_at(target, host.rect())
    assert callout.geometry().right() <= host.rect().right()
    middle = callout.geometry().left() + callout._point_at * callout.width()
    assert abs(middle - target.center().x()) <= 2
    host.deleteLater()


# ---- what the window does with it --------------------------------------

def test_clicking_a_pick_opens_it_and_clicking_again_shuts_it(window):
    tile = a_rated_tile(window)
    assert not window.role_callout.isVisible()
    tile.clicked.emit()
    _settle()
    assert window.role_callout.isVisible(), "no callout on a clicked pick"
    assert window.role_callout.geometry().bottom() <= tile.mapTo(
        window.centralWidget(), tile.rect().topLeft()).y() + 1
    tile.clicked.emit()
    _settle()
    assert not window.role_callout.isVisible(), "it outlived the selection"


def test_it_follows_the_one_selection_onto_a_suggestion(window):
    """ONE selection, so this follows `focus` like everything else rather
    than hanging off a click on a pick."""
    assert window.suggest_row.tiles, "the fixture should have suggestions"
    hero = window.suggest_row.tiles[0].hero_id
    window.suggest_row.clicked_hero.emit(hero)
    _settle()
    if roles_mod.known(hero):
        assert window.role_callout.isVisible()
    # And a pick clicked afterwards takes it over, rather than two boxes.
    tile = a_rated_tile(window)
    tile.clicked.emit()
    _settle()
    assert window.focus == ("ally", tile.property("hero_id"))


def test_it_never_covers_the_title_bar_or_the_tabs(window):
    """The chrome is not somewhere a callout about a portrait may go, and
    covering the window buttons with one would be worse than moving it —
    so the room it is clamped into is the TAB'S CONTENT, not the whole
    window."""
    tile = a_rated_tile(window)
    tile.clicked.emit()
    _settle()
    assert window.role_callout.isVisible()
    shell = window.centralWidget()
    page = window.draft_scroll.viewport()
    top = page.mapTo(shell, page.rect().topLeft()).y()
    assert window.role_callout.geometry().top() >= top, (
        "the callout is up over the chrome")


def test_clearing_the_board_takes_it_with_it(window):
    tile = a_rated_tile(window)
    tile.clicked.emit()
    _settle()
    assert window.role_callout.isVisible()
    window._clear_all()
    _settle()
    assert not window.role_callout.isVisible(), (
        "a callout outlived the hero it was about")
