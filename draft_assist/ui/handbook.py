"""Help ▸ User manual — everything the app used to explain in place.

Named `handbook` rather than `manual` because `ui/manual.py` was taken
years earlier by `ManualDraft`, the hand-entered picks. Two modules that
differ only by what a reader assumes "manual" means is a trap set for
the next person, and the class in that one is the older claim.

**THE EXPLANATIONS WERE SPREAD ACROSS THE APP AND NOBODY READ THEM
TWICE.** A wall of text in the first-run wizard, three sentences under
every download button, a paragraph in the update dialog and an About box
that described the product rather than the build. All of it true, all of
it read once, and all of it standing between somebody and the thing they
had come to that screen to do — the same fault the History tab's block
cards, the "this run" card and the empty-grid captions were each cut for.

So the screens keep ONE LINE — what this control does, in the fewest
words that still say it — and the detail lives here, in one place, where
somebody who wants it can read it in order. The rule for what belongs
where: a screen says what a button will DO, the manual says how the thing
WORKS and what to do when it does not.

**IT IS TEXT IN THE APP, not a page on the web**, at the user's request.
It has to answer a question about an app whose commonest fault is having
no connection, and a manual you cannot open without one would be missing
exactly when it is needed.

The section list down the left is `SectionBar`, the History tab's own —
one implementation of "a list of anchors that scrolls the page beside
it", because two would drift apart.
"""

from __future__ import annotations

from PyQt6.QtCore import QPoint, Qt
from PyQt6.QtWidgets import (QDialog, QFrame, QHBoxLayout, QLabel,
                             QScrollArea, QVBoxLayout, QWidget)

from . import theme
from .section_bar import SectionBar, edge

