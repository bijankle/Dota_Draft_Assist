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
ACCENT = "#b5342c"        # deep vermilion; see the note above
ACCENT_HOVER = "#95271f"
GOOD = "#23a55a"
BAD = "#f23f43"
WARN = "#f0b232"
ROW_ALT = "#2e3035"
# The window frame's lit edge (see `ui/ornate.py`), so the app's name and
# the border round it read as one piece rather than two decisions.
FRAME_GOLD = "#c9a45a"
# The hairline between one control and the next, at the user's request:
# "right in the middle" of white and black, which is exactly #808080. It
# is deliberately NOT one of the greys above — those are surfaces and
# text, and a rule is neither; it has to read on the dark band and on the
# card alike.
RULE = "#808080"
# The card and team headings — "Radiant", "Suggested picks".
HEADING_PX = 21
# The body, and with it every signed number in the app: the grids print
# their deltas at this size, so the figure on a portrait is set from the
# same value rather than from one that happens to match today.
BODY_PX = 18

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

STYLESHEET = f"""
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
QMainWindow::separator {{ background: {BORDER}; width: 1px; height: 1px; }}

QMenuBar {{ background: {BG_DEEP}; border-bottom: 1px solid {BG_DEEP}; }}
QMenuBar::item {{ padding: 6px 12px; background: transparent; }}
QMenuBar::item:selected {{ background: {BG_INPUT}; }}
QMenu {{ background: {BG_ELEVATED}; border: 1px solid {BORDER}; padding: 4px; }}
QMenu::item {{ padding: 6px 24px 6px 12px; }}
QMenu::item:selected {{ background: {ACCENT}; color: #ffffff; }}
QMenu::separator {{ height: 1px; background: {BORDER}; margin: 4px 8px; }}

QToolBar {{
    background: {BG_DEEP};
    border-bottom: 1px solid {BORDER};
    padding: 6px;
    spacing: 8px;
}}
/* On the tab strip it is part of the strip, not a band above it. */
QToolBar#tabStripTools {{
    background: {BG_DEEP}; border: none; padding: 0 2px; spacing: 8px;
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
QToolBar#tabStripTools QPushButton {{
    background: transparent; border: none;
    padding: 8px 18px; color: {TEXT_DIM}; font-weight: bold;
}}
QToolBar#tabStripTools QPushButton:hover {{
    background: transparent; border: none; color: {TEXT};
}}
QToolBar#tabStripTools QPushButton:pressed {{
    background: transparent; border: none; color: {TEXT_STRONG};
}}
QToolBar#tabStripTools QPushButton:disabled {{
    background: transparent; color: {BORDER};
}}
QToolBar#tabStripTools QLabel,
QToolBar#tabStripTools QCheckBox {{ color: {TEXT_DIM}; }}

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
QTabBar::tab:selected {{ color: {TEXT}; border-bottom: 2px solid {ACCENT}; }}
QTabBar::tab:hover {{ color: {TEXT}; }}

QPushButton {{
    background: {BG_INPUT};
    border: 1px solid transparent;
    border-radius: 4px;
    padding: 7px 14px;
    color: {TEXT};
    font-weight: 500;
}}
QPushButton:hover {{ background: {BG_HOVER}; border-color: {BG_HOVER}; }}
QPushButton:pressed {{ background: {BG_DEEP}; }}
QPushButton:disabled {{ color: {TEXT_DIM}; background: {BG_ELEVATED}; }}
QPushButton[accent="true"] {{
    background: {ACCENT}; border-color: {ACCENT}; color: #ffffff;
    font-weight: 600;
}}
QPushButton[accent="true"]:hover {{ background: {ACCENT_HOVER}; border-color: {ACCENT_HOVER}; }}
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
    border-left: 3px solid {ACCENT}; font-weight: 600;
}}

QComboBox {{
    background: {BG_INPUT};
    border: 1px solid {BORDER};
    border-radius: 5px;
    padding: 5px 10px;
}}
QComboBox:hover {{ border-color: {ACCENT}; }}
QComboBox QAbstractItemView {{
    background: {BG_ELEVATED};
    border: 1px solid {BORDER};
    selection-background-color: {ACCENT};
}}
QSlider::groove:horizontal {{
    height: 4px; border-radius: 2px; background: {BG_INPUT};
}}
QSlider::sub-page:horizontal {{
    height: 4px; border-radius: 2px; background: {ACCENT};
}}
QSlider::handle:horizontal {{
    background: {ACCENT}; border: none; width: 12px; height: 12px;
    margin: -4px 0; border-radius: 6px;
}}
QSlider::handle:horizontal:hover {{ background: {ACCENT_HOVER}; }}

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
QSpinBox:hover {{ border-color: {ACCENT}; }}

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

QTextBrowser, QPlainTextEdit {{
    background: {BG_ELEVATED};
    border: 1px solid {BORDER};
    border-radius: 6px;
    padding: 6px;
}}
QScrollBar:vertical {{ background: transparent; width: 11px; margin: 0; }}
QScrollBar::handle:vertical {{
    background: {BG_DEEP}; border-radius: 5px; min-height: 28px;
}}
QScrollBar::handle:vertical:hover {{ background: #111214; }}
QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; width: 0; }}
QScrollBar:horizontal {{ background: transparent; height: 11px; }}
QScrollBar::handle:horizontal {{ background: {BG_DEEP}; border-radius: 5px; }}

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
QProgressBar::chunk {{ background: {ACCENT}; border-radius: 4px; }}

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
    font-family: "{TITLE_FAMILY}", {FONT_STACK};
    font-weight: 600; font-size: 25px;
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
    border-color: {ACCENT};
}}

QFrame[card="true"] {{
    background: {BG_ELEVATED};
    border: 1px solid {BORDER};
    border-radius: 8px;
}}
/* The advertising slot. It keeps its height whether or not an ad is in
   it — a banner that appears and disappears while pushing the ten picks
   up and down is a board that moves under the cursor mid-draft. */
QWidget#adSlot {{ background: transparent; border: none; }}
QLabel#adCreative {{ background: transparent; border: none; color: {TEXT_DIM}; }}
QWidget#adSlot[live="true"] QLabel#adCreative {{
    background: {BG_ELEVATED};
    border: 1px dashed {BORDER};
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
