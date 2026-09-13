"""A title bar the app draws itself, and the floating button that hides it.

Windows' own title bar is a white strip above a dark app, which is what it
looked like — a different program bolted on top. Steam, Discord and every
other client the user has open all draw their own, so this one does too:
frameless window, our palette, our buttons, and the drag and resize that
the system bar was providing put back by hand.

Putting it back is the whole cost of the decision, and it is not free —
`ResizeGrip` and the drag handling below exist only because a frameless
window has neither. Both are deliberately dumb: eight-pixel margins, a
press, a move, a release.
"""

from PyQt6.QtCore import (QEvent, QObject, QPoint, QPointF, QRect, QRectF,
                          QSize, QTimer, Qt, pyqtSignal)
from PyQt6.QtGui import (QColor, QFontMetrics, QPainter, QPen,
                         QPolygonF)
from PyQt6.QtWidgets import (QAbstractButton, QCheckBox, QComboBox, QFrame,
                             QHBoxLayout, QLabel, QMenuBar, QPushButton,
                             QSizeGrip, QSizePolicy, QSpinBox, QTabBar,
                             QTabWidget, QVBoxLayout, QWidget)

from . import appicon, theme


def card(title: str | None = None,
         corner: QWidget | None = None) -> tuple[QFrame, QVBoxLayout]:
    """A titled panel. `corner` rides on the heading's right-hand end.

    That is where a control BELONGS when it changes the panel under it —
    "how many of these do I want" is answered by looking at the answer, and
    it was two menus away in Settings.

    It lives HERE rather than in `app.py` because it is the app's one
    container: the draft screen and the match history tab both build
    themselves out of these, and a second card that only looked nearly the
    same is exactly how two halves of one window start to disagree.
    """
    frame = QFrame()
    frame.setProperty("card", True)
    layout = QVBoxLayout(frame)
    layout.setContentsMargins(12, 10, 12, 12)
    layout.setSpacing(8)
    if title:
        label = QLabel(title)
        label.setProperty("heading", True)
        if corner is None:
            layout.addWidget(label)
        else:
            head = QHBoxLayout()
            head.setContentsMargins(0, 0, 0, 0)
            head.addWidget(label)
            head.addSpacing(8)
            head.addWidget(corner)
            head.addStretch(1)
            layout.addLayout(head)
    return frame, layout

# Tall enough for the app icon to be an icon rather than a bullet point.
BAR_HEIGHT = 48
# The icon fills the bar's height bar a few pixels of breathing room. It is
# drawn letterboxed into a square (see `appicon`), so a square icon fills
# that box edge to edge and a wide one keeps its whole picture instead of
# being sliced top and bottom.
ICON = BAR_HEIGHT - 8
EDGE = 6            # how close to the border counts as a resize grab
# A CORNER IS A BIGGER TARGET THAN AN EDGE, deliberately. An edge is
# reached for when the window is already where you want it and one
# dimension is wrong; a corner is what you reach for when the window has
# got away from you and has to be rescued, which is the harder aim and
# the one that matters more. Sixteen is about a fingertip at 100% scale
# and still small enough not to shadow anything a card puts in a corner.
CORNER = 16
# The selected tab's underline, in pixels. MUST match the `border-bottom`
# on `QTabBar::tab` in the stylesheet: the tab's text centres in what is
# left above it, and the toolbar beside it has to use the same middle.
TAB_UNDERLINE = 2


class WindowButton(QAbstractButton):
    """Minimise, maximise and close, PAINTED rather than typed.

    They were the characters "─", "□" and "✕" in whatever face the app is
    using, and a hollow square has no ink in the middle of it — at the
    same point size as a dash and a cross it reads noticeably smaller, and
    changing the app's font changed all three by different amounts. Three
    lines and a rectangle are the same size in every font there has ever
    been. Same reason `TickBox` and `RecordButton` paint themselves.
    """

    GLYPH = 11          # the box the mark is drawn inside

    def __init__(self, kind: str, parent=None):
        super().__init__(parent)
        self.kind = kind
        self.setObjectName(f"win_{kind}")
        self.setFixedSize(46, BAR_HEIGHT)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setAttribute(Qt.WidgetAttribute.WA_Hover, True)

    def paintEvent(self, event) -> None:            # noqa: N802 - Qt naming
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        hot = self.underMouse()
        if hot:
            painter.fillRect(self.rect(),
                             QColor(theme.BAD if self.kind == "close"
                                    else theme.BG_HOVER))
        ink = QColor("#ffffff" if hot else theme.TEXT_DIM)
        painter.setPen(QPen(ink, 1.6))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        box = QRectF(0, 0, self.GLYPH, self.GLYPH)
        box.moveCenter(QRectF(self.rect()).center())
        if self.kind == "min":
            middle = box.center().y()
            painter.drawLine(QPointF(box.left(), middle),
                             QPointF(box.right(), middle))
        elif self.kind == "max":
            painter.drawRect(box.adjusted(0.5, 0.5, -0.5, -0.5))
        else:
            painter.drawLine(box.topLeft(), box.bottomRight())
            painter.drawLine(box.topRight(), box.bottomLeft())
        painter.end()

    def enterEvent(self, event) -> None:            # noqa: N802
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:            # noqa: N802
        self.update()
        super().leaveEvent(event)


