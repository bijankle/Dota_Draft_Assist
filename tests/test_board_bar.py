"""The row above the two cards, and the controls' one height.

Four requests that all landed in the same place:

  "change the paddign so that dire and radiant are above it, not in it"
  "move dire to align on the right side"
  "move these 3 buttons clear / detect / demon into the middle in line
   with Radiant and dire"
  "the clear / detec / etc fotn looks different to draft / analysis...
   also the yellow box is too tall... it shoudl be the height of the
   boxes around the number entry fields... standardize the height of
   these button boxes across the boartd to be this height", and then
   "there is a bit of a grey color added to the cclear / detect / etc
   button backgfground... should be same as the background behidn it"
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

from PyQt6.QtWidgets import QApplication, QPushButton       # noqa: E402

from draft_assist.config import RULES_FILE                  # noqa: E402
from draft_assist.model import items as items_mod           # noqa: E402
from draft_assist.ui import chrome, theme                   # noqa: E402
from draft_assist.ui.app import MainWindow                  # noqa: E402
from draft_assist.ui.demo import demo_dataset               # noqa: E402
from draft_assist.ui.providers import DemoProvider          # noqa: E402


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
    rules, meta = items_mod.load_rules(RULES_FILE)
    win = MainWindow(ds, DemoProvider(ds), rules, meta)
    win.timer.stop()
    win.resize(1400, 1000)
    win.show()
    for _ in range(4):
        QApplication.processEvents()
    yield win
    win.close()


def _at(window, widget):
    return widget.mapTo(window, widget.rect().topLeft())


# ---- the heading came out of the card ---------------------------------

def test_each_heading_sits_above_its_own_card(window):
    """"change the paddign so that dire and radiant are above it, not in
    it". The card's padding is what says which five are whose, and the
    name is about the card rather than part of it."""
    for side in ("ally", "enemy"):
        header = window.team_panels[side].header
        card = window.side_cards[side]
        assert header.parent() is not card
        assert (_at(window, header).y() + header.height()
                <= _at(window, card).y() + 2), f"{side} heading is inside"


def test_the_left_name_starts_where_its_own_PORTRAITS_start(window):
    """AND THAT IS ITS CARD'S INNER EDGE, NOT ITS OUTER ONE.

    This asked for the name to sit on the card's outer edge, which is
    where it sat while the five portraits were inset twice — once by the
    card and again by the panel inside it. With that duplicate gone the
    portraits sit on the card's padding, and a name on the outer edge is
    a border and a padding to the left of the picks it names: "i can
    aklls osee that the radiant header is not horixontally aligned with
    top heores". The column is what matters, so the column is what is
    asked for.
    """
    left, _right = window._panel_order
    name = _at(window, window.team_panels[left].caption).x()
    tile = _at(window, window.team_buttons[left][0]).x()
    assert abs(name - tile) <= 2, (
        f"the name starts at {name} and its first portrait at {tile}")


def test_the_right_name_finishes_where_its_card_finishes(window):
    """"move dire to align on the right side". The left heading starts at
    its picks' column, so the right one has to FINISH at its own or the
    two drift towards the middle with the buttons between them.

    THE CARD'S INNER EDGE, mirroring the left. The name used to be held
    to the card's OUTER edge, which is a border and a padding past the
    last portrait now that the panel no longer insets itself twice.
    """
    _left, right = window._panel_order
    panel = window.team_panels[right]
    end = max(w.mapTo(window, w.rect().topRight()).x()
              for w in (panel.caption, panel.total) if w.isVisible())
    last = window.team_buttons[right][-1]
    edge = last.mapTo(window, last.rect().topRight()).x()
    assert abs(end - edge) <= 2, (
        f"the right heading ends at {end} and its last portrait at {edge}")


def test_the_order_of_the_name_is_not_mirrored(window):
    """"Radiant | -9.0" reads the same way on both sides. Only the end
    they are anchored to changes — flipping one to "-9.8 | Dire" would
    make the two halves disagree about which figure is the heading."""
    for side in ("ally", "enemy"):
        panel = window.team_panels[side]
        panel.set_total(0.05)
        QApplication.processEvents()
        assert (_at(window, panel.caption).x()
                < _at(window, panel.total).x()), side


def test_the_board_actions_sit_between_the_two_headings(window):
    """"move these 3 buttons clear / detect / demon into the middle in
    line with Radiant and dire"."""
    left, right = window._panel_order
    actions = window.board_actions
    assert {w.text() for w in actions.findChildren(QPushButton)} == {
        "Clear all", "Detect all", "Demo"}
    here = _at(window, actions).x()
    assert _at(window, window.team_panels[left].caption).x() < here
    assert here + actions.width() < (
        window.team_panels[right].caption.mapTo(
            window, window.team_panels[right].caption.rect().topLeft()).x())
    # IN LINE: the three buttons and the two names share a row.
    for side in (left, right):
        caption = window.team_panels[side].caption
        assert abs(caption.mapTo(window, caption.rect().center()).y()
                   - actions.mapTo(window, actions.rect().center()).y()) <= 6


def test_playing_dire_swaps_the_headings_with_the_cards(window):
    """A name seated over the other team's five is worse than no name."""
    window._order_panels("enemy")
    QApplication.processEvents()
    left, right = window._panel_order
    assert left == "enemy"
    assert (_at(window, window.team_panels["enemy"].header).x()
            < _at(window, window.team_panels["ally"].header).x())
    # And the one on the right is the one anchored right.
    assert window.team_panels["ally"]._heading_right is True
    assert window.team_panels["enemy"]._heading_right is False


