"""The debug picture, with the crop boxes draggable on top of it.

Calibration used to be six fractional numbers in six spin boxes. Every one
of them is a fraction of Dota's 16:9 HUD box rather than of the window, so
"the boxes are 135 pixels left of the portraits" is not a number anybody can
convert in their head into "radiant_x should be 0.11 rather than 0.0575".
The user could see exactly what was wrong and had no way to say it.

So they say it by DRAGGING. Three rectangles — the first portrait of your
bank, the last portrait of your bank, the first of theirs — and the six
numbers fall out with no assumptions in them: the first gives the origin
and the size, the last gives the pitch across four steps, and the third
gives where the other bank starts. One portrait at a time, because a box
around a whole bank leaves the gap between portraits unknown and there is
no honest way to guess it.

The view maps widget pixels back to FRAME pixels, which is the only part
with any subtlety: the frame is scaled to fit and centred, so a click is
offset by the letterbox margin and scaled by whatever ratio the fit chose.
"""

from PyQt6.QtCore import QPoint, QRect, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QPainter, QPen
from PyQt6.QtWidgets import QLabel

from . import theme


class FrameView(QLabel):
    """The captured frame, with a rubber band for picking out a rectangle."""

    # The dragged rectangle, in the FRAME's own pixels.
    boxed = pyqtSignal(int, int, int, int)

    def __init__(self, text: str = "", parent=None):
        super().__init__(text, parent)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setMouseTracking(True)
        self._frame_size: tuple[int, int] = (0, 0)
        self._picking = False
        self._from: QPoint | None = None
        self._to: QPoint | None = None

    # ---- what is being shown -------------------------------------------
    def show_frame(self, pixmap, frame_width: int, frame_height: int) -> None:
        """`pixmap` is the frame already scaled to fit this widget."""
        self._frame_size = (int(frame_width), int(frame_height))
        self.setPixmap(pixmap)

    def set_picking(self, on: bool) -> None:
        self._picking = bool(on)
        self._from = self._to = None
        self.setCursor(Qt.CursorShape.CrossCursor if on
                       else Qt.CursorShape.ArrowCursor)
        self.update()

    @property
    def picking(self) -> bool:
        return self._picking

    # ---- widget pixels <-> frame pixels ---------------------------------
    def _drawn_rect(self) -> QRect | None:
        """Where the frame actually sits inside this widget.

        Scaled to fit and centred, so both a margin and a ratio stand
        between a click and the pixel it is over.
        """
        pixmap = self.pixmap()
        if pixmap is None or pixmap.isNull():
            return None
        return QRect((self.width() - pixmap.width()) // 2,
                     (self.height() - pixmap.height()) // 2,
                     pixmap.width(), pixmap.height())

    def to_frame(self, point: QPoint) -> tuple[int, int] | None:
        drawn = self._drawn_rect()
        width, height = self._frame_size
        if drawn is None or not width or not height or not drawn.width():
            return None
        x = (point.x() - drawn.left()) * width / drawn.width()
        y = (point.y() - drawn.top()) * height / drawn.height()
        return (max(0, min(width - 1, int(round(x)))),
                max(0, min(height - 1, int(round(y)))))

    # ---- the drag -------------------------------------------------------
    def mousePressEvent(self, event) -> None:       # noqa: N802 - Qt naming
        if self._picking and event.button() == Qt.MouseButton.LeftButton:
            self._from = self._to = event.position().toPoint()
            self.update()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:        # noqa: N802
        if self._from is not None:
            self._to = event.position().toPoint()
            self.update()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:     # noqa: N802
        if self._from is None:
            return super().mouseReleaseEvent(event)
        start, end = self._from, event.position().toPoint()
        self._from = self._to = None
        self.update()
        first, second = self.to_frame(start), self.to_frame(end)
        if first is None or second is None:
            return
        x0, x1 = sorted((first[0], second[0]))
        y0, y1 = sorted((first[1], second[1]))
        # A click is not a box. Anything this small is a mis-hit, and
        # acting on it would move the boxes somewhere absurd.
        if x1 - x0 < 6 or y1 - y0 < 6:
            return
        self.boxed.emit(x0, y0, x1 - x0, y1 - y0)

    def paintEvent(self, event) -> None:            # noqa: N802
        super().paintEvent(event)
        if self._from is None or self._to is None:
            return
        painter = QPainter(self)
        painter.setPen(QPen(QColor(theme.ACCENT), 2, Qt.PenStyle.DashLine))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRect(QRect(self._from, self._to).normalized())
        painter.end()
