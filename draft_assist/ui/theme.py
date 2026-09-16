"""Application palette and stylesheet — Discord's dark theme.

Deliberately borrowed rather than invented: the app is read at a glance
while a draft timer runs, and a palette the user already reads fluently
every day costs no attention to parse. Discord's greys are also unusually
well tuned for exactly this job — a dense dark surface where the only
saturated colour is meaning.

Colour is reserved for meaning: green and red for signed deltas, the
accent for the one action a screen wants, amber for warnings. Everything
else is grey, so a number in colour is always worth reading.

**The accent is RED, not Discord's blurple** — the user asked for it, and
it sits better beside a Warcraft-inspired frame than a blue does. It is a
DEEPER red than `BAD` on purpose: `BAD` is the bright coral a negative
number is printed in, and if the two were the same colour a selected tab
would read as a warning. Keep them apart if either is ever retuned.
"""

# Discord's dark theme, by role rather than by name.
BG = "#313338"            # main content
BG_ELEVATED = "#2b2d31"   # chrome: menus, toolbar, cards
BG_DEEP = "#1e1f22"       # the darkest surface, behind everything
BG_INPUT = "#383a40"      # inputs and unselected buttons
BG_HOVER = "#404249"
BORDER = "#3f4147"
TEXT = "#dbdee1"
TEXT_STRONG = "#f2f3f5"
TEXT_DIM = "#949ba4"
ACCENT = "#38040e"        # maroon; see the note below
ACCENT_HOVER = "#540716"
# THE ACCENT WITH THE PRESS TAKEN OUT OF IT, for a control that is there
# and cannot be used — the down arrow on a count box already at nought.
# At the user's request: "if i cant go any lower e.e.g im at 0, i sitll
# want the down arrow to become dim, just a dim version of the red". A
# GREY one would say the arrow is a different kind of thing from its
# twin; a dim red says it is the same control with nothing left to do.
# Mixed against `BG_INPUT` rather than darkened, so it sits on the
# surface it is drawn on.
# TWO MAROONS, AND THE SPLIT IS MEASURED RATHER THAN TASTE. At the
# user's request every red accent in the chrome is #38040e - but that
# colour is 0.010 relative luminance, where the red it replaces was
# 0.125. As a GROUND it is excellent: off-white on it measures 15.9:1,
# against 5.4:1 before. As a MARK on any surface in this palette it sits
# between 1.07 and 1.55:1 and effectively disappears, so a caret, a
# count box arrow or the selected tab's underline drawn in it could be
# located only by knowing where it was.
# So ACCENT is the FILL - anything with white text or a tick on top -
# and ACCENT_MARK is every line, edge and small shape drawn ON dark with
# nothing over it. It is the same hue lifted to the visibility the old
# accent had: 2.06-2.69:1 against these surfaces, where #b5342c managed
# 2.10-2.74:1. Nothing became harder to see than it already was.
# The signed numbers are NOT in this: GOOD and BAD are the app's one
# universal convention and the user pointedly left every one of them
# out of the request.
ACCENT_MARK = "#c30e31"
# The spent end of a stepper, at the same share of its own mark colour
# that the old dim red was of the old accent (0.59).
ACCENT_MARK_DIM = "#980b26"
# The pill the three board buttons sit in. BG_DEEP rather than
# BG_ELEVATED: elevated is the CARDS' own colour and the two team cards
# flank that row, so a pill in that shade would read as a third card
# rather than as a group.
GROUP_BG = BG_DEEP
GOOD = "#23a55a"
BAD = "#f23f43"
WARN = "#f0b232"
ROW_ALT = "#2e3035"
# The window frame's lit edge (see `ui/ornate.py`), so the app's name and
# the border round it read as one piece rather than two decisions.
FRAME_GOLD = "#c9a45a"
# The heart on a suggestion you play and win on. PINK rather than the red
# it was first asked for, at the user's own second thought - and it is
# the better call: every signed number in this app is printed in green or
# red, and a red mark sits directly above a red "-2.4" on the same tile.
# Pink belongs to nothing else here, so it cannot be read as a judgement
# about the figure beside it.
HEART_PINK = "#ff6fa5"
# The hairline between one control and the next, at the user's request:
# "right in the middle" of white and black, which is exactly #808080. It
# is deliberately NOT one of the greys above — those are surfaces and
# text, and a rule is neither; it has to read on the dark band and on the
# card alike.
RULE = "#808080"

# The scrollbar handle. Light enough to find against every surface it sits
# on — the content grey, a card, and the near-black of a log panel — and
# quiet enough not to compete with the draft. It was BG_DEEP, which is
# darker than the panel it sits in and so read as a hole rather than a
# control.
SCROLL = "#4e515a"
SCROLL_HOVER = "#5f6470"
# The card and team headings — "Radiant", "Suggested picks".
HEADING_PX = 21
# The body, and with it every signed number in the app: the grids print
# their deltas at this size, so the figure on a portrait is set from the
# same value rather than from one that happens to match today.
BODY_PX = 18

