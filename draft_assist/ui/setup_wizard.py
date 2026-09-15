"""First-run setup: the key, the ranks, the game feed, and get on with it.

A fresh install needs two things the app cannot work out for itself — a
free Stratz API key, and which ranks the statistics should describe — and
before this existed it asked for neither. It opened to a grid of empty
plates with a banner naming a file, which is fine for the person who wrote
it and no use at all to somebody who has just unzipped it.

**AND A THIRD CARD THAT ASKS FOR ALMOST NOTHING.** Game data (GSI) has
two halves: a config file in the Dota install, which this writes on
Finish because there is nothing in it for anybody to decide, and
`-gamestateintegration` in Steam's launch options, which cannot be
automated at all — Steam holds that file in memory and rewrites it on
exit. So the card does the first silently and spells the second out as a
numbered procedure with the option on the clipboard, at the user's
request. Neither half used to be here at all, and the app opened telling
people to go and find a menu item for the half it could have done
itself.

**IT ASKS ONCE AND THEN DOES THE WORK.** Ticking the boxes is the whole
interaction: on Finish it writes `.env`, saves the brackets, and starts
the download itself. An install that ends by telling the user to go and
find a menu item has not finished installing.

**THE KEY IS CHECKED BEFORE IT IS TRUSTED** (`stratz.check_key`). A typo
accepted here surfaces three minutes later as a failure inside a progress
dialog, which reads as the app being broken rather than as a bad paste.
But a check that could not be MADE — rate limit, no connection — never
blocks: `KeyCheck.ok` is three-valued, and only an outright rejection
stops the Finish button.

**IT IS SKIPPABLE**, at the user's request. Somebody offline, or who
wants a look before signing up for anything, must not meet a wall. Skip
leaves the banner at the top of the window as the way back, and the
wizard opens again next time until setup is actually done.
"""

import webbrowser

from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtGui import QGuiApplication
from PyQt6.QtWidgets import (QApplication, QCheckBox, QDialog, QFrame,
                             QGridLayout, QHBoxLayout, QLabel, QLineEdit,
                             QPushButton, QScrollArea, QVBoxLayout, QWidget)

from ..config import (ALL_BRACKETS, DEFAULT_TARGET_BRACKETS, has_stratz_key,
                      save_stratz_key, save_target_brackets, target_brackets)
from ..gsi import install as gsi_install

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


