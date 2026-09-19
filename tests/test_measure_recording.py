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


def test_a_frame_is_labelled_with_the_state_that_was_live(capsys):
    """THE FAULT THE FIRST REAL RECORDING SHOWED.

    It kept ONE boundary - where hero selection ended - and called
    everything after it "strategy". A real session runs HERO_SELECTION,
    STRATEGY_TIME, TEAM_SHOWCASE, WAIT_FOR_MAP_TO_LOAD, PRE_GAME, so
    frames taken with the pick bar long gone were labelled strategy time
    and compared against frames where it is up.
    """
    states = [{"at": 1.0, "game_state": "DOTA_GAMERULES_STATE_HERO_SELECTION"},
              {"at": 40.0, "game_state": "DOTA_GAMERULES_STATE_HERO_SELECTION"},
              {"at": 55.0, "game_state": "DOTA_GAMERULES_STATE_STRATEGY_TIME"},
              {"at": 90.0, "game_state": "DOTA_GAMERULES_STATE_PRE_GAME"}]
    marks = tool.timeline(states)
    assert tool.state_at(marks, 10.0) == "HERO_SELECTION"
    assert tool.state_at(marks, 60.0) == "STRATEGY_TIME"
    # The one that was wrong: well past strategy time is NOT strategy.
    assert tool.state_at(marks, 100.0) == "PRE_GAME"
    # And past the END of the log it is not PRE_GAME either — the log
    # stops when the app stops hearing from Dota, and nothing after that
    # has any evidence behind it. See `test_a_state_expires...`.
    assert tool.state_at(marks, 200.0) == tool.PAST_THE_END
    assert tool.state_at([], 5.0) == "?"
    assert tool.state_at(marks, None) == "?"


def test_the_five_on_five_case_reports_the_rule_fitting(payload, capsys):
    """The fixture is the settled case: five on the slots, five in the world."""
    ten = tool.say_teams(payload, FakeDataset())
    out = capsys.readouterr().out
    assert "on a lane slot: 5" in out
    assert "the strategy-slot rule" in out and "cannot invert" in out
    # THE RULE IS READ OFF THE APP, never re-derived here.
    assert "strategy slots" in out
    assert "certain about the sides:  YES" in out
    assert len(ten) == 10


def test_ten_on_the_slots_is_the_paired_case_and_is_named_as_one(
        payload, capsys):
    """THE FAULT THE FIRST REAL RECORDING SHOWED, and the worse of the two.

    The user's own draft put all ten heroes on the five lane slots, two
    apiece - both teams' lanes predicted. `_split_by_lane_pairs` handles
    that perfectly well, and this tool told them the app had "fallen
    through to splitting the ten in list order, which is a coin flip",
    because it worked the answer out from the slot counts instead of
    asking. An answer assembled out of our own rules wearing the clothes
    of a measurement - inside the tool written to stop exactly that.
    """
    slots = sorted(minimap_lane_slots())
    for index, obj in enumerate(sorted(
            payload["minimap"].items(), key=lambda kv: kv[0])):
        obj[1]["xpos"], obj[1]["ypos"] = slots[index % len(slots)]
    tool.say_teams(payload, FakeDataset())
    out = capsys.readouterr().out
    assert "ALL TEN stand on the lane slots" in out
    assert "PAIRED case" in out
    # And it must NOT claim the app fell through to object order.
    assert "list order" not in out


def minimap_lane_slots():
    from draft_assist.gsi import minimap
    return minimap.LANE_SLOTS


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
    assert "declines" in out
    assert "certainly YOURS" in out   # wrapped across two printed lines


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


def test_the_button_asks_for_the_table_row():
    """The in-app button is the whole route a measurement takes back.

    `--row` prints the line that goes into `vision/measured.py`'s EXACT,
    and that table is the only reason somebody plays a bot draft at a
    resolution they do not use. A button that printed everything except
    that line would leave the measurement taken and unreachable — the
    "produced where nobody is looking" fault this project has already
    paid for with the proof sheet nothing ever opened.
    """
    from draft_assist.ui.tasks import TASKS

    steps = TASKS["measure_recording"].steps
    assert len(steps) == 1
    assert "--row" in steps[0], steps[0]


def test_a_state_expires_rather_than_running_for_ever():
    """A real run measured seven frames of the Dota MENU and printed
    six fractions off them.

    The user closed Dota a few seconds into strategy time, exactly as
    asked. The state log therefore stopped at 32s — and the recorder
    kept saving frames for another twenty minutes, all of which this
    labelled STRATEGY_TIME because the last named state was carried
    forward with no end. The tool then reported that "the bar moves
    between the two screens", which is an answer assembled out of our
    own bookkeeping standing where a measurement goes.
    """
    from tools.measure_recording import PAST_THE_END, state_at

    marks = [(0.0, "HERO_SELECTION"), (3.0, "STRATEGY_TIME"),
             (32.0, "STRATEGY_TIME")]
    assert state_at(marks, 0) == "HERO_SELECTION"
    assert state_at(marks, 10) == "STRATEGY_TIME"
    # a short gap is the feed stuttering, not the session ending
    assert state_at(marks, 40) == "STRATEGY_TIME"
    # twenty minutes later there is no evidence of anything
    assert state_at(marks, 164) == PAST_THE_END
    assert state_at(marks, 1149) == PAST_THE_END


def test_the_drafting_states_are_derived_from_the_app():
    """Two hand-written lists is one of them going stale."""
    from draft_assist.gsi import state as gsi_state
    from tools.measure_recording import BAR_IS_UP

    assert BAR_IS_UP == {n.replace("DOTA_GAMERULES_STATE_", "")
                         for n in gsi_state.DRAFTING_STATES}
    assert "HERO_SELECTION" in BAR_IS_UP


