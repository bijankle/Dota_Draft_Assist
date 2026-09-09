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

from PyQt6.QtCore import (QPoint, QPointF, QRect, QRectF, QSize, QTimer,
                          Qt, pyqtSignal)
from PyQt6.QtGui import QColor, QPainter, QPen, QPolygonF
from PyQt6.QtWidgets import (QAbstractButton, QCheckBox, QFrame, QHBoxLayout,
                             QLabel, QMenuBar, QPushButton, QSizeGrip,
                             QSizePolicy, QSpinBox, QTabBar,
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

    # The strip we keep for the arrows, and how big the arrowheads in it
    # are. Both are drawn, never styled — see the class docstring.
    ARROWS_W = 18
    ARROW_W = 9
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
        self.setFixedWidth(
            QSpinBox.minimumSizeHint(self).width() + self.ARROWS_W)
        self.setSizePolicy(QSizePolicy.Policy.Fixed,
                           QSizePolicy.Policy.Fixed)

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
        row.setSpacing(0)
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
