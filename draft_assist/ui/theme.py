"""Application palette and stylesheet — Discord's dark theme.

Deliberately borrowed rather than invented: the app is read at a glance
while a draft timer runs, and a palette the user already reads fluently
every day costs no attention to parse. Discord's greys are also unusually
well tuned for exactly this job — a dense dark surface where the only
saturated colour is meaning.

Colour is reserved for meaning: green and red for signed deltas, blurple
for the one action a screen wants, amber for warnings. Everything else is
grey, so a number in colour is always worth reading.
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
ACCENT = "#5865f2"        # blurple
ACCENT_HOVER = "#4752c4"
GOOD = "#23a55a"
BAD = "#f23f43"
WARN = "#f0b232"
ROW_ALT = "#2e3035"
HIGHLIGHT_ROW = "#28352c"
# Discord ships "gg sans"; anyone who has the client has it installed.
FONT_STACK = '"gg sans", "Noto Sans", "Inter", "Segoe UI", system-ui, sans-serif'

STYLESHEET = f"""
QWidget {{
    background: {BG};
    color: {TEXT};
    font-family: {FONT_STACK};
    font-size: 13px;
}}
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

QTabWidget::pane {{ border: none; background: {BG}; }}
QTabBar {{ background: {BG_DEEP}; }}
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
QCheckBox {{ spacing: 7px; }}
QCheckBox::indicator {{
    width: 15px; height: 15px; border-radius: 3px;
    border: 1px solid {BORDER}; background: {BG_INPUT};
}}
QCheckBox::indicator:checked {{ background: {ACCENT}; border-color: {ACCENT}; }}

QTableWidget {{
    background: {BG};
    alternate-background-color: {ROW_ALT};
    gridline-color: transparent;
    border: 1px solid {BORDER};
    border-radius: 6px;
    selection-background-color: {ACCENT};
    selection-color: #ffffff;
}}
QHeaderView::section {{
    background: {BG_ELEVATED};
    color: {TEXT_DIM};
    padding: 7px 8px;
    border: none;
    border-bottom: 1px solid {BORDER};
    font-weight: 600;
}}
QTableWidget::item {{ padding: 5px 8px; }}

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

QStatusBar {{ background: {BG_DEEP}; border-top: 1px solid {BG_DEEP}; }}
QStatusBar::item {{ border: none; }}

QProgressBar {{
    background: {BG_INPUT}; border: 1px solid {BORDER};
    border-radius: 5px; height: 8px; text-align: center;
}}
QProgressBar::chunk {{ background: {ACCENT}; border-radius: 4px; }}

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
QLabel[heading="true"] {{ font-size: 15px; font-weight: 600; color: {TEXT_STRONG}; }}
/* Discord's section labels: small, upper, wide-tracked, muted. */
QLabel[eyebrow="true"] {{
    font-size: 11px; font-weight: 700; color: {TEXT_DIM};
    letter-spacing: 1px;
}}
QLabel[dim="true"] {{ color: {TEXT_DIM}; }}
QLabel[pill="true"] {{
    background: {BG_INPUT}; border: 1px solid {BORDER};
    border-radius: 9px; padding: 2px 9px; color: {TEXT_DIM};
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
