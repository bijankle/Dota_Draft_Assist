"""The profile in the title bar, and what drops out of it.

Four requests, in the order they arrived:

  "why is the thumbnail not working??"
  "Instead of showign the date where it is atm next to bijson, i want it
   to be in brackets after bijson in the main menu look, so Bijson (6
   months) <arrow down> and when you click you see profiele pic  Bijson
   and below that you see a 6 motnhs box that you can click to see a
   dropdown and select different durations and an apply button next to
   that to change the history look back range... updates from today
   backlwards"
  "when the user clicks the down arrow on the profile i want to see win
   rate %, in brackets after that i want the delta from the previous XXX
   duration)... and below those two i want games played (with a delta
   also, qty)"
  "for these deltas i want them to show green if positive and red if
   negative... ensure bvlack halo effect is on green / red text so it is
   readable"
"""

import os
import sys
from datetime import datetime
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

pytest.importorskip("PyQt6")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication                        # noqa: E402

from draft_assist.history import avatars                        # noqa: E402
from draft_assist.history.report import (Before, Options,       # noqa: E402
                                         Report)
from draft_assist.history.shape import Match                    # noqa: E402
from draft_assist.ui import theme                               # noqa: E402
from draft_assist.ui.accountrow import (NOTHING, NO_PROFILE,    # noqa: E402
                                        ProfileButton, ProfileCard)

ACCOUNT = 4242424242            # see `test_no_personal_data`
NAME = "ExampleDrafter"


@pytest.fixture(scope="module")
def qapp():
    yield QApplication.instance() or QApplication([])


def a_match(win: bool) -> Match:
    return Match(match_id=8000000001, start=0, when=datetime(2026, 9, 1),
                 duration=2000, slot=1, radiant=True, win=win,
                 hero_id=1, hero="Anti-Mage")


def a_report(*, played=100, won=60, before=None, window="6m") -> Report:
    matches = [a_match(i < won) for i in range(played)]
    return Report(options=Options(account_id=ACCOUNT, window=window),
                  how="", name=NAME, matches=matches, blocks=[], dropped={},
                  sessions=1, returned=played,
                  ran_at=datetime(2026, 9, 15), before=before)


# ---- the two deltas, on the report ------------------------------------

def test_the_deltas_are_points_and_a_count():
    """"XXX % (+ YYY%) where XXX is the winr rate for the last year and
    YYY is the win rate % increase or decrease since the year before
    that... and below those two i want games played (with a delta also,
    qty)".

    POINTS, not a ratio: 60% against 50% is +10, never +0.2.
    """
    report = a_report(played=100, won=60, before=Before(matches=80, wins=40))
    assert report.win_rate == pytest.approx(0.60)
    assert report.win_rate_delta == pytest.approx(10.0)
    assert report.games_delta == 20


def test_nothing_measured_is_not_no_change():
    """`before` is three-valued for the same reason `required` and
    `Profile.known` are: "All history" has nothing before it, the fetch
    can fail, and it can come back clipped. A zero there would read as
    "exactly the same as last time", which is a measurement nobody made.
    """
    report = a_report(before=None)
    assert report.win_rate_delta is None and report.games_delta is None
    # An empty stretch IS an answer: a new account is up from nothing.
    fresh = a_report(played=40, won=20, before=Before())
    assert fresh.win_rate_delta is None          # no rate over no games
    assert fresh.games_delta == 40


def test_a_rate_over_no_games_is_not_nought():
    assert Before(matches=0, wins=0).rate is None
    assert Before(matches=4, wins=1).rate == pytest.approx(0.25)


def test_the_window_label_loses_its_prefix_for_the_button():
    """"Bijson (6 months)", not "Bijson (Last 6 months)"."""
    assert Options(window="6m").window_short == "6 months"
    assert Options(window="12m").window_short == "12 months"
    # Nothing to drop, so nothing is dropped.
    assert Options(window="all").window_short == "All history"


# ---- the card ----------------------------------------------------------

