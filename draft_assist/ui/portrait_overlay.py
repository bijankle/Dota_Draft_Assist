"""Numbers under the ten portraits, drawn over the Dota window.

This is the click view from the Draft tab, put where the eye already is:
mid-draft nobody looks away to a second monitor, so the synergy and matchup
figures are painted directly beneath the pick bar. Green favours you, red
does not, and the sign convention is the one `scoring.relations_to` uses —
positive is good for YOUR team whichever portrait it sits under.

No panel, no background, no chrome: a halo (a dark stroke around the glyphs)
is what makes text legible over an arbitrary screen, and a filled box over
the pick bar would hide the thing it annotates.

Like `ui/overlay.py` this sits OVER Dota and never inside it — an ordinary
frameless top-level window. Nothing is injected, the present chain is
untouched, no input is sent to the game (see CLAUDE.md). Locked, it is
click-through, so it cannot even take a click meant for Dota.

The anchors are the vision layout's crop boxes, which is the only geometry
in the app that is known to line up with the portraits. They can still be
out — the boxes are calibrated per user — so the overlay unlocks for
dragging and remembers a fractional nudge, in the same units as everything
else here (fractions of Dota's 16:9 HUD box, never pixels).
"""

from PyQt6.QtCore import QPointF, QRectF, Qt, pyqtSignal
from PyQt6.QtGui import (QColor, QFont, QFontMetricsF, QPainter, QPainterPath,
                         QPen)
from PyQt6.QtWidgets import QWidget

from . import theme
from ..vision import layout as layout_mod

# Where the number sits relative to its portrait, before the user's nudge:
# a hair below the box, centred on it.
GAP = 4.0
HALO = QColor(0, 0, 0, 235)
UNLOCK_TINT = QColor(88, 101, 242, 40)      # blurple, barely there
UNLOCK_BOX = QColor(88, 101, 242, 190)