# A section is (ident, title, blocks); a block is a paragraph, or a list
# of bullets, or a ("term", "meaning") pair drawn as a small table row.
# Content in ONE structure so the contents list and the page cannot
# disagree about what is in the manual or what order it is in.
SECTIONS: tuple = (
    ("what", "What this is", (
        "A drafting assistant for Ranked All Pick. It reads the ten picks "
        "out of the Dota 2 window, scores every hero against the draft on "
        "screen, and flags the items that answer what the other side has "
        "taken.",
        "Everything it says is measured from real match statistics for the "
        "ranks you choose, with one exception that is always labelled: the "
        "item flags are hand-authored rules rather than measurements.",
        ("bullets", (
            "It never injects code into Dota, reads its memory, or sends "
            "it input. It reads the game's own published data and pixels "
            "from a window already on your screen.",
            "It makes no network call while a draft is running. "
            "Statistics are downloaded when you ask for them and cached.",
            "Nothing about you or your games is uploaded anywhere.",
        )),
    )),
    ("score", "The score", (
        "The number on a hero is DRAFT FIT: what the ten heroes on the "
        "board do to that hero. Zero means this draft neither helps nor "
        "hurts it.",
        "The hero's own win rate is deliberately not in that number. "
        "Adding it would float the strongest heroes to the top of every "
        "list whatever the draft, which is the one thing the list is not "
        "for. It is shown beside the score, labelled as not scored.",
        "Every number in the app reads from your team's point of view: "
        "positive is good for you, whichever portrait it sits under. The "
        "one exception is the synergy card, where each triangle is read "
        "as \"how well does this team's pair work\" — so a big green "
        "number in the enemy triangle is bad for you.",
    )),
    ("setup", "Setting up", (
        "The app opens a setup dialog the first time it runs, and asks "
        "for two things.",
        ("terms", (
            ("A Stratz API key",
             "Free, from stratz.com/api. It is what pulls hero "
             "statistics. It is stored in a file called .env beside the "
             "app, never leaves your machine, and no update replaces it. "
             "You can skip it and add it later from the banner."),
            ("Which ranks",
             "Hero win rates and matchups differ by rank. The default is "
             "Ancient and Divine combined — about one bracket above "
             "Legend — because pulling from just above where you play "
             "tilts the advice toward the games you are trying to win. "
             "Change it in Settings ▸ Downloads."),
        )),
        "Finishing downloads the statistics and the artwork. The artwork "
        "is 126 hero portraits and about 500 item icons; it needs no "
        "account of any kind and takes a few minutes.",
        "Game data is set up separately, in Settings ▸ Game data. See "
        "\"Where the picks come from\" below.",
    )),
    ("draft", "The Draft tab", (
        "It reads top to bottom as one argument: the board, then which "
        "hero to take, then what to build.",
        ("terms", (
            ("The ten picks",
             "Radiant on the left, Dire on the right, the way they sit "
             "on Dota's own pick bar. Each tile carries what that hero "
             "is worth overall. A \"+\" is a slot nothing has filled."),
            ("Suggested picks",
             "The ranked list cut to its head: best draft fit on the "
             "left. It stays blank until a hero is on the board, "
             "because with an empty draft every fit is zero. Clicking "
             "one measures the whole board against it; it does not "
             "enter it."),
            ("A gold star on a suggestion",
             "A hero the last History run says you play a lot and win "
             "on. It follows whichever account is loaded on that tab, "
             "and the two bars it has to clear are yours to set in "
             "Settings \u25b8 General \u2014 top X% by picks and top Y% by "
             "win rate, ranked against the heroes in that run. Hover it "
             "for the games and the rate behind it, each with where it "
             "stands among the heroes you played."),
            ("Items",
             "Hand-authored rules against what the enemy has taken, "
             "ordered by severity. Silence is a real answer — many "
             "drafts flag nothing urgent."),
            ("Counters and Synergies",
             "The pairwise numbers behind the totals. A comfortable "
             "total can hide one lane losing badly, which is what these "
             "are for. Synergy is one square holding both teams: yours "
             "in the lower left against the portraits along the bottom, "
             "theirs in the upper right against the portraits along the "
             "top."),
        )),
        "Click a pick to see it one row at a time — that hero's synergy "
        "with its own side and its matchups against the other. Click it "
        "again to clear.",
        ("bullets", (
            "Click an empty slot to enter a hero by hand.",
            "Right-click a tile to change it, clear it, move it across, "
            "name it as your own pick, or set its role.",
            "Drag a tile onto the other team to exchange two heroes; "
            "drag within a team to swap two positions.",
            "Clear all wipes everything you told the app about this "
            "match and blanks the board. Detect all reads the screen "
            "again from scratch.",
        )),
        "Roles are per SLOT rather than per hero, because a slot is a "
        "lane. Your own hero's role is what filters the item advice.",
    )),
    ("reading", "Reading picks", (
        "Two sources, because measurement showed neither is enough alone. "
        "Both are on by default, and turning one off is a debugging step.",
        ("terms", (
            ("Game data (GSI)",
             "Dota's own channel. It reports the phase and who you are, "
             "which is what tells the app a draft is happening — but "
             "during hero selection it names no hero but your own. From "
             "strategy time onward it carries all ten."),
            ("The screen",
             "The picks themselves, recognised from the Dota window "
             "during the draft, which is the only place they exist "
             "while there is still a pick to make."),
        )),
        "Precedence is strict: what the game reports beats the screen, "
        "which beats what you entered by hand. A slot nothing resolved "
        "stays unknown rather than being guessed at.",
        "Setting up game data is Settings ▸ Game data: it writes a config "
        "file into your Dota install, and Dota needs the launch option "
        "-gamestateintegration, which is the step everyone forgets. "
        "Diagnose game data names the one link that is broken rather than "
        "handing you the whole checklist.",
        "Recognition needs to know where the portraits are on your "
        "screen, and it works that out by itself. The pick slots are "
        "fractions of Dota's 16:9 HUD area rather than pixels, so one "
        "set of numbers is right at every resolution the maths can "
        "predict — and where it is not, the app measures the real "
        "geometry off your own screen: at strategy time the game names "
        "all ten heroes in the frame it is holding, so it can hunt for "
        "those ten portraits and read the positions and sizes off where "
        "it finds them. What it measures is saved and used from then on.",
        "Dota has to be in Borderless or Windowed for any of it, because "
        "measuring takes a picture of the window and an "
        "exclusive-fullscreen game cannot be captured. If the app says "
        "it cannot find the pick portraits, the banner's button measures "
        "them again; the numbers themselves are shown in Settings ▸ "
        "Debug ▸ Live, where a bad reading can be diagnosed. There is "
        "nothing to drag: drawing the boxes by hand was how this worked "
        "before it could measure, and it has been removed.",
    )),
    ("analysis", "The History tab", (
        "This is about your own match history rather than the game on "
        "screen: across a few hundred of your own games, what actually "
        "goes with winning.",
        "Enter your Dota friend ID and press Run. A display name will not "
        "do — that search times out more often than it answers. The run "
        "is cached, so opening the tab later shows it again without "
        "measuring anything; Update re-fetches.",
        ("terms", (
            ("The sidebar",
             "Every section, always in the same order, most actionable "
             "first. Click one to jump to it. The tick box on the row "
             "is what turns that section on and off."),
            ("Win rate",
             "One line per section carrying its best and its worst on a "
             "0 to 100% scale, so the distance between the two dots is "
             "the size of the effect and means the same thing on every "
             "row. The grey dot is your own overall rate."),
            ("Impact",
             "The same shape for hero damage per minute, KDA and siege "
             "damage per minute — damage to buildings. These keep their "
             "own range, because there is no 100 to scale an average "
             "against."),
            ("Each section's table",
             "A cut and a sort, which are two different questions: how "
             "many rows to keep and what ranks them, above the table; "
             "and the column headings, which re-order what survived."),
        )),
        "Rows with too few games behind them are muted and sink to the "
        "bottom whichever way you sort. A bucket of two games at 100% is "
        "noise wearing a number.",
        "Read every finding as a hypothesis to test against your next "
        "hundred games, not a conclusion. A dozen splits run at once, so "
        "some will clear any bar by chance alone.",
        "Export writes a workbook: every match on one sheet under a "
        "filter, the whole report on the other.",
    )),
    ("settings", "Settings", (
        "File ▸ Settings, and everything that is not a live control lives "
        "in one of its tabs.",
        ("terms", (
            ("General", "How the app behaves, and how often it reminds "
                        "you that the statistics are getting old."),
            ("Downloads", "The rank brackets, and every artwork and "
                          "statistics download as its own button."),
            ("Game data", "Installing Dota's config file, and Diagnose."),
            ("Appearance", "The app icon."),
            ("Advanced", "Which site supplies the pairwise numbers, and "
                         "the capture sources."),
            ("Debug", "What the app is reading right now, the "
                      "recognition log, loop timings, and Copy "
                      "everything — which is the one thing worth "
                      "pasting when something is wrong."),
        )),
        "It applies as you go: there is no OK button, and closing it "
        "keeps whatever you changed.",
        "View holds the two things tuned by eye — transparency and the "
        "size of portraits and numbers. Help ▸ Search (Ctrl+K) finds any "
        "of it by whatever you call it rather than by its menu name.",
    )),
    ("update", "Updating", (
        "Help ▸ Update application. It fetches the new code, then closes "
        "and reopens the app.",
        "There are two kinds of install and the button works on both: a "
        "git clone is updated by git, and a copy unzipped from GitHub "
        "downloads the current release and writes the files out.",
        "An update can only ever write files that are in the repository, "
        "so nothing of yours is touched: your key, your settings, your "
        "calibration, your cached runs and every downloaded picture are "
        "all outside it.",
        "The update is the code alone and takes seconds. Artwork and "
        "statistics are their own buttons, and the banner at the top of "
        "the window offers whichever of them is actually missing.",
    )),
    ("wrong", "Troubleshooting", (
        ("terms", (
            ("\"No data from Dota\"",
             "Settings ▸ Game data ▸ Diagnose. It names the first "
             "broken link and its fix. The usual answer is the "
             "-gamestateintegration launch option."),
            ("The board is wrong or empty mid-draft",
             "Press Detect all to read the screen again. If the tiles "
             "are on the wrong side, drag one across — it exchanges. If "
             "recognition is finding nothing at all, the pick boxes are "
             "probably off the portraits: the banner at the top says so "
             "and its button measures them again, with Dota open."),
            ("Blank tiles or item names instead of pictures",
             "The artwork is not downloaded. Settings ▸ Downloads ▸ All "
             "artwork; it skips what is already there. An item that "
             "still draws its name is one the rules name and the "
             "download could not find."),
            ("The History tab finds no matches",
             "Either Expose Public Match Data is off in Dota's "
             "settings, or the ID is not the one you meant. The tab "
             "says which."),
            ("The taskbar button is blank, or says Python",
             "Windows builds a pinned button from a Start-menu shortcut, "
             "which the app writes at every start. Nothing can pin on "
             "your behalf — Windows removed that verb — so unpin what is "
             "there, restart, and pin it again: a pin keeps whatever "
             "identity it was made with."),
            ("The numbers look like the wrong rank",
             "Changing the bracket invalidates the cache. The banner "
             "says so; press its button to pull the new ones."),
            ("Anything else",
             "Settings ▸ Debug ▸ Copy everything puts the status line, "
             "what the app is reading, the recognition log and the loop "
             "timings on the clipboard in one paste."),
        )),
    )),
    ("files", "Your files", (
        "Everything the app keeps about you stays in its own folder and "
        "none of it is in the repository, so a copy of this app handed to "
        "somebody else carries none of it.",
        ("terms", (
            (".env", "Your Stratz API key."),
            ("ui_settings.json", "Every setting and window size."),
            ("preferences.json", "Rank brackets and the statistics "
                                 "source."),
            ("calibration_local.json", "Where the pick portraits are on "
                                       "your screen."),
            ("history_accounts.json", "The accounts the History tab "
                                      "remembers."),
            ("history_cache/", "Your cached Analysis runs."),
            ("data_cache/", "Downloaded hero statistics."),
            ("assets/", "Downloaded portraits and item icons. "
                        "Alternative portraits are filed under "
                        "portraits/variants in a folder named for the "
                        "hero's numeric id, so that folder looks empty "
                        "until you open one."),
            ("recordings/", "Sessions recorded from the Record button."),
        )),
    )),
)