# EVERY BUTTON IS THE HEIGHT OF A NUMBER BOX, at the user's request:
# "the yellow box is too tall... it shoudl be the height of the boxes
# around the number entry fields... standardize the height of these
# button boxes across the board to be this height". A button was 41px
# against a count box's 33, so the three board actions sat visibly
# taller than the quantity boxes below them wearing the same gold.
# ONE NUMBER, read by the QPushButton rule's own padding (which lands
# on it exactly at the body size) and applied outright by
# `chrome.CountBox`, which paints its own border and so cannot get its
# height from the stylesheet's.
CONTROL_H = 33

# THE ONE LINE WEIGHT THE APP'S DELIBERATE OUTLINES ARE DRAWN AT: the
# window's own frame, the ring round a clicked portrait, the box round a
# relation's figure, the hero callout, and the three board buttons. It
# lives HERE rather than in `ornate` — which is where it used to, and
# which imports this module, so the dependency only goes one way — and
# `ornate.WIDTH` and `tilekit.FOCUS_WIDTH` both read it. One number, or
# "the same line width as the border round the selected portrait" is a
# thing somebody has to keep true by hand in five places.
FRAME_WIDTH = 3
# What the plain buttons pad with, so a 3px border still lands on
# `CONTROL_H`: a border sits OUTSIDE the padding box, so the two have to
# add up. Stated rather than inlined, because the pair is the invariant.
PLAIN_PAD_Y = 1
# The strip a combo box keeps clear on its right for the caret this app
# paints itself (see `chrome.Dropdown`).
ARROW_STRIP = 18

# THE APP'S NAME IN THE TITLE BAR, at the user's request: "reduce the
# font size of the app logo by 10% and reduce the thickess of the font
# by 20%" — and then, to be clear about which logo: "not logo sorry i
# mean the logo texct.. the logo (app icon) should not be touchned".
# 25px less a tenth is 22, and the weight is the part that could not be
# done where it was: `TITLE_FAMILY` is Alegreya BLACK, a single-weight
# face, so `font-weight` on it changes nothing at all (Qt synthesises
# heavier, never lighter). A fifth off ~900 is ~720, which is Alegreya's
# own BOLD — already bundled, already registered, so the name is still
# the body face raised rather than a second typeface. TITLE_FAMILY
# itself stays: the rank digit on a suggestion is drawn in it.
TITLE_PX = 22
TITLE_WEIGHT = 700

# The app's own name. The same family as the body at its heaviest weight
# — `assets/fonts/Alegreya-Black.ttf` registers it — so the title is the
# app's own voice raised rather than a second typeface arguing with it.
TITLE_FAMILY = "Alegreya Black"
# Alegreya, under the SIL Open Font License — registered from
# `assets/fonts/` at startup by `ui/fonts.load_bundled` rather than
# installed. Everything after it is the fallback if the files are not
# there: the app must still open with a readable UI, which is the same
# rule a missing portrait or a missing app icon follows.
BODY_FAMILY = "Alegreya"
FONT_STACK = (f'"{BODY_FAMILY}", "Palatino Linotype", "Book Antiqua", '
              '"Georgia", "Noto Serif", "Segoe UI", system-ui, serif')

# HOW FAR A CONTROL ON THE TAB ROW SITS FROM THE RULE BESIDE IT, as the
# EYE measures it: from the last pixel of ink to the line, not from the
# widget's rectangle to it. The two are the same thing only for a widget
# with no padding — which is why the text buttons, carrying the tab's
# own 18px, read as twice as far from their rules as the record dot and
# the tick did. The buttons gave that padding up here, and this is
# the gap the row uses instead: stated here, read by the toolbar's
# stylesheet and by the strip that holds the leading rule, so the two
# cannot drift.
TOOL_GAP = 14


