"""The recording measurer, on the case it was written for.

The app put the user's own team on the wrong side of the board in a real
match, and the reason is visible in the screenshot they sent: CHOOSE YOUR
LANE read 4/5. The rule that decides the teams outright needs exactly five
of your team standing on the strategy map's lane slots, so a team-mate who
never picked a lane drops it through to a coin flip.

These hold the tool to saying so - and to saying it in words that name the
missing hero rather than reporting that a rule "declined".
"""

import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
FIXTURE = ROOT / "tests" / "fixtures" / "gsi" / "strategy_slots_8000000002.json"


def load_tool():
    spec = importlib.util.spec_from_file_location(
        "measure_recording", ROOT / "tools" / "measure_recording.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


tool = load_tool()

NAMES = ["axe", "storm_spirit", "juggernaut", "rubick", "hoodwink",
         "riki", "grimstroke", "snapfire", "nyx_assassin", "winter_wyvern"]


class FakeDataset:
    """Enough of a dataset for the teams half: ids, internal names, names."""

    def __init__(self):
        self.heroes = {
            number: {"internal_name": f"npc_dota_hero_{name}",
                     "localized_name": name.replace("_", " ").title()}
            for number, name in enumerate(NAMES, 1)}

    def name(self, hero_id):
        return self.heroes.get(hero_id, {}).get("localized_name", "?")


@pytest.fixture
def payload():
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def a_recording(tmp_path: Path, payload, states) -> Path:
    folder = tmp_path / "2026-09-17_2031"
    (folder / "gsi").mkdir(parents=True)
    (folder / "frames").mkdir()
    (folder / "gsi" / "gsi_00001.json").write_text(
        json.dumps(payload), encoding="utf-8")
    (folder / "state.jsonl").write_text(
        "".join(json.dumps(row) + "\n" for row in states), encoding="utf-8")
    return folder


def test_it_finds_the_strategy_payload(tmp_path, payload):
    folder = a_recording(tmp_path, payload, [])
    assert tool.strategy_payload(folder) is not None


def test_a_recording_with_no_strategy_payload_says_so(tmp_path, capsys):
    folder = a_recording(tmp_path, {"map": {"game_state": "DOTA_GAMERULES_"
                                            "STATE_HERO_SELECTION"}}, [])
    assert tool.strategy_payload(folder) is None
    assert tool.say_teams(None, FakeDataset()) == []
    assert "cannot answer the teams question" in capsys.readouterr().out


def test_hero_selection_is_where_the_phases_part():
    states = [{"at": 1.0, "game_state": "DOTA_GAMERULES_STATE_HERO_SELECTION"},
              {"at": 40.0, "game_state": "DOTA_GAMERULES_STATE_HERO_SELECTION"},
              {"at": 55.0, "game_state": "DOTA_GAMERULES_STATE_STRATEGY_TIME"}]
    assert tool.phase_boundary(states) == 40.0
    assert tool.phase_boundary([]) is None


def test_the_five_on_five_case_reports_the_rule_fitting(payload, capsys):
    """The fixture is the settled case: five on the slots, five in the world."""
    ten = tool.say_teams(payload, FakeDataset())
    out = capsys.readouterr().out
    assert "on a lane slot: 5" in out
    assert "the strategy-slot rule fits" in out
    assert len(ten) == 10


def test_a_teammate_with_no_lane_is_named_rather_than_lost(payload, capsys):
    """THE CASE FROM THE USER'S OWN MATCH - CHOOSE YOUR LANE 4/5.

    One hero is moved off its lane slot to the origin, which is where a
    player who chose no lane comes through. The rule must decline, the
    tool must say the split is now a coin flip, and it must point at the
    hero standing at the origin as the likely team-mate - because that is
    the lead, and "a rule declined" is not.
    """
    for obj in payload["minimap"].values():
        if obj.get("unitname") == "npc_dota_hero_hoodwink":
            obj["xpos"], obj["ypos"] = 0, 0
    tool.say_teams(payload, FakeDataset())
    out = capsys.readouterr().out
    assert "on a lane slot: 4" in out
    assert "at the origin: 1" in out
    assert "IT DECLINES" in out
    assert "coin flip" in out
    assert "almost certainly YOURS" in out


def test_every_line_it_prints_is_ascii():
    """A Windows console is cp1252 and a report of a failure must not
    itself fail - the same rule `fetch_assets` learned the hard way."""
    source = (ROOT / "tools" / "measure_recording.py").read_bytes()
    assert not [byte for byte in source if byte > 127]


def test_it_writes_nothing(tmp_path, payload):
    """Stated in its own closing line, and held here: this tool reads."""
    folder = a_recording(tmp_path, payload, [])
    before = sorted(path.name for path in folder.rglob("*"))
    tool.strategy_payload(folder)
    tool.say_teams(payload, FakeDataset())
    assert sorted(path.name for path in folder.rglob("*")) == before
