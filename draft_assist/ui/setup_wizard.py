"""First-run setup: the key, the rank, and then get on with it.

A fresh install needs two things the app cannot work out for itself — a
free Stratz API key, and which ranks the statistics should describe — and
before this existed it asked for neither. It opened to a grid of empty
plates with a banner naming a file, which is fine for the person who wrote
it and no use at all to somebody who has just unzipped it.

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
from PyQt6.QtWidgets import (QCheckBox, QDialog, QFrame, QGridLayout,
                             QHBoxLayout, QLabel, QLineEdit, QPushButton,
                             QVBoxLayout)

from ..config import (ALL_BRACKETS, DEFAULT_TARGET_BRACKETS, has_stratz_key,
                      save_stratz_key, save_target_brackets, target_brackets)

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


class SetupWizard(QDialog):
    """One dialog: what this needs, the key, the ranks, and Finish."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Set up Dota Draft Assist")
        self.setMinimumWidth(640)
        self.checked: bool | None = None       # what check_key last said
        self.worker: KeyWorker | None = None

        lay = QVBoxLayout(self)
        lay.setSpacing(10)

        heading = QLabel("Two things and it is ready")
        heading.setProperty("heading", True)
        lay.addWidget(heading)

        # ONE LINE. It was four, explaining where the numbers come from
        # and why each of the two things below is being asked for — all
        # true, all read once, and all of it between somebody and the
        # only two controls on the screen. It is the manual's first page
        # now (Help ▸ User manual).
        blurb = paragraph(
            "Both are stored on this machine and can be changed later.")
        blurb.setProperty("dim", True)
        lay.addWidget(blurb)

        lay.addWidget(self._key_section())
        lay.addWidget(self._bracket_section())

        self.note = QLabel("")
        self.note.setWordWrap(True)
        self.note.setProperty("dim", True)
        self.note.setVisible(False)
        lay.addWidget(self.note)

        buttons = QHBoxLayout()
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
        lay.addLayout(buttons)

        self._update_summary()

    # ---- the two sections ----------------------------------------------
    def _key_section(self) -> QFrame:
        frame = QFrame()
        frame.setProperty("card", True)
        lay = QVBoxLayout(frame)
        title = QLabel("1 · Your Stratz API key")
        title.setProperty("heading", True)
        lay.addWidget(title)
        why = paragraph("Free, and it takes a minute. Skip it and the "
                        "app still opens.")
        why.setProperty("dim", True)
        lay.addWidget(why)

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
        title = QLabel("2 · Which ranks")
        title.setProperty("heading", True)
        lay.addWidget(title)
        why = paragraph("Rates differ by rank. One bracket above where "
                        "you play is the usual choice.")
        why.setProperty("dim", True)
        lay.addWidget(why)

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
