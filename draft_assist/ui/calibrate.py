"""Two red boxes you drag over the pick bar, and Confirm.

**CALIBRATION WAS SIX CLICKS DEEP IN A DEBUG PANEL**, drawn as a drag on
a small picture of the frame — "it should not be done in this silly
debugging menu". It is the setup step the whole draft reading depends on:
boxes that are not on the portraits read two of ten slots and there is
nothing else the user can do about it. So it is a first-class action now
(File > Calibrate pick boxes, and a task flagged in the banner) and it
happens ON THE GAME: two frameless always-on-top rectangles over the real
Dota window, dragged and resized by hand, with a Confirm.

**TWO BOXES, NOT TEN** — "just 2 big rectangles that go over all the
portraits for Radiant and all the portraits for Dire". Ten labelled boxes
were offered and turned down, and the simpler answer is also the only one
the stored calibration can hold: a `DraftLayout` is seven numbers — two
bank starts, one portrait size, one pitch — so ten rectangles placed by
hand could describe a pick bar that cannot exist. One box round each bank
is exactly what `autocal.measure_bank` was written to take.

**THEY EXIST ONLY WHILE CALIBRATING**, also at the user's request. They
are `Qt.Tool` windows so they stay out of the taskbar and Alt-Tab, which
is what got the old floating toggle deleted, and they are created on
Start and destroyed on Confirm or Cancel — nothing of this is on screen
during a draft.

**AND CONFIRM FITS THEM TO THE PORTRAITS IT CAN SEE.** Nobody drags a
rectangle accurate to the pixel and a box a few pixels out is a reading a
few pixels out for ever, so the drag is the starting point and
`autocal.layout_from_banks` snaps it onto the borders in the frame. When
the picture is too flat to fit anything it says so and keeps what was
drawn, rather than reporting noise as a measurement.
"""

from __future__ import annotations

from PyQt6.QtCore import QObject, QPoint, QRect, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QFont, QPainter, QPen
from PyQt6.QtWidgets import (QHBoxLayout, QLabel, QPushButton, QVBoxLayout,
                             QWidget)

from . import theme

# The handle in the bottom-right corner, and the smallest a box may get.
GRIP = 22
MIN_SIDE = 60
BORDER = 3
# The name sits in a strip ABOVE the rectangle rather than inside it. In
# the box it covered the first portrait of the bank — the very thing the
# left edge is being lined up against — which is the pick tile's rule
# again: a label over a picture hides the half you recognise it by.
LABEL_H = 22


def to_frame_rect(box: tuple[int, int, int, int],
                  client: tuple[int, int, int, int],
                  frame_size: tuple[int, int]) -> tuple[int, int, int, int]:
    """A rectangle on the SCREEN -> pixels in the captured frame.

    The frame is a picture of the window's client area, so the two differ
    by the window's origin and by whatever scaling the capture applied.
    Both are handled here rather than assumed to be 1:1, because a capture
    that hands back a different size than the client area is a resolution
    change waiting to put every box a fixed fraction out.
    """
    ox, oy, cw, ch = client
    fw, fh = frame_size
    sx = (fw / cw) if cw else 1.0
    sy = (fh / ch) if ch else 1.0
    return (round((box[0] - ox) * sx), round((box[1] - oy) * sy),
            round(box[2] * sx), round(box[3] * sy))


def measure_from_boxes(frame, client, first, second, base=None):
    """The two drawn boxes -> a saved-ready layout, or None and a reason.

    Screen coordinates in, `DraftLayout` out. Kept apart from the widgets
    so the arithmetic can be tested without a Dota window, a screen, or
    Windows — none of which exist where this is written.
    """
    from ..vision.autocal import layout_from_banks

    if frame is None:
        return None, "there is no picture of the game to measure"
    height, width = frame.shape[:2]
    size = (width, height)
    return layout_from_banks(frame,
                             to_frame_rect(first, client, size),
                             to_frame_rect(second, client, size), base)