def test_the_card_prints_both_figures_and_both_deltas(qapp):
    card = ProfileCard()
    card.show_report(a_report(played=100, won=53,
                              before=Before(matches=63, wins=32)))
    assert card.values["rate"].text() == "53%"
    assert card.values["games"].text() == "100"
    assert card.deltas["rate"].text() == "(+2.2%)"
    assert card.deltas["games"].text() == "(+37)"
    card.deleteLater()


def test_up_is_green_and_down_is_red(qapp):
    """"for these deltas i want them to show green if positive and red if
    negative"."""
    card = ProfileCard()
    card.show_report(a_report(played=100, won=70,
                              before=Before(matches=120, wins=60)))
    assert card.deltas["rate"].colour == theme.GOOD      # 70% from 50%
    assert card.deltas["games"].colour == theme.BAD      # 100 from 120
    card.deleteLater()


def test_a_flat_delta_is_neither(qapp):
    """Green means better and red means worse, so "no different" must be
    a third thing rather than borrowing one of them."""
    card = ProfileCard()
    card.show_report(a_report(played=100, won=50,
                              before=Before(matches=100, wins=50)))
    assert card.deltas["rate"].text() == "(+0.0%)"
    assert card.deltas["rate"].colour == theme.TEXT_DIM
    assert card.deltas["games"].colour == theme.TEXT_DIM
    card.deleteLater()


def test_no_brackets_around_a_measurement_nobody_made(qapp):
    card = ProfileCard()
    card.show_report(a_report(before=None))
    assert card.deltas["rate"].text() == ""
    assert card.deltas["games"].text() == ""
    # The figures themselves are still there — only the comparison is not.
    assert card.values["rate"].text().endswith("%")
    card.deleteLater()


def test_the_deltas_carry_the_apps_own_halo(qapp):
    """"ensure bvlack halo effect is on green / red text so it is
    readable". It is the same `HaloLabel` the side totals use, which is
    the same `tilekit.stroked` every badge in the app draws through —
    one implementation, so two of them cannot drift apart."""
    from draft_assist.ui.teams import HaloLabel

    card = ProfileCard()
    assert all(isinstance(label, HaloLabel)
               for label in card.deltas.values())
    card.deleteLater()


def test_nothing_measured_draws_the_prompt(qapp):
    card = ProfileCard()
    card.show_report(None)
    assert card.values["rate"].text() == NOTHING
    assert card.values["games"].text() == NOTHING
    assert card.deltas["rate"].text() == ""
    card.deleteLater()


def test_the_button_says_update_and_not_apply(qapp):
    """"i actually think you should call it 'update' so that it can be
    hit even if the user has not changed the dropdown, as sometimes you
    may want to keep amoutn of time the same and just update it".

    Apply names a change to the box beside it, which makes a press with
    nothing changed look like a no-op. Update names what the press
    actually does — re-measure from today backwards — and it is the same
    word the History tab's own button takes once there is a run behind
    it.
    """
    card = ProfileCard()
    assert card.apply_button.text() == "Update"
    assert card.apply_button.isEnabled(), (
        "it has to be pressable with the dropdown untouched")
    card.deleteLater()


def test_pressing_it_unchanged_still_asks_for_a_run(qapp):
    card = ProfileCard()
    card.show_report(a_report(window="6m"))
    seen = []
    card.applied.connect(seen.append)
    card._apply()
    assert seen == ["6m"], "a press with nothing changed did nothing"
    card.deleteLater()


def test_the_tooltip_names_the_two_stretches_it_compared(qapp):
    """A reader who thinks a figure looks wrong has to be able to check
    it against something — "6 motnhs to now my win rate is 5.8% worse
    than it was 12 months to 6 months ago???" is the question this line
    exists to let somebody answer."""
    card = ProfileCard()
    card.show_report(a_report(played=100, won=49, window="6m",
                              before=Before(matches=63, wins=35)))
    tip = card.toolTip()
    assert "63 matches, 35 won" in tip
    # The run was made on 15 Sep 2026 over six months, so the two spans
    # are Sep 2025 -> Mar 2026 and Mar 2026 -> Sep 2026.
    assert "Sep 2025" in tip and "Mar 2026" in tip and "Sep 2026" in tip
    card.deleteLater()