class TitleBar(QWidget):
    """Icon, title, and the three buttons Windows would have drawn."""

    minimise = pyqtSignal()
    maximise = pyqtSignal()
    # NOT `close`: a signal of that name shadows QWidget.close(), so the
    # bar could never be closed programmatically and the failure was a
    # baffling "native Qt signal is not callable".
    close_clicked = pyqtSignal()

    def __init__(self, title: str, parent=None):
        super().__init__(parent)
        self.setFixedHeight(BAR_HEIGHT)
        self.setObjectName("titleBar")
        # WITHOUT THIS THE BAR IS THE CONTENT COLOUR. Qt paints a
        # stylesheet background on a plain QWidget subclass only when this
        # attribute is set, so `QWidget#titleBar { background: ... }` was
        # being parsed and then ignored — the bar drew in the body's grey
        # while the tab row below it was properly dark, which is the step
        # the user kept pointing at. It was invisible while everything
        # above the tabs was the same grey.
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self._press: QPoint | None = None

        lay = QHBoxLayout(self)
        lay.setContentsMargins(8, 0, 0, 0)
        lay.setSpacing(8)

        middle = Qt.AlignmentFlag.AlignVCenter
        self.icon = QLabel()
        self.icon.setFixedSize(ICON, ICON)
        self.icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.refresh_icon()
        lay.addWidget(self.icon, 0, middle)
        self.title = QLabel(title)
        self.title.setObjectName("titleText")
        lay.addWidget(self.title, 0, middle)
        self.menus = QHBoxLayout()
        self.menus.setContentsMargins(8, 0, 0, 0)
        # Everything on the bar is centred on the bar's middle. A layout
        # left to itself stretches each child to the full 48px and the menu
        # bar then draws its items hard against the top, which is what
        # "Setup Game View Help" sitting high in the strip was.
        self.menus.setAlignment(middle)
        lay.addLayout(self.menus)
        lay.addStretch(1)

        self.extras = QHBoxLayout()
        self.extras.setContentsMargins(0, 0, 0, 0)
        self.extras.setSpacing(6)
        self.extras.setAlignment(middle)
        lay.addLayout(self.extras)

        for name, signal in (("min", self.minimise),
                             ("max", self.maximise),
                             ("close", self.close_clicked)):
            button = WindowButton(name, self)
            button.clicked.connect(signal.emit)
            lay.addWidget(button)

    def add_menu_bar(self, menu_bar: QWidget) -> None:
        """The menus live in the bar, not above it.

        QMainWindow would otherwise put its own menu strip above the
        central widget — a second bar sitting on top of this one, which is
        the arrangement this class exists to get rid of.
        """
        menu_bar.setObjectName("titleMenus")
        # Its own natural height, then centred: given the bar's full height
        # it fills it and draws the menu titles along the top edge.
        menu_bar.setFixedHeight(menu_bar.sizeHint().height())
        # And its own natural WIDTH as a floor. Given less, a QMenuBar
        # hides menus behind a ">>" extension button — Setup, Game, View
        # and Help disappearing into a chevron in our own title bar, with
        # a light square where the button sits. Four menus always fit; the
        # window has a minimum width far larger than they need.
        menu_bar.setMinimumWidth(menu_bar.sizeHint().width())
        self.menus.addWidget(menu_bar, 0, Qt.AlignmentFlag.AlignVCenter)

    def add_widget(self, widget: QWidget) -> None:
        """Anything that belongs on the bar rather than under it."""
        self.extras.addWidget(widget, 0, Qt.AlignmentFlag.AlignVCenter)

    def refresh_icon(self) -> None:
        """Re-read the app icon — after the user supplies their own."""
        self.icon.setPixmap(appicon.pixmap(ICON))

    # ---- dragging the window by its bar ---------------------------------
    def mousePressEvent(self, event) -> None:       # noqa: N802 - Qt naming
        if event.button() == Qt.MouseButton.LeftButton:
            self._press = (event.globalPosition().toPoint()
                           - self.window().frameGeometry().topLeft())
            event.accept()

    def mouseMoveEvent(self, event) -> None:        # noqa: N802
        if self._press is not None and not self.window().isMaximized():
            self.window().move(event.globalPosition().toPoint() - self._press)
            event.accept()

    def mouseReleaseEvent(self, event) -> None:     # noqa: N802
        self._press = None

    def mouseDoubleClickEvent(self, event) -> None:  # noqa: N802
        self.maximise.emit()


class ResizeGrip(QSizeGrip):
    """The corner Windows would have given us, drawn to match."""

    def paintEvent(self, event) -> None:            # noqa: N802
        painter = QPainter(self)
        painter.setPen(QColor(theme.TEXT_DIM))
        span = min(self.width(), self.height())
        for offset in (3, 7, 11):
            painter.drawLine(span - offset, span - 2, span - 2, span - offset)
        painter.end()


def _side(value: int, last: int, reach: int) -> int:
    """-1 near the low end, +1 near the high end, 0 in between."""
    if value <= reach:
        return -1
    if value >= last - reach:
        return 1
    return 0


