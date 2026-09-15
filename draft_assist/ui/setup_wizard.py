"""First-run setup: one step at a time, in the order they have to happen.

**IT IS A STEPPED INSTALLER, NOT A FORM**, at the user's request: "i
think its nicer to have the step by step process be a forced step by
step like your typical install windows steps, and the bookmarks bar on
the left is just showing where your progress sits, so you knwo all the
steps in the setup and where you are at currently."

What it replaced was three cards stacked on one scrolling page. That
shape asks for everything at once, which is fine when you already know
what all of it is for and useless on the run that matters — the first
one. Four questions on four pages, each with the one control it is
about, is the same information with somewhere to stand.

**EVERY STEP SAYS HOW AND WHY**, also at the user's request: "a concise
window askign for something e.g. Stratz key and then below that it says
how to get the key (with a link to the appropriate website) and then
'why this step is important' where the details of how this step enables
a particular aspect of the program in nice concise terms". So `Step`
carries `how` and `why` as data and the page renders them, which is what
lets a test hold both to a length — prose grows back, and this dialog
has been cut down for that reason once already.

**THE SIDEBAR IS `SectionBar`**, the History tab's own, because two
implementations of "a list of places down the left, with the one you are
on lit" would drift. Here it is a progress bar rather than a switchboard:
a step you have reached is reachable and can be gone back to, a step
ahead of you is dim and cannot be jumped to. That is what makes the
order forced.

**THE DOTA LAUNCH OPTION IS LAST**, at the user's request — "i thnik its
best to have the steam -gamestateintegratio nstep to be last as its
annoying (iisnt a click 'run' type step)". Everything before it is
typing or ticking in this window; that one sends you into another
program. It is also the only step the app cannot do any part of for you,
which is the same fact from the other side.

**A SKIPPED STEP IS REMEMBERED, NOT LOST** (`ui_settings.setup_pending`).
Skip this step moves on and writes the step's name down; the main
window's banner then names what is outstanding and opens this again at
it. Nobody offline, or who wants a look before signing up for anything,
should meet a wall — and nothing should quietly stay undone either.

**THE KEY IS CHECKED BEFORE IT IS TRUSTED** (`stratz.check_key`). A typo
accepted here surfaces three minutes later as a failure inside a progress
dialog, which reads as the app being broken rather than as a bad paste.
But a check that could not be MADE — rate limit, no connection — never
blocks: `KeyCheck.ok` is three-valued, and only an outright rejection
stops you moving on.
"""

import webbrowser
from dataclasses import dataclass, field

from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtGui import QGuiApplication
from PyQt6.QtWidgets import (QApplication, QCheckBox, QDialog, QFrame,
                             QGridLayout, QHBoxLayout, QLabel, QLineEdit,
                             QPushButton, QScrollArea, QStackedWidget,
                             QVBoxLayout, QWidget)

from ..config import (ALL_BRACKETS, DEFAULT_TARGET_BRACKETS, has_stratz_key,
                      save_stratz_key, save_target_brackets, target_brackets)
from ..gsi import install as gsi_install
from ..history import account as account_mod
from . import section_bar

KEY_URL = "https://stratz.com/api"

# Two adjacent brackets, because that roughly doubles the sample for a
# metagame difference smaller than the noise it removes — the same
# reasoning `BracketDialog` states at greater length.
PRESETS = [
    ("Herald – Crusader", ("HERALD", "GUARDIAN", "CRUSADER")),
    ("Archon – Legend", ("ARCHON", "LEGEND")),
    ("Legend – Ancient", ("LEGEND", "ANCIENT")),
    ("Ancient – Divine", ("ANCIENT", "DIVINE")),
    ("Divine – Immortal", ("DIVINE", "IMMORTAL")),
]


@dataclass(frozen=True)
class Step:
    """One page: what it asks, how to answer it, and what it buys.

    `how` and `why` are DATA rather than widgets built inline, so a test
    can hold every one of them to a length. This dialog was four
    paragraphs about where statistics come from before it was cut back,
    and prose grows back.
    """
    ident: str
    label: str                  # the sidebar row; it is 178px wide
    title: str
    how: str
    why: str
    link: tuple = ()            # (button text, url), optional


