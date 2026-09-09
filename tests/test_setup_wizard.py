"""First-run setup: the key, the ranks, and the checks around both.

A fresh install used to open to empty tiles and a banner naming a file.
These cover the three things that must hold for a stranger's first five
minutes: the key is verified before it is trusted, a check that could not
be MADE never blocks, and skipping leaves a way back.
"""

import os

import pytest

pytest.importorskip("PyQt6")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication          # noqa: E402

from draft_assist import config                   # noqa: E402
from draft_assist.data import stratz              # noqa: E402
from draft_assist.ui.setup_wizard import SetupWizard, needed  # noqa: E402


@pytest.fixture(scope="module")
def qapp():
    yield QApplication.instance() or QApplication([])


@pytest.fixture()
def sandbox(tmp_path, monkeypatch):
    """A fresh machine: no .env, no preferences."""
    monkeypatch.setattr(config, "ENV_FILE", tmp_path / ".env")
    monkeypatch.setattr(config, "PREFS_FILE", tmp_path / "preferences.json")
    monkeypatch.delenv(config.KEY_NAME, raising=False)
    return tmp_path


class Answer:
    """Whatever the HTTP layer is told to say."""

    def __init__(self, status=200, payload=None):
        self.status_code = status
        self.ok = status < 400
        self._payload = payload or {"data": {"__typename": "Query"}}

    def json(self):
        return self._payload


# ------------------------------------------------------------- the key ----

def test_the_key_is_checked_without_touching_the_schema(monkeypatch):
    """Every other call in that module validates itself against the live
    schema. A key check must NOT: one that depended on Stratz's fields
    would start reporting "your key is bad" the day they rename one.
    `__typename` is part of GraphQL itself."""
    sent = {}

    def fake_post(url, json=None, headers=None, timeout=None):
        sent.update(url=url, query=json["query"], headers=headers)
        return Answer()

    monkeypatch.setattr(stratz.requests, "post", fake_post)
    answer = stratz.check_key("a-real-looking-key")
    assert answer.ok is True
    assert sent["query"] == "{__typename}"
    assert sent["headers"]["Authorization"] == "Bearer a-real-looking-key"


def test_a_rejected_key_is_told_apart_from_an_unanswered_check(monkeypatch):
    """THREE-VALUED, like every other "did the network answer" question
    here. Telling somebody with flaky wifi that their key is bad sends
    them off to get another one they did not need."""
    monkeypatch.setattr(stratz.requests, "post",
                        lambda *a, **k: Answer(status=403))
    assert stratz.check_key("wrong").ok is False

    for status in (429, 500, 503):
        monkeypatch.setattr(stratz.requests, "post",
                            lambda *a, s=status, **k: Answer(status=s))
        assert stratz.check_key("fine").ok is None, status

    def explode(*args, **kwargs):
        raise stratz.requests.RequestException("no route to host")
    monkeypatch.setattr(stratz.requests, "post", explode)
    unreachable = stratz.check_key("fine")
    assert unreachable.ok is None
    assert "says nothing about the key" in unreachable.message


def test_an_empty_key_is_refused_before_any_request(monkeypatch):
    monkeypatch.setattr(stratz.requests, "post", lambda *a, **k: pytest.fail(
        "it asked Stratz about an empty key"))
    assert stratz.check_key("").ok is False
    assert stratz.check_key("your-stratz-api-key-here").ok is False


# ------------------------------------------------------------ storage ----

def test_saving_the_key_keeps_everything_else_in_the_file(sandbox):
    """`.env` is exactly the sort of file people add lines to, and
    rewriting it wholesale would drop them."""
    env = sandbox / ".env"
    env.write_text("# my notes\nOTHER=keep me\n"
                   "STRATZ_API_KEY=old\nTRAILING=also keep\n",
                   encoding="utf-8")
    config.save_stratz_key("brand-new")
    written = env.read_text(encoding="utf-8")
    assert "STRATZ_API_KEY=brand-new" in written
    assert "OTHER=keep me" in written
    assert "TRAILING=also keep" in written
    assert "# my notes" in written
    assert "old" not in written


def test_a_key_saved_now_is_readable_now(sandbox):
    """`load_dotenv` does not overwrite a variable already in the
    environment, so a key entered after one was read this session would
    otherwise be ignored until a restart."""
    assert not config.has_stratz_key()
    config.save_stratz_key("fresh-key")
    assert config.stratz_api_key() == "fresh-key"
    assert config.has_stratz_key()