def test_with_no_comparison_the_tooltip_says_why_rather_than_nothing(qapp):
    card = ProfileCard()
    card.show_report(a_report(before=None))
    assert "could not be measured in full" in card.toolTip()
    card.deleteLater()


def test_the_window_box_follows_the_run_and_apply_hands_the_key_back(qapp):
    """The card CHOOSES; the window runs. A second path to a run would be
    a second set of answers to the account, the cap and the filters."""
    card = ProfileCard()
    card.show_report(a_report(window="3m"))
    assert card.window_key() == "3m"

    seen = []
    card.applied.connect(seen.append)
    card.set_window("12m")
    card._apply()
    assert seen == ["12m"]
    card.deleteLater()


def test_setting_the_window_is_not_the_user_applying_it(qapp):
    """Restoring a control to what the run already says must not fire the
    action — the `_apply_options` trap, one card over."""
    card = ProfileCard()
    seen = []
    card.applied.connect(seen.append)
    card.show_report(a_report(window="1m"))
    card.set_window("6m")
    assert seen == []
    card.deleteLater()


def test_the_callout_does_not_repeat_the_button_that_opened_it(qapp):
    """"you dont need to shwo profile pic and name in the dropdown - its
    in the button already".

    It opened with a face and a name an inch below the same face and the
    same name, so its first two rows said nothing. THE CARD KEEPS NO
    IDENTITY AT ALL now — not hidden, gone — which is why
    `accountrow.display_name` exists: the window used to take the name
    for the title bar off this card's own label.
    """
    from PyQt6.QtWidgets import QLabel

    card = ProfileCard()
    card.show_report(a_report())
    assert not hasattr(card, "who")
    assert not hasattr(card, "face")
    shown = {label.text() for label in card.findChildren(QLabel)}
    assert NAME not in shown, "the name is on the card again"
    assert str(ACCOUNT) not in shown, "the account id is on the card"
    card.deleteLater()


def test_the_name_comes_off_the_report_rather_than_a_widget(qapp):
    from draft_assist.ui.accountrow import display_name

    assert display_name(a_report()) == NAME
    # No persona resolved: the number is what a person has to go on.
    bare = a_report()
    bare.name = ""
    assert display_name(bare) == str(ACCOUNT)
    assert display_name(None) == ""


# ---- the load bar ------------------------------------------------------

def test_pressing_update_says_so_before_anything_else_can(qapp):
    """"when the user hits update on the 3 month oor whatevber, i want
    some sort of feedback to aknowledge that it is loading".

    SET ON THE PRESS rather than waiting for the run to report itself: a
    failure that never reaches a worker — a bad id, a run already going —
    would otherwise leave the press with no acknowledgement at all, and
    `set_busy(False)` arrives from the tab either way.
    """
    card = ProfileCard()
    card.show_report(a_report())
    assert not card.busy()
    card._apply()
    assert card.busy(), "the press said nothing"
    card.set_busy(False)
    assert not card.busy()
    card.deleteLater()


def test_the_bar_is_only_there_while_it_is_running(qapp):
    card = ProfileCard()
    assert not card.load_bar.isVisibleTo(card)
    card.set_busy(True)
    assert card.load_bar.isVisibleTo(card)
    card.set_busy(False)
    assert not card.load_bar.isVisibleTo(card)
    card.deleteLater()


def test_the_bar_costs_nothing_when_nobody_is_looking(qapp):
    """It lives inside a QMenu that is shut most of the time, and a
    repaint every 40ms for a widget nobody can see is the kind of cost
    the live loop has rules about."""
    from draft_assist.ui import chrome

    bar = chrome.LoadBar()
    assert not bar._timer.isActive()
    bar.set_busy(True)
    bar.show()
    assert bar._timer.isActive()
    bar.hide()
    assert not bar._timer.isActive(), "still ticking while hidden"
    bar.show()
    assert bar._timer.isActive(), "did not pick up again"
    bar.set_busy(False)
    assert not bar._timer.isActive()
    bar.deleteLater()


