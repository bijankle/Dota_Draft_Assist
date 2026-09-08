"""The two team panels on the Draft tab.

Five heroes across, as tiles, because that is the shape the same ten picks
have on Dota's own pick bar — the eye arrives already knowing the layout,
and a row of full-width name buttons cost five times the vertical space to
say less.

**Tiles are square and capped, never stretched.** They used to take whatever
width the layout gave them at a fixed height, so full-screening the window
turned every portrait into a wide letterbox slice with the hero's head cropped
off. The panel now sizes its own tiles: one square edge, computed from the
width available, clamped, and the leftover space goes to the margins. The art
is then scaled to FIT that square rather than to fill it, so the whole
portrait is visible and nothing is ever distorted by the window's aspect.

The name gets its OWN strip above the art rather than sitting on top of it:
a label over a portrait hides the half of the portrait you recognise the
hero by, and the point of drawing the art at all is that it is quicker to
read than the name. The signed number sits in a small tinted badge in the
bottom-right corner — the same treatment as the name strip, cut to the size
of the number, so it reads over whatever is behind it without covering more
than it needs.
"""

from PyQt6.QtCore import QMimeData, QPoint, QRect, QSize, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QDrag, QFont, QPainter, QPen
from PyQt6.QtWidgets import (QAbstractButton, QFrame, QHBoxLayout, QLabel,
                             QSizePolicy, QVBoxLayout)

from . import theme, tilekit
from .portraits import scaled
from .textfit import fit, split_two  # noqa: F401  (re-exported)
# One look for every tile in the app: the name band, the number badge and
# the point sizes are shared with the item strip and the suggested picks,
# so the three strips cannot drift apart again.
from .tilekit import (BADGE_PAD_X, BADGE_PAD_Y, CHROME,  # noqa: F401
                      NAME_MAX_PT, NAME_MIN_PT, NUMBER_PT)

# "with" and "vs" are different questions and the eye should not have to
# read a legend to tell which it is looking at. Words rather than glyphs:
# a symbol that falls back to a box on the user's font would say nothing.
KIND_MARK = {"with": "with", "vs": "vs"}

# Dragging a pick onto the other panel is how a wrong team split is fixed by
# hand. Our own mime type, so nothing else on the desktop can drop into it
# and the tiles ignore anything that is not one of their own.
SLOT_MIME = "application/x-dota-draft-slot"

# A tile is square. These bound how big the panel may make one; between them
# it takes whatever five-across leaves, so the row breathes on a wide window
# without any tile turning into a letterbox.
# A tile is capped so a wide window does not turn the draft into five
# posters, and floored at the matrix's own column width so that when the
# window is at its narrowest the tiles still line up with the grid below.
TILE_MAX = 132
# Below this there is no room for a portrait and the tile stops being a
# picture of a hero, which is the only reason it exists.
TILE_MIN = 64
# The two sizes this file draws itself, up with the rest of the app and
# bold like everything else: the slot's role in its corner, and the "+" on
# an empty one. Everything else on a tile comes from `tilekit`.
ROLE_PT = 12
PLUS_PT = 22
PANEL_MARGIN = 12
TILE_GAP = 6


def minimum_panel_width() -> int:
    """Five tiles at their floor, plus the panel's own margins."""
    return 2 * PANEL_MARGIN + 5 * TILE_MIN + 4 * TILE_GAP
EMPTY_TEXT = "+"