def needed() -> bool:
    """Is there anything left for first-run setup to ask?

    Only the KEY, deliberately. The brackets always have a defensible
    default and an install with a key is one somebody has already been
    through this for — so an existing install never sees the wizard, and
    a fresh one sees it exactly once.
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


# How much width a paragraph inside a card actually gets: the dialog's
# minimum, less the dialog's margins and the card's.
TEXT_WIDTH = 640 - 72


def paragraph(text: str, width: int = TEXT_WIDTH) -> QLabel:
    """A wrapped label that reports its own height honestly.

    A word-wrapped QLabel's size hint is a single line until something
    tells it how wide it will be, and `heightForWidth` does not propagate
    up through nested layouts — so the dialog measured every paragraph
    here as one line tall, and the two long ones were drawn ON TOP of the
    controls beneath them with the preset buttons squashed to nothing.
    Measuring the text at the width it will actually get and making that
    the minimum is the fix, and it holds at any size at or above the
    dialog's minimum because a wider label only ever needs fewer lines.
    """
    label = QLabel(text)
    label.setWordWrap(True)
    # `heightForWidth`, not a font-metrics bounding rect: the metrics
    # measure the STRING, while the label measures what it will actually
    # lay out — margins, indent and the stylesheet's font included. The
    # bounding rect came out a line short, which put the last line of two
    # paragraphs underneath the controls below them.
    needed = label.heightForWidth(width)
    label.setMinimumHeight(max(needed, label.sizeHint().height()))
    return label


def steps(lines) -> QLabel:
    """A numbered procedure, which is NOT a paragraph.

    The rule on this dialog is that it asks rather than explains, and it
    is held by a test: no `paragraph` over 120 characters, because four
    of them about where statistics come from is what this screen was cut
    back from. A PROCEDURE is a different shape and earns its place by
    being the thing the user has to carry out by hand — it is scanned a
    line at a time rather than read, and each line here is one action.
    Cutting it to a sentence is what left "add the launch option" as a
    thing people were told about and did not do.
    """
    label = QLabel("\n".join(f"{n}.  {line}"
                              for n, line in enumerate(lines, 1)))
    label.setWordWrap(True)
    label.setTextInteractionFlags(
        Qt.TextInteractionFlag.TextSelectableByMouse)
    label.setMinimumHeight(label.heightForWidth(TEXT_WIDTH))
    return label


class SetupWizard(QDialog):
    """One dialog: what this needs, the key, the ranks, and Finish."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Set up Dota Draft Assist")
        self.setMinimumWidth(640)
        self.checked: bool | None = None       # what check_key last said
        self.worker: KeyWorker | None = None

        # THE CARDS SCROLL, and the third one is what made that necessary.
        # A dialog is sized to its contents, so three cards and a
        # seven-step procedure came to 1218px — taller than the usable
        # height of a 1080p screen and half as tall again as a 1366x768
        # laptop's, with Finish somewhere below the bottom of both. This
        # is `app._scrolling`'s lesson in a dialog: a long page inside a
        # scroll area asks for nothing, so the height becomes a choice
        # rather than a demand. The buttons stay OUTSIDE it — Skip and
        # Finish scrolling away with the content is the fault being
        # fixed, not a smaller version of it.
        shell = QVBoxLayout(self)
        shell.setContentsMargins(0, 0, 0, 0)
        page = QWidget()
        page.setProperty("bare", True)
        lay = QVBoxLayout(page)
        lay.setSpacing(10)

        heading = QLabel("Three steps and it is ready")
        heading.setProperty("heading", True)
        lay.addWidget(heading)

        # ONE LINE. It was four, explaining where the numbers come from
        # and why each thing below is being asked for — all true, all
        # read once, and all of it between somebody and the controls
        # they came for. It is the manual's first page now (Help ▸ User
        # manual). What this line has to carry is the two facts somebody
        # decides on: nothing leaves the machine, nothing is permanent.
        blurb = paragraph(
            "Everything here stays on this machine, and all of it can be "
            "changed later in Settings.")
        blurb.setProperty("dim", True)
        lay.addWidget(blurb)

        lay.addWidget(self._key_section())
        lay.addWidget(self._bracket_section())
        lay.addWidget(self._game_data_section())

        self.note = QLabel("")
        self.note.setWordWrap(True)
        self.note.setProperty("dim", True)
        self.note.setVisible(False)
        lay.addWidget(self.note)

        lay.addStretch(1)
        area = QScrollArea()
        area.setWidgetResizable(True)
        area.setFrameShape(QScrollArea.Shape.NoFrame)
        area.setWidget(page)
        shell.addWidget(area, 1)

        buttons = QHBoxLayout()
        buttons.setContentsMargins(12, 0, 12, 12)
        self.skip = QPushButton("Skip for now")
        self.skip.setToolTip("The banner at the top is the way back.")
        self.skip.clicked.connect(self.reject)
        buttons.addWidget(self.skip)
        buttons.addStretch(1)
        self.finish = QPushButton("Finish and download")
        self.finish.setProperty("accent", True)
        self.finish.setDefault(True)
        self.finish.clicked.connect(self._finish)
        buttons.addWidget(self.finish)
        shell.addLayout(buttons)

        # AS TALL AS IT WANTS, UP TO WHAT THE SCREEN HAS. Asking for the
        # full 1218 and letting the window manager clip it is how Finish
        # ends up off the bottom edge with no way to reach it; asking for
        # a fixed short height would make everybody scroll on a monitor
        # with room to spare.
        self.resize(660, self._fitting_height())
        self._update_summary()

    @staticmethod
    def _fitting_height(wanted: int = 1218) -> int:
        """What the content wants, or what the screen can show, whichever
        is less.

        `wanted` is the measured height of all three cards laid out. The
        ceiling is 88% of the AVAILABLE geometry rather than the screen's
        -- available already excludes the taskbar -- which leaves the
        dialog reading as a dialog rather than filling the display. The
        520 floor is there for the degenerate case of a very short
        screen, where scrolling is the answer rather than a dialog too
        small to show a card.
        """
        screen = QGuiApplication.primaryScreen()
        if screen is None:
            return 820
        return max(520, min(wanted, int(screen.availableGeometry().height()
                                        * 0.88)))

    # ---- the three sections ----------------------------------------------
    def _key_section(self) -> QFrame:
        frame = QFrame()
        frame.setProperty("card", True)
        lay = QVBoxLayout(frame)
        title = QLabel("1 · A Stratz API key")
        title.setProperty("heading", True)
        lay.addWidget(title)
        # WHAT IT IS FOR, WHAT IT COSTS, WHERE IT GOES. The old line said
        # only "free, and it takes a minute", which answers none of them:
        # somebody being asked to go and sign up for a thing wants to
        # know what stops working if they do not.
        why = paragraph(
            "Every win rate and matchup in the app comes from Stratz. "
            "Free: sign in with Steam and copy the key.")
        why.setProperty("dim", True)
        lay.addWidget(why)
        where = paragraph(
            "It is written to .env beside the app and never sent anywhere "
            "but Stratz.")
        where.setProperty("dim", True)
        lay.addWidget(where)

        row = QHBoxLayout()
        get = QPushButton("Open stratz.com/api")
        get.clicked.connect(lambda: webbrowser.open(KEY_URL))
        row.addWidget(get)
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
        return frame

    def _bracket_section(self) -> QFrame:
        frame = QFrame()
        frame.setProperty("card", True)
        lay = QVBoxLayout(frame)
        title = QLabel("2 · Which ranks the advice describes")
        title.setProperty("heading", True)
        lay.addWidget(title)
        # WHY "ABOVE", which the old line asserted without saying. Two
        # ticked rather than one is the other half and is why the presets
        # are pairs: it roughly doubles the sample.
        why = paragraph(
            "Heroes perform differently by rank. Pick the bracket you "
            "play in, or one above if you are climbing.")
        why.setProperty("dim", True)
        lay.addWidget(why)
        pair = paragraph(
            "Two adjacent brackets are combined, which doubles the sample "
            "for a difference smaller than the noise.")
        pair.setProperty("dim", True)
        lay.addWidget(pair)

        # A GRID, NOT A ROW. Eight brackets and five presets across one
        # line each came out with every label elided — "Guardi", "Crusad",
        # "ald - Crusa" — which is a rank picker you cannot read the ranks
        # off. Four columns fits the longest name at the app's body size
        # with room to spare, and the dialog stays a sensible shape.
        current = target_brackets() or DEFAULT_TARGET_BRACKETS
        ticks = QGridLayout()
        ticks.setHorizontalSpacing(18)
        self.boxes: dict[str, QCheckBox] = {}
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
        return frame

    def _game_data_section(self) -> QFrame:
        """The third card: one half automatic, one half the user's.

        It exists because the app used to ask for NEITHER half here and
        then put a banner up about it — "why is it not just auto run at
        setup with all the other crap like portraits". The config file is
        auto-run now, on Finish, with nothing on this card to decide; the
        launch option cannot be, so it gets the procedure.
        """
        frame = QFrame()
        frame.setProperty("card", True)
        lay = QVBoxLayout(frame)
        title = QLabel("3 · Letting Dota tell the app about the draft")
        title.setProperty("heading", True)
        lay.addWidget(title)
        why = paragraph(
            "Dota can send the app the draft as it happens. Valve's own "
            "feature: nothing is injected into the game.")
        why.setProperty("dim", True)
        lay.addWidget(why)
        auto = paragraph(
            "Finish writes the config file into your Dota install for "
            "you. One step is yours, in Steam:")
        auto.setProperty("dim", True)
        lay.addWidget(auto)

        lay.addWidget(steps(gsi_install.LAUNCH_STEPS))

        # ONE BUTTON DOING BOTH, because they are one action: the
        # clipboard is loaded by the time the box you paste into is in
        # front of you. It covers steps 1 and 2, which is as far as
        # anything can carry somebody -- the box it lands on is the one
        # they have to type in.
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
        return frame

    def _copy_launch_option(self) -> None:
        """Copy it and open the dialog it goes in.

        A press with no visible result is a press nobody trusts, and both
        halves of this one land somewhere the dialog cannot see -- the
        clipboard, and another program's window. So it says what it did.
        And it says the same thing whether or not the handler reported
        success: Steam is silent either way, so a True there is not
        evidence the Properties window opened.
        """
        QApplication.clipboard().setText(gsi_install.LAUNCH_OPTION)
        gsi_install.open_properties()
        self._note(self.gsi_note,
                   "Copied, and Steam should be opening Dota's properties. "
                   "Paste into Launch Options, then restart Dota. If Steam "
                   "did not open, step 1 above does it by hand.")

    # ---- state ----------------------------------------------------------
    @property
    def selected(self) -> tuple[str, ...]:
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
        self._update_finish()

    def _key_changed(self) -> None:
        # A key that has been edited since the check is UNCHECKED again,
        # not still-good: otherwise a rejected key could be corrected by
        # one character and inherit the previous answer.
        self.checked = None
        self._note(self.key_note, "")
        self._update_finish()

    def _update_finish(self) -> None:
        self.finish.setEnabled(bool(self.selected)
                               and bool(self.key_box.text().strip())
                               and self.checked is not False
                               and self.worker is None)

    @staticmethod
    def _note(label: QLabel, text: str, warn: bool = False) -> None:
        label.setText(text)
        label.setVisible(bool(text))
        label.setProperty("warn", warn)
        label.style().unpolish(label)
        label.style().polish(label)

    # ---- checking -------------------------------------------------------
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
        self._update_finish()

    def _checked(self, answer) -> None:
        self.checked = answer.ok
        # ok is None — asked and not answered — is NOT a bad key, so it is
        # a plain note and Finish stays available.
        self._note(self.key_note, answer.message, warn=answer.ok is False)
        # The verdict has to reach the button in the same breath: without
        # this a rejected key left Finish enabled until something else
        # happened to re-evaluate it, which is the whole point of asking.
        self._update_finish()

    def _worker_done(self) -> None:
        self.worker = None
        self.check.setEnabled(True)
        self._update_finish()

    # ---- finishing ------------------------------------------------------
    def _finish(self) -> None:
        """Save both, then accept. Whichever fails, say which and stay."""
        try:
            save_target_brackets(self.selected)
        except (OSError, ValueError) as failure:
            self._note(self.note, f"Could not save the ranks: {failure}",
                       warn=True)
            return
        try:
            save_stratz_key(self.key_box.text())
        except (OSError, ValueError) as failure:
            self._note(self.note, f"Could not save the key: {failure}",
                       warn=True)
            return
        # THE CONFIG ITSELF IS THE WINDOW'S, not this dialog's
        # (`MainWindow._ensure_gsi_config`). It has to know the listener's
        # real port and hand the new token to the running server in the
        # same breath, and it is the same call that runs at every start
        # for installs that never see this wizard — so writing it here
        # too would be two implementations of one step. Accepting is what
        # asks for it; a failure to find Dota is reported by the banner
        # rather than blocking Finish, since setting the app up before
        # installing Dota is a perfectly ordinary order to do it in.
        self.accept()

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