def edge_at(window, pos: QPoint,
            edge: int = EDGE, corner: int = CORNER) -> Qt.Edge | None:
    """Which border `pos` is close enough to grab, if any.

    CORNERS ARE TESTED FIRST and with a longer reach, because a corner is
    two edges and an edge is one: asking "is this within `edge` of the
    left AND within `edge` of the top" makes the corner the SMALLEST
    target on the border rather than the largest, which is backwards —
    the corner is the one you reach for when the window has to be
    rescued.
    """
    rect: QRect = window.rect()
    right, bottom = rect.width() - 1, rect.height() - 1
    across = _side(pos.x(), right, corner)
    down = _side(pos.y(), bottom, corner)
    if across and down:
        return ((Qt.Edge.LeftEdge if across < 0 else Qt.Edge.RightEdge)
                | (Qt.Edge.TopEdge if down < 0 else Qt.Edge.BottomEdge))
    across = _side(pos.x(), right, edge)
    down = _side(pos.y(), bottom, edge)
    if across and not down:
        return Qt.Edge.LeftEdge if across < 0 else Qt.Edge.RightEdge
    if down and not across:
        return Qt.Edge.TopEdge if down < 0 else Qt.Edge.BottomEdge
    return None


#: The pointer for each grab, so the handle can be seen before it is used.
_CURSORS = {
    Qt.Edge.LeftEdge: Qt.CursorShape.SizeHorCursor,
    Qt.Edge.RightEdge: Qt.CursorShape.SizeHorCursor,
    Qt.Edge.TopEdge: Qt.CursorShape.SizeVerCursor,
    Qt.Edge.BottomEdge: Qt.CursorShape.SizeVerCursor,
    Qt.Edge.LeftEdge | Qt.Edge.TopEdge: Qt.CursorShape.SizeFDiagCursor,
    Qt.Edge.RightEdge | Qt.Edge.BottomEdge: Qt.CursorShape.SizeFDiagCursor,
    Qt.Edge.RightEdge | Qt.Edge.TopEdge: Qt.CursorShape.SizeBDiagCursor,
    Qt.Edge.LeftEdge | Qt.Edge.BottomEdge: Qt.CursorShape.SizeBDiagCursor,
}


def work_area(window) -> QRect | None:
    """The screen's usable rectangle — the monitor less its taskbar.

    Follows the window rather than the primary screen, so a second
    monitor of a different size gets its own answer. None when there is
    no screen to ask, which is every headless test.
    """
    screen = window.screen() if hasattr(window, "screen") else None
    if screen is None:
        from PyQt6.QtWidgets import QApplication
        screen = QApplication.primaryScreen()
    return screen.availableGeometry() if screen is not None else None


def is_corner(edges: Qt.Edge | None) -> bool:
    """Two edges at once — a corner rather than a side."""
    if edges is None:
        return False
    return bool(edges & (Qt.Edge.LeftEdge | Qt.Edge.RightEdge)) and bool(
        edges & (Qt.Edge.TopEdge | Qt.Edge.BottomEdge))


def reachable(where: QPoint, size: QSize,
              grab: int = 120, bar: int = BAR_HEIGHT) -> QPoint | None:
    """`where` nudged so a window of `size` opened there can be grabbed.

    A remembered position is only as good as the screen it was
    remembered on. Unplug the second monitor, or come back to a laptop
    undocked, and the spot the window was closed at is somewhere no
    display reaches — it opens invisible, and because the title bar is
    the only thing that MOVES this window, invisible means gone.

    So the answer is never the raw saved point. None when it lands on no
    attached screen at all, in which case the caller lets the window
    manager place it; otherwise the point pulled back just far enough
    that a piece of the title bar is on the work area and can be taken
    hold of. It is deliberately a NUDGE rather than a centring: a window
    parked deliberately half off the side is a thing people do, and
    "reachable" is a lower bar than "fully visible" on purpose.
    """
    from PyQt6.QtWidgets import QApplication
    box = QRect(where, size)
    screens = QApplication.screens()
    if not screens:
        return None
    def covered(screen) -> int:
        shared = screen.availableGeometry().intersected(box)
        return shared.width() * shared.height()
    best = max(screens, key=covered)
    if not covered(best):
        return None
    area = best.availableGeometry()
    # Horizontally it may hang off either side, so long as `grab` pixels
    # of it remain. Vertically the TOP edge is special: a title bar above
    # the top of the screen cannot be reached at all, however much of the
    # window is showing below it.
    x = min(max(where.x(), area.left() - size.width() + grab),
            area.right() - grab)
    y = min(max(where.y(), area.top()), area.bottom() - bar)
    return QPoint(x, y)


