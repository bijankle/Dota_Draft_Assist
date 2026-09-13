"""What the status line says the screen reader is doing.

Reported from a bot match: at strategy time the GAME fills the slots,
so a board full of heroes said nothing whatever about whether
recognition had run - and the portrait search takes SECONDS on a worker
with nothing on screen to say so. "I may close it before it's done."
"""

import sys
import types
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from draft_assist.ui import providers
from draft_assist.vision.library import EMPTY_SLOT


def slot(hero_id):
    return types.SimpleNamespace(hero_id=hero_id)


def provider(vision=object(), running=None, share=0.0):
    hybrid = providers.HybridProvider.__new__(providers.HybridProvider)
    hybrid.vision = vision
    import threading
    hybrid._search_lock = threading.Lock()
    hybrid._search_running = running
    hybrid._search_at = share
    return hybrid


def snap(read=None):
    return providers.Snapshot(read=read)


def test_vision_off_says_nothing_rather_than_failing():
    """Off is not a fault and must not read as one."""
    assert provider(vision=None).vision_note(snap()) == ""


def test_the_slow_search_is_the_one_that_gets_a_percentage():
    note = provider(running=("m", (1,)), share=0.42).vision_note(snap())
    assert "42%" in note
    assert "portrait" in note.lower()


def test_a_part_read_board_says_how_much():
    read = types.SimpleNamespace(
        slots=[slot(1), slot(2), slot(None), slot(EMPTY_SLOT)] + [slot(None)] * 6)
    assert provider().vision_note(snap(read)) == "screen: 2/10 read"


def test_a_finished_read_says_so_in_words():
    """"10/10" and "3/10" are the same shape at a glance, and the whole
    question being asked is whether it is safe to close the window."""
    read = types.SimpleNamespace(slots=[slot(i + 1) for i in range(10)])
    note = provider().vision_note(snap(read))
    assert "all 10" in note
    assert "/10" not in note


def test_nothing_read_yet_is_its_own_state():
    assert provider().vision_note(snap()) == "screen: not reading"


@pytest.mark.parametrize("read", [
    None,
    types.SimpleNamespace(),                       # no slots at all
    types.SimpleNamespace(slots=[]),               # empty
    types.SimpleNamespace(slots=[object()]),       # slots without hero_id
])
def test_it_never_raises_whatever_it_is_handed(read):
    """One cosmetic segment, written four times a second from inside the
    refresh loop. A shape it did not expect must cost the SENTENCE, never
    the tick - which is how a test double with no `.slots` took down
    seven tests the first time this shipped."""
    assert isinstance(provider().vision_note(snap(read)), str)


def test_the_note_is_stamped_in_one_place():
    """`_poll` has five exits; stamping at each is five chances to add a
    sixth and forget, and the forgotten one would go silently blank."""
    source = (ROOT / "draft_assist" / "ui" / "providers.py").read_text(
        encoding="utf-8")
    assert source.count("snap.vision_note = ") == 1


# --------------------------------------------------------------------
# THE RECOGNITION CHECK IS A BUTTON, at the user's request: "I still
# don't understand why I need to manually type this command into
# Command Prompt." They should not have to.


def test_the_recognition_check_is_a_task_the_app_can_run():
    from draft_assist.ui.tasks import TASKS
    task = TASKS["score_recognition"]
    assert any("score_recording.py" in part
               for step in task.steps for part in step)


def test_it_is_reachable_from_the_help_menu():
    source = (ROOT / "draft_assist" / "ui" / "app.py").read_text(
        encoding="utf-8")
    head = source[source.index('help_menu = bar.addMenu'):
                  source.index('self.help_menu = help_menu')]
    assert "_check_recognition" in head
    assert "Debug view" in head, "debugging was asked to live under Help"


def test_the_report_is_copied_rather_than_left_to_be_selected():
    """The thing done with the report is always the same - paste it back -
    and selecting a console window by hand is the step that makes
    somebody not bother. Same lesson as Debug > Copy everything."""
    source = (ROOT / "draft_assist" / "ui" / "app.py").read_text(
        encoding="utf-8")
    body = source[source.index("def _recognition_finished"):]
    body = body[:body.index("\n    def ")]
    assert "clipboard().setText" in body
    assert "toPlainText" in body
