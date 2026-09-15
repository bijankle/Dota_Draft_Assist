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

def _at(wizard, ident: str):
    """Put the wizard on a step by name, as walking to it would."""
    from draft_assist.ui.setup_wizard import STEPS
    index = [step.ident for step in STEPS].index(ident)
    wizard.reached.update(step.ident for step in STEPS[:index + 1])
    wizard._show_step(index)
    return wizard


def test_each_step_writes_its_own_answer_as_you_leave_it(qapp, sandbox,
                                                         monkeypatch):
    """PER STEP, not all at the end. A stepped installer that only saves
    on the last page loses every answer when somebody closes it on the
    fourth, and the whole point of the banner is that what IS done stays
    done."""
    monkeypatch.setattr(stratz.requests, "post", lambda *a, **k: Answer())
    wizard = SetupWizard()

    wizard.key_box.setText("pasted-key")
    wizard._next()
    assert config.stratz_api_key() == "pasted-key", "the key waited"

    wizard.ranks.boxes["Legend – Ancient"].click()
    wizard._next()
    assert config.target_brackets() == ("LEGEND", "ANCIENT")
    wizard.deleteLater()


def test_the_friend_id_is_remembered_so_the_history_tab_opens_on_you(
        qapp, sandbox, monkeypatch, tmp_path):
    """It replaces opening on a professional player's public id —
    "forget about topsons accoutn, that was a silly addition"."""
    from draft_assist.history import store
    monkeypatch.setattr(store, "STORE_FILE", tmp_path / "accounts.json")

    wizard = _at(SetupWizard(), "account")
    wizard.account_box.setText("86680300")
    wizard._next()
    assert wizard.account_id == 86680300
    assert [row["account_id"] for row in store.load()] == [86680300]
    wizard.deleteLater()


def test_a_steam64_is_converted_rather_than_refused(qapp, sandbox,
                                                    monkeypatch, tmp_path):
    """The box takes five shapes of id and a profile URL, and says which
    it read — "converted from a 64 bit Steam ID" is the difference
    between trusting the number and wondering whether the paste landed
    whole."""
    from draft_assist.history import store
    monkeypatch.setattr(store, "STORE_FILE", tmp_path / "accounts.json")

    wizard = _at(SetupWizard(), "account")
    wizard.account_box.setText("76561198046946028")
    assert not wizard.account_note.isHidden()
    assert "64 bit" in wizard.account_note.text()
    wizard._next()
    assert wizard.account_id == 86680300
    wizard.deleteLater()


def test_a_rejected_key_blocks_the_step_and_an_unreachable_one_does_not(
        qapp, sandbox):
    """THREE-VALUED, like every other "did the network answer" question
    here: telling somebody with flaky wifi that their key is bad sends
    them off to get another one they did not need."""
    wizard = SetupWizard()
    wizard.key_box.setText("something")

    wizard._checked(stratz.KeyCheck(False, "Stratz rejected that key."))
    wizard._next()
    assert wizard.at == 0, "a rejected key walked straight past the step"
    assert wizard.note.property("warn") is True

    # Could not ask is NOT a no.
    wizard._checked(stratz.KeyCheck(None, "Could not reach Stratz."))
    wizard._next()
    assert wizard.at == 1
    wizard.deleteLater()


def test_editing_the_key_forgets_the_last_answer(qapp, sandbox):
    """Otherwise a rejected key corrected by one character inherits the
    previous verdict."""
    wizard = SetupWizard()
    wizard.key_box.setText("bad")
    wizard._checked(stratz.KeyCheck(False, "no"))
    assert wizard.checked is False
    wizard.key_box.setText("bad-corrected")
    assert wizard.checked is None
    wizard.deleteLater()


def test_the_ranks_page_can_no_longer_be_empty_at_all(qapp, sandbox):
    """This REPLACES "no ranks ticked cannot be moved past". With eight
    independent boxes, none ticked was reachable and Next had to refuse
    it; an exclusive picker cannot get there, so the refusal has nothing
    left to refuse and the page always has an answer to save."""
    wizard = _at(SetupWizard(), "ranks")
    assert wizard.selected, "the page opened with no ranks at all"
    wizard._next()
    assert wizard.at == 2, "a page with a valid answer refused to advance"
    assert config.target_brackets() == wizard.ranks.chosen
    wizard.deleteLater()


def test_an_empty_step_is_refused_but_skipping_it_is_not(qapp, sandbox):
    """Skip is a DECISION and pressing Next with an empty box is not.
    The difference is whether the app has been told to stop asking for
    now, or is being walked past an unanswered question by accident."""
    wizard = SetupWizard()
    wizard._next()
    assert wizard.at == 0, "an empty key walked past the step"
    assert "Skip this step" in wizard.note.text()

    wizard._skip()
    assert wizard.at == 1
    assert "key" in wizard.pending, "a skipped step must stay outstanding"
    wizard.deleteLater()


def test_you_cannot_jump_ahead_but_you_can_go_back(qapp, sandbox,
                                                   monkeypatch):
    """"a forced step by step like your typical install windows steps".
    The sidebar shows where you are; it is not a way around the order.
    Going BACK is different — correcting an answer is not skipping a
    question."""
    monkeypatch.setattr(stratz.requests, "post", lambda *a, **k: Answer())
    wizard = SetupWizard()
    wizard._jump_to("gsi")
    assert wizard.at == 0, "the sidebar let somebody jump to the last step"

    wizard.key_box.setText("a-key")
    wizard._next()
    assert wizard.at == 1
    wizard._jump_to("key")
    assert wizard.at == 0, "going back to a step already reached is allowed"
    wizard.deleteLater()