class PortraitOverlay(QWidget):
    """Signed deltas under each pick, anchored to the crop boxes."""

    anchors_moved = pyqtSignal(float, float)   # fractional dx, dy

    def __init__(self, layout_spec=None, offset=(0.0, 0.0), parent=None):
        super().__init__(parent)
        self.layout_spec = layout_spec or layout_mod.DraftLayout()
        self.offset_x, self.offset_y = offset
        self.left: list[float | None] = [None] * 5
        self.right: list[float | None] = [None] * 5
        self._unlocked = False
        self._drag_from: QPointF | None = None
        self._drag_origin = (0.0, 0.0)

        self.setWindowFlags(Qt.WindowType.FramelessWindowHint
                            | Qt.WindowType.WindowStaysOnTopHint
                            | Qt.WindowType.Tool
                            | Qt.WindowType.WindowTransparentForInput)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        # Appearing mid-draft must never pull keyboard focus out of the game.
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)

    # ---- what to draw ---------------------------------------------------
    def set_layout(self, layout_spec) -> None:
        self.layout_spec = layout_spec
        self.update()

    def set_offset(self, dx: float, dy: float) -> None:
        self.offset_x, self.offset_y = float(dx), float(dy)
        self.update()

    def set_values(self, left, right) -> None:
        """Two banks of five, screen order, None where there is no number."""
        self.left = list(left)[:5] + [None] * max(0, 5 - len(left))
        self.right = list(right)[:5] + [None] * max(0, 5 - len(right))
        self.update()

    def clear_values(self) -> None:
        self.set_values([None] * 5, [None] * 5)

    def set_window_rect(self, rect) -> None:
        """Cover the Dota client area, in logical pixels.

        `capture.window.window_rect` returns physical pixels; a scaled
        display needs them divided by the device pixel ratio before Qt sees
        them, or the overlay lands a quarter of the screen off.
        """
        if not rect:
            return
        x, y, w, h = rect
        ratio = self.devicePixelRatioF() or 1.0
        self.setGeometry(round(x / ratio), round(y / ratio),
                         round(w / ratio), round(h / ratio))

    # ---- unlocked for dragging -----------------------------------------
    def set_unlocked(self, unlocked: bool) -> None:
        """Unlocked, the overlay takes the mouse so the numbers can be
        dragged into place; locked, it is click-through and Dota never
        knows it is there."""
        self._unlocked = bool(unlocked)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents,
                          not self._unlocked)
        flags = self.windowFlags()
        if self._unlocked:
            flags &= ~Qt.WindowType.WindowTransparentForInput
        else:
            flags |= Qt.WindowType.WindowTransparentForInput
        was_visible = self.isVisible()
        self.setWindowFlags(flags)
        if was_visible:
            self.show()
        self.update()

    @property
    def unlocked(self) -> bool:
        return self._unlocked

    def attribute_transparent(self) -> bool:
        """True when clicks fall straight through to Dota."""
        return self.testAttribute(
            Qt.WidgetAttribute.WA_TransparentForMouseEvents)

    def mousePressEvent(self, event) -> None:   # noqa: N802 - Qt naming
        if self._unlocked and event.button() == Qt.MouseButton.LeftButton:
            self._drag_from = event.position()
            self._drag_origin = (self.offset_x, self.offset_y)
            event.accept()

    def mouseMoveEvent(self, event) -> None:    # noqa: N802
        if self._drag_from is None:
            return
        span = self._span()
        moved = event.position() - self._drag_from
        self.offset_x = self._drag_origin[0] + moved.x() / max(span, 1.0)
        self.offset_y = (self._drag_origin[1]
                         + moved.y() / max(self.height(), 1))
        self.update()
        event.accept()

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802
        if self._drag_from is not None:
            self._drag_from = None
            self.anchors_moved.emit(self.offset_x, self.offset_y)
            event.accept()

    # ---- painting -------------------------------------------------------
    def _span(self) -> float:
        return layout_mod.hud_box(self.width(), self.height())[1]

    def _anchors(self) -> list[tuple[str, int, QRectF]]:
        """Each slot's crop box in this window's coordinates, nudge applied."""
        out = []
        dx = self.offset_x * self._span()
        dy = self.offset_y * self.height()
        for rect in self.layout_spec.slots():
            x, y, w, h = rect.to_pixels(self.width(), self.height())
            out.append((rect.team, rect.slot,
                        QRectF(x + dx, y + dy, w, h)))
        return out

    def paintEvent(self, event) -> None:        # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        if self._unlocked:
            painter.fillRect(self.rect(), UNLOCK_TINT)

        font = QFont(self.font())
        # Scale with the window: the same overlay serves 1080p and 1440p.
        font.setPointSizeF(max(9.0, self.height() * 0.0155))
        font.setBold(True)
        painter.setFont(font)
        metrics = QFontMetricsF(font)

        banks = {"radiant": self.left, "dire": self.right}
        for team, index, box in self._anchors():
            if self._unlocked:
                painter.setPen(QPen(UNLOCK_BOX, 1.5, Qt.PenStyle.DashLine))
                painter.setBrush(Qt.BrushStyle.NoBrush)
                painter.drawRect(box)
            value = banks[team][index]
            if value is None:
                continue
            text = f"{value * 100:+.1f}"
            centre = QPointF(
                box.center().x() - metrics.horizontalAdvance(text) / 2.0,
                box.bottom() + GAP + metrics.ascent())
            self._halo_text(painter, centre, text,
                            QColor(theme.GOOD if value >= 0 else theme.BAD))
        painter.end()

    @staticmethod
    def _halo_text(painter: QPainter, at: QPointF, text: str,
                   colour: QColor) -> None:
        """Stroke the glyph outline in near-black, then fill it.

        A drop shadow only works against a lighter background and the pick
        bar is neither reliably light nor dark; an outline is legible over
        both, which is why it is the halo rather than a panel behind.
        """
        path = QPainterPath()
        path.addText(at, painter.font(), text)
        painter.setPen(QPen(HALO, 3.0, Qt.PenStyle.SolidLine,
                            Qt.PenCapStyle.RoundCap,
                            Qt.PenJoinStyle.RoundJoin))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawPath(path)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(colour)
        painter.drawPath(path)
