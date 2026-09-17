"""A stranger's bad draft reports itself, and fixes itself first.

The detection was all there and nothing was listening: `crop_boxes_wrong`
is a VERDICT (the game named the ten heroes on screen and the calibrated
boxes matched too few of them), `compare_sources` has graded the screen
against the minimap since the recorder was written, and both said so
where only the owner would ever look.
"""

import json
import zipfile
from pathlib import Path

import pytest

from draft_assist import bugreport
from draft_assist.config import SUPPORT_EMAIL
from draft_assist.ui import mailer


@pytest.fixture()
def window(qapp):
    from draft_assist.config import RULES_FILE
    from draft_assist.model import items as items_mod
    from draft_assist.ui.app import MainWindow
    from draft_assist.ui.demo import demo_dataset
    from draft_assist.ui.providers import DemoProvider

    ds = demo_dataset()
    rules, meta = items_mod.load_rules(RULES_FILE)
    win = MainWindow(ds, DemoProvider(ds), rules, meta)
    win.timer.stop()
    win.show()
    yield win
    win.close()


@pytest.fixture(scope="module")
def qapp():
    import os
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PyQt6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


def a_tick(**over):
    row = {"at": 0.0, "game_state": "DOTA_GAMERULES_STATE_HERO_SELECTION",
           "has_frame": True, "ran_recognition": True, "read_heroes": 10,
           "source": "screen", "allies": [], "enemies": [],
           "crop_boxes_wrong": False, "sides_certain": True}
    row.update(over)
    return row