# ---- the frame is the client, not the window ---------------------------

def test_an_odd_frame_size_is_not_a_display_resolution():
    """Every mode a monitor has ever offered is even in both axes, and
    all four padded recordings came back odd: 1375, 1929, 3449."""
    from tools import measure_recording as mr

    for size in [(1375, 800), (1929, 1112), (3449, 1472), (1929, 1232)]:
        assert mr.looks_padded(*size), f"{size} is a window, not a client"
    for size in [(1366, 768), (1920, 1080), (3440, 1440), (1920, 1200)]:
        assert not mr.looks_padded(*size), f"{size} is a real resolution"


def test_the_chrome_is_what_three_displays_measured():
    from tools import measure_recording as mr

    for client, captured in [((1366, 768), (1375, 800)),
                             ((1920, 1080), (1929, 1112)),
                             ((1920, 1200), (1929, 1232)),
                             ((3440, 1440), (3449, 1472))]:
        assert (captured[0] - client[0],
                captured[1] - client[1]) == mr.CHROME


def test_a_padded_frame_is_refused_a_row(capsys):
    """It would bake a buffer size into a table keyed by display size,
    for every install of this app, permanently."""
    from tools import measure_recording as mr

    class Fit:
        radiant_x = dire_x = y = slot_w = slot_h = pitch = 0.05

    rows = [{"layout": Fit(), "found": 10, "size": (1929, 1232)}
            for _ in range(3)]
    mr.say_row(rows)
    out = capsys.readouterr().out
    assert "NO ROW" in out
    assert "1920x1200" in out, "it should name what the frame really was"
    assert "Reading(" not in out


def test_a_clean_frame_still_gets_its_row(capsys):
    from tools import measure_recording as mr

    class Fit:
        radiant_x = 0.05
        dire_x = 0.5926
        y = 0.0052
        slot_w = 0.0692
        slot_h = 0.0525
        pitch = 0.0709

    rows = [{"layout": Fit(), "found": 10, "size": (1920, 1200)}
            for _ in range(3)]
    mr.say_row(rows)
    out = capsys.readouterr().out
    assert "Reading(" in out and "(1920, 1200)" in out


# ---- a row is written from frames that agree, and never from one ------

class Fit:
    """A fitted layout with every fraction settable."""

    def __init__(self, **kw):
        self.radiant_x = kw.get("radiant_x", 0.1052)
        self.dire_x = kw.get("dire_x", 0.5710)
        self.y = kw.get("y", 0.0056)
        self.slot_w = kw.get("slot_w", 0.0615)
        self.slot_h = kw.get("slot_h", 0.0611)
        self.pitch = kw.get("pitch", 0.0652)


def frames_of(size, fits):
    return [{"layout": f, "found": 10, "size": size} for f in fits]


def test_one_frame_is_never_a_row(capsys):
    """A single frame agrees with itself to 0.0000 whatever it fitted, so
    every spread check passes vacuously. A real 1024x768 run printed a
    paste-ready row off one hero-selection frame whose own left origin
    was out by a factor of thirty."""
    from tools import measure_recording as mr

    mr.say_row(frames_of((1024, 768), [Fit(y=0.0697, slot_w=0.0264,
                                           pitch=0.0669, radiant_x=0.0068,
                                           dire_x=0.5039, slot_h=0.0456)]))
    out = capsys.readouterr().out
    assert "NO ROW" in out and "Reading(" not in out


def test_a_bad_fit_is_dropped_rather_than_vetoing_the_rest(capsys):
    """1280x1024: six strategy frames identical to four decimal places
    with all ten boxes landing, refused because two hero-selection frames
    in the same recording had fitted the CHOOSE YOUR HERO grid."""
    from tools import measure_recording as mr

    good = Fit(dire_x=0.5922, y=0.0059, slot_w=0.0695, slot_h=0.0488,
               pitch=0.0703, radiant_x=0.0555)
    roster = Fit(dire_x=0.40, y=0.1670, slot_w=0.030, slot_h=0.0469,
                 pitch=0.031, radiant_x=0.02)
    mr.say_row(frames_of((1280, 1024), [roster] + [good] * 6))
    out = capsys.readouterr().out
    assert "Reading(" in out, out
    assert "(1280, 1024)" in out
    assert "slot_h=0.0488" in out
    assert "1 frame(s) set aside" in out


def test_a_left_origin_that_cannot_be_the_mirror_is_refused(capsys):
    """The bar is centred on the HUD span, so the mirror of the right
    bank IS the left one - within a few pixels on every frame that has
    located ten. A big gap is a missed leading portrait."""
    from tools import measure_recording as mr

    broken = Fit(radiant_x=0.0068, dire_x=0.5039, slot_w=0.0264,
                 pitch=0.0669)
    mr.say_row(frames_of((1024, 768), [broken] * 4))
    out = capsys.readouterr().out
    assert "NO ROW" in out and "Reading(" not in out
    assert "leading portrait was missed" in out or "missed" in out


def test_frames_that_all_agree_still_get_their_row(capsys):
    from tools import measure_recording as mr

    good = Fit(dire_x=0.5938, y=0.0058, slot_w=0.0682, slot_h=0.0617,
               pitch=0.0719, radiant_x=0.0500)
    mr.say_row(frames_of((1920, 1200), [good] * 5))
    out = capsys.readouterr().out
    assert "(1920, 1200)" in out and "slot_h=0.0617" in out