class BankBox(QWidget):
    """One draggable, resizable red rectangle with its bank's name in it."""

    def __init__(self, name: str, below: bool = False, parent=None):
        super().__init__(parent)
        self.name = name
        # THE STRIP GOES UNDER THE BOX WHEN THERE IS NO ROOM ABOVE IT,
        # which is the normal case rather than an edge one: Dota's pick
        # bar hugs the TOP of the screen, so a name above the rectangle
        # opens at a negative y and is clipped off the display.
        self.below = below
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint
                            | Qt.WindowType.WindowStaysOnTopHint
                            # A TOOL WINDOW, so two more entries do not
                            # appear in the taskbar and in Alt-Tab. The
                            # floating overlay toggle was removed from
                            # this app for doing exactly that.
                            | Qt.WindowType.Tool)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setMouseTracking(True)
        self._drag: QPoint | None = None
        self._sizing = False

    # ---- moving and resizing -------------------------------------------
    def box_rect(self) -> QRect:
        """The RED RECTANGLE, which is the widget less its name strip."""
        top = 0 if self.below else LABEL_H
        return QRect(0, top, self.width(), self.height() - LABEL_H)

    def label_rect(self) -> QRect:
        top = self.height() - LABEL_H if self.below else 0
        return QRect(0, top, self.width(), LABEL_H)

    def _on_the_grip(self, point) -> bool:
        return (point.x() > self.width() - GRIP
                and point.y() > self.height() - GRIP)

    def mousePressEvent(self, event) -> None:       # noqa: N802 - Qt naming
        if event.button() != Qt.MouseButton.LeftButton:
            return
        where = event.position().toPoint()
        self._sizing = self._on_the_grip(where)
        self._drag = event.globalPosition().toPoint() - self.pos()

    def mouseMoveEvent(self, event) -> None:        # noqa: N802
        if self._drag is None:
            self.setCursor(
                Qt.CursorShape.SizeFDiagCursor
                if self._on_the_grip(event.position().toPoint())
                else Qt.CursorShape.SizeAllCursor)
            return
        point = event.globalPosition().toPoint()
        if self._sizing:
            self.resize(max(MIN_SIDE, point.x() - self.x()),
                        max(MIN_SIDE, point.y() - self.y()))
        else:
            self.move(point - self._drag)

    def mouseReleaseEvent(self, event) -> None:     # noqa: N802
        self._drag = None
        self._sizing = False

    # ---- drawing --------------------------------------------------------
    def paintEvent(self, event) -> None:            # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        inner = self.box_rect().adjusted(BORDER // 2, BORDER // 2,
                                         -BORDER // 2, -BORDER // 2)
        painter.setPen(QPen(QColor(theme.BAD), BORDER))
        painter.setBrush(QColor(255, 70, 70, 28))
        painter.drawRect(inner)

        font = QFont(self.font())
        font.setPixelSize(max(11, round(theme.BODY_PX * 0.9)))
        font.setBold(True)
        painter.setFont(font)
        painter.setPen(QColor(theme.BAD))
        painter.drawText(self.label_rect(),
                         int(Qt.AlignmentFlag.AlignLeft
                             | Qt.AlignmentFlag.AlignVCenter), self.name)

        # The grip, so it is obvious the box resizes as well as moves.
        painter.setPen(QPen(QColor(theme.BAD), 2))
        for step in (6, 11, 16):
            painter.drawLine(self.width() - step, self.height() - 4,
                             self.width() - 4, self.height() - step)
        painter.end()

    def screen_rect(self) -> tuple[int, int, int, int]:
        """Where the RECTANGLE is, in PHYSICAL screen pixels.

        The name strip above it is chrome and is not part of what is
        being measured — handing the widget's own geometry to the
        measurer would put every box a label's height too high.

        Qt lays out in logical pixels and `window_rect` answers in
        physical ones, so on a display at 150% the two disagree by half
        again — which would put every box a third of the way across the
        bar without a single number looking wrong.
        """
        ratio = self.devicePixelRatioF() or 1.0
        box = self.box_rect().translated(self.pos())
        return (round(box.x() * ratio), round(box.y() * ratio),
                round(box.width() * ratio), round(box.height() * ratio))