def test_the_sidebar_lists_every_step_in_order(qapp, sandbox):
    """It is the progress indicator, so it is FIXED and always complete —
    listing only what you have reached would make the rows move under the
    cursor and would say nothing about how much is left."""
    from draft_assist.ui.setup_wizard import STEPS
    wizard = SetupWizard()
    assert wizard.sections.order == [step.ident for step in STEPS]
    assert wizard.sections.lit() == STEPS[0].ident
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
    ranks off. The range labels are longer than a bracket name, so this
    matters more now rather than less."""
    wizard = SetupWizard()
    wizard.resize(640, 820)
    qapp.processEvents()
    for name, box in wizard.ranks.boxes.items():
        assert box.width() >= box.sizeHint().width(), name
    wizard.deleteLater()


# ------------------------------------------ pairs, when pairs is all there is ----

def _meta(tmp_path, exact: bool, covers=("LEGEND", "ANCIENT")):
    import json
    from draft_assist.data import store
    path = tmp_path / "meta.json"
    path.write_text(json.dumps({"stratz_bracket_filter": {
        "arg": "bracketBasicIds", "values": ["LEGEND_ANCIENT"],
        "exact": exact, "covers": list(covers)}}), encoding="utf-8")
    return path


def test_pair_only_is_read_from_what_stratz_actually_did(tmp_path):
    """Not asserted by this app. Stratz's schema decides it,
    `choose_bracket_filter` discovers it on every build, and the dataset
    meta is the record."""
    from draft_assist.data import store
    assert store.pair_only_brackets(_meta(tmp_path, exact=False)) is True
    assert store.pair_only_brackets(_meta(tmp_path, exact=True)) is False


def test_never_measured_is_not_the_same_as_pairs_only(tmp_path):
    """THREE-VALUED, like `required`, `Profile.known` and `KeyCheck.ok`.
    A fresh install, an OpenDota-sourced dataset and a cache written
    before this was recorded all mean "no build has ever said" — and
    hiding the individual ranks on that would take away real control
    (they set the OpenDota BASELINES exactly) to prevent a problem
    nobody has measured."""
    from draft_assist.data import store
    assert store.pair_only_brackets(tmp_path / "absent.json") is None
    (tmp_path / "bare.json").write_text("{}", encoding="utf-8")
    assert store.pair_only_brackets(tmp_path / "bare.json") is None


def test_the_ranks_are_five_ranges_and_exactly_one_is_ticked(
        qapp, sandbox, monkeypatch):
    """"get ride of the tick boxes above (iondividual ranks) and and just
    make the rank pairings have tick boxes ... (only allow selection of 1
    pair / range)".

    It was eight individual boxes AND the same five ranges as push
    buttons underneath, where pressing a button silently re-ticked the
    boxes above it: two controls for one setting, and two rows of card
    saying one thing twice.
    """
    from draft_assist.ui import rankpick
    from draft_assist.ui.setup_wizard import SetupWizard

    config.save_target_brackets(("ANCIENT", "DIVINE"))
    wizard = _at(SetupWizard(), "ranks")
    assert not hasattr(wizard, "boxes"), "the individual ranks are back"
    assert len(wizard.ranks.boxes) == len(rankpick.RANGES) == 5
    ticked = [name for name, box in wizard.ranks.boxes.items()
              if box.isChecked()]
    assert ticked == ["Ancient – Divine"], ticked
    wizard.deleteLater()


def test_the_choice_moves_and_never_empties(qapp, sandbox):
    """A tick box normally toggles OFF, which here would leave no rank
    chosen at all — a state that means nothing. Radio behaviour without
    the radio look: clicking the ticked one keeps it."""
    from draft_assist.ui.setup_wizard import SetupWizard

    config.save_target_brackets(("ANCIENT", "DIVINE"))
    wizard = _at(SetupWizard(), "ranks")
    picker = wizard.ranks

    picker.boxes["Archon – Legend"].click()
    assert picker.chosen == ("ARCHON", "LEGEND")
    assert sum(b.isChecked() for b in picker.boxes.values()) == 1

    picker.boxes["Archon – Legend"].click()          # the ticked one
    assert picker.chosen == ("ARCHON", "LEGEND"), "the choice emptied"
    assert sum(b.isChecked() for b in picker.boxes.values()) == 1

    wizard._next()
    assert config.target_brackets() == ("ARCHON", "LEGEND")
    wizard.deleteLater()


def test_a_saved_set_that_is_not_a_range_still_opens_on_something(qapp):
    """A `preferences.json` written before this existed can hold one
    bracket, or three that are not a range. Exact match first, then the
    range sharing the most with it, then the default — never nothing,
    because a picker opening with no box ticked is asking a question the
    file has already answered."""
    from draft_assist.ui import rankpick

    assert rankpick.best_match(("ANCIENT", "DIVINE")) == ("ANCIENT", "DIVINE")
    assert rankpick.best_match(("LEGEND",)) in [
        tuple(b) for _l, b in rankpick.RANGES]
    assert rankpick.best_match(()) == config.DEFAULT_TARGET_BRACKETS
    assert rankpick.best_match(("NOT_A_RANK",)) == config.DEFAULT_TARGET_BRACKETS


def test_one_list_of_ranges_serves_both_pickers(qapp):
    """There were TWO and they disagreed: the settings dialog labelled
    the ranges by who plays them ("I play Legend, climbing to Ancient")
    and handed back the bracket ABOVE what the label said."""
    from draft_assist.ui import bracket_dialog, rankpick, setup_wizard

    assert not hasattr(setup_wizard, "PRESETS")
    assert not hasattr(bracket_dialog, "SUGGESTIONS")
    assert rankpick.RANGES, "the one list went missing"
