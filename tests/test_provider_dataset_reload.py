"""The provider's dataset is a different object from the window's.

`MainWindow.reload_backend` re-read the statistics into its own
`self.ds` and left the provider holding whatever existed when the
window was built. On a fresh install that is the EMPTY dataset - there
are no statistics until the wizard fetches them - so the GSI parser
could not name a single hero the minimap reported, for the life of the
process, while everything on screen looked perfectly healthy because
everything on screen reads the window's copy.

Reported as a whole bot match that read one hero: "153 ticks none",
and 90 notes reading "minimap named heroes this dataset does not know"
listing all ten.
"""

import ast

import pytest

from draft_assist.data import store
from draft_assist.gsi import state as gsi_state
from draft_assist.ui.demo import demo_dataset
from draft_assist.ui.providers import GsiProvider, HybridProvider


@pytest.fixture
def named():
    ds = demo_dataset()
    for hid, info in ds.heroes.items():
        slug = info["name"].lower().replace(" ", "_").replace("'", "")
        info["internal_name"] = f"npc_dota_hero_{slug}"
    return ds


def test_an_empty_dataset_knows_no_internal_names():
    """The premise. If this ever stops being true the bug changes shape."""
    assert gsi_state._hero_id_by_internal_name(store.empty_dataset()) == {}


def test_a_reloaded_dataset_reaches_the_parser(named):
    provider = GsiProvider(store.empty_dataset(), server=None)
    assert gsi_state._hero_id_by_internal_name(provider.ds) == {}
    provider.set_dataset(named)
    resolved = gsi_state._hero_id_by_internal_name(provider.ds)
    assert len(resolved) == len(named.heroes)


def test_the_hybrid_passes_it_down(named):
    gsi = GsiProvider(store.empty_dataset(), server=None)
    hybrid = HybridProvider(gsi, vision=None)
    hybrid.set_dataset(named)
    assert hybrid.gsi.ds is named


def test_reload_backend_pushes_the_dataset_to_the_provider():
    """The line that was missing. A reload that updates only the window
    leaves the parser on the dataset the app started with."""
    from pathlib import Path
    text = Path("draft_assist/ui/app.py").read_text(encoding="utf-8")
    tree = ast.parse(text)
    body = None
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "reload_backend":
            body = ast.dump(node)
    assert body is not None, "reload_backend has gone"
    assert "set_dataset" in body, (
        "reload_backend re-reads the dataset without handing it to the "
        "provider, which is the whole of this bug")