def a_folder(tmp_path: Path, rows) -> Path:
    folder = tmp_path / "2026-09-18_2000"
    (folder / "gsi").mkdir(parents=True)
    (folder / "frames").mkdir()
    (folder / "state.jsonl").write_text(
        "".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")
    return folder


def test_a_clean_draft_reports_nothing(tmp_path):
    folder = a_folder(tmp_path, [a_tick(at=float(n)) for n in range(20)])
    verdict = bugreport.grade(folder)
    assert not verdict.bad
    assert "nothing looked wrong" in verdict.headline()


def test_the_crop_box_verdict_is_read_rather_than_inferred(tmp_path):
    """The one signal that is a verdict rather than a guess.

    At strategy time the GAME names the ten heroes on screen, so boxes
    matching too few of them is proof of geometry rather than
    recognition being unlucky - which is exactly why it is worth acting
    on, and why the recorder had to start writing it down.
    """
    rows = [a_tick(at=float(n)) for n in range(5)]
    rows.append(a_tick(at=6.0, crop_boxes_wrong=True))
    verdict = bugreport.grade(a_folder(tmp_path, rows))
    assert [f.key for f in verdict.faults] == ["crop_boxes"]
    assert verdict.faults[0].repairable


def test_a_long_blind_stretch_while_picking_is_a_fault(tmp_path):
    """The fault this is drawn from: two of ten slots for eighty seconds."""
    rows = [a_tick(at=float(n), read_heroes=0)
            for n in range(0, int(bugreport.BLIND_SECONDS) + 6)]
    verdict = bugreport.grade(a_folder(tmp_path, rows))
    assert "blind" in [f.key for f in verdict.faults]


def test_no_frame_is_not_a_blind_stretch(tmp_path):
    """Capture failing and recognition failing are different bugs.

    A tick with no picture says the app is not bound to Dota, which
    wants a completely different answer from one where it had the
    picture and read nothing out of it.
    """
    rows = [a_tick(at=float(n), read_heroes=0, has_frame=False)
            for n in range(0, int(bugreport.BLIND_SECONDS) + 6)]
    verdict = bugreport.grade(a_folder(tmp_path, rows))
    assert "blind" not in [f.key for f in verdict.faults]


def test_repairable_is_every_fault_and_not_any_of_them():
    """Fixing the boxes and going quiet about the rest would lose
    exactly the reports worth having."""
    fixable = bugreport.Fault("a", "a", "a", repairable=True)
    not_fixable = bugreport.Fault("b", "b", "b", repairable=False)
    assert bugreport.Verdict(faults=[fixable]).repairable
    assert not bugreport.Verdict(faults=[fixable, not_fixable]).repairable
    assert not bugreport.Verdict().repairable


def test_the_headline_counts_the_rest(tmp_path):
    two = [bugreport.Fault("a", "first thing", ""),
           bugreport.Fault("b", "second", "")]
    assert bugreport.Verdict(faults=two).headline() == "first thing (and 1 more)"


def test_the_zip_says_what_went_into_it(tmp_path):
    rows = [a_tick(at=6.0, crop_boxes_wrong=True)]
    folder = a_folder(tmp_path, rows)
    (folder / "gsi" / "gsi_00001.json").write_text(
        json.dumps({"minimap": {"o1": {"unitname": "npc_dota_hero_axe"}}}),
        encoding="utf-8")
    verdict = bugreport.grade(folder)
    zipped, packed = bugreport.write_zip(folder, verdict, tmp_path / "out")

    assert zipped.is_file()
    assert zipped.stat().st_size <= bugreport.SIZE_CAP
    assert "report.txt" in packed and "state.jsonl" in packed
    # ONE PAYLOAD, NOT ALL OF THEM - a session holds hundreds of nearly
    # identical ones and the fullest is the only one that answers
    # anything.
    assert "payload.json" in packed
    with zipfile.ZipFile(zipped) as archive:
        text = archive.read("report.txt").decode()
    assert "could not find the hero portraits" in text
    assert "WHAT WAS MEASURED" in text


def test_a_report_sent_by_hand_says_so(tmp_path):
    """Nothing wrong is a legitimate thing to send, and must not print
    an empty list of faults with no explanation."""
    folder = a_folder(tmp_path, [a_tick()])
    zipped, _packed = bugreport.write_zip(
        folder, bugreport.Verdict(), tmp_path / "out")
    with zipfile.ZipFile(zipped) as archive:
        text = archive.read("report.txt").decode()
    assert "sent by hand" in text


def test_grading_a_folder_with_no_log_says_so(tmp_path):
    folder = tmp_path / "empty"
    (folder / "gsi").mkdir(parents=True)
    (folder / "frames").mkdir()
    verdict = bugreport.grade(folder)
    assert not verdict.bad
    assert any("no state log" in note for note in verdict.notes)


# ---- where it goes ------------------------------------------------------

def test_the_address_is_the_projects_and_not_a_persons():
    """CLAUDE.md: NOTHING IN THIS REPOSITORY IDENTIFIES ITS OWNER.

    This string ships in everybody's copy, so a personal address here is
    one a spam harvester reads off the first public clone - and it would
    fail `test_no_personal_data` besides.
    """
    assert SUPPORT_EMAIL == "dotadraftassist@outlook.com"
    assert "@" in SUPPORT_EMAIL


def test_mailto_is_never_asked_to_carry_the_attachment():
    """`mailto:` CANNOT attach a file - no mainstream client honours
    `attach=`, and Outlook removed it around 2002 as a security hole.

    A link that quietly drops the file is worse than one that admits it
    cannot take it, because the person hits send on an empty report and
    nobody learns anything. This scans the source so that a later
    simplification down to "just use mailto" fails here rather than in
    somebody's inbox.
    """
    source = Path(mailer.__file__).read_text(encoding="utf-8")
    body = source.split('"""', 2)[2]          # drop the module docstring
    assert "attach" not in body.split("def _mailto")[1].split("def ")[0]
    assert "MAPISendMail" in body


def test_the_mailer_never_raises_and_always_answers(tmp_path, monkeypatch):
    """A mail client that will not open is a nuisance; an app that dies
    because it could not is worse."""
    monkeypatch.setattr(mailer, "_mapi", lambda *a, **k: False)
    monkeypatch.setattr(mailer, "reveal", lambda path: False)
    monkeypatch.setattr(mailer, "_mailto", lambda *a, **k: False)
    sent = mailer.send("a@b.c", "s", "b", tmp_path / "x.zip")
    assert isinstance(sent, mailer.Sent)
    assert sent.how == "nothing" and not sent.ok
    assert not sent.carried_the_file


def test_the_fallback_says_the_file_was_not_attached(tmp_path, monkeypatch):
    """"it opened an empty email" and "it opened one with your file on
    it" must not look the same from here."""
    monkeypatch.setattr(mailer, "_mapi", lambda *a, **k: False)
    monkeypatch.setattr(mailer, "reveal", lambda path: True)
    monkeypatch.setattr(mailer, "_mailto", lambda *a, **k: True)
    sent = mailer.send("a@b.c", "s", "b", tmp_path / "x.zip")
    assert sent.ok and not sent.carried_the_file
    assert "drag it" in sent.detail


def test_a_user_who_closed_the_draft_is_not_a_failure():
    """They saw the message and decided not to send it, which is the
    point of showing it; opening a second empty email at them there
    would be the app arguing."""
    assert mailer.MAPI_E_USER_ABORT == 1


@pytest.mark.parametrize("note,expected", [
    ("measured the crop boxes off 00007.png and saved them (...)", True),
    ("could not locate all ten portraits in any frame", False),
    ("", False),
])
def test_the_repair_note_is_what_says_whether_it_worked(note, expected):
    """One sentence, read in one place, rather than a second flag
    nobody would keep in step with it."""
    assert ("saved them" in note) is expected


# ---- what the window does with it ---------------------------------------

def test_the_banner_names_the_fault_and_offers_to_send(window):
    """THIRD RUNG. The two above it are faults happening NOW that cost
    the draft on screen; this one is about a draft already finished, so
    it must never stand in front of them."""
    folder = Path("recordings") / "2026-09-18_2000"
    verdict = bugreport.Verdict(faults=[bugreport.Fault(
        "crop_boxes", "the app could not find the hero portraits", "why")])
    window._bug = (folder, verdict, "could not locate all ten portraits")
    window._update_first_run_banner()
    assert window.banner.isVisible()
    assert "could not find the hero portraits" in window.banner_label.text()
    assert window.banner_button.text() == "Send bug report"


def test_a_draft_the_app_repaired_raises_no_banner(window):
    """Asking somebody to post a report about a fault the app has just
    cured is the app interrupting them about something that no longer
    matters."""
    folder = Path("recordings") / "2026-09-18_2000"
    verdict = bugreport.Verdict(faults=[bugreport.Fault(
        "crop_boxes", "the app could not find the hero portraits", "why",
        repairable=True)])
    window._bug = (folder, verdict,
                   "measured the crop boxes off 00007.png and saved them")
    assert window._repaired_itself()
    window._update_first_run_banner()
    assert not (window.banner.isVisible()
                and "portraits" in window.banner_label.text())


def test_a_new_draft_clears_the_last_verdict(window):
    """A banner about the game before this one, over a draft happening
    now, is the stale-board fault one surface over."""
    window._bug = ("folder", bugreport.Verdict(), "")

    class Snap:
        game_state = "DOTA_GAMERULES_STATE_HERO_SELECTION"

    window.auto_record_check.setChecked(False)
    window._consider_auto_record(Snap())
    assert window._graded() is None
