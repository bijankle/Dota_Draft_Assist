"""The advertising banner above the draft.

A placeholder, deliberately: there is no ad network wired in and no
network call is made. What is here is the SLOT — the space an ad takes,
and a creative of the right size in it — so the layout question ("what
does the window look like with this in it") can be answered now, and so
turning it on and living with it for an evening is a thing the owner can
actually try before committing to it.

**It is off by default and it is a setting** (`ui_settings.ads_enabled`).
This is the user's own app on their own machine; something that sits over
the board has to be asked for.

**ON MEANS ON: the banner shows the whole time**, at the user's request.
It began as five seconds in every fifteen, which was worse in both
directions — an ad that appears out of nothing mid-draft pulls the eye at
exactly the wrong moment, and one that is always there is furniture after
ten minutes. Off is off and takes no window at all; on is a strip that
never moves.

**It reserves its height while ads are ON, and NONE while they are off.**
A banner that came and went while pushing the ten picks up and down the
window would be a board that moves under the cursor mid-draft, which is
how a pick gets misclicked. With the feature switched off there is
nothing to hold still for, and reserving the space anyway is a strip of
dead window above the draft that nobody asked for; the slot collapses to
nothing instead.

**THE CREATIVE IS PAINTED HERE, and it is nobody's real advertisement.**
A genuine banner off the web is somebody's copyrighted artwork, and this
repository does not carry other people's artwork — the same rule that
keeps Valve's portraits out of it. So what fills the slot is a house
creative drawn in code for a product that does not exist: the right size,
the right shape, the right amount of noise beside a draft, and no file to
commit. When a real network is wired in, this is what its creative
replaces.

**The size is a real ad unit**, not a number I liked the look of: 728x90,
the IAB leaderboard, which is what a banner slot is actually sold as. It
is worth knowing what the window looks like with the real thing in it
rather than with a placeholder that turns out to be the wrong shape. It
fits at the window's minimum width (~1464px) with room to spare, and it is
CENTRED in a full-width slot rather than stretched, because a leaderboard
is a fixed-size creative.

The live scoring loop never makes network calls (see CLAUDE.md), and that
still holds: whatever eventually fills this must fetch on its own timer,
off the draft path, or it will cost a draft the first time a network
hiccups.
"""

from PyQt6.QtCore import QPointF, QRectF, Qt
from PyQt6.QtGui import (QColor, QFont, QFontMetricsF, QLinearGradient,
                         QPainter, QPainterPath, QPixmap)
from PyQt6.QtWidgets import QLabel, QVBoxLayout, QWidget

from . import theme
# The IAB leaderboard — the size a banner slot is actually sold as, so the
# layout is tested against the real thing rather than against a guess.
AD_WIDTH = 728
AD_HEIGHT = 90
# A little air above and below, so the creative is not welded to the draft.
PADDING = 6
HEIGHT = AD_HEIGHT + 2 * PADDING


# The house creative's own colours. Deliberately NOT the app's palette:
# an advertisement that matches the window it sits in reads as part of the
# app, and the one thing this has to be honest about is that it is not.
AD_INK = "#f4f6fb"
AD_DIM = "#9fb0cc"
AD_BACK = "#101a2e"
AD_BACK_2 = "#1b2f52"
AD_ACCENT = "#ffb020"
AD_HEADLINE = "Vantage 8K"
AD_SUB = "Wireless. 0.125 ms. Built for the 45-minute fight."
AD_BRAND = "MERIDIAN"
AD_CTA = "SHOP NOW"


def _face(size: int, bold: bool = True, spacing: float = 0.0) -> QFont:
    """The app's own family for the creative, since the app owns it."""
    font = QFont(theme.FONT_STACK.split(",")[0].strip().strip("'\""))
    font.setPixelSize(size)
    font.setBold(bold)
    if spacing:
        font.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, spacing)
    return font


def elided(text: str, room: float, size: int) -> str:
    """Copy cut to the space before the button.

    A line of copy that runs under the call to action is the one mistake
    a real banner never makes, and it is the mistake a fixed x position
    makes the moment the wording changes.
    """
    metrics = QFontMetricsF(_face(size, bold=False))
    return metrics.elidedText(text, Qt.TextElideMode.ElideRight, room)


