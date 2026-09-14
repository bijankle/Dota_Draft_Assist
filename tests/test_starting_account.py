"""Which account the History tab opens on, and for how long.

"i think it would be cool to have topson steam ID be the one that gets
used for the app by default... i think it is 94054712", and then what
"by default" means: "by default i mean only when its being setup. If the
user searches for their account to analyse it should be remembered and
appear when the app is closed and reopened."

So it is the value the box STARTS on, not a preference and not a
remembered account — the Run button has something real behind it on a
fresh install, and the moment anybody measures an account of their own
that one takes over permanently.
"""

import os
import sys
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from draft_assist.history import account, store          # noqa: E402


def test_a_fresh_machine_starts_on_the_example(tmp_path):
    assert store.starting_account(tmp_path / "none.json") \
        == store.EXAMPLE_ACCOUNT


def test_and_stops_the_moment_the_user_has_one_of_their_own(tmp_path):
    """The whole of "only when its being setup"."""
    file = tmp_path / "accounts.json"
    store.remember(11223344, "Someone", path=file)
    assert store.starting_account(file) is None


def test_the_example_is_never_written_into_the_remembered_list(tmp_path):
    """That file is the accounts THIS MACHINE has looked at. An entry
    nobody ran would read as a run that happened — and it would then be
    adopted on the next start, which is exactly the thing that is
    supposed to stop once the user has their own."""
    file = tmp_path / "accounts.json"
    store.starting_account(file)
    assert store.load(file) == []
    assert not file.exists()


def test_the_app_can_actually_parse_it():
    """A starting value the parser refuses would open the tab on a box
    that cannot be run, which is worse than an empty one."""
    parsed = account.parse(str(store.EXAMPLE_ACCOUNT))
    assert parsed.ok
    assert parsed.account_id == store.EXAMPLE_ACCOUNT
    assert store.EXAMPLE_ACCOUNT <= account.MAX_ACCOUNT_ID


def test_it_is_a_REAL_account_and_that_is_the_point_here():
    """The opposite of the rule the test FIXTURES follow.

    `test_the_example_account_is_not_a_real_one` requires a made-up id,
    because there the number stands in for the player themselves and
    pinning a stranger to that data would be inventing a record about
    them. Here the tab needs a public match history to measure: a number
    that cannot exist comes back with no matches, which is one of the
    three things "your history is private" is meant to tell apart, and
    it would read as the app being broken on its first run.

    Held as a test because the two rules contradict each other on
    purpose, and a later sweep for "example account ids" would otherwise
    correct this one into uselessness.
    """
    from draft_assist.history import account as acct

    assert store.EXAMPLE_ACCOUNT < 2_500_000_000, (
        "inside the range Steam has allocated, unlike the fixtures' id")
    # And the two must never be confused for one another.
    import tests.test_no_personal_data as privacy          # noqa: F401
    assert store.EXAMPLE_ACCOUNT != 4242424242
    assert acct.parse(str(store.EXAMPLE_ACCOUNT)).ok


@pytest.mark.parametrize("remembered", [False, True])
def test_the_tab_opens_on_the_right_one(tmp_path, monkeypatch, remembered):
    """End to end, through the tab's own start-up path."""
    from PyQt6.QtWidgets import QApplication

    file = tmp_path / "accounts.json"
    monkeypatch.setattr(store, "STORE_FILE", file)
    if remembered:
        store.remember(11223344, "Someone", path=file)

    app = QApplication.instance() or QApplication([])
    from draft_assist.ui.history_tab import HistoryTab

    from PyQt6.QtWidgets import QWidget
    host = QWidget()
    tab = HistoryTab(parent=host, settings={})
    app.processEvents()
    expected = "11223344" if remembered else str(store.EXAMPLE_ACCOUNT)
    assert tab.account_box.text().strip() == expected
    host.deleteLater()
