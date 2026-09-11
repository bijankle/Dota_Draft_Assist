"""Type into the Help menu itself, the way the Windows key does.

"When I hit help and start typing I should see it being entered into a
text box which sits on the help dropdown list" - so there is no Search
item to click and no window to open. The menu drops down, the box is
already at the top of it, and the first key pressed lands in the box.

THE BOX NEVER TAKES KEYBOARD FOCUS, and that is the whole trick. An open
QMenu holds a keyboard GRAB: every key press goes to the menu whatever
has focus, which is how its arrow navigation and its type-to-jump
shortcuts work. Fighting that grab for focus is the losing approach - it
half works, breaks the arrows, and behaves differently depending on which
widget the window last focused.

So the keys are FORWARDED instead. An event filter on the menu takes the
printable ones and backspace and hands them to the box; Up, Down, Enter
and Escape are left alone, so the menu still navigates its own results
with the keyboard exactly as it always did. Nothing is fought and nothing
depends on focus at all.

The CARET still needs the box focused to blink, so focus is asked for as
well - but only as decoration. Every keystroke works whether it lands or
not, which is what makes this reliable rather than lucky.
"""

from PyQt6.QtCore import QEvent, QObject, Qt, QTimer
from PyQt6.QtWidgets import (QHBoxLayout, QLineEdit, QWidget,
                             QWidgetAction)

from . import theme

# How many results the menu will show. A menu is not a scrolling list:
# past a handful it stops being readable and starts being a page.
CAP = 8
PLACEHOLDER = "Search settings and actions…"
NOTHING = "No match"

# Keys the MENU keeps, because they are how a menu is driven.
MENU_KEYS = frozenset((
    Qt.Key.Key_Up, Qt.Key.Key_Down, Qt.Key.Key_Return, Qt.Key.Key_Enter,
    Qt.Key.Key_Escape, Qt.Key.Key_Tab, Qt.Key.Key_Backtab,
    Qt.Key.Key_Left, Qt.Key.Key_Right, Qt.Key.Key_Home, Qt.Key.Key_End,
    Qt.Key.Key_PageUp, Qt.Key.Key_PageDown))