def _paragraph(text: str, dim: bool = False) -> QLabel:
    label = QLabel(text)
    label.setWordWrap(True)
    label.setProperty("prose", True)
    label.setTextInteractionFlags(
        Qt.TextInteractionFlag.TextSelectableByMouse)
    if dim:
        label.setProperty("dim", True)
    return label


def _bullet(text: str) -> QWidget:
    """A bullet whose second line lines up under its first.

    A "•  " typed into the label puts the wrap back at the margin, so a
    three-line bullet reads as a paragraph with a dot on it.
    """
    row = QWidget()
    # A PLAIN QWidget PAINTS THE CONTENT COLOUR. On a card, which is
    # darker, that is a lighter box round every bullet — the same trap
    # the app-wide "a QLabel is transparent" rule exists for, one widget
    # up. Worth a line here rather than a rule in the theme, since this
    # is the only bare container the manual builds.
    row.setStyleSheet("background: transparent;")
    lay = QHBoxLayout(row)
    lay.setContentsMargins(8, 0, 0, 0)
    lay.setSpacing(8)
    dot = QLabel("•")
    dot.setProperty("dim", True)
    dot.setAlignment(Qt.AlignmentFlag.AlignTop)
    lay.addWidget(dot)
    lay.addWidget(_paragraph(text, dim=True), 1)
    return row


