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

from PyQt6.QtCore import QPoint, QRect, QRectF, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QPainter, QPen
from PyQt6.QtWidgets import (QHBoxLayout, QLabel, QPushButton, QSizeGrip,
                             QWidget)

from . import appicon, theme

# Tall enough for the app icon to be an icon rather than a bullet point.
BAR_HEIGHT = 48
# The icon fills the bar's height bar a few pixels of breathing room. It is
# drawn letterboxed into a square (see `appicon`), so a square icon fills
# that box edge to edge and a wide one keeps its whole picture instead of
# being sliced top and bottom.
ICON = BAR_HEIGHT - 8
EDGE = 6            # how close to the border counts as a resize grab


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

        for name, glyph, signal in (
                ("min", "─", self.minimise),
                ("max", "□", self.maximise),
                ("close", "✕", self.close_clicked)):
            button = QPushButton(glyph)
            button.setObjectName(f"win_{name}")
            button.setFixedSize(46, BAR_HEIGHT)
            button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
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


class OverlayToggle(QPushButton):
    """The one thing that stays on screen when the window is hidden.

    It is the app's own icon rather than a plus sign, because it is the
    app: the button and the window it summons should look like the same
    program. Checkable so it reads as on or off at a glance — mid-draft the
    user needs to know whether the window is hidden or merely behind Dota.

    **It paints itself**, plate and icon both, rather than handing the icon
    to QPushButton. A translucent frameless top-level button styled by a
    stylesheet drew its plate and nothing else on Windows, so the one thing
    on screen when the window is hidden was a blank square — the same class
    of bug as QHeaderView refusing to honour `iconSize`. Drawing it is a
    dozen lines and it cannot be styled out from under us.
    """

    SIZE = 48
    PAD = 7             # plate edge to icon, so the border stays visible

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("overlayToggle")
        self.setCheckable(True)
        self.setChecked(True)
        self.setFixedSize(self.SIZE, self.SIZE)
        self._art = appicon.pixmap(self.SIZE - 2 * self.PAD)
        self.setToolTip("Show or hide the draft window · drag to move")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint
                            | Qt.WindowType.WindowStaysOnTopHint
                            | Qt.WindowType.Tool)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        # Appearing mid-draft must never pull keyboard focus out of the game.
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        self._press: QPoint | None = None
        self._dragging = False

    moved = pyqtSignal(int, int)

    def refresh_icon(self) -> None:
        """Re-read the app icon — after the user supplies their own."""
        self._art = appicon.pixmap(self.SIZE - 2 * self.PAD)
        self.update()

    def paintEvent(self, event) -> None:            # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
        plate = QRectF(self.rect()).adjusted(1, 1, -1, -1)
        # Pressed-in when the window is showing, popped-out when it is not:
        # the button has to say which state it is in without a label.
        painter.setPen(QPen(QColor(theme.ACCENT if self.isChecked()
                                   else (theme.TEXT_DIM if self.underMouse()
                                         else theme.BORDER)), 2))
        painter.setBrush(QColor(theme.BG_DEEP if self.isChecked()
                                else theme.BG_ELEVATED))
        painter.drawRoundedRect(plate, 8, 8)
        if not self._art.isNull():
            painter.setOpacity(1.0 if self.isChecked() else 0.75)
            painter.drawPixmap(
                (self.width() - self._art.width()) // 2,
                (self.height() - self._art.height()) // 2, self._art)
        painter.end()

    # Press becomes a drag once it has moved far enough to mean one; the
    # release is then swallowed so moving it never also toggles the window.
    def mousePressEvent(self, event) -> None:       # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            self._press = event.globalPosition().toPoint()
            self._offset = self._press - self.frameGeometry().topLeft()
            self._dragging = False
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:        # noqa: N802
        if self._press is None:
            return super().mouseMoveEvent(event)
        here = event.globalPosition().toPoint()
        if self._dragging or (here - self._press).manhattanLength() > 5:
            self._dragging = True
            self.move(here - self._offset)
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:     # noqa: N802
        if self._dragging:
            self._press, self._dragging = None, False
            self.setDown(False)
            self.moved.emit(self.x(), self.y())
            return
        self._press = None
        super().mouseReleaseEvent(event)


def edge_at(window, pos: QPoint) -> Qt.Edge | None:
    """Which border `pos` is close enough to grab, if any."""
    rect: QRect = window.rect()
    edges = Qt.Edge(0)
    if pos.x() <= EDGE:
        edges |= Qt.Edge.LeftEdge
    if pos.x() >= rect.width() - EDGE:
        edges |= Qt.Edge.RightEdge
    if pos.y() <= EDGE:
        edges |= Qt.Edge.TopEdge
    if pos.y() >= rect.height() - EDGE:
        edges |= Qt.Edge.BottomEdge
    return edges or None