STEPS: tuple = (
    Step(
        "key", "Stratz key", "Your Stratz API key",
        how="Sign in with Steam at stratz.com/api and copy the key it "
            "shows you. It is free and takes about a minute.",
        why="Every win rate, matchup and synergy number in the app is "
            "built from Stratz. Without a key the app opens and the "
            "draft board works, but there is nothing to score it with.",
        link=("Open stratz.com/api", KEY_URL)),
    Step(
        "ranks", "Ranks", "Which ranks the advice describes",
        how="Tick the bracket you play in, or one above it if you are "
            "climbing. Two adjacent brackets are combined.",
        why="Heroes perform differently at different ranks, so the "
            "matrices are BUILT for the ranks you choose here. Two "
            "brackets together roughly double the sample."),
    Step(
        "account", "Your account", "Your Dota friend ID",
        how=account_mod.IN_GAME,
        why="The History tab measures your own matches — what you win "
            "on, when you play worst, which items go with winning — and "
            "stars the suggestions you already play well."),
    Step(
        "gsi", "Dota's feed", "Letting Dota tell the app about the draft",
        how="The app writes Dota's config file for you when you "
            "finish. The steps above are the part no program can do.",
        why="It is how the app knows a draft has started and which side "
            "is yours. Valve's own channel: nothing is injected into "
            "the game and no memory is read."),
)


def needed() -> bool:
    """Is there anything left for first-run setup to ask?

    Only the KEY, deliberately. Every other step has either a defensible
    default or a banner of its own, and an install that already has a key
    has been through this — so an existing install never has the wizard
    opened at it, and a fresh one sees it exactly once.
    """
    return not has_stratz_key()


class KeyWorker(QThread):
    """The key check, off the UI thread — it is a network call, and a
    dialog that stops repainting while it waits looks like a crash."""

    answered = pyqtSignal(object)

    def __init__(self, key: str, parent=None):
        super().__init__(parent)
        self.key = key

    def run(self) -> None:                          # noqa: D102 - QThread
        from ..data.stratz import check_key
        self.answered.emit(check_key(self.key))


# How much width a paragraph inside a step page actually gets: the page
# column, less its margins.
TEXT_WIDTH = 560


def paragraph(text: str, width: int = TEXT_WIDTH) -> QLabel:
    """A wrapped label that reports its own height honestly.

    A word-wrapped QLabel's size hint is a single line until something
    tells it how wide it will be, and `heightForWidth` does not propagate
    up through nested layouts — so this dialog measured every paragraph
    as one line tall and drew the long ones ON TOP of the controls
    beneath them, with the preset buttons squashed to nothing. Measuring
    the text at the width it will actually get and making that the
    minimum is the fix, and it holds at any size at or above the dialog's
    minimum because a wider label only ever needs fewer lines.
    """
    label = QLabel(text)
    label.setWordWrap(True)
    # `heightForWidth`, not a font-metrics bounding rect: the metrics
    # measure the STRING, while the label measures what it will actually
    # lay out — margins, indent and the stylesheet's font included.
    needs = label.heightForWidth(width)
    label.setMinimumHeight(max(needs, label.sizeHint().height()))
    return label


def steps_list(lines) -> QLabel:
    """A numbered procedure, which is NOT a paragraph.

    A procedure is scanned a line at a time rather than read, and each
    line is one action. Naming the launch option and leaving somebody to
    it is exactly how "add the launch option" became a thing people were
    told about and did not do.
    """
    label = QLabel("\n".join(f"{n}.  {line}"
                             for n, line in enumerate(lines, 1)))
    label.setWordWrap(True)
    label.setTextInteractionFlags(
        Qt.TextInteractionFlag.TextSelectableByMouse)
    label.setMinimumHeight(label.heightForWidth(TEXT_WIDTH))
    return label