def test_the_bar_is_painted_in_the_apps_accent(qapp):
    """PAINTED, not a QProgressBar: this app's stylesheet does not name
    that widget's sub-controls, and once a stylesheet touches a widget
    the parts it does not name go to the NATIVE style — which on Windows
    would be a stock blue bar in the one palette where blue means
    nothing. The scrollbars' lesson."""
    from PyQt6.QtGui import QColor

    from draft_assist.ui import chrome, theme

    bar = chrome.LoadBar()
    bar.resize(200, chrome.LoadBar.HEIGHT)
    bar.set_busy(True)
    bar.show()
    # A cycle STARTS with the block just off the left-hand edge, so a
    # grab at rest is a picture of the track and nothing else.
    for _ in range(12):
        bar._step()
    picture = bar.grab().toImage()
    want = QColor(theme.ACCENT).rgb()
    assert any(picture.pixel(x, y) == want
               for x in range(picture.width())
               for y in range(picture.height())), "no accent on the bar"
    # And it MOVES, or it is a red rectangle rather than a loading bar.
    was = bar._at
    for _ in range(3):
        bar._step()
    assert bar._at != was
    bar.deleteLater()


def test_the_bar_keeps_its_block_inside_the_track(qapp):
    """It runs off one end and comes back on at the other, so the travel
    is one block longer than the track — and the arithmetic must not
    leave it stranded off-screen at either end."""
    from draft_assist.ui import chrome

    bar = chrome.LoadBar()
    bar.resize(200, chrome.LoadBar.HEIGHT)
    bar.set_busy(True)
    seen = []
    block = 200 * chrome.LoadBar.BLOCK
    for _ in range(200):
        bar._step()
        seen.append(bar._at * (200 + block) - block)
    assert min(seen) < 0, "the block never enters from the left"
    assert max(seen) + block > 200, "the block never reaches the right"
    # And it is never placed WHOLLY past either end, which is a bar that
    # pauses once a cycle.
    assert min(seen) > -block
    assert max(seen) < 200
    bar.deleteLater()


# ---- the button --------------------------------------------------------

def test_the_button_names_the_window_in_brackets(qapp):
    button = ProfileButton()
    button.show_run(NAME, ACCOUNT, "6 months")
    assert button.who.text() == f"{NAME} (6 months)"
    button.deleteLater()


def test_the_button_falls_back_to_its_own_short_form(qapp):
    """The card says "No account measured yet", which is a sentence —
    right for a callout and four times too long for a title bar."""
    button = ProfileButton()
    button.show_run("", 0, "")
    assert button.who.text() == NO_PROFILE
    button.deleteLater()


def test_the_button_draws_the_picture_that_is_on_disk(qapp, tmp_path,
                                                      monkeypatch):
    """THE BUG THIS FILE WAS OPENED FOR — "why is the thumbnail not
    working??".

    `show_name` set the LABEL and nothing else, so the face kept the "?"
    it was given in `__init__` for the life of the app, on every account,
    however many runs had been measured. The picture was on disk the
    whole time: `AccountRow` has always drawn it from the same file.
    """
    from PyQt6.QtGui import QImage

    picture = tmp_path / "avatars"
    picture.mkdir(parents=True)
    image = QImage(32, 32, QImage.Format.Format_RGB32)
    image.fill(0x00FF00)
    image.save(str(picture / f"{ACCOUNT}.img"), "PNG")
    monkeypatch.setattr(avatars, "cache_dir", lambda: tmp_path)

    button = ProfileButton()
    button.show_run(NAME, ACCOUNT, "6 months")
    assert button.face._pixmap is not None, "the face is still the initial"

    # And an account with no picture falls back rather than drawing
    # nothing — a missing avatar is normal, like a missing portrait.
    button.show_run(NAME, 1, "6 months")
    assert button.face._pixmap is None
    assert button.face._initial == "E"
    button.deleteLater()
