"""The advertising banner above the draft.

A placeholder, deliberately: there is no ad network wired in and no
network call is made. What is here is the SLOT — the space an ad would
take, on the schedule it would appear on — so the layout question ("what
does the window look like with this in it") can be answered now, and so
turning it on and living with it for an evening is a thing the owner can
actually try before committing to it.

**It is off by default and it is a setting** (`ui_settings.ads_enabled`).
This is the user's own app on their own machine; something that covers
part of the board every few seconds has to be asked for.

**It reserves its height while ads are ON, and NONE while they are off.**
A banner that appears and disappears while pushing the ten picks up and
down the window is a board that moves under the cursor mid-draft, which is
how a pick gets misclicked — so between the showing and hidden halves of
the cycle the slot keeps its height and only its CONTENT changes. But with
the whole feature switched off there is no cycle to hold still for, and
reserving the space anyway is a strip of dead window above the draft that
nobody asked for; the slot collapses to nothing instead.

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

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtWidgets import QLabel, QVBoxLayout, QWidget

from . import theme

# Five seconds on, ten off, at the user's request.
SHOWING_MS = 5_000
HIDDEN_MS = 10_000
# The IAB leaderboard — the size a banner slot is actually sold as, so the
# layout is tested against the real thing rather than against a guess.
AD_WIDTH = 728
AD_HEIGHT = 90
# A little air above and below, so the creative is not welded to the draft.
PADDING = 6
HEIGHT = AD_HEIGHT + 2 * PADDING


class AdSlot(QWidget):
    """A banner that shows for `SHOWING_MS` in every cycle, or never."""

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
        self._showing = False
        # A single-shot restarted each turn rather than two timers: one
        # clock cannot get out of step with itself.
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self._turn)
        self.setFixedHeight(0)
        self._paint()

    def set_enabled(self, on: bool) -> None:
        """Switch the whole thing on or off.

        ON reserves the slot's full height for as long as it is on, so the
        board below never moves between the showing and hidden halves of
        the cycle. OFF collapses it to nothing: with no cycle running there
        is nothing to hold still for, and a permanent strip of dead window
        above the draft for a switched-off feature is worse than either.
        """
        on = bool(on)
        if on == self._enabled:
            return
        self._enabled = on
        self._showing = False
        self._timer.stop()
        self.setFixedHeight(HEIGHT if on else 0)
        if on:
            self._timer.start(HIDDEN_MS)
        self._paint()

    @property
    def showing(self) -> bool:
        return self._showing

    def _turn(self) -> None:
        self._showing = not self._showing
        self._timer.start(SHOWING_MS if self._showing else HIDDEN_MS)
        self._paint()

    def _paint(self) -> None:
        # The SLOT stays; only what is in it comes and goes. Hiding the
        # widget itself would move the ten picks up and down the window
        # every few seconds, and a board that moves is one you misclick.
        # It says what it IS. A blank grey box that appears every ten
        # seconds looks like something broken rather than like a slot
        # nobody has sold yet.
        self.creative.setText(
            f"Advertisement · {AD_WIDTH}x{AD_HEIGHT}" if self._showing else "")
        self.setProperty("live", "true" if self._showing else "false")
        self.style().unpolish(self)
        self.style().polish(self)
