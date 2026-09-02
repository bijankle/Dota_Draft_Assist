"""Application palette and stylesheet.

One dark theme, chosen because the app is read at a glance while a draft
timer runs: high contrast for the numbers that matter, muted chrome for
everything else, and colour reserved for meaning (good/bad deltas, severity,
warnings) rather than decoration.
"""

BG = "#15181d"
BG_ELEVATED = "#1c2027"
BG_INPUT = "#232833"
BORDER = "#2e3542"
TEXT = "#e6e9ef"
TEXT_DIM = "#98a2b3"
ACCENT = "#4f8cc9"
GOOD = "#5fbf7f"
BAD = "#e06c6c"
WARN = "#e0a955"
ROW_ALT = "#191d24"
HIGHLIGHT_ROW = "#1e3a2a"

STYLESHEET = f"""
QWidget {{
    background: {BG};
    color: {TEXT};
    font-family: "Segoe UI", "Inter", system-ui, sans-serif;
    font-size: 13px;
}}
QMainWindow::separator {{ background: {BORDER}; width: 1px; height: 1px; }}

QMenuBar {{ background: {BG_ELEVATED}; border-bottom: 1px solid {BORDER}; }}
QMenuBar::item {{ padding: 6px 12px; background: transparent; }}
QMenuBar::item:selected {{ background: {BG_INPUT}; }}
QMenu {{ background: {BG_ELEVATED}; border: 1px solid {BORDER}; padding: 4px; }}
QMenu::item {{ padding: 6px 24px 6px 12px; }}
QMenu::item:selected {{ background: {ACCENT}; color: #ffffff; }}
QMenu::separator {{ height: 1px; background: {BORDER}; margin: 4px 8px; }}

QToolBar {{
    background: {BG_ELEVATED};
    border-bottom: 1px solid {BORDER};
    padding: 6px;
    spacing: 8px;
}}

QTabWidget::pane {{ border: none; background: {BG}; }}
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
    border: 1px solid {BORDER};
    border-radius: 5px;
    padding: 6px 12px;
}}
QPushButton:hover {{ border-color: {ACCENT}; }}
QPushButton:pressed {{ background: {BORDER}; }}
QPushButton:disabled {{ color: #5b6472; background: {BG_ELEVATED}; }}
QPushButton[accent="true"] {{
    background: {ACCENT}; border-color: {ACCENT}; color: #ffffff;
    font-weight: 600;
}}
QPushButton[accent="true"]:hover {{ background: #5f9cd9; }}
QPushButton[slot="true"] {{ text-align: left; padding: 8px 10px; }}

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
    background: #39414f; border-radius: 5px; min-height: 28px;
}}
QScrollBar::handle:vertical:hover {{ background: #4a5464; }}
QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; width: 0; }}
QScrollBar:horizontal {{ background: transparent; height: 11px; }}
QScrollBar::handle:horizontal {{ background: #39414f; border-radius: 5px; }}

QStatusBar {{ background: {BG_ELEVATED}; border-top: 1px solid {BORDER}; }}
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
    background: #2a2318;
    border: 1px solid {WARN};
    border-radius: 8px;
}}
QLabel[heading="true"] {{ font-size: 15px; font-weight: 600; }}
QLabel[dim="true"] {{ color: {TEXT_DIM}; }}
QLabel[pill="true"] {{
    background: {BG_INPUT}; border: 1px solid {BORDER};
    border-radius: 9px; padding: 2px 9px; color: {TEXT_DIM};
}}
QLabel[pill="warn"] {{
    background: #33291a; border: 1px solid {WARN};
    border-radius: 9px; padding: 2px 9px; color: {WARN};
}}
QLabel[pill="good"] {{
    background: #1b2f22; border: 1px solid {GOOD};
    border-radius: 9px; padding: 2px 9px; color: {GOOD};
}}
"""
