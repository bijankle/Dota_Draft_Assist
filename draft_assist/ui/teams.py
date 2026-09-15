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

from PyQt6.QtCore import (QMimeData, QPoint, QPointF, QRect, QSize, Qt,
                          pyqtSignal)
from PyQt6.QtGui import QColor, QDrag, QFont, QPainter, QPen
from PyQt6.QtWidgets import (QAbstractButton, QFrame, QHBoxLayout, QLabel,
                             QLayout, QSizePolicy, QVBoxLayout)

from . import theme, tilekit
from .portraits import scaled
from .textfit import fit, split_two  # noqa: F401  (re-exported)
# One look for every tile in the app: the name band, the number badge and
# the point sizes are shared with the item strip and the suggested picks,
# so the three strips cannot drift apart again.
from .tilekit import (BADGE_PAD_X, BADGE_PAD_Y, CHROME,  # noqa: F401
                      NAME_MAX_PT, NAME_MIN_PT, NUMBER_PX)

# "with" and "vs" are different questions and the eye should not have to
# read a legend to tell which it is looking at. Words rather than glyphs:
# a symbol that falls back to a box on the user's font would say nothing.
# Dragging a pick onto the other panel is how a wrong team split is fixed by
# hand. Our own mime type, so nothing else on the desktop can drop into it
# and the tiles ignore anything that is not one of their own.
SLOT_MIME = "application/x-dota-draft-slot"

# These bound how big the panel may make a tile; between them it takes
# whatever five-across leaves, so the row FILLS its card at any width.
# The ceiling used to be 132, which is a size an ordinary window reaches
# and passes — so past about 1500px the five picks stopped growing and sat
# small in the middle of their own card with a wide margin either side,
# which is what "they should be scaling to reach the end margins" was
# about. It is a sanity ceiling now, not a working size: it stops a
# full-screen window on a very wide monitor turning the draft into five
# posters, and the user's multiplier still moves it.
TILE_MAX = 256
# Below this there is no room for a portrait and the tile stops being a
# picture of a hero, which is the only reason it exists.
TILE_MIN = 64
# THE USER'S OWN MULTIPLIER (View ▸ Sizes ▸ Portraits). It moves the CAP,
# not the floor: a pick still shrinks with the window, and the window's
# own minimum width — which is derived from `TILE_MIN` — must not move
# when a display setting does, or turning the portraits up would leave a
# window that cannot be made narrow again.
SCALE = 1.0
# SYMMETRICAL AROUND 100%, at the user's request: "redefine what 100%
# is and rejig the min / max percentage to be relative to this and jsut
# make it 25% to 175%". It ran 50% to 200% with the default at 100, so
# the MIDDLE of the travel was 125 and dragging right reached twice as
# far as dragging left — the handle sat a third of the way along a
# slider whose centre was a size nobody had asked for. 100% is what the
# app has always drawn and still is; what moved is where it SITS.
SCALE_MIN, SCALE_MAX = 0.25, 1.75


def set_scale(factor: float) -> None:
    global SCALE
    SCALE = max(SCALE_MIN, min(SCALE_MAX, float(factor)))


# What the GRIDS can afford, or None before they have been measured. The
# draft panel has always decided one box for every portrait in the app —
# but it decided it from ITS OWN width, and the grids are the tighter
# constraint: counters fits its row header plus five columns where a panel
# fits five tiles, so the same hero came out visibly smaller in the grid
# than on the pick above it at every window size. One box means the
# SMALLEST of what the two can honestly draw, not the panel's alone.
_grid_cap: int | None = None


def set_grid_cap(px: int | None) -> None:
    """What the matrix cards can fit a portrait into. See `_grid_cap`."""
    global _grid_cap
    _grid_cap = None if px is None else max(TILE_MIN, int(px))


def grid_cap() -> int | None:
    return _grid_cap


def tile_cap() -> int:
    """The biggest a pick tile gets: the user's multiplier, and nothing
    else.

    It used to be held down by whatever the GRIDS could match as well
    (`set_grid_cap`), so that every portrait in the window was one size.
    The cost was paid at the top: counters is six sections across where
    the picks are five, so on a real 5v5 the ten picks came down to about
    five sixths of what their own card could hold and sat small in the
    middle of it with a wide margin either side. The picks are the subject
    of the screen and they fill their card; a grid takes this as its
    CEILING and goes smaller when its own sections will not fit
    (`MatrixTable._portrait_room`), which is counters and only counters.
    """
    return max(TILE_MIN, round(TILE_MAX * SCALE))


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
        self.setFixedSize(tile_cap(), round(tile_cap() * 9 / 16))
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
        edge = max(TILE_MIN, min(tile_cap(), int(edge)))
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
        self._delta = tilekit.delta_text(delta, kind)
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
        if self._focused and not self._drop_target:
            # The window's own frame, in the window's own gold. One ring,
            # drawn by `tilekit`, so a focused pick and a focused
            # suggestion cannot end up wearing two different boxes.
            # THE WIDGET'S OWN RECT, not the inset `box` the other pens
            # use. The ring places itself half a pen inside whatever it is
            # given, so handing it a rect already a pixel short would put
            # the gold a pixel off the tile edge on two sides and flush on
            # the other two — and a suggestion tile, which passes its full
            # rect, would wear a different ring from a pick.
            tilekit.paint_focus_ring(painter, self.rect())
            return
        if self._drop_target:
            pen = QPen(QColor(theme.WARN), 2)
        elif self.hasFocus() or self.underMouse():
            pen = QPen(QColor(theme.TEXT_DIM), 1)
        elif self.filled:
            pen = QPen(QColor(theme.BORDER), 1)
        else:
            pen = QPen(QColor(theme.BORDER), 1, Qt.PenStyle.DashLine)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRoundedRect(box, tilekit.PLATE_RADIUS,
                                tilekit.PLATE_RADIUS)

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


