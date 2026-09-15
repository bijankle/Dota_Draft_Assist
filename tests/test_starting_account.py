"""Which account the History tab opens on.

IT USED TO BE A PROFESSIONAL PLAYER'S PUBLIC FRIEND ID, so that the Run
button had a real match history behind it on a fresh install rather than
coming back empty and reading as a broken app. That is gone at the
user's request — "forget about topsons accoutn, that was a silly
addition" — and what replaces it is better: first-run setup ASKS for
your own friend ID, remembers it, and runs the analysis once. The tab
then opens on you from the first launch, which is what the example
account was standing in for.

So there is no starting value any more. The box opens on a remembered
account if there is one, and otherwise empty with a placeholder saying
where to set it.
"""

import os
import sys
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from draft_assist.history import store                   # noqa: E402


def test_nobody_elses_account_is_shipped():
    """A stranger's id in the source is a record about somebody who did
    not ask to be in this repository, and it only existed to give Run
    something to show. Setup asks for the user's own now."""
    source = (ROOT / "draft_assist/history/store.py").read_text(
        encoding="utf-8")
    assert "EXAMPLE_ACCOUNT" not in source
    assert "starting_account" not in source
    assert "94054712" not in source, "Topson's id is back in the source"
    assert "Topson" not in source


def test_no_module_still_asks_for_a_starting_account():
    """A caller left behind would be an AttributeError on the first
    opening of the History tab, which is exactly where nobody would see
    it until a fresh install."""
    for path in (ROOT / "draft_assist").rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        assert "starting_account" not in text, path.name
        assert "EXAMPLE_ACCOUNT" not in text, path.name


@pytest.mark.parametrize("remembered", [True, False])
def test_the_box_opens_on_a_remembered_account_or_on_nothing(
        tmp_path, monkeypatch, remembered):
    pytest.importorskip("PyQt6")
    from PyQt6.QtWidgets import QApplication, QWidget

    file = tmp_path / "accounts.json"
    monkeypatch.setattr(store, "STORE_FILE", file)
    from draft_assist.history import cache
    monkeypatch.setattr(cache, "CACHE_DIR", tmp_path / "history_cache")
    if remembered:
        store.remember(11223344, "Someone", path=file)

    app = QApplication.instance() or QApplication([])
    from draft_assist.ui.history_tab import HistoryTab

    host = QWidget()
    tab = HistoryTab(parent=host, settings={})
    app.processEvents()
    if remembered:
        assert tab.account_box.text().strip() == "11223344"
    else:
        assert tab.account_box.text().strip() == ""
        # AND IT SAYS WHERE TO SET IT. An empty box with no placeholder
        # is indistinguishable from a broken tab, which is the whole
        # reason a starting value existed in the first place.
        assert "friend ID" in tab.account_box.placeholderText()
    host.deleteLater()
