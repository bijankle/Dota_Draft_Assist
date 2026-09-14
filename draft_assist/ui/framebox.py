"""The debug picture: the captured frame, scaled to fit and centred.

IT USED TO BE DRAGGABLE, and that is gone with the rest of the hand
calibration — "my plan now is to have the automatic detection work so the
user never needs to draw out these vision boxes". The rubber band, the
widget-pixels-to-frame-pixels mapping and the `boxed` signal all existed
to turn a drawn rectangle into six fractions of Dota's HUD box, which
`autocal` now measures off a frame the game has named the heroes in.

What is left is a QLabel that shows a picture and refuses to let the
picture decide how big it is, which is the one piece of subtlety here —
see `minimumSizeHint`.
"""

from PyQt6.QtCore import QSize, Qt
from PyQt6.QtWidgets import QLabel


class FrameView(QLabel):
    """The captured frame, drawn at whatever size it is given."""

    def __init__(self, text: str = "", parent=None):
        super().__init__(text, parent)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._frame_size: tuple[int, int] = (0, 0)

    # ---- what is being shown -------------------------------------------
    def show_frame(self, pixmap, frame_width: int, frame_height: int) -> None:
        """`pixmap` is the frame already scaled to fit this widget."""
        self._frame_size = (int(frame_width), int(frame_height))
        self.setPixmap(pixmap)

    # THE PICTURE MUST NOT SET THIS WIDGET'S FLOOR, or the view grows
    # without end. QLabel answers `minimumSizeHint` with its pixmap's
    # size PLUS its own margins and frame — and this one is a card, so
    # the stylesheet gives it a 1px border, two pixels in each axis.
    # The caller fits the frame into the size this widget currently has,
    # so the floor then lands two pixels ABOVE the space the picture was
    # fitted into; the layout grants it, the next frame is fitted two
    # pixels taller, and round it goes. Measured at about a pixel a tick,
    # three a second, settling only when the picture becomes limited by
    # the width instead — which is the "Debug > Live keeps expanding, and
    # after about twenty seconds it stops" this fixes.
    #
    # A view of something else's size has no business having a size of
    # its own: it shows whatever it is given at whatever size it is
    # given, so both hints are answered without asking the pixmap.
    # `setMinimumHeight` still floors it, and now it can shrink back to
    # that floor when the window does, which following the pixmap never
    # allowed either.
    def minimumSizeHint(self) -> QSize:             # noqa: N802 - Qt naming
        return QSize(0, 0)

    def sizeHint(self) -> QSize:                    # noqa: N802 - Qt naming
        return QSize(0, self.minimumHeight())