class MenuSearch(QObject):
    """A search box living at the top of a menu, with live results.

    `commands_of` is a callable rather than a list because the app's
    command list is built fresh - one list builds the Settings tabs AND
    feeds this, so asking for it late is what keeps the two from
    drifting.
    """

    def __init__(self, menu, commands_of, parent=None):
        super().__init__(parent or menu)
        self.menu = menu
        self.commands_of = commands_of
        self._results: list = []

        holder = QWidget(menu)
        lay = QHBoxLayout(holder)
        lay.setContentsMargins(8, 6, 8, 6)
        self.edit = QLineEdit(holder)
        self.edit.setPlaceholderText(PLACEHOLDER)
        self.edit.setClearButtonEnabled(False)
        self.edit.setMinimumWidth(280)
        self.edit.setStyleSheet(
            f"QLineEdit {{ background: {theme.BG_INPUT}; color: "
            f"{theme.TEXT}; border: 1px solid {theme.RULE}; "
            f"border-radius: 4px; padding: 4px 8px; }}")
        lay.addWidget(self.edit)

        self.box = QWidgetAction(menu)
        self.box.setDefaultWidget(holder)

        # The menu's OWN items, kept so an empty box can put them back.
        # Read once, here, before any result is ever added.
        self._own = list(menu.actions())
        menu.insertAction(self._own[0] if self._own else None, self.box)
        self._separator = menu.insertSeparator(
            self._own[0] if self._own else None)

        self.edit.textChanged.connect(self._refresh)
        menu.aboutToShow.connect(self._opened)
        menu.aboutToHide.connect(self._closed)
        menu.installEventFilter(self)

    # ------------------------------------------------------------ keys --

    def eventFilter(self, obj, event):                  # noqa: N802 - Qt
        """Printable keys go to the box; the menu keeps its own.

        READ THROUGH `getattr`, because this can fire while the object is
        being torn down. A filter stays installed on the menu until the
        menu itself goes, and Python clears an instance's __dict__ before
        the C++ side is destroyed - so a key arriving in that window hit
        `self.menu` on an object that no longer had one. That raises
        inside a Qt event filter, which does not propagate: the process
        ABORTS, with no traceback and no test failure, exactly like the
        QPixmap-before-QApplication trap this app already documents.
        """
        menu = getattr(self, "menu", None)
        edit = getattr(self, "edit", None)
        if menu is None or edit is None:
            return False
        if obj is menu and event.type() == QEvent.Type.KeyPress:
            if event.key() in MENU_KEYS:
                return False                 # arrows, Enter, Escape: theirs
            if event.key() == Qt.Key.Key_Backspace:
                edit.setText(edit.text()[:-1])
                return True
            text = event.text()
            # A BARE MODIFIER HAS NO TEXT and must fall through, or
            # holding Ctrl would be swallowed and the shortcuts below the
            # menu would stop working.
            if text and text.isprintable() and not (
                    event.modifiers() & (Qt.KeyboardModifier.ControlModifier
                                         | Qt.KeyboardModifier.AltModifier)):
                edit.setText(edit.text() + text)
                return True
        return super().eventFilter(obj, event)

    # --------------------------------------------------------- opening --

    def _opened(self) -> None:
        """A fresh box every time the menu drops.

        Leaving the last query in it would have the menu open showing
        somebody else's search, and the first key typed would append to
        it rather than start a new one.
        """
        self.edit.clear()
        self._refresh("")
        # Decoration only - see the module note. Deferred because the
        # widget is not on screen yet at `aboutToShow`.
        QTimer.singleShot(0, self.edit.setFocus)

    def _closed(self) -> None:
        self.edit.clear()

    # --------------------------------------------------------- results --

    def matches(self, query: str) -> list:
        from . import commands as commands_mod
        if not query.strip():
            return []
        return commands_mod.search(query, self.commands_of())[:CAP]

    def _clear_results(self) -> None:
        for action in self._results:
            self.menu.removeAction(action)
        self._results = []

    def _refresh(self, query: str = "") -> None:
        """Redraw the menu under the box.

        EMPTY MEANS THE MENU'S OWN ITEMS, at the user's request: "top 8
        matches, nothing when empty". A menu that listed every command
        before a key was pressed would be thirty rows of nothing anybody
        asked for.
        """
        self._clear_results()
        typing = bool(query.strip())
        for action in self._own:
            action.setVisible(not typing)
        self._separator.setVisible(not typing)

        if not typing:
            return

        found = self.matches(query)
        if not found:
            action = self.menu.addAction(NOTHING)
            action.setEnabled(False)
            self._results.append(action)
            return
        for command in found:
            # `title` carries the TRAIL - "Settings > Game data >
            # Diagnose game data" - because knowing where a thing lives
            # is most of what somebody searching for it wanted, and this
            # menu is now the only place that answer appears.
            action = self.menu.addAction(command.title)
            if command.detail:
                action.setToolTip(command.detail)
            action.triggered.connect(
                lambda _checked=False, c=command: self._take(c))
            self._results.append(action)

        # THE TOP RESULT IS HIGHLIGHTED, or Enter does nothing at all. A
        # QMenu activates nothing until an arrow key is pressed, so
        # without this you could type the exact name of a setting, press
        # Enter, and watch the menu sit there. Down and Up then move from
        # the top result rather than from nowhere.
        self.menu.setActiveAction(self._results[0])

    def _take(self, command) -> None:
        self.edit.clear()
        runner = getattr(command, "run", None)
        if callable(runner):
            runner()

    # ------------------------------------------------------------ open --

    def popup_under(self, bar) -> None:
        """Drop the menu open with the box ready, for Ctrl+K.

        The KEYBOARD path has to land in the same place as the mouse one,
        or the shortcut is a second way to search that behaves like a
        different feature.
        """
        action = self.menu.menuAction()
        where = bar.mapToGlobal(bar.actionGeometry(action).bottomLeft())
        self.menu.popup(where)
