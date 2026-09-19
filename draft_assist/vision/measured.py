"""Where the pick bar sits, measured per display shape rather than guessed.

**THIS IS THE TABLE THE OWNER ASKED FOR**: "i just run every resolution of
dota 2 - draft against bots - record via the dota draft assist app - send
back reports - refine the protrait recognition for each resolution... and
then the user of this app has their current rresdolution sensed by this app
and it knows exactly where to look fort the portraits ... o nthe first try".

What it buys is DRAFT NUMBER ONE. The app has measured itself at strategy
time for a long while (`autocal`, `_remember_measured_layout`) and now
repairs itself from a bad draft's own recording (`bugreport.repair`), so a
fresh install has been self-correcting from the second draft onwards. The
one thing neither could do is be right during the FIRST hero selection,
which is the screen the app exists for.

**A TABLE OF RESOLUTIONS WOULD HAVE A HUNDRED ROWS AND TWO ANSWERS.**
`layout.hud_box` already computes every resolution from `scale = min(w/16,
h/9)`, centred — so 1920x1080, 2560x1440 and 3840x2160 are the SAME
fractions, exactly, and measuring each of them separately measures the same
thing three times. What actually varies is the display's SHAPE, and the
measurement says it varies in one step:

    bar width / HUD span   frames
    0.780 - 0.791          1360x768, 1920x1080, 2560x1440, 3440x1440
    0.889 - 0.898          800x600, 1024x768, 1280x1024, 1440x900, 1600x1200

which is 16:9-and-wider against narrower-than-16:9. Nobody has explained
the mechanism and nothing here claims one; `GROUPS` records the step as
measured and stops there.

**SO THERE ARE TWO LEVELS AND THE SPECIFIC ONE WINS.** `EXACT` is keyed by
resolution and is where a bot-game measurement goes — one row per display
actually played on, pasted from `tools/measure_recording.py --row`. `GROUPS`
is the shape-level answer, which is what an untried resolution falls back
to. A table alone could say nothing about a display nobody owned; a group
alone would ignore a real reading somebody took. Having both means adding a
row can only ever make one resolution better and can never make another
worse.

**AND THE MACHINE'S OWN MEASUREMENT STILL BEATS BOTH** (`load_layout`).
`calibration_local.json` is this display, this install, measured by this app
off a real match — it is an ANSWER where everything in this file is a good
starting guess. The order is: the local file, then `EXACT`, then `GROUPS`,
then `DraftLayout()`'s own defaults.

**`radiant_x` IS DERIVED, NOT MEASURED, AND THAT IS THE STRONGER NUMBER.**
The bar is centred on the HUD span: predict the left bank's origin as the
mirror of the right one — `1 - (dire_x + 4*pitch + slot_w)` — and it lands
within 1 to 4 PIXELS of the measured origin on all seven frames that
located ten portraits. Measuring it directly is the one reading with a
known failure: `banks_from` reads a bank's origin off the FIRST portrait it
finds in that bank, so a single missed leading portrait moves it by a whole
pitch and moves nothing else. That is exactly why `radiant_x` is the
fraction that never settled in the screenshot sweep while the other five
did. `mirrored_x` is therefore what fills it, and a row states the four it
measured.
"""

from dataclasses import dataclass, replace

from .layout import DraftLayout, HUD_ASPECT


def mirrored_x(dire_x: float, slot_w: float, pitch: float) -> float:
    """The left bank's origin, from the right bank's, assuming a centred bar.

    Spelled once. `bank_span` is four pitches plus one portrait — the
    arithmetic this project has already got wrong once by writing
    `4 * slot_w + 4 * pitch`, which hung a bank off the right of the
    screen.
    """
    return 1.0 - (dire_x + 4 * pitch + slot_w)


@dataclass(frozen=True)
class Reading:
    """One measured pick bar, and where the measurement came from.

    The four fractions are the ones a located frame reads directly.
    `radiant_x` is not among them deliberately — see the module note.
    """

    dire_x: float
    y: float
    slot_w: float
    slot_h: float
    pitch: float
    source: str
    frames: int = 1

    def layout(self) -> DraftLayout:
        """A full `DraftLayout`, with the left bank mirrored in.

        `role_dy` and `role_h` keep `DraftLayout`'s own values: there is
        no role strip in a located pick bar, so nothing here has ever
        measured them and inventing a number would be worse than
        inheriting one.
        """
        return replace(
            DraftLayout(),
            radiant_x=round(mirrored_x(self.dire_x, self.slot_w, self.pitch), 4),
            dire_x=self.dire_x,
            y=self.y,
            slot_w=self.slot_w,
            slot_h=self.slot_h,
            pitch=self.pitch,
        )


@dataclass(frozen=True)
class Group:
    """One display SHAPE, and the band of aspects it answers for.

    Half-open on the low side (`low <= aspect < high`) so the two groups
    partition every aspect there can be and no display falls between
    them — a gap here would be a fresh install with no answer at all,
    which is the state this file exists to end.
    """

    label: str
    low: float
    high: float
    reading: Reading

    def covers(self, aspect: float) -> bool:
        return self.low <= aspect < self.high