class ResizeBorder(QObject):
    """The four CORNER resize handles a frameless window does not get.

    Only the bottom-right corner was draggable — one `ResizeGrip` in the
    status bar — and that is the one handle a window stretched off the
    bottom of the screen does not have on screen any more. Being unable
    to reach the only handle is being unable to fix the window at all,
    which is what "it stretched very tall and I can't make it smaller"
    was: the fault and the way out went off the screen together.

    AN EVENT FILTER RATHER THAN EIGHT LITTLE WIDGETS, and the window
    buttons are why. `WindowButton` is 46 by the title bar's FULL height,
    so it reaches the very top-right pixel of the window — a handle
    widget laid over that corner would sit on top of Close and take a
    bite out of it, and a resize handle that eats the close button is a
    worse bug than the one being fixed. A filter sees only what its
    watched widgets did not accept, and a button accepts its own press,
    so every control on the border keeps all of its hit area.

    It therefore has to be installed on the widgets that ACCEPT mouse
    presses on the border — the title bar and the status bar — as well as
    on the window, which is where everything that ignores a press ends up
    by propagation.

    CORNERS ONLY, AND THE EDGES ARE LEFT ALONE, at the user's request:
    "now I can't drag to move the app window, can you make it so that it
    is only the corner (all 4) that can be dragged to resize, and the
    edges are just drag to move as they were before".

    A live top edge and a draggable title bar cannot share the same
    pixels, and the title bar is what the window is MOVED by — so a strip
    along the top of it that resized instead was the move gesture failing
    on the widget that exists for it. Sides are the same trade one axis
    over, for a gesture nobody was missing: the complaint this started
    from was reaching a CORNER of a window that had grown off the screen,
    and four corners answer it completely. `edge_at` still reports sides,
    because it describes the border; this decides what to act on.
    """

    def __init__(self, window):
        super().__init__(window)
        self.window = window
        self._edges: Qt.Edge | None = None
        self._from: QPoint | None = None
        self._was: QRect | None = None
        self._shaped = None         # the widget whose cursor WE set
        self.watching: list = []

    def watch(self, widget) -> None:
        """Take this widget's border presses, and its hovers for the cursor."""
        widget.setMouseTracking(True)
        widget.installEventFilter(self)
        self.watching.append(widget)

    # ---- the drag -------------------------------------------------------
    def begin(self, edges: Qt.Edge, where: QPoint) -> None:
        self._edges, self._from = edges, QPoint(where)
        self._was = QRect(self.window.geometry())

    def dragging(self) -> bool:
        return self._edges is not None

    def end(self) -> None:
        self._edges = self._from = self._was = None

    def release(self) -> None:
        """Give the mouse back and stop resizing."""
        if self.dragging():
            self.window.releaseMouse()
        self.end()

    def geometry_for(self, where: QPoint) -> QRect:
        """Where the window lands with the pointer here.

        The edge being dragged is the one that moves; the opposite edge is
        held, which is what makes dragging the TOP grow the window upwards
        instead of sliding it. Every limit is applied by pushing the
        dragged edge back, never the held one — clamping the far edge
        would walk the window across the screen while the pointer stood
        still.
        """
        box = QRect(self._was)
        shift = where - self._from
        left = bool(self._edges & Qt.Edge.LeftEdge)
        top = bool(self._edges & Qt.Edge.TopEdge)
        if left:
            box.setLeft(box.left() + shift.x())
        if self._edges & Qt.Edge.RightEdge:
            box.setRight(box.right() + shift.x())
        if top:
            box.setTop(box.top() + shift.y())
        if self._edges & Qt.Edge.BottomEdge:
            box.setBottom(box.bottom() + shift.y())

        low = self.window.minimumSize()
        high = self.window.maximumSize()
        # NEVER TALLER THAN THE SCREEN IT IS ON, at the user's request.
        # This is the live half of that; the saved size is clamped on the
        # way in as well, since a window can also arrive oversized from a
        # settings file an older build wrote.
        area = work_area(self.window)
        tallest = high.height()
        if area is not None:
            # IT STOPS THE WINDOW GROWING PAST THE SCREEN; it never yanks
            # one that is already past it. Clamping outright looks like
            # the same rule and is a trap: a window 4000 tall on an 800
            # tall screen would snap to 800 on the first touch, anchored
            # to whichever edge was being held — so the held edge stays
            # off the bottom, the whole window lands below the display
            # and the title bar goes with it. That is the complaint
            # again, one drag later and worse. Starting oversized, the
            # cap is simply where you started, so the drag shrinks it the
            # ordinary way; `MainWindow` clamps the SAVED size on the way
            # in, which is what actually ends the oversized state.
            tallest = min(tallest, max(area.height(), self._was.height()))

        want = max(low.width(), min(box.width(), high.width()))
        if want != box.width():
            if left:
                box.setLeft(box.right() - want + 1)
            else:
                box.setRight(box.left() + want - 1)
        want = max(low.height(), min(box.height(), tallest))
        if want != box.height():
            if top:
                box.setTop(box.bottom() - want + 1)
            else:
                box.setBottom(box.top() + want - 1)
        return box

    # ---- the filter -----------------------------------------------------
    def eventFilter(self, watched, event) -> bool:   # noqa: N802 - Qt naming
        kind = event.type()
        if kind == QEvent.Type.MouseButtonPress:
            return self._pressed(event)
        if kind == QEvent.Type.MouseMove:
            return self._moved(watched, event)
        if kind == QEvent.Type.MouseButtonRelease and self.dragging():
            self.release()
            return True
        if kind == QEvent.Type.Leave and not self.dragging():
            self._unshape(watched)
        return False

    def _at(self, event) -> QPoint:
        """The pointer in the WINDOW's coordinates, whoever saw the event.

        Read from the global position rather than the widget's own, since
        the same handler serves the window, the title bar and the status
        bar and each of those has a different origin.
        """
        return self.window.mapFromGlobal(event.globalPosition().toPoint())

    def grab_at(self, pos: QPoint) -> Qt.Edge | None:
        """The handle under `pos`, which is a corner or nothing at all."""
        edges = edge_at(self.window, pos)
        return edges if is_corner(edges) else None

    def _pressed(self, event) -> bool:
        if (event.button() != Qt.MouseButton.LeftButton
                or self.window.isMaximized()):
            return False
        edges = self.grab_at(self._at(event))
        if edges is None:
            return False
        self.begin(edges, event.globalPosition().toPoint())
        # THE WINDOW TAKES THE MOUSE FOR THE DRAG. Without it the moves
        # go to whichever widget the press was delivered to, and a press
        # on the border usually lands on a child that merely IGNORED it
        # and let it propagate up. Moves propagate the same way — until
        # the pointer crosses something that ACCEPTS them, which a table,
        # a tab bar or anything doing a hover effect does. The resize
        # would then freeze halfway across the window for no reason the
        # user could see. A grab makes delivery certain, and the release
        # below always gives it back.
        self.window.grabMouse()
        return True

    def _moved(self, watched, event) -> bool:
        if self.dragging():
            # A RESIZE WITH NO BUTTON HELD IS OVER, whatever happened to
            # the release. Losing one — the grab failing, the release
            # delivered somewhere unwatched — would otherwise leave every
            # later move resizing the window, and the title bar would
            # stop moving it for the rest of the session with nothing on
            # screen saying why.
            if not (event.buttons() & Qt.MouseButton.LeftButton):
                self.release()
                return False
            self.window.setGeometry(
                self.geometry_for(event.globalPosition().toPoint()))
            return True
        # Not a drag: say where the handles are. The event is NOT
        # consumed, or the title bar would never see the move that drags
        # the window and the tabs would never light under the pointer.
        if not self.window.isMaximized():
            self.hover(watched, self.grab_at(self._at(event)))
        return False

    def hover(self, widget, edges: Qt.Edge | None) -> None:
        """Show the grab under the pointer, and put the cursor back after.

        THE WIDGET IS REMEMBERED, not merely the fact that a cursor was
        set. Four widgets are watched and the pointer crosses between
        them — leaving the title bar's left edge for the status bar's
        would otherwise unset the cursor on the widget being ENTERED,
        which never had one, and leave the title bar wearing a resize
        arrow for the rest of the session.

        And only ever a cursor THIS object set: a widget with one of its
        own — the menu bar, a text field — must keep it.
        """
        if edges is None:
            self._unshape(widget)
            return
        if self._shaped is not None and self._shaped is not widget:
            self._unshape(self._shaped)
        widget.setCursor(_CURSORS[edges])
        self._shaped = widget

    def _unshape(self, widget) -> None:
        if self._shaped is widget and widget is not None:
            widget.unsetCursor()
            self._shaped = None