def _build_stylesheet() -> str:
    """The stylesheet, built from whatever the colour globals say NOW.

    It was a module-level f-string evaluated once at import, which is
    right until the palette can change under it — View ▸ Greyscale
    rewrites every colour above and then asks for this again.
    """
    return f"""
QWidget {{
    background: {BG};
    color: {TEXT};
    font-family: {FONT_STACK};
    /* +20% and then another 15% on everything, and BOLD everywhere, at
       the user's request. The app is read in the corner of the eye over a
       game, so weight is legibility rather than decoration — and
       Alegreya's bold is one of the files bundled, so it resolves rather
       than being synthesised. */
    font-size: {BODY_PX}px;
    font-weight: bold;
}}
/* A QLabel INHERITS the rule above, so every label in the app painted a
   rectangle of CONTENT colour ({BG}) wherever it sat — which on a card
   ({BG_ELEVATED}) is a lighter box round the heading, and on an empty
   label still in the layout is the 3mm stub at the end of a team's
   heading row. It had already been patched twice, once for the title bar
   and once for the tab strip, and each patch only covered the widget
   somebody happened to be looking at. Transparent by DEFAULT instead; a
   label that wants a background says so, and the pills below win on
   specificity. */
QLabel {{ background: transparent; }}
/* THE TOOLTIP WAS THE ONE WIDGET IN THIS APP NOBODY HAD NAMED —
   "when i mouse over these text boxes i see a weird black callout".
   Exactly the scrollbars' fault, and it hides in exactly the same place:
   a fallback that this machine CANNOT REPRODUCE. Rendered here the
   unstyled tip comes out in Fusion's own pale yellow (#ffffdc) with
   black text, which is merely wrong for a dark app; on Windows the same
   omission draws the BLACK RECTANGLE the user is looking at. So neither
   the screenshot nor a render says what went wrong, and the thing to fix
   is the same either way: name it.
   It is every tooltip in the app, on every control — and the ones that
   carry real information are the ones it cost most: a role filter's
   1-to-3 scale, a star's two percentiles, why an item icon is missing,
   which two date spans a delta compared.
   A BORDER AND PADDING, not just a colour: a tip floats over whatever is
   behind it, so it needs an edge of its own, and `BG_DEEP` is the
   darkest surface here, which reads as sitting above a card rather than
   in it. BOLD, because everything in this app is. */
QToolTip {{
    background: {BG_DEEP};
    color: {TEXT};
    border: 1px solid {BORDER};
    border-radius: 4px;
    padding: 6px 8px;
    font-weight: bold;
}}
/* THE CARET THAT DROPS THE PROFILE CALLOUT. One of this app's clickable
   arrows, and they are all red now — "all of the up/down arrows
   (clickable) that ever feature in this app, i want them to be red....
   that includes the one on the steam profile section top right of app
   window". A PROPERTY rather than a widget stylesheet, so
   `set_greyscale` rebuilds it with everything else. */
QLabel[caret="true"] {{ background: transparent; color: {ACCENT_MARK}; }}
QMainWindow::separator {{ background: {BORDER}; width: 1px; height: 1px; }}

QMenuBar {{ background: {BG_DEEP}; border-bottom: 1px solid {BG_DEEP}; }}
QMenuBar::item {{ padding: 6px 12px; background: transparent; }}
QMenuBar::item:selected {{ background: {BG_INPUT}; }}
QMenu {{ background: {BG_ELEVATED}; border: 1px solid {BORDER}; padding: 4px; }}
QMenu::item {{ padding: 6px 24px 6px 12px; }}
QMenu::item:selected {{ background: {ACCENT}; color: #ffffff; }}
QMenu::separator {{ height: 1px; background: {BORDER}; margin: 4px 8px; }}
/* A CHECKABLE MENU ITEM DRAWS THE APP'S OWN TICK. `QMenu::item` is
   styled, and once a stylesheet touches a widget the parts it does not
   name are handed to somebody else to draw — the scrollbars' lesson,
   which cost a clump of white specks through a translucent window. So
   the indicator is named, and it is pointed at a picture, because a
   stylesheet can colour a box and cannot put a MARK in one.
   `{TICK_URL}` is empty until `install_tick()` has written the file,
   which cannot happen before the QApplication exists — an unchecked
   item is a plain outlined box either way, so the fallback is correct
   rather than merely harmless. */
QMenu::indicator {{
    width: 15px; height: 15px; margin-left: 6px;
    border-radius: 3px; border: 1px solid {BORDER}; background: {BG_INPUT};
}}
QMenu::indicator:checked {{ {TICK_URL} border-color: {ACCENT_MARK}; }}

QToolBar {{
    background: {BG_DEEP};
    border-bottom: 1px solid {BORDER};
    padding: 6px;
    spacing: 8px;
}}
/* On the tab strip it is part of the strip, not a band above it. */
QToolBar#tabStripTools {{
    background: {BG_DEEP}; border: none;
    /* No LEFT padding: the rule before the record dot is the
       strip's, outside this widget, so 2px here made that one gap
       two wider than every rule inside the toolbar. */
    padding: 0 2px 0 0;
    spacing: {TOOL_GAP}px;
}}
/* Every child, not just the labels: a QSlider left to the base
   QWidget rule painted a rectangle of CONTENT colour inside the dark
   band, which is the same discontinuity from the other direction. */
QToolBar#tabStripTools QLabel,
QToolBar#tabStripTools QCheckBox,
QToolBar#tabStripTools QSlider {{ background: {BG_DEEP}; }}
/* THE CONTROLS ON THIS ROW ARE TAB LABELS, not buttons. They are on the
   tab bar's own line and read as one series with it, so a raised plate in
   {BG_INPUT} with a radius round it was a second kind of object on a row
   that only has one. Every value below is the QTabBar::tab rule further
   down, copied deliberately: same padding, same {TEXT_DIM}, same lift to
   {TEXT} under the cursor. `font-weight` has to be said again because the
   base QPushButton rule sets 500 and would otherwise win over the app's
   bold. */
/* The tab row's QToolBar is gone: the record dot and Auto moved to
   the Run menu and the three board actions are added to the strip
   directly, which left an empty toolbar drawing a second divider.
   Its rules went with it rather than being left to be read as
   documentation for a widget that no longer exists. */

/* One BAND, laid out as one row (see chrome.BandedTabs): the strip is a
   plain widget holding the tab bar and the toolbar, so there is no gap
   between them for another colour to show through. */
QWidget#tabStrip {{ background: {BG_DEEP}; }}
QWidget#tabStrip QLabel,
QWidget#tabStrip QCheckBox,
QWidget#tabStrip QSlider,
QWidget#tabStrip QToolBar {{ background: {BG_DEEP}; }}

QTabWidget::pane {{ border: none; background: {BG}; }}
QTabBar {{ background: transparent; }}
QTabBar::tab {{
    background: transparent;
    color: {TEXT_DIM};
    padding: 8px 18px;
    border-bottom: 2px solid transparent;
}}
QTabBar::tab:selected {{ color: {TEXT}; border-bottom: 2px solid {ACCENT_MARK}; }}
QTabBar::tab:hover {{ color: {TEXT}; }}

/* NO GOLD ON A CONTROL, which REVERSES "a gold border on every button".
   That was asked for — "id like to make all buttons have a gold border
   (the same as the app border).. even for the quantity boxes" — and then
   withdrawn on sight: "remove the gold border from all the input boxes
   ... revert that change i made - i dont liek it now that i have seen
   it... obviosuly keep the app window border though".
   So gold goes back to meaning "THIS ONE" and nothing else: the window's
   frame, the focus ring, the suggestion star, the pin, the role pills
   and the box round a relation's figure. A border that every control in
   the app wears says nothing about any of them, and it was competing
   with the five marks that are supposed to catch the eye. */
QPushButton {{
    background: {BG_INPUT};
    border: 1px solid transparent;
    border-radius: 4px;
    /* 3px, NOT a min-height: at the body size this lands on exactly
       {CONTROL_H}px, which is what a count box measures, and it leaves a
       button that has to hold two lines free to be two lines tall. A
       min-height would have capped those instead. */
    padding: 3px 14px;
    color: {TEXT};
    font-weight: 500;
}}
QPushButton:hover {{ background: {BG_HOVER}; border-color: {BG_HOVER}; }}
QPushButton:pressed {{ background: {BG_DEEP}; }}
QPushButton:disabled {{
    color: {TEXT_DIM}; background: {BG_ELEVATED};
}}
QPushButton[accent="true"] {{
    background: {ACCENT}; border-color: {ACCENT}; color: #ffffff;
    font-weight: 600;
}}
QPushButton[accent="true"]:hover {{
    background: {ACCENT_HOVER}; border-color: {ACCENT_HOVER};
}}
/* AFTER the accent rule, or it never applies. The plain
   `QPushButton:disabled` above is declared earlier, so on a button
   carrying [accent="true"] the accent wins on specificity and a disabled
   one stayed fully red — a control that looks pressable and is not. Same
   ordering lesson as the amber warning label. */
QPushButton[accent="true"]:disabled {{
    background: {BG_ELEVATED}; border-color: {BG_INPUT}; color: {TEXT_DIM};
    font-weight: 500;
}}
/* A BUTTON THAT IS ONLY ITS OUTLINE — the gold, the app's own bold, and
   whatever is behind it showing through. At the user's request, about
   Clear all / Detect all / Demo: "there is a bit of a grey color added
   to the cclear / detect / etc button backgfground... should be same as
   the background behidn it", and "the clear / detec / etc fotn looks
   different to draft / analysis".
   Both are the base rule above doing what it does everywhere else:
   {BG_INPUT} is a raised plate, which against a darker surface reads as
   a grey box, and `font-weight: 500` is the one weight in this app that
   is not the app's bold. A PROPERTY rather than an ancestor selector,
   because these three have now been seated on the tab row, on a board
   bar, back on the tab row and on a board bar again — a rule keyed to
   where they happen to sit is a rule that stops applying the next time
   they move.
   DECLARED AFTER every `QPushButton:` state above: a property selector
   and a pseudo-class score the same, so the tie goes to whichever is
   written last. */
/* A RED OUTLINE AT THE FOCUS RING'S OWN WEIGHT, at the user's request:
   "i want these buttons to have a red border, same line width as the
   border that goes aroudn the 5 /5 hero portrait when it is selected".
   `FRAME_WIDTH` is that number, and it is the same one the ring, the
   window frame and the hero callout are drawn at.
   THE PADDING GIVES BACK WHAT THE BORDER TAKES: a border sits outside
   the padding box, so three pixels instead of one is four more pixels of
   height, and the vertical padding drops to hold `CONTROL_H` — the one
   height every control in this app is. */
/* THE BORDER STAYS AND IS THE FILL'S OWN COLOUR, which is what removes
   it to the eye without moving the button. {PLAIN_PAD_Y}px of padding
   plus {FRAME_WIDTH}px of border is what lands this on {CONTROL_H}px,
   exactly what a count box measures - drop the border and all three
   lose 6px of height and stop matching the boxes below them. */
QPushButton[plain="true"] {{
    background: {ACCENT}; font-weight: bold;
    border: {FRAME_WIDTH}px solid {ACCENT};
    padding: {PLAIN_PAD_Y}px 12px;
    color: {TEXT_STRONG};
}}
QPushButton[plain="true"]:hover {{
    background: {ACCENT_HOVER}; border-color: {ACCENT_HOVER};
}}
QPushButton[plain="true"]:pressed {{
    background: {ACCENT}; border-color: {ACCENT_HOVER};
}}
QPushButton[plain="true"]:disabled {{
    background: {ACCENT}; color: {TEXT_DIM}; border-color: {ACCENT};
}}
/* Recording is the one state the eye must catch across the room. */
QPushButton[recording="true"] {{
    background: #c2453f; border-color: #c2453f; color: #ffffff;
    font-weight: 700;
}}
QPushButton[recording="true"]:hover {{ background: #d4544e; }}
QPushButton[slot="true"] {{
    text-align: left; padding: 8px 11px; background: {BG_INPUT};
    border-left: 3px solid {BG_INPUT};
}}
/* An empty slot is an invitation, not a pick: it reads as a dashed hole. */
QPushButton[slot="true"][filled="false"] {{
    background: transparent; color: {TEXT_DIM};
    border: 1px dashed {BORDER}; border-left: 3px solid transparent;
}}
/* The hero whose relations every other slot is currently showing. */
QPushButton[slot="true"][focused="true"] {{
    background: {BG_HOVER}; color: {TEXT_STRONG};
    border-left: 3px solid {ACCENT_MARK}; font-weight: 600;
}}

QComboBox {{
    background: {BG_INPUT};
    border: 1px solid {BORDER};
    border-radius: 5px;
    padding: 5px 10px;
}}
QComboBox:hover {{ border-color: {ACCENT_MARK}; }}
/* THE ARROW IS PAINTED BY `chrome.Dropdown`, so the sub-controls are
   cleared out of its way here. This is the tick box's lesson used
   deliberately for once: naming a sub-control puts Qt on the stylesheet
   path for it, and a stylesheet can colour one but cannot put a MARK in
   one without an image file — so naming it is how the native arrow is
   got RID of, and the widget draws the red one itself. */
QComboBox::drop-down {{
    border: none; background: transparent; width: {ARROW_STRIP}px;
}}
QComboBox::down-arrow {{ image: none; width: 0px; height: 0px; }}
QComboBox QAbstractItemView {{
    background: {BG_ELEVATED};
    border: 1px solid {BORDER};
    selection-background-color: {ACCENT};
}}
QSlider::groove:horizontal {{
    height: 4px; border-radius: 2px; background: {BG_INPUT};
}}
QSlider::sub-page:horizontal {{
    height: 4px; border-radius: 2px; background: {ACCENT_MARK};
}}
QSlider::handle:horizontal {{
    background: {ACCENT_MARK}; border: none; width: 12px; height: 12px;
    margin: -4px 0; border-radius: 6px;
}}
QSlider::handle:horizontal:hover {{ background: {ACCENT_MARK_DIM}; }}

/* The little count box beside a strip's heading. Without a rule of its
   own it took the base QWidget background — the same lighter-than-the-card
   rectangle the labels had. A border says "control" without a fill that
   fights the card it sits on.
   THERE ARE NO ::up-button / ::down-button RULES. Styling a sub-control
   puts Qt on the stylesheet path for it, and a stylesheet can colour a
   sub-control but cannot put a MARK in one without an image file — so the
   box lost its arrows altogether. `chrome.CountBox` draws them, the same
   answer as the tick box and the three window buttons. */
QSpinBox {{
    background: transparent; border: 1px solid {BORDER};
    border-radius: 4px; padding: 1px 3px; color: {TEXT};
    selection-background-color: {ACCENT}; selection-color: #ffffff;
}}
QSpinBox:hover {{ border-color: {ACCENT_MARK}; }}

QCheckBox {{ spacing: 7px; }}
QCheckBox::indicator {{
    width: 15px; height: 15px; border-radius: 3px;
    border: 1px solid {BORDER}; background: {BG_INPUT};
}}
QCheckBox::indicator:checked {{ background: {ACCENT}; border-color: {ACCENT}; }}

QTableWidget {{
    background: {BG};
    alternate-background-color: {ROW_ALT};
    /* Cell borders are ON. The numbers alone were meant to be the
       structure, and in a 5x5 of signed deltas they are not: the eye
       loses which column it is in halfway across. */
    gridline-color: {BORDER};
    border: 1px solid {BORDER};
    border-radius: 6px;
    selection-background-color: {ACCENT};
    selection-color: #ffffff;
}}
QHeaderView::section {{
    background: {BG_ELEVATED};
    color: {TEXT_DIM};
    padding: 2px 4px;
    border: none;
    border-bottom: 1px solid {BORDER};
    font-weight: 600;
}}
/* Centred both ways: a grid of signed numbers reads as a grid, and
   left-aligned cells under a centred portrait do not line up with it. */
QTableWidget::item {{ padding: 2px 4px; }}
/* A LIST IS STYLED OR IT IS NATIVE, the same rule the scrollbars taught:
   the parts a stylesheet does not name are not left alone, they are
   handed to somebody else to draw. The session list and the search
   results were painting their selection in Qt's own blue — the one
   colour in the app that means nothing, in a palette where colour is
   reserved for meaning and the accent is red. */
QListWidget, QListView {{
    background: {BG_INPUT}; border: 1px solid {BG_DEEP};
    border-radius: 4px;
}}
QListWidget::item, QListView::item {{ padding: 4px 8px; }}
QListWidget::item:selected, QListView::item:selected {{
    background: {ACCENT}; color: #ffffff;
}}
QListWidget::item:hover, QListView::item:hover {{ background: {BG_HOVER}; }}

QTextBrowser, QPlainTextEdit {{
    background: {BG_ELEVATED};
    border: 1px solid {BORDER};
    border-radius: 6px;
    padding: 6px;
}}
/* EVERY SUB-CONTROL IS STYLED, and that is the whole point of this block.
   Qt draws a scrollbar out of six separate pieces — the groove, the
   handle, two stepper buttons, their arrows, and the track either side of
   the handle — and styling SOME of them leaves the rest to the native
   style. That is what the speckled bars were: `add-page` and `sub-page`
   (the track) were never named here, so Windows drew them itself, in a
   dithered texture that reads as a clump of white specks through a
   translucent window, with the stepper buttons as specks at each end.
   Same lesson as the tick box and the count box's arrows, from the other
   direction: once a stylesheet touches a widget, anything it does not
   name is not "left alone", it is drawn by somebody else. */
QScrollBar:vertical {{
    background: transparent; border: none; width: 12px; margin: 0;
}}
QScrollBar:horizontal {{
    background: transparent; border: none; height: 12px; margin: 0;
}}
QScrollBar::handle:vertical {{
    background: {SCROLL}; border: none; border-radius: 4px;
    min-height: 32px; margin: 2px;
}}
QScrollBar::handle:horizontal {{
    background: {SCROLL}; border: none; border-radius: 4px;
    min-width: 32px; margin: 2px;
}}
QScrollBar::handle:hover {{ background: {SCROLL_HOVER}; }}
QScrollBar::handle:pressed {{ background: {TEXT_DIM}; }}
/* The steppers and their arrows, gone and EXPLICITLY gone: a zero size
   alone still leaves the native style something to paint. */
QScrollBar::add-line, QScrollBar::sub-line {{
    background: none; border: none; height: 0; width: 0;
}}
QScrollBar::up-arrow, QScrollBar::down-arrow,
QScrollBar::left-arrow, QScrollBar::right-arrow {{
    background: none; border: none; image: none; height: 0; width: 0;
}}
/* The track either side of the handle. THIS is the one that was missing. */
QScrollBar::add-page, QScrollBar::sub-page {{
    background: transparent; border: none;
}}
/* The square where a vertical and a horizontal bar meet, which is its own
   sub-control again and was drawing as a native grey notch. */
QAbstractScrollArea::corner {{ background: transparent; border: none; }}

/* The status line is a FOOTNOTE: it is read when something is wrong and
   ignored the rest of the time, so at the body size it competed with the
   draft above it for no reason. 70% of the body, at the user's request. */
QStatusBar {{
    background: {BG_DEEP}; border-top: 1px solid {BG_DEEP};
    font-size: 13px;
}}
QStatusBar QLabel {{ font-size: 13px; }}
QStatusBar::item {{ border: none; }}

QProgressBar {{
    background: {BG_INPUT}; border: 1px solid {BORDER};
    border-radius: 5px; height: 8px; text-align: center;
}}
QProgressBar::chunk {{ background: {ACCENT_MARK}; border-radius: 4px; }}

/* Our own title bar: the system one is a white strip above a dark app. */
QWidget#titleBar {{ background: {BG_DEEP}; }}
/* EVERY label on the bar, not just the title: a QLabel takes its
   background from the base QWidget rule, so the app icon — which is
   letterboxed into a square and therefore transparent top and bottom —
   sat on a rectangle of content colour. */
QWidget#titleBar QLabel {{ background: transparent; }}
/* Backstop for anything Qt puts on the bar that we did not: a menu bar's
   own overflow button, for one, which drew a light square. */
QWidget#titleBar QToolButton {{
    background: transparent; border: none; color: {TEXT_DIM};
}}
/* Half again the body size: it is the app's name in its own frame, and
   at 13px it read as another label rather than as the title. TRANSPARENT,
   because a QLabel takes its background from the base QWidget rule and
   drew a rectangle of content colour behind the text — a box round the
   title that nobody asked for. The colour is the frame's own gold, so the
   name and the border it sits inside are the same thing. */
QLabel#titleText {{
    background: transparent; color: {FRAME_GOLD};
    font-family: {FONT_STACK};
    font-weight: {TITLE_WEIGHT}; font-size: {TITLE_PX}px;
}}
QMenuBar#titleMenus {{ background: transparent; border: none; }}
QMenuBar#titleMenus::item {{ padding: 5px 10px; background: transparent; }}
QMenuBar#titleMenus::item:selected {{ background: {BG_HOVER}; }}
/* The window buttons are painted, not styled: see chrome.WindowButton.
   A hollow square glyph reads smaller than a dash and a cross at the same
   point size, and every font sized the three differently. */

/* The floating toggle: the only part of the app on screen when the window
   is hidden, so it reads as pressed-in or popped-out at a glance. */
QPushButton#overlayToggle {{
    background: {BG_ELEVATED};
    border: 2px solid {BORDER};
    border-radius: 8px;
}}
QPushButton#overlayToggle:hover {{ border-color: {TEXT_DIM}; }}
QPushButton#overlayToggle:checked {{
    background: {BG_DEEP};
    border-color: {ACCENT_MARK};
}}

/* A BARE CONTAINER PAINTS NOTHING. The base rule above gives every
   QWidget the CONTENT colour, so a plain QWidget used purely to hold a
   layout draws a pale rectangle wherever it sits on something darker -
   a card, the tab strip, a banner. That is the QLabel fault one widget
   kind over, and it showed up as "the padding is a lighter color" round
   the Suggested picks heading. Anything whose job is to hold a layout
   rather than to be a surface carries `bare`. */
QWidget[bare="true"] {{ background: transparent; }}
/* THE THREE BOARD BUTTONS SIT IN ONE PILL, at the user's request, so
   they read as one group rather than as three loose controls between
   the two team headings. Its padding is the LAYOUT's margins rather
   than this rule's: stylesheet padding on a container does not move the
   children inside it. */
QWidget[group="true"] {{
    background: {GROUP_BG};
    border-radius: 8px;
}}

QFrame[card="true"] {{
    background: {BG_ELEVATED};
    border: 1px solid {BORDER};
    border-radius: 8px;
}}
QFrame[banner="true"] {{
    background: #3d3524;
    border: 1px solid {WARN};
    border-radius: 8px;
}}
QLabel[heading="true"] {{ font-size: {HEADING_PX}px; font-weight: bold; color: {TEXT_STRONG}; }}
/* Discord's section labels: small, upper, wide-tracked, muted. */
QLabel[eyebrow="true"] {{
    font-size: 15px; font-weight: bold; color: {TEXT_DIM};
    letter-spacing: 1px;
}}
QLabel[dim="true"] {{ color: {TEXT_DIM}; }}
/* PROSE IS THE ONE PLACE THIS APP IS NOT BOLD. Everything else here is
   read at a glance over a running game, where weight IS legibility — but
   the user manual is read at LENGTH, and a page of 18px bold is a wall
   whatever it says, which is the fault the manual exists to fix rather
   than to repeat. */
QLabel[prose="true"] {{ font-weight: 400; line-height: 140%; }}
/* Amber, and declared AFTER dim so it wins the cascade on a label that
   carries both: a note the user has to act on must not be the colour of
   one they can ignore. */
QLabel[warn="true"] {{ color: {WARN}; }}
QLabel[pill="true"] {{
    background: {BG_INPUT}; border: 1px solid {BORDER};
    border-radius: 9px; padding: 2px 9px; color: {TEXT_DIM};
}}
/* No box at all: used where a pill would be a badge for nothing being
   wrong, and where its border made a toolbar taller than the row it sits
   in. */
QLabel[pill="quiet"] {{
    background: transparent; border: none; padding: 0 2px;
    color: {TEXT_DIM};
}}
QLabel[pill="warn"] {{
    background: #3d3524; border: 1px solid {WARN};
    border-radius: 9px; padding: 2px 9px; color: {WARN};
}}
QLabel[pill="good"] {{
    background: #1f3327; border: 1px solid {GOOD};
    border-radius: 9px; padding: 2px 9px; color: {GOOD};
}}
"""