def test_the_wizard_is_needed_only_until_there_is_a_key(sandbox):
    assert needed()
    config.save_stratz_key("anything")
    assert not needed(), "an existing install must never see the wizard"


# ------------------------------------------------------------- dialog ----

def test_finishing_writes_both_and_downloads(qapp, sandbox, monkeypatch):
    """Ticking the boxes is the whole interaction: an install that ends by
    telling the user to find a menu item has not finished installing."""
    monkeypatch.setattr(stratz.requests, "post", lambda *a, **k: Answer())
    wizard = SetupWizard()
    wizard.key_box.setText("pasted-key")
    wizard._apply_preset(("LEGEND", "ANCIENT"))
    assert wizard.finish.isEnabled()
    wizard._finish()

    assert config.stratz_api_key() == "pasted-key"
    assert config.target_brackets() == ("LEGEND", "ANCIENT")
    wizard.deleteLater()


def test_a_rejected_key_blocks_finish_and_an_unreachable_one_does_not(
        qapp, sandbox):
    wizard = SetupWizard()
    wizard.key_box.setText("something")
    wizard._apply_preset(("ANCIENT",))

    wizard._checked(stratz.KeyCheck(False, "Stratz rejected that key."))
    assert not wizard.finish.isEnabled()
    assert wizard.key_note.property("warn") is True

    # Could not ask is NOT a no.
    wizard._checked(stratz.KeyCheck(None, "Could not reach Stratz."))
    assert wizard.finish.isEnabled()
    assert wizard.key_note.property("warn") is False
    wizard.deleteLater()


def test_editing_the_key_forgets_the_last_answer(qapp, sandbox):
    """Otherwise a rejected key corrected by one character inherits the
    previous verdict."""
    wizard = SetupWizard()
    wizard._apply_preset(("ANCIENT",))
    wizard.key_box.setText("bad")
    wizard._checked(stratz.KeyCheck(False, "no"))
    assert wizard.checked is False
    wizard.key_box.setText("bad-corrected")
    assert wizard.checked is None
    assert wizard.finish.isEnabled()
    wizard.deleteLater()


def test_no_ranks_ticked_cannot_be_finished(qapp, sandbox):
    wizard = SetupWizard()
    wizard.key_box.setText("a-key")
    wizard._apply_preset(())
    assert not wizard.finish.isEnabled()
    assert "at least one" in wizard.summary.text()
    wizard.deleteLater()


def test_skipping_writes_nothing_at_all(qapp, sandbox):
    """Somebody offline, or who wants a look before signing up for
    anything, must not meet a wall — and must not have half a setup
    written behind them either."""
    wizard = SetupWizard()
    wizard.key_box.setText("typed-but-not-saved")
    wizard.reject()
    assert not (sandbox / ".env").exists()
    assert not config.has_stratz_key()
    wizard.deleteLater()


def test_a_paragraph_reserves_room_for_every_line_it_wraps_to(qapp):
    """A word-wrapped QLabel's size hint is ONE LINE until something tells
    it how wide it will be, and heightForWidth does not propagate up
    through nested layouts — so both long paragraphs in this dialog were
    drawn on top of the controls under them, with the preset buttons
    squashed to no height at all."""
    from draft_assist.ui.setup_wizard import TEXT_WIDTH, paragraph
    long_text = ("Hero win rates and matchups differ by rank. Pulling from "
                 "about one bracket above where you play tilts the advice "
                 "toward the games you are trying to win. You can change "
                 "this later in Settings - Downloads - Statistics bracket.")
    label = paragraph(long_text)
    one_line = label.fontMetrics().height()
    assert label.minimumHeight() >= 3 * one_line
    assert label.minimumHeight() >= label.heightForWidth(TEXT_WIDTH)


def test_the_ranks_are_readable_rather_than_elided(qapp, sandbox):
    """Eight brackets and five presets across one line each came out as
    "Guardi", "Crusad", "ald - Crusa" — a rank picker you cannot read the
    ranks off."""
    wizard = SetupWizard()
    wizard.resize(640, 820)
    qapp.processEvents()
    for name, box in wizard.boxes.items():
        assert box.width() >= box.sizeHint().width(), name
    wizard.deleteLater()