class HeroTile(QAbstractButton):
    """One pick: portrait behind, name across the top, number bottom-right.

    A button rather than a composed widget because it is one click target;
    `text()` keeps the same "Pos 3 · Necrophos" form the rest of the app
    reads, so the tile is a drop-in for the row button it replaces.
    """

    dropped_on = pyqtSignal(str, int, str, int)   # from side/i, to side/i

    def __init__(self, side: str, index: int, parent=None):
        super().__init__(parent)
        self.side = side
        self.index = index
        # Also dynamic properties: the window reads a clicked tile's side
        # and index straight off the sender, the way it did the buttons
        # these replaced.
        self.setProperty("side", side)
        self.setProperty("slot_index", index)
        self.setProperty("hero_id", None)
        self.hero_name: str | None = None
        self.role: str | None = None
        self._delta = ""
        self._delta_colour = theme.TEXT_DIM
        self._focused = False
        self._drop_target = False
        self.setFixedSize(TILE_MAX, round(TILE_MAX * 9 / 16))
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        # Focusable so Tab walks the ten slots in order.
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setAcceptDrops(True)
        self._press: QPoint | None = None

    def sizeHint(self) -> QSize:            # noqa: N802 - Qt naming
        return self.size()

    # ---- dragging a pick to the other team ------------------------------
    def mousePressEvent(self, event) -> None:       # noqa: N802 - Qt naming
        self._press = event.position().toPoint()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:        # noqa: N802
        """Past the drag distance, the press becomes a drag rather than a
        click — the same rule the overlay badge uses, so a pick is never
        picked up by accident and a click is never lost to a shaky hand."""
        if (self._press is None or not self.filled
                or not (event.buttons() & Qt.MouseButton.LeftButton)):
            return super().mouseMoveEvent(event)
        moved = (event.position().toPoint() - self._press).manhattanLength()
        if moved < self.startDragDistance():
            return super().mouseMoveEvent(event)

        data = QMimeData()
        data.setData(SLOT_MIME,
                     f"{self.side}:{self.index}".encode("ascii"))
        drag = QDrag(self)
        drag.setMimeData(data)
        drag.setPixmap(self.grab())
        drag.setHotSpot(self._press)
        self._press = None
        drag.exec(Qt.DropAction.MoveAction)
        # The button is still "down" when the drag ends; leaving it so would
        # fire a click on release and open the picker on top of the move.
        self.setDown(False)

    def startDragDistance(self) -> int:             # noqa: N802
        from PyQt6.QtWidgets import QApplication
        return QApplication.startDragDistance()

    def dragEnterEvent(self, event) -> None:        # noqa: N802
        source = self._source_of(event)
        if source is None or source == (self.side, self.index):
            return event.ignore()
        self.set_drop_target(True)
        event.acceptProposedAction()

    def dragLeaveEvent(self, event) -> None:        # noqa: N802
        self.set_drop_target(False)
        event.accept()

    def dropEvent(self, event) -> None:             # noqa: N802
        self.set_drop_target(False)
        source = self._source_of(event)
        if source is None or source == (self.side, self.index):
            return event.ignore()
        event.acceptProposedAction()
        self.dropped_on.emit(source[0], source[1], self.side, self.index)

    @staticmethod
    def _source_of(event) -> tuple[str, int] | None:
        data = event.mimeData()
        if not data.hasFormat(SLOT_MIME):
            return None
        try:
            side, index = bytes(data.data(SLOT_MIME)).decode("ascii").split(":")
            return side, int(index)
        except (UnicodeDecodeError, ValueError):
            return None

    def set_edge(self, edge: int) -> None:
        """The PORTRAIT'S shape, 16:9 — the panel decides how big.

        It used to be square, because the name band across the top took
        the difference. With the name gone a square tile is a 16:9 picture
        with a dead strip above and below it, on all ten picks; matching
        the art's own aspect gives that height back to the window.
        """
        edge = max(TILE_MIN, min(TILE_MAX, int(edge)))
        height = max(TILE_MIN * 9 // 16, round(edge * 9 / 16))
        if (edge, height) != (self.width(), self.height()):
            self.setFixedSize(edge, height)

    # ---- what the tile holds -------------------------------------------
    def set_pick(self, name: str | None, role: str | None,
                 hero_id: int | None) -> None:
        self.hero_name = name
        self.role = role
        self.setProperty("hero_id", hero_id)
        prefix = f"{role} · " if role else ""
        self.setText(prefix + (name or EMPTY_TEXT))
        self.update()

    @property
    def filled(self) -> bool:
        return self.hero_name is not None

    # ---- the relation line ---------------------------------------------
    def show_delta(self, delta: float, kind: str | None = None) -> None:
        mark = KIND_MARK.get(kind or "", "")
        self._delta = f"{mark} {delta * 100:+.1f}".strip()
        self._delta_colour = theme.GOOD if delta >= 0 else theme.BAD
        self.update()

    def clear_delta(self) -> None:
        self._delta = ""
        self.update()

    def delta_text(self) -> str:
        return self._delta

    # ---- the focused pick ----------------------------------------------
    def set_focused(self, on: bool) -> None:
        self._focused = bool(on)
        self.update()

    @property
    def focused(self) -> bool:
        return self._focused

    def set_drop_target(self, on: bool) -> None:
        self._drop_target = bool(on)
        self.update()

    # ---- painting -------------------------------------------------------
    def paintEvent(self, event) -> None:    # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
        box = self.rect().adjusted(0, 0, -1, -1)
        painter.fillRect(box, QColor(theme.BG_DEEP))

        if not self.filled:
            self._paint_empty(painter, box)
            self._paint_border(painter, box)
            painter.end()
            return

        # THE PICTURE IS THE TILE. The name was a strip across the top of
        # every pick, and a player who knows the game reads the face faster
        # than the four letters — a board of ten portraits reads at a
        # glance where ten labelled portraits read as a list. The name is
        # still the tooltip, and it comes BACK below when there is no art,
        # because a blank plate names nothing.
        art = scaled(self.property("hero_id"), box.width(), box.height())
        if art is not None:
            painter.drawPixmap(
                box.left() + (box.width() - art.width()) // 2,
                box.top() + (box.height() - art.height()) // 2, art)
        else:
            self._paint_name(painter, QRect(box.left(), box.top(),
                                            box.width(),
                                            self._band_height(box)))
        self._paint_number(painter, box)
        if self.role:
            painter.setFont(self._font(ROLE_PT, bold=True))
            painter.setPen(QColor(theme.TEXT_DIM))
            painter.drawText(box.adjusted(5, 0, 0, -4),
                             Qt.AlignmentFlag.AlignLeft
                             | Qt.AlignmentFlag.AlignBottom, self.role)
        self._paint_border(painter, box)
        painter.end()

    def _band_height(self, box: QRect) -> int:
        return tilekit.band_height(box.height())

    def _paint_name(self, painter: QPainter, band: QRect) -> None:
        """Shrink to fit, then wrap to two lines, then elide.

        A hero name sheared in half or spilling past its tile is the one
        thing the panel exists to show, so the font gives way before the
        text does — but the strip's height is fixed, so two lines only
        happen at a size where two lines still fit.
        """
        tilekit.paint_band(painter, band, self.hero_name or "", self.font())

    def _fit_name(self, name: str, avail: int,
                  band_h: int) -> tuple[int, list[str]]:
        return fit(name, avail, band_h, self.font(),
                   NAME_MAX_PT, NAME_MIN_PT, bold=True)

    def _paint_number(self, painter: QPainter, box: QRect) -> None:
        """A badge in the bottom-right, cut to the size of the number.

        Same tint as the name strip so the two read as one layer over the
        art, and no bigger than the digits need — a full-width bar there
        would hide as much of the portrait as the name used to.
        """
        tilekit.paint_badge(painter, box, self._delta, self._delta_colour,
                            self.font())

    def _paint_border(self, painter: QPainter, box: QRect) -> None:
        if self._drop_target:
            pen = QPen(QColor(theme.WARN), 2)
        elif self._focused:
            pen = QPen(QColor(theme.ACCENT), 2)
        elif self.hasFocus() or self.underMouse():
            pen = QPen(QColor(theme.TEXT_DIM), 1)
        elif self.filled:
            pen = QPen(QColor(theme.BORDER), 1)
        else:
            pen = QPen(QColor(theme.BORDER), 1, Qt.PenStyle.DashLine)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRoundedRect(box, 6, 6)

    def _paint_empty(self, painter: QPainter, box: QRect) -> None:
        """An empty slot is an invitation, not a pick."""
        painter.setFont(self._font(PLUS_PT, bold=True))
        painter.setPen(QColor(theme.TEXT_DIM))
        painter.drawText(box, Qt.AlignmentFlag.AlignCenter, EMPTY_TEXT)
        if self.role:
            painter.setFont(self._font(ROLE_PT, bold=True))
            painter.drawText(box.adjusted(5, 0, 0, -4),
                             Qt.AlignmentFlag.AlignLeft
                             | Qt.AlignmentFlag.AlignBottom, self.role)

    def _font(self, size: int, bold: bool = False) -> QFont:
        font = QFont(self.font())
        font.setPointSize(size)
        font.setBold(bold)
        return font


class TeamPanel(QFrame):
    """Five tiles under one heading — one half of the draft."""

    tile_resized = pyqtSignal(int, int)

    def __init__(self, side: str, caption: str, parent=None):
        super().__init__(parent)
        self.side = side
        self.setProperty("card", True)
        self._told: tuple[int, int] | None = None

        lay = QVBoxLayout(self)
        lay.setContentsMargins(PANEL_MARGIN, 8, PANEL_MARGIN, 10)
        lay.setSpacing(6)

        head = QHBoxLayout()
        self.caption = QLabel(caption)
        self.caption.setProperty("heading", True)
        head.addWidget(self.caption)
        # The side's own total, beside its name: "Radiant | +11.2". It is
        # the sum of the five numbers `net_contributions` gives that side,
        # so it answers the question the five tiles answer one at a time —
        # and it is ALWAYS that sum, even while a hero is clicked and the
        # tiles are showing that hero's relations instead, because a
        # heading that moved every time you clicked a portrait would be
        # something you had to stop and re-read.
        self.rule = QLabel("|")
        self.rule.setProperty("dim", True)
        self.rule.setContentsMargins(8, 0, 8, 0)
        self.rule.setVisible(False)
        head.addWidget(self.rule)
        self.total = QLabel("")
        self.total.setProperty("heading", True)
        self.total.setVisible(False)
        head.addWidget(self.total)
        head.addStretch(1)
        self.note = QLabel("")
        self.note.setProperty("dim", True)
        # Hidden while it says nothing. It used to stay in the layout with
        # an empty string, and a QLabel took its background from the base
        # QWidget rule — so an empty note was a 3mm block of content colour
        # sitting on the darker card at the end of every team's heading.
        self.note.setVisible(False)
        head.addWidget(self.note)
        lay.addLayout(head)

        self.spacing = TILE_GAP
        row = QHBoxLayout()
        row.setSpacing(self.spacing)
        row.addStretch(1)
        self.slots = [HeroTile(side, i, self) for i in range(5)]
        for tile in self.slots:
            row.addWidget(tile)
        row.addStretch(1)
        lay.addLayout(row)
        self._resize_tiles(self.width())

    # The panel owns the tile size: a square edge from the width available,
    # clamped, with the remainder going to the stretches either side. Qt
    # would otherwise hand each tile the leftover width and stretch the art.
    def resizeEvent(self, event) -> None:   # noqa: N802 - Qt naming
        super().resizeEvent(event)
        self._resize_tiles(event.size().width())

    def _resize_tiles(self, width: int) -> None:
        margins = self.layout().contentsMargins()
        inner = width - margins.left() - margins.right() - 4 * self.spacing
        for tile in self.slots:
            tile.set_edge(inner // 5)
        # EVERY tile in the app is this tile. The two strips below have no
        # width of their own to reason from — theirs was fixed at 78x44
        # while these grew with the window, so a suggestion was a different
        # size from a pick and, worse, from itself before and after the
        # game. The panel is the one place that decides, and it says so.
        size = self.slots[0].size() if self.slots else None
        if size is not None and (size.width(), size.height()) != self._told:
            self._told = (size.width(), size.height())
            self.tile_resized.emit(size.width(), size.height())

    def set_total(self, value: float | None) -> None:
        """The signed figure beside the side's name, or nothing at all.

        Nothing when no hero on this side has resolved: a heading reading
        "Radiant | +0.0" over five empty slots claims a measurement that
        was never made.
        """
        if value is None:
            self.rule.setVisible(False)
            self.total.setVisible(False)
            self.total.setText("")
            return
        self.total.setText(f"{value * 100:+.1f}")
        colour = theme.GOOD if value >= 0 else theme.BAD
        self.total.setStyleSheet(f"color: {colour};")
        self.rule.setVisible(True)
        self.total.setVisible(True)

    def set_note(self, text: str) -> None:
        self.note.setText(text)
        self.note.setVisible(bool(text))

    @property
    def buttons(self) -> list[HeroTile]:
        return list(self.slots)

    def clear_deltas(self) -> None:
        for tile in self.slots:
            tile.clear_delta()
            tile.set_focused(False)