class TickBox(QCheckBox):
    """A check box that draws an actual TICK when it is on.

    Qt's stylesheet can colour the indicator but cannot put a mark in it
    without an image file, so a checked box read as "a blue square" — which
    says something is different about it, not that it is selected. The mark
    is what makes it obvious, so the indicator is painted here: the label
    still comes from QCheckBox, only the box is ours.
    """

    BOX = 15

    def __init__(self, text: str = "", parent=None):
        super().__init__(text, parent)
        self.setAttribute(Qt.WidgetAttribute.WA_Hover, True)

    def paintEvent(self, event) -> None:            # noqa: N802 - Qt naming
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        top = (self.height() - self.BOX) // 2
        box = QRectF(0, top, self.BOX, self.BOX)
        painter.setPen(QPen(QColor(theme.ACCENT if self.isChecked()
                                   else theme.BORDER), 1))
        painter.setBrush(QColor(theme.ACCENT) if self.isChecked()
                         else QColor(theme.BG_INPUT))
        painter.drawRoundedRect(box.adjusted(0.5, 0.5, -0.5, -0.5), 3, 3)
        if self.isChecked():
            # Three points, thick and round-capped, so it still reads as a
            # tick at fifteen pixels rather than as a smudge.
            pen = QPen(QColor("#ffffff"), 2.0)
            pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
            painter.setPen(pen)
            left, top_y = box.left(), box.top()
            painter.drawPolyline(QPolygonF([
                QPointF(left + self.BOX * 0.24, top_y + self.BOX * 0.52),
                QPointF(left + self.BOX * 0.42, top_y + self.BOX * 0.71),
                QPointF(left + self.BOX * 0.78, top_y + self.BOX * 0.29)]))
        # THE LABEL TAKES THE STYLESHEET'S COLOUR, not a hardcoded one.
        # Painting the text ourselves means the `color:` rule that dims
        # every other label on this row never reached it, so "Auto" sat
        # brighter than the tabs and the buttons beside it and read as a
        # different kind of thing. The palette is where a stylesheet's
        # `color` lands, so asking it puts this back under the same rule
        # as everything else — and the hover lift is the tabs' own, done
        # here because a pseudo-state colour does not reach a widget that
        # paints its own text.
        painter.setPen(QColor(theme.TEXT) if self.underMouse()
                       else self.palette().color(self.foregroundRole()))
        painter.drawText(
            QRectF(self.BOX + self.TEXT_GAP, 0,
                   self.width() - self.BOX - self.TEXT_GAP, self.height()),
            int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter),
            self.text())
        painter.end()

    # The label is drawn at `BOX + TEXT_GAP` and the widget ends one
    # pixel past it. It used to end THREE past, and since the gap either
    # side of a rule on this row is measured from the last INK rather
    # than from the widget, "Auto" sat 24px from its rule where every
    # other control sat 22 — near enough to look wrong and not near
    # enough to see why.
    TEXT_GAP = 7

    def sizeHint(self):                             # noqa: N802
        hint = super().sizeHint()
        return QSize(self.BOX + self.TEXT_GAP + 1 + self.fontMetrics()
                     .horizontalAdvance(self.text()),
                     max(hint.height(), self.BOX + 4))