# ---- one height for every control -------------------------------------

def test_a_button_is_the_height_of_a_number_box(window):
    """"the yellow box is too tall... it shoudl be the height of the
    boxes around the number entry fields... standardize the height of
    these button boxes across the board to be this height". A button was
    41px against a count box's 33."""
    box = window.suggested_box
    assert box.height() == theme.CONTROL_H
    for button in (window.clear_all_button, window.detect_all_button,
                   window.demo_button):
        assert button.sizeHint().height() == theme.CONTROL_H, button.text()


def test_the_board_actions_show_the_surface_behind_them(window, qapp):
    """"there is a bit of a grey color added to the cclear / detect / etc
    button backgfground... should be same as the background behidn it".

    Checked against the PIXELS, because "it is in the stylesheet" has
    repeatedly not meant "it is on the screen" in this app.
    """
    from PyQt6.QtGui import QColor

    for _ in range(3):
        qapp.processEvents()
    picture = window.clear_all_button.grab().toImage()
    plate = QColor(theme.BG_INPUT).rgb()
    assert not any(picture.pixel(x, y) == plate
                   for x in range(2, picture.width() - 2)
                   for y in range(2, picture.height() - 2)), (
        "the button still paints a raised plate")


def test_the_board_actions_are_the_apps_own_bold(window):
    """"the clear / detec / etc fotn looks different to draft / analysis"
    — the base QPushButton rule sets `font-weight: 500`, which is the one
    weight in this app that is not the app's bold."""
    from PyQt6.QtGui import QFont

    for button in (window.clear_all_button, window.detect_all_button,
                   window.demo_button):
        button.ensurePolished()
        assert button.font().weight() == QFont.Weight.Bold, button.text()


# ---- the count box's border ------------------------------------------

def test_the_border_goes_round_the_field_and_not_the_arrows(styled, qapp):
    """"the numebr boxes should be about the size shown in green, with
    the [border] jsut aroudn thaat green box area and the arrows on the
    putside".

    The stylesheet's border wraps the whole WIDGET and there is no
    sub-control to exclude, so it enclosed the arrow strip too and the
    box read half again as wide as the number in it. The border is
    painted now; this checks where the ink lands.
    """
    from PyQt6.QtGui import QColor

    box = chrome.CountBox(20, 0, 20)
    box.ensurePolished()
    box.show()
    qapp.processEvents()
    # Qt answers `underMouse` from a cursor position of (0, 0) when there
    # is no pointer at all, and showing a widget at the origin delivers
    # an enter event with it — which is why this state is a FLAG the
    # widget sets rather than a question it asks. Cleared here so the
    # border is drawn in its resting colour.
    box._hover = False
    picture = box.grab().toImage()
    want = QColor(theme.BORDER)

    def near(pixel):
        got = QColor(pixel)
        return all(abs(a - b) < 24 for a, b in
                   ((got.red(), want.red()), (got.green(), want.green()),
                    (got.blue(), want.blue())))

    # THE MIDDLE ROW, where the two vertical sides are solid: a rounded
    # corner is antialiased away at the very top and bottom, and the
    # digits inside are antialiased against the ground all the way down.
    middle = box.height() // 2
    xs = [x for x in range(picture.width()) if near(picture.pixel(x, middle))]
    assert xs, "the box has no border at all"
    assert min(xs) == 0, f"the border does not start at the left edge: {xs}"
    assert max(xs) == box.field_box().right(), (
        f"the border runs past the field into the arrows: {xs}")
    # The arrows are outside it, and there is room for them.
    up, down = box._arrow_boxes()
    assert up.left() > box.field_box().right()
    assert down.right() <= box.width()
    box.deleteLater()


def test_stepping_a_count_box_does_not_highlight_its_own_number(styled,
                                                                qapp):
    """"when i click the up and down arrow the text box content is still
    highlighted... dont want the highlighted look".

    `QAbstractSpinBox.stepBy` selects the whole field on every step,
    which is right for a box you are about to type over and wrong for one
    you are clicking up and down — and on this app's palette the
    selection is the ACCENT, the deep red that means "the one action this
    screen wants", so a number nudged by one arrived looking like a
    warning.

    EVERY ROUTE, not just the arrows: the keyboard, Page Up and the
    accelerated repeat all arrive through `stepBy`, which is why the fix
    is there rather than on the click.
    """
    box = chrome.CountBox(20, 0, 33)
    box.ensurePolished()
    box.show()
    qapp.processEvents()
    edit = box.lineEdit()
    for act in (box.stepUp, box.stepDown, lambda: box.stepBy(5)):
        edit.selectAll()
        assert edit.selectedText(), "the fixture did not select anything"
        act()
        assert edit.selectedText() == "", "the number came back highlighted"
    box.deleteLater()


def test_no_control_in_the_app_wears_the_frames_gold(styled, qapp):
    """THIS REVERSES "a gold border on every button", at the user's
    request one message after they asked for it: "remove the gold border
    from all the input boxes ... revert that change i made - i dont liek
    it now that i have seen it... obviosuly keep the app window border
    though".

    Gold goes back to meaning "THIS ONE" and nothing else — the window's
    frame, the focus ring, the star, the pin, the role pills and the box
    round a relation's figure.
    """
    assert f"1px solid {theme.FRAME_GOLD}" not in theme.STYLESHEET
    rule = theme.STYLESHEET[theme.STYLESHEET.index("QSpinBox {"):]
    assert theme.FRAME_GOLD not in rule[:rule.index("}")]