class HaloLabel(QLabel):
    """A label whose text carries the black halo every OTHER signed number
    in this app has.

    The side's total — the "+11.2" beside "Radiant" — was the last figure
    in the window drawn as plain text. Every other one is stroked: the
    badge on a pick, the number in a counters cell, the sigma on an axis
    portrait. The halo is not decoration there, it is what separates a
    figure from whatever is behind it and what makes two numbers read as
    the same kind of object rather than as two conventions — so the one
    that skipped it read as a different kind of thing from the five tiles
    it is the sum of.

    Painted rather than styled because a stylesheet cannot put a stroke
    round a glyph: same reason the tick box, the window buttons and the
    count box's arrows are all painted. The colour comes in through
    `set_value` rather than off the palette, since it means something —
    green good for you, red not.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self._colour = theme.TEXT

    @property
    def colour(self) -> str:
        """What the text is painted in. A stylesheet cannot reach text a
        widget paints itself, so this is where the answer lives now —
        and it means something, so it is worth being able to read."""
        return self._colour

    def set_value(self, text: str, colour: str) -> None:
        self._colour = colour
        self.setText(text)
        self.updateGeometry()
        self.update()

    def _stroke(self) -> float:
        """The halo's thickness at THIS label's size. A stylesheet sets
        the heading's point size, so the figure has to be read off the
        font rather than taken from the tiles' own constant."""
        size = self.font().pixelSize()
        if size <= 0:
            size = max(1, self.fontMetrics().height())
        return tilekit.stroke_width(size)

    def sizeHint(self):                     # noqa: N802 - Qt naming
        hint = super().sizeHint()
        # Room for the stroke, which sits OUTSIDE the letterforms.
        hint.setWidth(hint.width() + 2 * round(self._stroke()))
        return hint

    def paintEvent(self, event) -> None:    # noqa: N802 - Qt naming
        text = self.text()
        if not text:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        metrics = self.fontMetrics()
        baseline = (self.height() + metrics.ascent() - metrics.descent()) / 2
        tilekit.stroked(painter, QPointF(self._stroke(), baseline),
                        text, self._colour, self.font())
        painter.end()