class RecordButton(QAbstractButton):
    """The record control as the round red dot everyone already knows.

    It was a 110px "● Record" / "■ Stop" button, which is a lot of a narrow
    toolbar for one action whose symbol needs no words. Circle to record,
    square to stop, and the label was never carrying anything the shape
    does not.
    """

    SIZE = 24

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(self.SIZE, self.SIZE)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._recording = False
        self.set_recording(False)

    def set_recording(self, recording: bool) -> None:
        self._recording = bool(recording)
        self.setToolTip("Stop recording" if recording
                        else "Record this game — what Dota sends, what the "
                             "screen showed, and what the app concluded")
        self.update()

    def paintEvent(self, event) -> None:            # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        edge = QRectF(1.5, 1.5, self.SIZE - 3, self.SIZE - 3)
        hot = self.underMouse()
        painter.setPen(QPen(QColor(theme.BAD if hot or self._recording
                                   else theme.BORDER), 1.4))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawEllipse(edge)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(theme.BAD))
        inner = edge.adjusted(4.5, 4.5, -4.5, -4.5)
        if self._recording:
            painter.drawRoundedRect(inner, 1.5, 1.5)   # stop
        else:
            painter.drawEllipse(inner)                 # record
        painter.end()

    def enterEvent(self, event) -> None:            # noqa: N802
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:            # noqa: N802
        self.update()
        super().leaveEvent(event)


class Dropdown(QComboBox):
    """A dropdown that does NOT change when the wheel rolls over it.

    Qt's default is to step the value on every wheel notch, which makes
    every dropdown in a scrolling page a trap: the page moves, a control
    passes under the cursor, and the setting silently changes — "I keep
    accidentally scrolling and changing them by accident". The value is
    somebody's deliberate choice and the wheel is almost never how they
    mean to change it.
    **CLICK, SCROLL, CLICK**, as the user put it: the wheel is ignored so
    the page beneath scrolls instead, and the popup list — a separate
    widget, opened deliberately — still scrolls with the wheel like any
    other list.
    """

    def stepBy(self, steps: int) -> None:            # noqa: N802 - Qt naming
        """Step, and DO NOT leave the number selected afterwards.

        QSpinBox selects its whole text on every step, so clicking an
        arrow leaves the digits sitting in a highlight block - "I don't
        like that when I toggle the up / down arrow the entry ends up
        being highlighted, it doesn't look good". That selection is for
        a keyboard user about to retype the value; it makes no sense
        after a click on an arrow, where the value has just been set.

        In `stepBy` rather than in the arrow handler, so it holds for
        every way of stepping there is - the painted arrows, the keyboard
        arrows, Page Up - since a rule that covers only the one somebody
        complained about is a rule with a hole in it.
        """
        super().stepBy(steps)
        cursor = self.lineEdit()
        if cursor is not None:
            cursor.deselect()
            cursor.setCursorPosition(len(cursor.text()))

    def wheelEvent(self, event) -> None:            # noqa: N802 - Qt naming
        event.ignore()