def leaderboard(width: int = AD_WIDTH, height: int = AD_HEIGHT) -> QPixmap:
    """A 728x90 banner, drawn rather than downloaded.

    Everything a real leaderboard has and in the places one has them: the
    brand at the left behind a mark, a headline big enough to read in
    passing, one line of copy under it, a call to action on the right, and
    the little "Ad" marker that every network is required to put on one.
    It exists to answer "what does the window look like with an ad in it",
    which a grey box with the word Advertisement in it does not.
    """
    art = QPixmap(width, height)
    art.fill(QColor(AD_BACK))
    painter = QPainter(art)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    wash = QLinearGradient(0, 0, width, height)
    wash.setColorAt(0.0, QColor(AD_BACK))
    wash.setColorAt(0.55, QColor(AD_BACK_2))
    wash.setColorAt(1.0, QColor(AD_BACK))
    painter.fillRect(0, 0, width, height, wash)

    # The mark: two chevrons, which is a shape rather than a logo.
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QColor(AD_ACCENT))
    for step in (0, 15):
        chevron = QPainterPath()
        chevron.moveTo(20 + step, 26)
        chevron.lineTo(36 + step, 45)
        chevron.lineTo(20 + step, 64)
        chevron.lineTo(28 + step, 45)
        chevron.closeSubpath()
        painter.fillPath(chevron, QColor(AD_ACCENT))

    def write(text: str, x: float, baseline: float, size: int, colour: str,
              spacing: float = 0.0, bold: bool = True) -> float:
        font = _face(size, bold, spacing)
        painter.setFont(font)
        painter.setPen(QColor(colour))
        painter.drawText(QPointF(x, baseline), text)
        return QFontMetricsF(font).horizontalAdvance(text)

    # The call to action, right-aligned with room to breathe. Measured
    # FIRST, because the copy on the left has to stop before it.
    button = QRectF(width - 168, 26, 140, 38)
    room = button.left() - 20 - 78
    write(AD_BRAND, 78, 32, 14, AD_ACCENT, spacing=3.0)
    write(AD_HEADLINE, 78, 62, 27, AD_INK)
    write(elided(AD_SUB, room, 14), 78, 82, 14, AD_DIM, bold=False)

    painter.setBrush(QColor(AD_ACCENT))
    painter.setPen(Qt.PenStyle.NoPen)
    painter.drawRoundedRect(button, 6, 6)
    painter.setFont(_face(16, spacing=1.5))
    painter.setPen(QColor(AD_BACK))
    painter.drawText(button, int(Qt.AlignmentFlag.AlignCenter), AD_CTA)

    # The marker. Every network puts one on; leaving it off would make the
    # layout look better than the real thing is allowed to.
    painter.setBrush(QColor(255, 255, 255, 30))
    painter.setPen(Qt.PenStyle.NoPen)
    painter.drawRoundedRect(QRectF(width - 30, 6, 24, 14), 3, 3)
    write("Ad", width - 26, 17, 11, AD_DIM, bold=False)
    painter.end()
    return art


class AdSlot(QWidget):
    """A banner that is either there the whole time, or not at all."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("adSlot")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, PADDING, 0, PADDING)
        # The creative is a FIXED-SIZE box centred in a full-width slot: a
        # leaderboard is 728x90 wherever it is served, and stretching one
        # across a 3440px window would be a shape no advertiser ever buys.
        self.creative = QLabel("")
        self.creative.setObjectName("adCreative")
        self.creative.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.creative.setFixedSize(AD_WIDTH, AD_HEIGHT)
        lay.addWidget(self.creative, 0, Qt.AlignmentFlag.AlignHCenter)
        # Kept under the old name too: `label` is what the tests and the
        # window reach for, and renaming it buys nothing.
        self.label = self.creative
        self._enabled = False
        self.setFixedHeight(0)
        self._paint()

    def set_enabled(self, on: bool) -> None:
        """Switch the whole thing on or off. There is nothing in between.

        ON puts the banner up and leaves it up for as long as it is on.
        OFF collapses the slot to nothing: a strip of dead window above
        the draft for a switched-off feature is worse than either.
        """
        on = bool(on)
        if on == self._enabled:
            return
        self._enabled = on
        self.setFixedHeight(HEIGHT if on else 0)
        self._paint()

    @property
    def showing(self) -> bool:
        """Whether a creative is on screen — which, now that the cycle is
        gone, is the same question as whether ads are on at all."""
        return self._enabled

    def _paint(self) -> None:
        if self._enabled:
            self.creative.setPixmap(leaderboard())
        else:
            self.creative.clear()
        self.setProperty("live", "true" if self._enabled else "false")
        self.style().unpolish(self)
        self.style().polish(self)