class StepPage(QWidget):
    """One step, laid out the same way as every other one.

    Ask, then how, then why — in that order every time, so the eye knows
    where to go on the second page as well as the first. The control
    belongs to the wizard; this only decides where it sits.
    """

    def __init__(self, step: Step, parent=None):
        super().__init__(parent)
        self.setProperty("bare", True)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(10)

        title = QLabel(step.title)
        title.setProperty("heading", True)
        lay.addWidget(title)

        self.body = QVBoxLayout()
        self.body.setSpacing(8)
        lay.addLayout(self.body)

        lay.addWidget(self._card("How", step.how, step.link))
        lay.addWidget(self._card("Why this step matters", step.why))
        lay.addStretch(1)

    def _card(self, heading: str, text: str, link: tuple = ()) -> QFrame:
        frame = QFrame()
        frame.setProperty("card", True)
        inner = QVBoxLayout(frame)
        inner.setSpacing(6)
        head = QLabel(heading)
        head.setProperty("dim", True)
        inner.addWidget(head)
        inner.addWidget(paragraph(text, TEXT_WIDTH - 24))
        if link:
            text_, url = link
            row = QHBoxLayout()
            button = QPushButton(text_)
            button.clicked.connect(lambda _c, u=url: webbrowser.open(u))
            row.addWidget(button)
            row.addStretch(1)
            inner.addLayout(row)
        return frame