class CountBox(QSpinBox):
    """The "how many to show" control, ON the thing it controls.

    It lived in Settings, two menus away from the strip whose length it
    sets, which is the wrong place for a number you tune by looking at the
    result. Small enough to sit beside a card heading, typable, and
    arrow-steppable.
    """

    # The strip we keep for the arrows, and how big the arrowheads in it
    # are. Both are drawn, never styled — see the class docstring.
    ARROWS_W = 18
    ARROW_W = 9

    def wheelEvent(self, event) -> None:            # noqa: N802 - Qt naming
        """The wheel belongs to the page — `Dropdown`'s reason exactly.

        This one sits on the same rows as those dropdowns and steps a
        number the same way, so scrolling past a card would quietly
        re-cut its table. The painted arrows and typing are how it is
        set.
        """
        event.ignore()
    ARROW_H = 5

    def __init__(self, value: int, low: int, high: int, parent=None):
        super().__init__(parent)
        self.setRange(low, high)
        self.setValue(value)
        self.setAccelerated(True)
        # LEFT, so the digits start where the box starts. Right-aligned
        # they were pushed up against the arrows, which reads as the
        # number belonging to the arrows rather than to the field.
        self.setAlignment(Qt.AlignmentFlag.AlignLeft
                          | Qt.AlignmentFlag.AlignVCenter)
        # WE DRAW THE ARROWS. Styling the sub-controls (`QSpinBox::up-
        # button`) puts Qt on the stylesheet path for them, and a
        # stylesheet can colour a sub-control but cannot put a MARK in one
        # without an image file — so the box lost its arrows entirely and
        # became a plain field you could not step. Same trap as the tick
        # box and the three window buttons, and the same answer.
        self.setButtonSymbols(QSpinBox.ButtonSymbols.NoButtons)
        # SIZED TO ITS CONTENTS, and FIXED: a Minimum policy let the
        # layout hand it whatever was going, which is how a two-digit box
        # ended up the width of a heading.
        #
        # The width comes from Qt'S OWN minimum, plus the strip we took for
        # the arrows. Adding up the digits and a guess at the padding does
        # not work: the stylesheet's padding and border are part of the
        # box too, so the arithmetic came out NARROWER than the widget's
        # own minimum and the number was clipped to its left half. Qt
        # already measures the widest value the range can hold against the
        # real font and the real chrome — the only thing it does not know
        # about is our arrow strip, because we draw that ourselves.
        self.setStyleSheet(f"padding-right: {self.ARROWS_W}px;")
        self._fit_width()
        self.setSizePolicy(QSizePolicy.Policy.Fixed,
                           QSizePolicy.Policy.Fixed)

    def _fit_width(self) -> None:
        """Qt's own minimum, widened for a prefix or suffix it forgot.

        **`minimumSizeHint` IS CACHED AND A SUFFIX DOES NOT INVALIDATE
        IT.** It answered 75 for this box before and after `setSuffix("
        days")`, while "14 days" measures 78 — so the field was two
        characters short of its own units and printed "14 day". Re-asking
        Qt is not enough; it has to be measured.
        It is still a FLOOR rather than a replacement, which is the rule
        this width has always had: arithmetic alone once came out
        NARROWER than the widget's own minimum and clipped the number to
        its left half. The chrome — the stylesheet's padding and border,
        which no font metric knows about — is recovered as the difference
        between Qt's hint and the bare digits it measured, so the sum can
        only ever be wider than the hint, never narrower.
        """
        self.ensurePolished()       # or the font is not the stylesheet's
        hint = QSpinBox.minimumSizeHint(self).width()
        metrics = QFontMetrics(self.font())
        bare = max((str(self.minimum()), str(self.maximum())),
                   key=lambda text: metrics.horizontalAdvance(text))
        chrome = max(0, hint - metrics.horizontalAdvance(bare))
        full = f"{self.prefix()}{bare}{self.suffix()}"
        self.setFixedWidth(
            max(hint, metrics.horizontalAdvance(full) + chrome)
            + self.ARROWS_W)

    # A SUFFIX IS PART OF THE WIDTH, and it is set AFTER construction —
    # which is where the box got its fixed width from Qt's minimum. So a
    # box asked for " days" came out measured for the bare digits and
    # printed "14 day", the number clipped by its own units. Re-fitting
    # here keeps the one rule the width has ever had: ask Qt, then add
    # the strip we took for the arrows.
    def setSuffix(self, text: str) -> None:         # noqa: N802 - Qt naming
        super().setSuffix(text)
        self._fit_width()

    def setPrefix(self, text: str) -> None:         # noqa: N802 - Qt naming
        super().setPrefix(text)
        self._fit_width()

    def _arrow_boxes(self) -> tuple[QRect, QRect]:
        """Up and down, stacked in the strip at the right-hand end."""
        strip = QRect(self.width() - self.ARROWS_W - 2, 1,
                      self.ARROWS_W, self.height() - 2)
        half = strip.height() // 2
        return (QRect(strip.x(), strip.y(), strip.width(), half),
                QRect(strip.x(), strip.y() + half, strip.width(),
                      strip.height() - half))

    def paintEvent(self, event) -> None:            # noqa: N802 - Qt naming
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setPen(Qt.PenStyle.NoPen)
        up, down = self._arrow_boxes()
        for box, rising in ((up, True), (down, False)):
            live = (self.value() < self.maximum() if rising
                    else self.value() > self.minimum())
            painter.setBrush(QColor(theme.TEXT if live else theme.BORDER))
            mid = box.center().x() + 1
            top = box.center().y() - self.ARROW_H // 2
            tip = top + (0 if rising else self.ARROW_H)
            base = top + (self.ARROW_H if rising else 0)
            painter.drawPolygon(QPolygonF([
                QPointF(mid, tip),
                QPointF(mid - self.ARROW_W / 2, base),
                QPointF(mid + self.ARROW_W / 2, base)]))
        painter.end()

    def mousePressEvent(self, event) -> None:       # noqa: N802 - Qt naming
        """The arrows are painted, so the clicks on them are ours too."""
        point = event.position().toPoint()
        up, down = self._arrow_boxes()
        if up.contains(point):
            self.stepUp()
            return
        if down.contains(point):
            self.stepDown()
            return
        super().mousePressEvent(event)