# ---- greyscale (View ▸ Greyscale) ---------------------------------------
#
# EVERY COLOUR IS SWAPPED AT THE SOURCE rather than an effect being laid
# over the window. A `QGraphicsEffect` on the shell would catch anything
# added later and costs an offscreen re-render of the WHOLE window on
# every repaint — four times a second, over a frameless translucent
# always-on-top window, which is the exact family of Qt trap this file's
# neighbours keep a list of. Swapping the palette costs nothing per
# frame and is testable.
#
# The true palette is captured ONCE at import so the switch goes both
# ways without a reload.
_COLOURS = tuple(name for name, value in list(globals().items())
                 if isinstance(value, str) and value.startswith("#")
                 and len(value) == 7)
_TRUE = {name: globals()[name] for name in _COLOURS}

GREYSCALE = False

# Where the generated tick lives once something has asked for it. Empty
# until then, so the stylesheet is valid with or without the file.
TICK_URL = ""

# TWO COLOURS ARE NOT DESATURATED BY LUMINANCE, because that is exactly
# what makes them useless: #23a55a and #f23f43 — the green and red every
# signed number in this app is printed in — both land on a mid grey
# about four points apart, so +6.4 and -6.4 would read identically.
# "Keep good/bad readable in grey" was the user's call, so good becomes
# the BRIGHTEST text and bad a muted one: on a dark ground, bright means
# good and quiet means bad, which survives having no hue at all.
# They must stay well apart from each other AND readable on the content
# grey — a dark grey would be the honest desaturation of a red and
# unreadable on this background.
# TRUE greys, not the app's near-white and dim text, which both carry a
# slight blue tint — in a palette that has had every other colour taken
# out, the two figures the eye goes to first must not be the only things
# left with a hue.
GREY_OVERRIDES = {"GOOD": "#f2f2f2", "BAD": "#8e8e8e"}