class Calibrator(QObject):
    """The two boxes and the small panel that confirms them."""

    finished = pyqtSignal(bool, str)        # saved?, what to say

    def __init__(self, client: tuple[int, int, int, int], parent=None):
        super().__init__(parent)
        self.client = client
        ratio = _ratio()
        ox, oy, width, height = [round(v / ratio) for v in client]
        # OPENED ROUGHLY WHERE THE BANKS ARE, from the layout the app is
        # already using, so the usual job is a nudge rather than finding
        # two boxes in the middle of the screen and dragging them up.
        #
        # **THROUGH `SlotRect.to_pixels`, NEVER BY MULTIPLYING THE WINDOW
        # WIDTH.** Every coordinate in a layout is a fraction of Dota's
        # 16:9 HUD BOX, which on anything wider than 16:9 is a centred
        # part of the window — taking them as fractions of the raw width
        # is what once put the crop boxes 440px left of the portraits.
        # And a bank spans four PITCHES plus ONE portrait, not five of
        # each: the first arithmetic here said `4 * slot_w + 4 * pitch`
        # and hung the Dire box a hundred pixels off the right edge of
        # the screen, where it could not be dragged at all.
        from ..vision.layout import load_layout
        slots = load_layout().slots()
        self.boxes = []
        for name, first, last in (("Radiant", 0, 4), ("Dire", 5, 9)):
            x0, y0, _w0, h0 = slots[first].to_pixels(width, height)
            x4, _y4, w4, _h4 = slots[last].to_pixels(width, height)
            below = y0 < LABEL_H          # the bar hugs the top edge
            box = BankBox(name, below=below)
            box.resize(max(MIN_SIDE, (x4 + w4) - x0),
                       max(MIN_SIDE, h0) + LABEL_H)
            box.move(ox + x0, oy + y0 - (0 if below else LABEL_H))
            self.boxes.append(box)

        self.panel = _Panel()
        self.panel.confirmed.connect(self._confirm)
        self.panel.cancelled.connect(lambda: self._close(False, ""))
        self.panel.move(ox + width // 2 - self.panel.width() // 2,
                        oy + height - round(160 / ratio))
        self.frame_of = None                # set by the caller

    def show(self) -> None:
        for box in self.boxes:
            box.show()
        self.panel.show()
        self.panel.raise_()

    def _confirm(self) -> None:
        from ..vision.layout import save_calibration

        frame = self.frame_of() if self.frame_of else None
        layout, note = measure_from_boxes(
            frame, self.client, self.boxes[0].screen_rect(),
            self.boxes[1].screen_rect())
        if layout is None:
            self.panel.say(note)
            return
        save_calibration(layout)
        self._close(True, f"Pick boxes calibrated — {note}")

    def _close(self, saved: bool, note: str) -> None:
        for box in self.boxes:
            box.close()
            box.deleteLater()
        self.panel.close()
        self.panel.deleteLater()
        self.finished.emit(saved, note)


class _Panel(QWidget):
    """What to do, and the two buttons. Its own window, above the boxes."""

    confirmed = pyqtSignal()
    cancelled = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint
                            | Qt.WindowType.WindowStaysOnTopHint
                            | Qt.WindowType.Tool)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        # NAMED, so the rule does not cascade into the buttons. Unscoped
        # it did, and the `border: none` each button then needed to undo
        # it beat `QPushButton[accent="true"]` as well — so Confirm, the
        # one action this window exists for, drew as a plain button.
        self.setObjectName("calPanel")
        self.setStyleSheet(
            f"QWidget#calPanel {{ background: {theme.BG_ELEVATED};"
            f" border: 1px solid {theme.BORDER}; border-radius: 8px; }}")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(16, 12, 16, 12)
        self.note = QLabel("Drag the red boxes over the two banks of five "
                           "portraits, then press Confirm.")
        self.note.setWordWrap(True)
        lay.addWidget(self.note)
        row = QHBoxLayout()
        cancel = QPushButton("Cancel")
        cancel.clicked.connect(self.cancelled)
        row.addWidget(cancel)
        row.addStretch(1)
        confirm = QPushButton("Confirm")
        confirm.setProperty("accent", True)
        confirm.setDefault(True)
        confirm.clicked.connect(self.confirmed)
        row.addWidget(confirm)
        lay.addLayout(row)
        self.setFixedWidth(460)

    def say(self, note: str) -> None:
        """A refusal, in place. The boxes stay up so it can be tried
        again — closing on a failure would throw away the drag."""
        self.note.setText(note)


def _ratio() -> float:
    from PyQt6.QtWidgets import QApplication

    screen = QApplication.primaryScreen()
    return (screen.devicePixelRatio() if screen else 1.0) or 1.0


def dota_client_rect() -> tuple[int, int, int, int] | None:
    """Dota's client area on screen, or None when it is not running.

    The boxes go ON the game, so there is nothing to put them on until it
    is open — which is why the action says so rather than opening two red
    rectangles over the desktop.
    """
    from ..capture.window import DOTA_TITLE, window_rect

    return window_rect(DOTA_TITLE)