class TeamPanel(QFrame):
    """Five tiles under one heading — one half of the draft.

    **ITS LAYOUT DOES NOT DICTATE ITS MINIMUM**, and that one line is
    what lets the ten portraits shrink with the window.
    `HeroTile.set_edge` calls `setFixedSize` — which is right, and is
    what stops Qt handing each tile the leftover width and stretching the
    art — but a layout full of fixed-size children reports a minimum of
    five of whatever they happen to be RIGHT NOW, and Qt hands that
    straight to the widget. That is a RATCHET: widen the window, the
    tiles grow, the panel's floor grows with them, and the width can
    never be given back. Two panels at 925 put the Draft page's floor at
    1884 against a window floor of 940, so inside the tab's scroll area
    the page stopped shrinking and a horizontal scrollbar appeared —
    "i also feel like portraits are nto scaling down as i make the
    windows smaller". Before the scroll area the same ratchet showed up
    as a window that would not narrow.

    `SetNoConstraint` is the documented way to say the layout's minimum
    is not the widget's, and the real floor is then stated once, as
    `minimum_panel_width()` — the number the window's own minimum width
    has always been derived from.

    **TWO OTHER FIXES FOR THIS WERE TRIED AND BOTH SEGFAULT**, which is
    worth recording because neither looks dangerous:
    overriding `minimumSizeHint` to report the floor leaves Qt's layout
    engine with constraints it cannot satisfy, and giving the tiles a
    minimum-and-maximum instead of a fixed size makes the tile's hint
    feed the panel's hint, which feeds the width that chose it. Both end
    in the same place — the ten tiles flipping 80, 78, 80, 78 through
    Qt's C++ layout until the stack goes, with no exception and a Python
    traceback naming whichever `show()` was on top. `_match_grid_
    portraits` carries the same warning: Qt ABORTS rather than raising,
    so this class of bug has no traceback to find it by.
    """

    tile_resized = pyqtSignal(int, int)

    def __init__(self, side: str, caption: str, parent=None):
        super().__init__(parent)
        self.side = side
        # BARE, NOT A CARD, and the card is now one level up. The five
        # picks and that side's role pills are ONE section — "i dont like
        # that the padding is not joined between the pills and the 5 / 5
        # portaits sectrions... they belong in the same section" — so the
        # surface and its padding belong to the thing holding both, and a
        # card inside a card would draw the lighter rectangle this rule
        # exists to prevent. Radiant and Dire stay two separate cards,
        # which is what says which five are whose.
        self.setProperty("bare", True)
        self.setMinimumWidth(minimum_panel_width())
        self._told: tuple[int, int] | None = None
        # Activating a layout can deliver a resize, which lands back here.
        self._flooring = False

        lay = QVBoxLayout(self)
        # SEE THE CLASS NOTE. Without this the layout hands the widget a
        # minimum of five tiles at their CURRENT size, which only ever
        # goes up.
        lay.setSizeConstraint(QLayout.SizeConstraint.SetNoConstraint)
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
        self.total = HaloLabel()
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
    def rescale(self) -> None:
        """Re-size the tiles after the user changed the size setting.

        The panel is the one place that decides how big a tile is, so it
        is also the one place that has to be told the rule changed — the
        strips and the grids are told by the signal this raises, the same
        way they are when the window is dragged.
        """
        self._told = None       # the size may be the same NUMBER as before
        self._resize_tiles(self.width())

    def resizeEvent(self, event) -> None:   # noqa: N802 - Qt naming
        super().resizeEvent(event)
        self._resize_tiles(event.size().width())

    # HOW MUCH THE WIDTH MUST MOVE BEFORE THE TILES FOLLOW IT.
    #
    # **THIS IS A DAMPER ON A SCROLLBAR LOOP, not a tidiness setting.**
    # The Draft tab is in a scroll area, and its page is as tall as it is
    # WIDE — the tiles are 16:9 and the Roles card reflows — so: the page
    # is a few pixels too tall, the vertical scrollbar appears, that takes
    # ~10px of width, the tiles shrink to suit, the page gets shorter, the
    # scrollbar is no longer needed, it goes, the width comes back. The
    # measured result is the ten tiles flipping 80, 78, 80, 78 for ever
    # inside Qt's C++ layout until the stack goes — and Qt does not raise
    # for that, it SEGFAULTS, with a Python traceback naming whichever
    # `show()` happened to be on top. `_match_grid_portraits` carries the
    # same warning one card down.
    # Two pixels on a portrait is invisible; an app that will not open is
    # not. A real drag moves the width by far more than this, so the tiles
    # still follow the window.
    #
    # **IT ONLY DAMPS GROWTH**, which is what makes it safe. Refusing to
    # SHRINK would let the tiles overrun the card they are in the moment
    # the scrollbar took its width — five tiles two pixels too wide is ten
    # pixels of portrait outside the panel. So a smaller size is always
    # taken at once and a bigger one has to be worth having, which settles
    # the flutter at the smaller of the two and can never overflow.
    STEADY = 3

    def _resize_tiles(self, width: int) -> None:
        margins = self.layout().contentsMargins()
        inner = width - margins.left() - margins.right() - 4 * self.spacing
        edge = inner // 5
        now = self.slots[0].width() if self.slots else 0
        if now and 0 < edge - now < self.STEADY:
            edge = now
        for tile in self.slots:
            tile.set_edge(edge)
        # **THE HEIGHT FLOOR HAS TO BE PUT BACK BY HAND.**
        # `SetNoConstraint` frees the widget from its layout's minimum in
        # BOTH axes, and only the WIDTH was ever the problem. Left free
        # vertically the panel was squeezed to 74px against a layout that
        # needed 102 — hero names sheared in half, which is the exact
        # symptom `test_draft_card_never_clips_the_hero_names` exists for.
        # So the width is stated once in `__init__` and the height is
        # restated here, where the tile size that decides it has just been
        # worked out.
        # **AND THE LAYOUT HAS TO BE MADE TO RUN BEFORE IT IS ASKED.** Qt
        # defers layout, so reading `minimumSize()` from inside a resize
        # reads the answer for the PREVIOUS tile size — it returned 74,
        # which was then stamped on as the floor and became the squeeze it
        # was meant to prevent. Same trap as `_hold_still` in the History
        # tab, where measuring before forcing the layout moved the control
        # out from under the cursor.
        if not self._flooring:
            self._flooring = True
            try:
                self.layout().activate()
                wanted = self.layout().minimumSize().height()
                if wanted and wanted != self.minimumHeight():
                    self.setMinimumHeight(wanted)
            finally:
                self._flooring = False
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
        self.total.set_value(f"{value * 100:+.1f}",
                             theme.GOOD if value >= 0 else theme.BAD)
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