def _luma(colour: str) -> str:
    """One hex colour as its own brightness, by Rec. 601 luma.

    Not a plain mean of the channels: the eye is far more sensitive to
    green than to blue, so averaging turns a mid green and a mid blue
    into visibly different greys from the ones they read as.
    """
    red, green, blue = (int(colour[i:i + 2], 16) for i in (1, 3, 5))
    grey = round(0.299 * red + 0.587 * green + 0.114 * blue)
    grey = max(0, min(255, grey))
    return f"#{grey:02x}{grey:02x}{grey:02x}"


def greyed_hex(colour: str) -> str:
    """One hex colour as its own brightness. For callers outside this
    module that hold a colour of their own — `ornate`'s frame shadow."""
    return _luma(colour)


def _grey_every_literal(sheet: str) -> str:
    """Desaturate the hex literals written INTO the stylesheet.

    Most of it reads the constants above, but a handful of rules carry
    their own colour — the tinted grounds behind the warning and "good"
    pills, for instance. Sweeping the built string catches those and
    anything added later without a list anybody has to maintain, which
    is the same argument `DEFAULTS` being the write filter makes.
    """
    import re
    return re.sub(r"#[0-9a-fA-F]{6}\b",
                  lambda found: _luma(found.group(0).lower()), sheet)