class ManualWindow(QDialog):
    """The manual: sections down the left, the text beside them."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Dota Draft Assist — User manual")
        self.resize(940, 720)
        self.setMinimumSize(620, 420)
        self._anchors: dict[str, QWidget] = {}

        outer = QHBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        self.sections = SectionBar()
        self.sections.jumped.connect(self._jump_to)
        outer.addWidget(self.sections)
        outer.addWidget(edge())

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.page = QWidget()
        self.body = QVBoxLayout(self.page)
        self.body.setContentsMargins(20, 16, 20, 24)
        self.body.setSpacing(10)
        self.scroll.setWidget(self.page)
        outer.addWidget(self.scroll, 1)

        for ident, title, blocks in SECTIONS:
            self.sections.add(ident, title)
            self._anchors[ident] = self._section(title, blocks)
        self.sections.set_reachable([ident for ident, _, _ in SECTIONS])
        self.sections.light(SECTIONS[0][0])
        self.body.addStretch(1)
        self.scroll.verticalScrollBar().valueChanged.connect(self._spy)

    # ---- building ------------------------------------------------------
    def _section(self, title: str, blocks) -> QWidget:
        card = QFrame()
        card.setProperty("card", True)
        lay = QVBoxLayout(card)
        lay.setSpacing(8)
        heading = QLabel(title)
        heading.setProperty("heading", True)
        lay.addWidget(heading)
        for block in blocks:
            if isinstance(block, str):
                lay.addWidget(_paragraph(block))
            elif block[0] == "bullets":
                for line in block[1]:
                    lay.addWidget(_bullet(line))
            elif block[0] == "terms":
                for term, meaning in block[1]:
                    name = QLabel(term)
                    name.setStyleSheet(
                        f"color: {theme.TEXT}; background: transparent;")
                    lay.addWidget(name)
                    body = _paragraph(meaning, dim=True)
                    body.setContentsMargins(16, 0, 0, 6)
                    lay.addWidget(body)
        self.body.addWidget(card)
        return card

    # ---- the sidebar ---------------------------------------------------
    def _jump_to(self, ident: str) -> None:
        widget = self._anchors.get(ident)
        if widget is None:
            return
        layout = self.page.layout()
        if layout is not None:
            layout.activate()
        bar = self.scroll.verticalScrollBar()
        bar.setValue(max(0, widget.mapTo(self.page, QPoint(0, 0)).y() - 8))
        self.sections.light(ident)

    def _spy(self) -> None:
        """Light whichever section the reader is actually looking at.

        Ranked by MEASURED position rather than by the order they were
        added, for the reason the History tab's own spy is: the two
        agree today, and a highlight that quietly lies the day they stop
        agreeing is worse than one that costs a sort.
        """
        top = self.scroll.verticalScrollBar().value()
        seen = sorted(
            ((widget.mapTo(self.page, QPoint(0, 0)).y(), ident)
             for ident, widget in self._anchors.items()),
            key=lambda pair: pair[0])
        current = seen[0][1] if seen else None
        for y, ident in seen:
            if y <= top + 24:
                current = ident
        self.sections.light(current)

    def show_section(self, ident: str) -> None:
        """Open at a named section — what Help ▸ Search jumps to."""
        self.show()
        self.raise_()
        self.activateWindow()
        self._jump_to(ident)