class SetupWizard(QDialog):
    """The stepped wizard: a sidebar of progress and one page at a time."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Set up Dota Draft Assist")
        self.checked: bool | None = None       # what check_key last said
        self.worker: KeyWorker | None = None
        self.at = 0
        # Steps left undone. Every step starts outstanding and is struck
        # off by finishing it, so closing the window half way through
        # leaves the rest on the banner rather than silently forgotten.
        self.pending: list = [step.ident for step in STEPS]
        self.reached: set = {STEPS[0].ident}
        self.account_id: int | None = None

        shell = QVBoxLayout(self)
        shell.setContentsMargins(0, 0, 0, 0)
        shell.setSpacing(0)

        across = QHBoxLayout()
        across.setContentsMargins(0, 0, 0, 0)
        across.setSpacing(0)
        self.sections = section_bar.SectionBar()
        for step in STEPS:
            self.sections.add(step.ident, step.label)
        self.sections.jumped.connect(self._jump_to)
        across.addWidget(self.sections)
        across.addWidget(section_bar.edge())

        # THE PAGE SCROLLS, THE SIDEBAR AND THE BUTTONS DO NOT. A dialog
        # is sized to its contents, and the launch-option page alone is
        # a heading, a seven-step procedure and two cards. Buttons that
        # scroll away with the content are the fault this avoids, not a
        # smaller version of it.
        self.pages = QStackedWidget()
        self.pages.setProperty("bare", True)
        for step in STEPS:
            page = StepPage(step)
            self.pages.addWidget(page)
        self._fill_pages()
        area = QScrollArea()
        area.setWidgetResizable(True)
        area.setFrameShape(QScrollArea.Shape.NoFrame)
        holder = QWidget()
        holder.setProperty("bare", True)
        inner = QVBoxLayout(holder)
        inner.setContentsMargins(18, 16, 18, 16)
        inner.addWidget(self.pages)
        area.setWidget(holder)
        across.addWidget(area, 1)
        shell.addLayout(across, 1)

        self.note = QLabel("")
        self.note.setWordWrap(True)
        self.note.setProperty("dim", True)
        self.note.setVisible(False)

        buttons = QHBoxLayout()
        buttons.setContentsMargins(18, 0, 18, 14)
        self.back = QPushButton("Back")
        self.back.clicked.connect(self._back)
        buttons.addWidget(self.back)
        # THE NOTE TAKES THE SLACK, AND A STRETCH BACKS IT UP. It is
        # hidden whenever there is nothing to say, and a hidden widget
        # contributes no stretch — so without the spacer the three
        # buttons shared the whole width and read as a tab bar rather
        # than as Back on one side and the way forward on the other.
        buttons.addWidget(self.note, 1)
        buttons.addStretch(1)
        self.skip = QPushButton("Skip this step")
        self.skip.setToolTip("It goes on the banner at the top of the "
                             "window, which opens this again here.")
        self.skip.clicked.connect(self._skip)
        buttons.addWidget(self.skip)
        self.next = QPushButton("Next")
        self.next.setProperty("accent", True)
        self.next.setDefault(True)
        self.next.clicked.connect(self._next)
        buttons.addWidget(self.next)
        shell.addLayout(buttons)

        self.resize(820, self._fitting_height())
        self._show_step(0)

    # ---- the controls each page owns -------------------------------------
    def _fill_pages(self) -> None:
        self._fill_key(self.pages.widget(0).body)
        self._fill_ranks(self.pages.widget(1).body)
        self._fill_account(self.pages.widget(2).body)
        self._fill_gsi(self.pages.widget(3).body)

    def _fill_key(self, lay: QVBoxLayout) -> None:
        row = QHBoxLayout()
        self.key_box = QLineEdit()
        self.key_box.setPlaceholderText("Paste the key here")
        # NOT a password field: the user needs to see that a paste landed
        # whole, and this is their own key on their own machine.
        self.key_box.textChanged.connect(self._key_changed)
        row.addWidget(self.key_box, 1)
        self.check = QPushButton("Check")
        self.check.clicked.connect(self._check_key)
        row.addWidget(self.check)
        lay.addLayout(row)
        self.key_note = QLabel("")
        self.key_note.setWordWrap(True)
        self.key_note.setProperty("dim", True)
        self.key_note.setVisible(False)
        lay.addWidget(self.key_note)

    def _fill_ranks(self, lay: QVBoxLayout) -> None:
        # A GRID, NOT A ROW. Eight brackets across one line came out with
        # every label elided — "Guardi", "Crusad" — which is a rank
        # picker you cannot read the ranks off.
        current = target_brackets() or DEFAULT_TARGET_BRACKETS
        ticks = QGridLayout()
        ticks.setHorizontalSpacing(18)
        self.boxes: dict = {}
        for index, bracket in enumerate(ALL_BRACKETS):
            box = QCheckBox(bracket.title())
            box.setChecked(bracket in current)
            box.toggled.connect(self._update_summary)
            ticks.addWidget(box, index // 4, index % 4)
            self.boxes[bracket] = box
        lay.addLayout(ticks)

        quick = QLabel("Or pick a pair:")
        quick.setProperty("dim", True)
        lay.addWidget(quick)
        presets = QGridLayout()
        for index, (label, brackets) in enumerate(PRESETS):
            button = QPushButton(label)
            button.clicked.connect(
                lambda _c, b=brackets: self._apply_preset(b))
            presets.addWidget(button, index // 3, index % 3)
        lay.addLayout(presets)
        self.summary = QLabel("")
        self.summary.setWordWrap(True)
        lay.addWidget(self.summary)

    def _fill_account(self, lay: QVBoxLayout) -> None:
        row = QHBoxLayout()
        self.account_box = QLineEdit()
        self.account_box.setPlaceholderText(
            "Friend ID, Steam ID, or a profile link")
        self.account_box.textChanged.connect(self._account_changed)
        row.addWidget(self.account_box, 1)
        lay.addLayout(row)
        self.account_note = QLabel("")
        self.account_note.setWordWrap(True)
        self.account_note.setProperty("dim", True)
        self.account_note.setVisible(False)
        lay.addWidget(self.account_note)

    def _fill_gsi(self, lay: QVBoxLayout) -> None:
        lay.addWidget(steps_list(gsi_install.LAUNCH_STEPS))
        row = QHBoxLayout()
        self.copy_option = QPushButton("Copy it and open Steam")
        self.copy_option.setProperty("accent", True)
        self.copy_option.clicked.connect(self._copy_launch_option)
        row.addWidget(self.copy_option)
        row.addStretch(1)
        lay.addLayout(row)
        self.gsi_note = QLabel("")
        self.gsi_note.setWordWrap(True)
        self.gsi_note.setProperty("dim", True)
        self.gsi_note.setVisible(False)
        lay.addWidget(self.gsi_note)

    # ---- moving between steps --------------------------------------------
    @staticmethod
    def _fitting_height(wanted: int = 760) -> int:
        """What the pages want, or what the screen can show, less.

        88% of the AVAILABLE geometry — available already excludes the
        taskbar — so the dialog reads as a dialog rather than filling the
        display. The floor is for a very short screen, where the answer
        is to scroll rather than to show a window too small for a card.
        """
        screen = QGuiApplication.primaryScreen()
        if screen is None:
            return wanted
        return max(480, min(wanted, int(screen.availableGeometry().height()
                                        * 0.88)))

    def _show_step(self, index: int) -> None:
        self.at = max(0, min(index, len(STEPS) - 1))
        step = STEPS[self.at]
        self.reached.add(step.ident)
        self.pages.setCurrentIndex(self.at)
        # REACHED STEPS ONLY. A step ahead of you is dim and cannot be
        # jumped to, which is what makes the order forced; one behind you
        # can be, because going back to correct something is not the same
        # as skipping ahead past a question.
        self.sections.set_reachable(self.reached)
        self.sections.light(step.ident)
        self.back.setEnabled(self.at > 0)
        last = self.at == len(STEPS) - 1
        self.next.setText("Finish" if last else "Next")
        self._note(self.note, "")
        self._update_next()

    def _jump_to(self, ident: str) -> None:
        if ident not in self.reached:
            return
        for index, step in enumerate(STEPS):
            if step.ident == ident:
                self._show_step(index)
                return

    def _back(self) -> None:
        self._show_step(self.at - 1)

    def _skip(self) -> None:
        """Move on, leaving this step on the banner's list.

        It is NOT the same as pressing Next with the box empty, which is
        refused: Skip is a decision, and the difference is whether the
        app has been told to stop asking for now or is being walked past
        an unanswered question by accident.
        """
        self._advance()

    def _next(self) -> None:
        done, problem = self._commit(STEPS[self.at])
        if problem:
            self._note(self.note, problem, warn=True)
            return
        if done:
            ident = STEPS[self.at].ident
            if ident in self.pending:
                self.pending.remove(ident)
        self._advance()

    def _advance(self) -> None:
        if self.at == len(STEPS) - 1:
            self.accept()
            return
        self._show_step(self.at + 1)

    def _commit(self, step: Step) -> tuple:
        """Save this step's answer. Returns (done, problem).

        PER STEP, not all at the end: a stepped installer that only
        writes anything on the last page loses four answers when
        somebody closes it on the fourth, and the whole point of the
        banner is that what IS done stays done.
        """
        if step.ident == "key":
            key = self.key_box.text().strip()
            if not key:
                return False, ("Paste your key, or press Skip this step "
                               "to come back to it later.")
            if self.checked is False:
                return False, "Stratz rejected that key."
            try:
                save_stratz_key(key)
            except (OSError, ValueError) as failure:
                return False, f"Could not save the key: {failure}"
            return True, ""
        if step.ident == "ranks":
            if not self.selected:
                return False, "Tick at least one rank."
            try:
                save_target_brackets(self.selected)
            except (OSError, ValueError) as failure:
                return False, f"Could not save the ranks: {failure}"
            return True, ""
        if step.ident == "account":
            text = self.account_box.text().strip()
            if not text:
                return False, ("Enter your friend ID, or press Skip this "
                               "step to come back to it later.")
            parsed = account_mod.parse(text)
            if parsed.error:
                return False, parsed.error
            if parsed.account_id is None:
                return False, ("That reads as a display name. Use the "
                               "Friend ID number from your Dota profile.")
            # REMEMBERED HERE, so the History tab opens on you. Reading
            # it back off this dialog would mean the wizard had to still
            # exist when the tab was first drawn.
            from ..history import store
            try:
                store.remember(parsed.account_id)
            except OSError as failure:
                return False, f"Could not save the account: {failure}"
            self.account_id = parsed.account_id
            return True, ""
        # The launch option is the user's to do in another program, so
        # there is nothing here to validate and nothing to save. Finish
        # takes it as done; the banner's rung is the GSI feed being
        # silent, which is a better test than anything this could ask.
        return True, ""

    # ---- state ------------------------------------------------------------
    @property
    def selected(self) -> tuple:
        return tuple(b for b in ALL_BRACKETS if self.boxes[b].isChecked())

    def _apply_preset(self, brackets) -> None:
        for name, box in self.boxes.items():
            box.setChecked(name in brackets)

    def _update_summary(self) -> None:
        chosen = self.selected
        if not chosen:
            self.summary.setText("Tick at least one rank.")
            self.summary.setProperty("warn", True)
        else:
            self.summary.setText(
                "Statistics will be pulled for "
                + " + ".join(b.title() for b in chosen)
                + (", combined." if len(chosen) > 1 else "."))
            self.summary.setProperty("warn", False)
        self.summary.style().unpolish(self.summary)
        self.summary.style().polish(self.summary)
        self._update_next()

    def _key_changed(self) -> None:
        # A key that has been edited since the check is UNCHECKED again,
        # not still-good: otherwise a rejected key could be corrected by
        # one character and inherit the previous answer.
        self.checked = None
        self._note(self.key_note, "")
        self._update_next()

    def _account_changed(self) -> None:
        text = self.account_box.text().strip()
        if not text:
            self._note(self.account_note, "")
        else:
            parsed = account_mod.parse(text)
            # SAY WHAT IT READ IT AS. This box takes five shapes of id
            # and a profile URL, and "converted from a 64 bit Steam ID"
            # is the difference between trusting the number and wondering
            # whether it took the paste whole.
            self._note(self.account_note,
                       parsed.error or parsed.how or "",
                       warn=bool(parsed.error))
        self._update_next()

    def _update_next(self) -> None:
        self.next.setEnabled(self.worker is None)

    @staticmethod
    def _note(label: QLabel, text: str, warn: bool = False) -> None:
        label.setText(text)
        label.setVisible(bool(text))
        label.setProperty("warn", warn)
        label.style().unpolish(label)
        label.style().polish(label)

    # ---- the two buttons that reach outside this window -------------------
    def _check_key(self) -> None:
        if self.worker is not None:
            return
        key = self.key_box.text().strip()
        if not key:
            self._note(self.key_note, "Paste the key first.", warn=True)
            return
        self._note(self.key_note, "Asking Stratz…")
        self.check.setEnabled(False)
        self.worker = KeyWorker(key, self)
        self.worker.answered.connect(self._checked)
        self.worker.finished.connect(self._worker_done)
        self.worker.start()
        self._update_next()

    def _checked(self, answer) -> None:
        self.checked = answer.ok
        # ok is None — asked and not answered — is NOT a bad key, so it is
        # a plain note and Next stays available.
        self._note(self.key_note, answer.message, warn=answer.ok is False)
        self._update_next()

    def _worker_done(self) -> None:
        self.worker = None
        self.check.setEnabled(True)
        self._update_next()

    def _copy_launch_option(self) -> None:
        """Copy it and open the dialog it goes in — ONE action, so the
        clipboard is loaded by the time the box is in front of you.

        It says the same thing whether or not the handler reported
        success: Steam is silent either way, so a True there is not
        evidence the Properties window opened.
        """
        QApplication.clipboard().setText(gsi_install.LAUNCH_OPTION)
        gsi_install.open_properties()
        self._note(self.gsi_note,
                   "Copied, and Steam should be opening Dota's properties. "
                   "Paste into Launch Options, then restart Dota. If Steam "
                   "did not open, step 1 above does it by hand.")

    # ---- closing ----------------------------------------------------------
    def shutdown(self) -> None:
        """A QThread destroyed while running takes the process with it, and
        closing the dialog mid-check is exactly when that happens."""
        worker, self.worker = self.worker, None
        if worker is not None:
            worker.wait(3000)

    def reject(self) -> None:                       # noqa: D102 - QDialog
        self.shutdown()
        super().reject()

    def accept(self) -> None:                       # noqa: D102 - QDialog
        self.shutdown()
        super().accept()