def set_greyscale(on: bool) -> None:
    """Swap the whole palette to grey, or back.

    Reassigns the module's own colour names, so every widget that reads
    `theme.X` AT CALL TIME follows — which is nearly all of them, and is
    why this file's colours are read that way rather than captured into
    locals. The caller re-applies `STYLESHEET` and clears the picture
    caches; this only decides what the colours are.
    """
    global GREYSCALE, STYLESHEET
    on = bool(on)
    for name, true in _TRUE.items():
        globals()[name] = (GREY_OVERRIDES.get(name) or _luma(true)) if on \
            else true
    GREYSCALE = on
    sheet = _build_stylesheet()
    STYLESHEET = _grey_every_literal(sheet) if on else sheet


STYLESHEET = _build_stylesheet()


def greyed(pixmap):
    """One picture with its colour taken out, alpha kept.

    THE ARTWORK HAS TO FOLLOW THE PALETTE or "greyscale" means "grey
    chrome round full-colour hero portraits", which is most of the
    screen still in colour.

    Alpha is the whole difficulty: `Format_Grayscale8` has no alpha
    channel, so converting straight to it and back leaves every item
    icon on an opaque black square. The alpha is lifted off the original
    and put back afterwards.

    Qt is imported INSIDE the function deliberately. This module is
    otherwise pure strings and numbers, and it is imported by things
    that have no business needing a GUI — and touching QPixmap before a
    QApplication exists does not raise, it ABORTS the process.
    """
    from PyQt6.QtGui import QImage, QPixmap

    if pixmap is None or pixmap.isNull():
        return pixmap
    source = pixmap.toImage().convertToFormat(QImage.Format.Format_ARGB32)
    grey = (source.convertToFormat(QImage.Format.Format_Grayscale8)
            .convertToFormat(QImage.Format.Format_ARGB32))
    grey.setAlphaChannel(
        source.convertToFormat(QImage.Format.Format_Alpha8))
    return QPixmap.fromImage(grey)


def install_tick(path) -> None:
    """Render the app's tick to `path` and point the menus at it.

    CALLED AFTER THE QApplication EXISTS and never at import: this
    reaches a QPixmap, and touching one before the application is
    constructed does not raise, it ABORTS the process — the trap
    `appicon.gui_ready` carries the same note about.

    The caller re-applies `STYLESHEET` afterwards. Never fatal: if the
    file cannot be written the menus keep an outlined box with no mark
    in it, which is what they had before.
    """
    global TICK_URL, STYLESHEET
    from pathlib import Path

    try:
        from .chrome import tick_pixmap
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        if not tick_pixmap().save(str(target), "PNG"):
            return
    except Exception:               # noqa: BLE001 - a mark, not the app
        return
    # Forward slashes: a Qt stylesheet url() takes them on every
    # platform, and a Windows backslash is an escape inside one.
    TICK_URL = f"image: url({target.as_posix()});"
    sheet = _build_stylesheet()
    STYLESHEET = _grey_every_literal(sheet) if GREYSCALE else sheet