class FramedShell(QWidget):
    """The window's contents, with the ornate band painted round them.

    It has to be THIS widget rather than the window: a QWidget under the
    app's stylesheet paints its own background across its whole rectangle,
    margins included, so a frame drawn by the window behind it was covered
    up completely. Here the background is transparent, the layout is inset
    by the band's width, and the band is painted in the inset before any
    child draws.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("appShell")
        self.setStyleSheet("#appShell { background: transparent; }")

    def paintEvent(self, event) -> None:            # noqa: N802 - Qt naming
        from PyQt6.QtCore import QRectF
        from . import ornate
        painter = QPainter(self)
        ornate.paint_frame(painter, QRectF(self.rect()))
        painter.end()


def paint_rules(painter: QPainter, gaps: list[tuple[int, int, int]],
                height: int) -> None:
    """Draw one hairline down the middle of each gap.

    `gaps` is (left edge, right edge, centre y) per gap. Painted rather
    than styled for the usual reason: QMenuBar and QTabBar have no
    between-items sub-control for a stylesheet to reach, and a "|" put in
    the label text is a glyph that moves with the font and cannot be
    coloured apart from the label it sits in.
    """
    painter.setPen(QPen(QColor(theme.RULE), 1))
    for left, right, middle in gaps:
        x = (left + right) // 2
        painter.drawLine(x, middle - height // 2, x, middle + height // 2)


class Divider(QWidget):
    """A vertical rule between two controls on a row.

    The toolbar's own `addSeparator` draws whatever the style feels like
    (usually nothing under a stylesheet), so this is one widget with one
    line in it.
    """

    WIDTH = 13
    HEIGHT = 15

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedWidth(self.WIDTH)
        self.setSizePolicy(QSizePolicy.Policy.Fixed,
                           QSizePolicy.Policy.Preferred)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents,
                          True)

    def paintEvent(self, event) -> None:            # noqa: N802 - Qt naming
        painter = QPainter(self)
        painter.setPen(QPen(QColor(theme.RULE), 1))
        middle = self.height() // 2
        painter.drawLine(self.WIDTH // 2, middle - self.HEIGHT // 2,
                         self.WIDTH // 2, middle + self.HEIGHT // 2)
        painter.end()

    def sizeHint(self) -> QSize:                    # noqa: N802
        return QSize(self.WIDTH, self.HEIGHT)


class RuledMenuBar(QMenuBar):
    """Setup | Game | View | Help — with the rules drawn in."""

    def paintEvent(self, event) -> None:            # noqa: N802 - Qt naming
        super().paintEvent(event)
        visible = [self.actionGeometry(a) for a in self.actions()
                   if a.isVisible() and not a.isSeparator()]
        if len(visible) < 2:
            return
        painter = QPainter(self)
        paint_rules(painter,
                    [(a.right(), b.left(), (a.top() + a.bottom()) // 2)
                     for a, b in zip(visible, visible[1:])],
                    Divider.HEIGHT)
        painter.end()


class RuledTabBar(QTabBar):
    """Draft | Analysis | Debug — same idea, same rule."""

    def paintEvent(self, event) -> None:            # noqa: N802 - Qt naming
        super().paintEvent(event)
        boxes = [self.tabRect(i) for i in range(self.count())]
        if len(boxes) < 2:
            return
        painter = QPainter(self)
        paint_rules(painter,
                    [(a.right(), b.left(), (a.top() + a.bottom()) // 2)
                     for a, b in zip(boxes, boxes[1:])],
                    Divider.HEIGHT)
        painter.end()


class BandedTabs(QTabWidget):
    """Tabs and toolbar in ONE row that we lay out ourselves.

    This started as a QTabWidget with the toolbar in its top-right corner
    widget, and that arrangement produced four different versions of the
    same bug: the gap between the tabs and the toolbar in the content
    colour, a lighter strip above the controls, the toolbar hanging three
    pixels below the band, and the controls' middle sitting below the tab
    labels' middle. Every fix was a correction applied against geometry
    QTabWidget had already decided, and every one of them was either a
    pixel out or fighting the next layout pass.

    So the corner widget is gone. Qt's own tab bar is HIDDEN and never
    shown; the row is a plain widget holding our own `QTabBar` and the
    toolbar, both added with `AlignVCenter`, which is the one arrangement
    where "on the same line" is not a calculation. The two bars are kept in
    step in both directions, so `currentIndex`, `addTab` and everything
    else on QTabWidget still work — the pages are still its pages.
    """

    # Room between the last control and the window's frame.
    EDGE_GAP = 12

    def __init__(self, parent=None):
        super().__init__(parent)
        self.tabBar().hide()
        self.strip = QWidget()
        self.strip.setObjectName("tabStrip")
        self.strip.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        row = QHBoxLayout(self.strip)
        # A margin on the RIGHT only. The tab labels carry their own left
        # padding, but the last control on the toolbar — the transparency
        # slider — ran its handle right into the window's frame, which
        # reads as the row having been cut off rather than as it ending.
        row.setContentsMargins(0, 0, self.EDGE_GAP, 0)
        # THE SAME GAP THE TOOLBAR PUTS BETWEEN ITS OWN CONTROLS
        # (`QToolBar#tabStripTools { spacing }`). The rule between the tab
        # labels and the controls lives out here rather than on the
        # toolbar, so at spacing 0 it sat 10px off the record dot while
        # every rule inside the toolbar sat 22 off its neighbours. Only
        # the tab bar and a stretch are to its left, so nothing else on
        # the row moves.
        row.setSpacing(theme.TOOL_GAP)
        self.bar = RuledTabBar()
        self.bar.setObjectName("tabStripBar")
        self.bar.setDrawBase(False)
        self.bar.setExpanding(False)
        row.addWidget(self.bar, 0, Qt.AlignmentFlag.AlignVCenter)
        row.addStretch(1)
        self._row = row
        self.bar.currentChanged.connect(self._bar_chose)
        self.currentChanged.connect(self._page_changed)

    # -- the row ---------------------------------------------------------
    def add_tools(self, widget: QWidget) -> None:
        """Put a widget at the right-hand end of the tab row."""
        self._row.addWidget(widget, 0, Qt.AlignmentFlag.AlignVCenter)

    def add_rule(self) -> None:
        """A rule between the tab labels and the controls beside them."""
        self._row.addWidget(Divider(), 0, Qt.AlignmentFlag.AlignVCenter)

    def addTab(self, page, label):                  # noqa: N802 - Qt naming
        index = super().addTab(page, label)
        while self.bar.count() <= index:
            self.bar.addTab("")
        self.bar.setTabText(index, label)
        self.bar.setCurrentIndex(self.currentIndex())
        return index

    def setTabText(self, index, label):             # noqa: N802
        super().setTabText(index, label)
        if index < self.bar.count():
            self.bar.setTabText(index, label)

    def _bar_chose(self, index: int) -> None:
        if index != self.currentIndex():
            self.setCurrentIndex(index)

    def _page_changed(self, index: int) -> None:
        if index != self.bar.currentIndex():
            self.bar.setCurrentIndex(index)