# The four fractions a frame reads, per shape. Measured by
# `tools/find_portraits.py` over the owner's own screenshots, except the
# 16:9-and-wider vertical, which is the app's OWN `autocal` measurement
# off a real 3440x1440 match — two independent routes agreeing that the
# shipped y=0.0330 / slot_h=0.0930 were never measured by anything.
WIDE = Group(
    label="16:9 and wider",
    low=HUD_ASPECT,
    high=float("inf"),
    reading=Reading(
        dire_x=0.5710,      # 0.5708, 0.5713
        y=0.0056,
        slot_w=0.0617,      # 0.0615, 0.0618
        slot_h=0.0611,
        pitch=0.0650,       # 0.0645, 0.0654
        source="1360x768 and 1920x1080 screenshots; vertical from a real "
               "3440x1440 match measured by autocal",
        frames=3,
    ),
)
TALL = Group(
    label="narrower than 16:9",
    low=0.0,
    high=HUD_ASPECT,
    reading=Reading(
        dire_x=0.5926,      # 0.5914 - 0.5938
        y=0.0052,           # worst miss 0.0008 across the sweep
        slot_w=0.0692,      # 0.0674 - 0.0711
        slot_h=0.0525,
        pitch=0.0709,       # 0.0703 - 0.0715
        source="800x600, 1024x768, 1280x1024, 1440x900 and 1600x1200 "
               "screenshots",
        frames=5,
    ),
)

GROUPS: tuple[Group, ...] = (WIDE, TALL)

# One row per resolution somebody has actually drafted on, keyed by the
# frame size the app captures. A row is produced by playing a bot draft at
# that resolution and running `tools/measure_recording.py <folder> --row`,
# which prints the line to paste here. It is deliberately EMPTY rather than
# pre-filled with the group's own numbers: a row that merely repeats its
# group says a measurement was taken when none was, and the fallback below
# already covers every resolution.
EXACT: dict[tuple[int, int], Reading] = {
    # **BOTH ROWS ARE HERE FOR ONE FRACTION: `slot_h`.** Six bot drafts
    # measured every resolution the owner plays on, and the three at 16:9
    # and wider came back within 0.0012 of `WIDE` on all five fractions -
    # so they get no row, which is the table working as designed. The two
    # NARROWER displays match `TALL` on `dire_x`, `y`, `slot_w` and
    # `pitch` just as closely, and disagree with it on `slot_h` in
    # OPPOSITE DIRECTIONS: 0.0488 here against the group's 0.0525, and
    # 0.0617 at 1920x1200. One constant cannot be both.
    (1280, 1024): Reading(
        dire_x=0.5922,
        y=0.0059,
        slot_w=0.0695,
        slot_h=0.0488,      # TALL says 0.0525; six frames say this
        pitch=0.0703,
        source="bot draft at 1280x1024, six strategy frames, all ten "
               "calibrated boxes landing",
        frames=6,
    ),
    (1920, 1200): Reading(
        dire_x=0.5938,
        y=0.0058,
        slot_w=0.0682,
        slot_h=0.0617,      # TALL says 0.0525 - out by 0.0092
        pitch=0.0719,
        source="bot draft at 1920x1200, five strategy frames, all ten "
               "calibrated boxes landing",
        frames=5,
    ),
}


def group_for(width: int, height: int) -> Group:
    """The measured shape this display belongs to.

    Never None: the groups partition every aspect, and a zero-height frame
    (which `hud_box` also guards against) is treated as the commonest case
    rather than as an error, since a capture that has not started yet must
    not be able to raise out of a layout lookup.
    """
    if not width or not height:
        return WIDE
    aspect = float(width) / float(height)
    for group in GROUPS:
        if group.covers(aspect):
            return group
    return WIDE


def reading_for(width: int, height: int) -> Reading:
    """This resolution's own measurement if one was taken, else its shape's."""
    exact = EXACT.get((int(width), int(height)))
    return exact if exact is not None else group_for(width, height).reading


def layout_for(width: int, height: int) -> DraftLayout:
    """Where to look for the portraits on a display of this size."""
    return reading_for(width, height).layout()


def describe(width: int, height: int) -> str:
    """One line for the diagnostic paste, naming which answer was used.

    Which of the three levels a reading came from is invisible in the six
    numbers, and it is the first thing worth knowing when the boxes are
    wrong — an exact row being wrong is a bad bot game, a group being
    wrong is a shape nobody has measured.
    """
    if not width or not height:
        return "crop boxes: no frame yet, so no resolution to match"
    exact = EXACT.get((int(width), int(height)))
    if exact is not None:
        return (f"crop boxes: {width}x{height} measured directly "
                f"({exact.frames} frame(s), {exact.source})")
    group = group_for(width, height)
    return (f"crop boxes: no reading for {width}x{height}, using "
            f"\"{group.label}\" ({group.reading.frames} frame(s), "
            f"{group.reading.source})")
