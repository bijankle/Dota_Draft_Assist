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

from PyQt6.QtCore import (QPoint, QPointF, QRect, QRectF, QSize,
                          Qt, pyqtSignal)
from PyQt6.QtGui import QColor, QPainter, QPen, QPolygonF
from PyQt6.QtWidgets import (QAbstractButton, QCheckBox, QHBoxLayout,
                             QLabel, QPushButton, QSizeGrip, QSizePolicy,
                             QSpinBox, QStyle, QStyleOptionSpinBox,
                             QTabWidget, QWidget)

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
        painter.setPen(QColor(theme.TEXT))
        painter.drawText(
            QRectF(self.BOX + 7, 0, self.width() - self.BOX - 7,
                   self.height()),
            int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter),
            self.text())
        painter.end()

    def sizeHint(self):                             # noqa: N802
        hint = super().sizeHint()
        return QSize(self.BOX + 9 + self.fontMetrics()
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


class CountBox(QSpinBox):
    """The "how many to show" control, ON the thing it controls.

    It lived in Settings, two menus away from the strip whose length it
    sets, which is the wrong place for a number you tune by looking at the
    result. Small enough to sit beside a card heading, typable, and
    arrow-steppable.
    """

    def __init__(self, value: int, low: int, high: int, parent=None):
        super().__init__(parent)
        self.setRange(low, high)
        self.setValue(value)
        self.setAccelerated(True)
        self.setAlignment(Qt.AlignmentFlag.AlignRight
                          | Qt.AlignmentFlag.AlignVCenter)
        # SIZED TO ITS CONTENTS, not to a number somebody guessed. A fixed
        # 58px cut the digits off the moment the theme's padding grew, and
        # a control that cannot show its own value is worse than no
        # control. The widest value it can ever hold, plus what the frame
        # and the arrows actually measure.
        widest = max(len(str(low)), len(str(high)))
        digits = self.fontMetrics().horizontalAdvance("8" * widest)
        style = self.style()
        option = QStyleOptionSpinBox()
        self.initStyleOption(option)
        arrows = style.subControlRect(
            QStyle.ComplexControl.CC_SpinBox, option,
            QStyle.SubControl.SC_SpinBoxUp, self).width()
        self.setMinimumWidth(digits + max(arrows, 12) + 18)
        self.setSizePolicy(QSizePolicy.Policy.Minimum,
                           QSizePolicy.Policy.Fixed)


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


class BandedTabs(QTabWidget):
    """A tab widget whose tab row is ONE dark band, edge to edge.

    The tabs paint their own strip and the corner widget paints its own,
    and between the two — and past the corner widget to the window's edge —
    the tab widget's background showed through in the content colour. Three
    tones across one row, so the record and transparency controls read as
    floating above the tabs rather than sitting beside them.

    A stylesheet cannot reach that gap: `QTabWidget { background: ... }`
    does not paint the tab-bar area, and `::pane` is only the part below
    it. So the band is filled here, before anything else draws.

    **The TAB BAR sets the height**, and the corner widget is held to it.
    Left to itself the corner widget is as tall as its own contents, which
    is not the same number — so one side of the same row was taller than
    the other, which is exactly the seam the band exists to remove.
    """

    def _band_height(self) -> int:
        """The band covers WHATEVER the tab row actually occupies.

        Filling only the tab bar's height left a lighter strip above the
        corner widget on any machine where the toolbar came out taller —
        which is the discontinuity this class exists to remove. Painting
        the larger of the two can never leave a gap; holding the corner to
        the tab bar (below) is what stops there being one to cover.
        """
        corner = self.cornerWidget(Qt.Corner.TopRightCorner)
        return max(self.tabBar().sizeHint().height(), self.tabBar().height(),
                   corner.height() if corner is not None else 0)

    def _hold_corner_to_the_band(self) -> None:
        """The TAB BAR sets the height and the toolbar is held to it.

        Left to itself the corner widget is as tall as its own contents,
        and QTabWidget then grows the whole tab row to fit it — so the
        tabs sat high in a taller band and the controls sat low in it,
        which is the step in the padding the user drew a circle round.
        """
        corner = self.cornerWidget(Qt.Corner.TopRightCorner)
        bar = max(self.tabBar().sizeHint().height(), self.tabBar().height())
        if corner is not None and bar > 0 and corner.height() != bar:
            corner.setFixedHeight(bar)

    def showEvent(self, event) -> None:             # noqa: N802 - Qt naming
        super().showEvent(event)
        self._hold_corner_to_the_band()

    def resizeEvent(self, event) -> None:           # noqa: N802
        super().resizeEvent(event)
        self._hold_corner_to_the_band()

    def paintEvent(self, event) -> None:            # noqa: N802
        painter = QPainter(self)
        painter.fillRect(0, 0, self.width(), self._band_height(),
                         QColor(theme.BG_DEEP))
        painter.end()
        super().paintEvent(event)
