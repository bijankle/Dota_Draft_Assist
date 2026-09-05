"""Game State Integration: config installation, the local listener, payload
parsing, and the provider that merges game data with hand-entered slots.

The parser's contract is that it never invents state. GSI's `draft` block is
understood to be a spectator component, so a player's own feed probably
cannot see the enemy line-up — these tests pin down that BOTH cases behave
correctly, so whichever one real payloads turn out to be, the app is right.
"""

import json
from pathlib import Path
import urllib.request

import pytest

from draft_assist.gsi import install as gsi_install
from draft_assist.gsi import state as gsi_state
from draft_assist.gsi.server import GsiServer
from draft_assist.ui.demo import demo_dataset
from draft_assist.ui.manual import ManualDraft, merge
from draft_assist.ui.providers import GsiProvider, ManualProvider


@pytest.fixture(scope="module")
def dataset():
    ds = demo_dataset()
    for hid, info in ds.heroes.items():
        slug = info["name"].lower().replace(" ", "_").replace("'", "")
        info["internal_name"] = f"npc_dota_hero_{slug}"
    return ds


def internal(dataset, hero_id):
    return dataset.heroes[hero_id]["internal_name"]


# ---- config installation ---------------------------------------------

def test_render_config_is_valid_keyvalues():
    text = gsi_install.render_config(53000, "tok3n")
    assert '"uri"        "http://127.0.0.1:53000/"' in text
    assert '"token"  "tok3n"' in text
    assert text.count("{") == text.count("}")
    for component in ("provider", "map", "player", "hero", "draft"):
        assert f'"{component}"  "1"' in text


def test_install_writes_config_and_is_idempotent(tmp_path, monkeypatch):
    dota = tmp_path / "dota 2 beta"
    (dota / "game" / "dota").mkdir(parents=True)
    monkeypatch.setattr(gsi_install, "find_dota_dir", lambda *a, **k: dota)

    first = gsi_install.install(port=53000, token="fixed")
    assert first.created
    assert first.config_path.exists()
    assert first.config_path.parent.name == "gamestate_integration"

    again = gsi_install.install(port=53000, token="fixed")
    assert not again.created          # unchanged config is not rewritten
    assert gsi_install.read_installed_token() == "fixed"


def test_find_dota_dir_reports_where_it_looked(monkeypatch, tmp_path):
    monkeypatch.setattr(gsi_install, "_steam_roots", lambda: [tmp_path])
    monkeypatch.delenv("DOTA_DIR", raising=False)
    with pytest.raises(gsi_install.DotaNotFound) as excinfo:
        gsi_install.find_dota_dir()
    assert "Looked in" in str(excinfo.value)


def test_library_paths_reads_libraryfolders_vdf(tmp_path):
    steamapps = tmp_path / "steamapps"
    steamapps.mkdir()
    (steamapps / "libraryfolders.vdf").write_text(
        '"libraryfolders"\n{\n  "0"\n  {\n    "path"  "D:\\\\Games\\\\Steam"\n'
        '  }\n}\n', encoding="utf-8")
    paths = gsi_install._library_paths(tmp_path)
    # Dota is very often on a different drive from Steam itself.
    assert any("Games" in str(p) for p in paths)


# ---- the listener ------------------------------------------------------

def post(port, payload):
    urllib.request.urlopen(f"http://127.0.0.1:{port}/",
                           json.dumps(payload).encode()).read()


def free_port() -> int:
    """A port nothing is using. The listener binds exclusively, so tests
    must not reuse fixed ports that may still be settling."""
    import socket
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


def test_server_accepts_authenticated_payloads():
    port = free_port()
    server = GsiServer(port, token="secret")
    server.start()
    try:
        post(port, {"auth": {"token": "secret"},
                     "map": {"game_state": gsi_state.STATE_HERO_SELECTION}})
        snap = server.snapshot()
        assert snap.count == 1 and snap.live
        assert snap.payload["map"]["game_state"] == gsi_state.STATE_HERO_SELECTION
    finally:
        server.stop()


def test_server_rejects_wrong_token():
    """Another local program must not be able to feed us game state."""
    port = free_port()
    server = GsiServer(port, token="secret")
    server.start()
    try:
        post(port, {"auth": {"token": "wrong"}, "map": {}})
        snap = server.snapshot()
        assert snap.count == 0 and snap.rejected == 1
        assert "auth token" in snap.last_error
    finally:
        server.stop()


def test_server_archives_payloads(tmp_path):
    port = free_port()
    server = GsiServer(port, token=None, archive_dir=tmp_path)
    server.start()
    try:
        post(port, {"map": {"game_state": "X"}})
        post(port, {"map": {"game_state": "Y"}})
    finally:
        server.stop()
    archived = sorted(tmp_path.glob("gsi_*.json"))
    assert len(archived) == 2
    assert json.loads(archived[0].read_text())["map"]["game_state"] == "X"


# ---- parsing -----------------------------------------------------------

def test_player_feed_reports_own_hero_but_not_the_enemy(dataset):
    """The expected real-world case: no draft block, so only your own hero
    is known and the app must say so rather than invent picks."""
    payload = {
        "provider": {"name": "Dota 2"},
        "map": {"game_state": gsi_state.STATE_HERO_SELECTION,
                "matchid": "7891"},
        "player": {"team_name": "radiant", "name": "Bij"},
        "hero": {"id": 5, "name": internal(dataset, 5)},
    }
    state = gsi_state.parse(payload, dataset)
    assert state.drafting
    assert state.match_id == "7891"
    assert state.my_team == "radiant"
    assert state.my_hero_id == 5
    assert state.allies == [5]          # your own locked pick counts
    assert state.enemies == []
    assert not state.has_full_draft
    assert any("no 'draft' block" in n for n in state.notes)
    assert state.capabilities["hero"] and not state.capabilities["draft"]


def test_spectator_feed_with_draft_block_yields_both_lineups(dataset):
    """If a real payload ever carries the draft block, the app uses it and
    manual entry becomes unnecessary."""
    radiant = [1, 2, 3, 4, 5]
    dire = [11, 12, 13, 14, 15]
    payload = {
        "map": {"game_state": gsi_state.STATE_HERO_SELECTION},
        "player": {"team_name": "radiant"},
        "draft": {
            "team2": {f"pick{i}_id": h for i, h in enumerate(radiant)},
            "team3": {f"pick{i}_class": internal(dataset, h)
                      for i, h in enumerate(dire)},
        },
    }
    state = gsi_state.parse(payload, dataset)
    assert state.allies == radiant
    assert state.enemies == dire       # resolved from hero class names
    assert state.has_full_draft


def test_draft_block_sides_follow_your_team(dataset):
    payload = {
        "map": {"game_state": gsi_state.STATE_HERO_SELECTION},
        "player": {"team_name": "dire"},
        "draft": {"team2": {"pick0_id": 1}, "team3": {"pick0_id": 11}},
    }
    state = gsi_state.parse(payload, dataset)
    assert state.allies == [11] and state.enemies == [1]


def test_unfilled_draft_slots_are_skipped(dataset):
    payload = {
        "map": {"game_state": gsi_state.STATE_HERO_SELECTION},
        "player": {"team_name": "radiant"},
        "draft": {"team2": {"pick0_id": 1, "pick1_id": 0, "pick2_class": ""},
                  "team3": {}},
    }
    state = gsi_state.parse(payload, dataset)
    assert state.allies == [1] and state.enemies == []


def test_parse_survives_junk(dataset):
    assert gsi_state.parse({}, dataset).game_state == ""
    assert gsi_state.parse({"map": "nonsense"}, dataset).game_state == ""
    assert gsi_state.parse([], dataset).notes


# ---- manual overlay ----------------------------------------------------

def test_merge_prefers_game_data_and_deduplicates():
    assert merge([1, 2], [3, 1]) == [1, 2, 3]
    assert merge([], [4, 5]) == [4, 5]
    assert len(merge([1, 2, 3, 4, 5], [6])) == 5


def test_manual_draft_slots():
    manual = ManualDraft()
    assert manual.is_empty
    manual.set_slot("enemy", 2, 42)
    assert manual.entered("enemy") == [42]
    assert not manual.is_empty
    manual.set_slot("enemy", 2, None)
    assert manual.entered("enemy") == []
    manual.set_slot("ally", 0, 7)
    manual.clear()
    assert manual.is_empty


# ---- provider ----------------------------------------------------------

class FakeServer:
    port = 53000

    def __init__(self, payload=None, live=True, count=1):
        from draft_assist.gsi.server import Reception
        import time as _time
        self._reception = Reception(
            payload=payload,
            received_at=_time.monotonic() if live else 0.0,
            count=count)
        self.token = None
        self.started = False

    def start(self):
        self.started = True

    def stop(self):
        self.started = False

    def snapshot(self):
        return self._reception


def test_provider_fills_missing_picks_from_manual_entry(dataset):
    """The core of the design: the game supplies what it can, the user
    clicks in the rest, and nothing is guessed."""
    payload = {
        "map": {"game_state": gsi_state.STATE_HERO_SELECTION},
        "player": {"team_name": "radiant"},
        "hero": {"id": 5},
    }
    manual = ManualDraft()
    manual.set_slot("enemy", 0, 11)
    manual.set_slot("enemy", 1, 12)
    provider = GsiProvider(dataset, FakeServer(payload), manual)
    snap = provider.poll()
    assert snap.left == [5]              # from the game
    assert snap.right == [11, 12]        # entered by hand
    assert snap.needs_manual
    assert snap.mode == "draft"
    assert snap.gsi_capabilities["hero"]


def test_provider_does_not_need_manual_when_game_reports_everything(dataset):
    payload = {
        "map": {"game_state": gsi_state.STATE_HERO_SELECTION},
        "player": {"team_name": "radiant"},
        "draft": {"team2": {f"pick{i}_id": i + 1 for i in range(5)},
                  "team3": {f"pick{i}_id": i + 11 for i in range(5)}},
    }
    provider = GsiProvider(dataset, FakeServer(payload), ManualDraft())
    snap = provider.poll()
    assert not snap.needs_manual
    assert len(snap.left) == 5 and len(snap.right) == 5


def test_provider_explains_silence_from_dota(dataset):
    manual = ManualDraft()
    provider = GsiProvider(dataset, FakeServer(payload=None, count=0), manual,
                           install_hint="hint text")
    snap = provider.poll()
    assert "no data from Dota yet" in snap.warning
    assert "hint text" in snap.warning
    assert snap.needs_manual


def test_provider_warns_when_the_feed_goes_quiet(dataset):
    payload = {"map": {"game_state": gsi_state.STATE_IN_PROGRESS}}
    provider = GsiProvider(dataset, FakeServer(payload, live=False),
                           ManualDraft())
    snap = provider.poll()
    assert "stopped sending data" in snap.warning


def test_manual_provider_stands_alone():
    manual = ManualDraft()
    manual.set_slot("ally", 0, 1)
    manual.set_slot("enemy", 0, 11)
    provider = ManualProvider(manual)
    assert "manual" in provider.start()
    snap = provider.poll()
    assert snap.left == [1] and snap.right == [11]
    assert snap.mode == "manual"


# ---- diagnostics -------------------------------------------------------

def test_diagnose_names_the_missing_config(tmp_path, monkeypatch):
    """The launch option alone does nothing: without a config file Dota has
    nothing to send, and that must be the reported cause."""
    from draft_assist.gsi import diagnose

    dota = tmp_path / "dota 2 beta"
    (dota / "game" / "dota").mkdir(parents=True)
    monkeypatch.setattr(gsi_install, "find_dota_dir", lambda *a, **k: dota)
    monkeypatch.setattr(diagnose, "_steam_userdata_launch_options",
                        lambda *a, **k: "-gamestateintegration -novid")

    checks = diagnose.run_checks(port=53000)
    by_name = {c.name: c for c in checks}
    assert by_name["Dota installation"].ok is True
    assert by_name["Dota launch options"].ok is True
    assert by_name["GSI config installed"].ok is False
    assert "Set up game data" in by_name["GSI config installed"].fix
    assert "GSI config installed" in diagnose.headline(checks)


def test_diagnose_flags_a_missing_launch_option(tmp_path, monkeypatch):
    from draft_assist.gsi import diagnose

    dota = tmp_path / "dota 2 beta"
    (dota / "game" / "dota").mkdir(parents=True)
    monkeypatch.setattr(gsi_install, "find_dota_dir", lambda *a, **k: dota)
    gsi_install.install(port=53000, token="t", dota_dir=dota)
    monkeypatch.setattr(diagnose, "_steam_userdata_launch_options",
                        lambda *a, **k: "-novid -high")

    checks = {c.name: c for c in diagnose.run_checks(port=53000)}
    assert checks["GSI config installed"].ok is True
    assert checks["Dota launch options"].ok is False
    assert "-gamestateintegration" in checks["Dota launch options"].fix


def test_diagnose_catches_a_port_mismatch(tmp_path, monkeypatch):
    """A config written for one port while the app listens on another is
    silent in exactly the same way as everything else."""
    from draft_assist.gsi import diagnose

    dota = tmp_path / "dota 2 beta"
    (dota / "game" / "dota").mkdir(parents=True)
    monkeypatch.setattr(gsi_install, "find_dota_dir", lambda *a, **k: dota)
    gsi_install.install(port=53000, token="t", dota_dir=dota)
    monkeypatch.setattr(diagnose, "_steam_userdata_launch_options",
                        lambda *a, **k: "-gamestateintegration")

    checks = {c.name: c for c in diagnose.run_checks(port=53999)}
    assert checks["Config port matches listener"].ok is False
    assert "53000" in checks["Config port matches listener"].detail


def test_diagnose_reports_rejected_payloads(tmp_path, monkeypatch):
    from draft_assist.gsi import diagnose
    from draft_assist.gsi.server import Reception

    dota = tmp_path / "dota 2 beta"
    (dota / "game" / "dota").mkdir(parents=True)
    monkeypatch.setattr(gsi_install, "find_dota_dir", lambda *a, **k: dota)
    gsi_install.install(port=53000, token="t", dota_dir=dota)
    monkeypatch.setattr(diagnose, "_steam_userdata_launch_options",
                        lambda *a, **k: "-gamestateintegration")

    class Server:
        port = 53000

        def snapshot(self):
            return Reception(count=0, rejected=7,
                             last_error="auth token mismatch")

    checks = {c.name: c for c in diagnose.run_checks(server=Server())}
    assert checks["Payloads received"].ok is False
    assert "7 rejected" in checks["Payloads received"].detail
    assert "token" in checks["Payloads received"].fix


def test_diagnose_explains_silence_when_all_checks_pass(tmp_path, monkeypatch):
    """Everything correct but no data is the normal state in the main menu,
    and the report must say so rather than implying a fault."""
    from draft_assist.gsi import diagnose
    from draft_assist.gsi.server import Reception

    dota = tmp_path / "dota 2 beta"
    (dota / "game" / "dota").mkdir(parents=True)
    monkeypatch.setattr(gsi_install, "find_dota_dir", lambda *a, **k: dota)
    gsi_install.install(port=53000, token="t", dota_dir=dota)
    monkeypatch.setattr(diagnose, "_steam_userdata_launch_options",
                        lambda *a, **k: "-gamestateintegration")
    monkeypatch.setattr(diagnose, "_port_is_listening", lambda port: True)

    class Server:
        port = 53000

        def snapshot(self):
            return Reception(count=0, rejected=0)

    report = diagnose.format_report(diagnose.run_checks(server=Server()))
    assert "only while you are IN a match" in report


def test_launch_option_parser_reads_the_dota_block(tmp_path, monkeypatch):
    from draft_assist.gsi import diagnose

    config = tmp_path / "userdata" / "1234" / "config"
    config.mkdir(parents=True)
    (config / "localconfig.vdf").write_text('''
"UserLocalConfigStore"
{
  "Software" { "Valve" { "Steam" { "apps"
  {
    "730" { "LaunchOptions" "-novid" }
    "570" { "LastPlayed" "1700000000" "LaunchOptions" "-gamestateintegration" }
  } } } }
}
''', encoding="utf-8")
    monkeypatch.setattr(gsi_install, "_steam_roots", lambda: [tmp_path])
    # Must read Dota's block, not the first LaunchOptions in the file.
    assert diagnose._steam_userdata_launch_options() == "-gamestateintegration"


# ---- port exclusivity --------------------------------------------------

def test_two_servers_cannot_share_a_port():
    """On Windows SO_REUSEADDR would let a second copy bind the same port and
    silently receive nothing while the first got every payload — two windows
    disagreeing about whether Dota is sending. The bind must be exclusive."""
    port = free_port()
    first = GsiServer(port)
    first.start()
    try:
        second = GsiServer(port)
        with pytest.raises(OSError):
            second.start(attempts=1)
    finally:
        first.stop()


def test_provider_reports_a_port_clash_persistently(dataset):
    """A failed bind looks exactly like Dota being silent, so it has to be
    stated every poll rather than in a status message that scrolls away."""
    class ClashingServer:
        port = 53000
        token = None

        def start(self):
            raise OSError(98, "Address already in use")

        def stop(self):
            pass

        def snapshot(self):
            from draft_assist.gsi.server import Reception
            return Reception()

    provider = GsiProvider(dataset, ClashingServer(), ManualDraft())
    message = provider.start()
    assert "could not open the GSI port" in message
    assert provider.bind_error
    for _ in range(3):                      # sticky across polls
        snap = provider.poll()
        assert "already in use" in snap.warning
        assert "another copy" in snap.warning


def test_diagnose_blames_the_other_copy_not_dota(tmp_path, monkeypatch):
    from draft_assist.gsi import diagnose
    from draft_assist.gsi.server import Reception

    dota = tmp_path / "dota 2 beta"
    (dota / "game" / "dota").mkdir(parents=True)
    monkeypatch.setattr(gsi_install, "find_dota_dir", lambda *a, **k: dota)
    gsi_install.install(port=53000, token="t", dota_dir=dota)
    monkeypatch.setattr(diagnose, "_steam_userdata_launch_options",
                        lambda *a, **k: "-gamestateintegration")

    class Server:
        port = 53000
        _bind_error = "port in use"

        def snapshot(self):
            return Reception(count=0, rejected=0)

    checks = {c.name: c for c in diagnose.run_checks(server=Server())}
    assert checks["GSI port owned by this app"].ok is False
    assert "another copy" in checks["GSI port owned by this app"].fix.lower()


# ---- the simulator -----------------------------------------------------

def test_modelled_scenario_matches_a_real_player_feed(dataset):
    """Without the draft block — the expected real case — the scenario must
    yield your own hero and NO enemies, never a fabricated line-up."""
    from draft_assist.gsi import simulate

    steps = simulate.all_pick_scenario(dataset, token="t", speed=100)
    assert steps and all(s.payload["auth"]["token"] == "t" for s in steps)

    states = [gsi_state.parse(s.payload, dataset) for s in steps]
    assert states[0].game_state == gsi_state.STATE_HERO_SELECTION
    assert states[0].drafting
    assert states[-1].game_state == gsi_state.STATE_IN_PROGRESS

    locked = [s for s in states if s.my_hero_id is not None]
    assert locked, "the scenario never locks in a hero"
    assert all(s.enemies == [] for s in states)
    assert all(not s.has_full_draft for s in states)


def test_modelled_scenario_can_rehearse_a_full_draft(dataset):
    """With the draft block on, the app must use it and stop asking for
    manual entry — the rehearsal for GSI turning out richer than expected."""
    from draft_assist.gsi import simulate

    steps = simulate.all_pick_scenario(dataset, token="t",
                                       include_draft_block=True, speed=100)
    final = gsi_state.parse(steps[-2].payload, dataset)
    assert len(final.allies) == 5 and len(final.enemies) == 5
    assert final.has_full_draft


def test_replay_scenario_reads_archives_and_retokens(tmp_path):
    """Archived payloads were recorded under an old token; replaying must
    rewrite it or every one would be rejected."""
    from draft_assist.gsi import simulate

    (tmp_path / "gsi_00001.json").write_text(json.dumps(
        {"auth": {"token": "OLD"},
         "map": {"game_state": gsi_state.STATE_HERO_SELECTION}}))
    (tmp_path / "gsi_00002.json").write_text(json.dumps(
        {"map": {"game_state": gsi_state.STATE_IN_PROGRESS}}))
    (tmp_path / "gsi_00003.json").write_text("not json")

    steps = simulate.replay_scenario(tmp_path, token="NEW")
    assert len(steps) == 2                      # unreadable file skipped
    assert all(s.payload["auth"]["token"] == "NEW" for s in steps)
    assert "gsi_00001.json" in steps[0].label
    assert "Hero Selection" in steps[0].label

    with pytest.raises(FileNotFoundError):
        simulate.replay_scenario(tmp_path / "nothing-here")


def test_simulator_drives_the_real_ingestion_path(dataset):
    """The point of the simulator: exercise listener, auth and parser, not
    just inject state into the UI the way --demo does."""
    from draft_assist.gsi import simulate

    port = free_port()
    server = GsiServer(port, token="tok")
    server.start()
    try:
        provider = GsiProvider(dataset, server, ManualDraft())
        steps = simulate.all_pick_scenario(dataset, token="tok", speed=1000)
        for step in steps:
            post(port, step.payload)
        snap = provider.poll()
        assert server.snapshot().count == len(steps)
        assert snap.game_state == gsi_state.STATE_IN_PROGRESS
        assert snap.left                      # own hero came through
        assert snap.needs_manual              # enemies did not, correctly
    finally:
        server.stop()


def test_simulated_payloads_are_rejected_with_the_wrong_token(dataset):
    """Guards the trap that produced silent failure before: a token drift
    between config and app rejects everything, and must be visible."""
    from draft_assist.gsi import simulate

    port = free_port()
    server = GsiServer(port, token="right")
    server.start()
    try:
        for step in simulate.all_pick_scenario(dataset, token="wrong",
                                               speed=1000):
            post(port, step.payload)
        snap = server.snapshot()
        assert snap.count == 0 and snap.rejected > 0
        assert "auth token" in snap.last_error
    finally:
        server.stop()


def test_labels_describe_the_payload_not_the_intention():
    """A label that announces picks the payload does not contain makes a
    correct app look broken — that exact defect cost a debugging cycle."""
    from draft_assist.gsi import simulate

    bare = {"map": {"game_state": gsi_state.STATE_HERO_SELECTION}}
    label = simulate.describe_payload(bare)
    assert "no draft block" in label
    assert "your hero: none yet" in label

    with_picks = {
        "map": {"game_state": gsi_state.STATE_HERO_SELECTION},
        "hero": {"id": 1, "name": "npc_dota_hero_antimage"},
        "draft": {"team2": {"pick0_id": 1, "pick1_id": 2},
                  "team3": {"pick0_id": 11}},
    }
    label = simulate.describe_payload(with_picks)
    assert "2 radiant, 1 dire" in label
    assert "npc_dota_hero_antimage" in label


def test_no_scenario_step_claims_picks_it_does_not_send(dataset):
    """Every label must be consistent with its own payload, both ways."""
    from draft_assist.gsi import simulate

    for include in (False, True):
        for step in simulate.all_pick_scenario(
                dataset, include_draft_block=include, speed=1000):
            has_draft = isinstance(step.payload.get("draft"), dict)
            says_absent = "no draft block" in step.label
            assert says_absent != has_draft
            if has_draft:
                assert ("draft block:" in step.label
                        or "NO picks read from it" in step.label)


def test_draft_block_persists_into_the_running_game(dataset):
    """With --with-draft every step carries the line-up, including the
    running-game payload; otherwise the draft vanishes when the game starts
    and the flag would mean different things at different moments."""
    from draft_assist.gsi import simulate

    steps = simulate.all_pick_scenario(dataset, include_draft_block=True,
                                       speed=1000)
    assert all(isinstance(s.payload.get("draft"), dict) for s in steps)
    final = gsi_state.parse(steps[-1].payload, dataset)
    assert final.game_state == gsi_state.STATE_IN_PROGRESS
    assert final.has_full_draft
    assert "items" in steps[-1].payload      # still the running payload


# ---- recording on the live listener ------------------------------------

def test_recording_toggles_on_the_running_listener(tmp_path):
    """Recording must use the listener already running: a second process
    cannot bind the port, which is exactly what crashed before."""
    port = free_port()
    server = GsiServer(port, token=None)
    server.start()
    try:
        assert not server.recording
        post(port, {"map": {"game_state": "A"}})
        assert not list(tmp_path.glob("*.json"))     # nothing archived yet

        server.set_archive_dir(tmp_path)
        assert server.recording
        post(port, {"map": {"game_state": "B"}})
        assert len(list(tmp_path.glob("gsi_*.json"))) == 1

        server.set_archive_dir(None)
        post(port, {"map": {"game_state": "C"}})
        assert len(list(tmp_path.glob("gsi_*.json"))) == 1   # stopped
    finally:
        server.stop()


def test_recording_resumes_after_existing_files(tmp_path):
    """Turning recording on again must not overwrite an earlier session."""
    (tmp_path / "gsi_00001.json").write_text("{}")
    (tmp_path / "gsi_00002.json").write_text("{}")
    port = free_port()
    server = GsiServer(port, token=None)
    server.start()
    try:
        assert server.set_archive_dir(tmp_path) == 2
        post(port, {"map": {"game_state": "X"}})
        assert (tmp_path / "gsi_00003.json").exists()
    finally:
        server.stop()


def test_status_endpoint_exposes_acceptance(tmp_path):
    """A rejected payload still returns 200, so a sender can only tell it
    was heard by asking. Without this, a token mismatch is invisible."""
    port = free_port()
    server = GsiServer(port, token="right")
    server.start()
    try:
        post(port, {"auth": {"token": "right"}, "map": {}})
        post(port, {"auth": {"token": "wrong"}, "map": {}})
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/") as response:
            status = json.loads(response.read().decode())
        assert status["accepted"] == 1
        assert status["rejected"] == 1
        assert "auth token" in status["last_error"]
        assert status["recording"] is False
    finally:
        server.stop()


# ---- the verdict over a recording --------------------------------------

def test_recording_verdict_says_no_draft_block(tmp_path):
    """The whole reason recordings exist: settle whether a player's own
    feed carries the enemy line-up, from payloads rather than belief."""
    from draft_assist.gsi import summary as gsi_summary

    for i, state in enumerate(["DOTA_GAMERULES_STATE_HERO_SELECTION"] * 3):
        (tmp_path / f"gsi_{i:05d}.json").write_text(json.dumps({
            "provider": {"name": "Dota 2"},
            "map": {"game_state": state},
            "player": {"name": "Bijson", "team_name": "radiant"},
            "hero": {"name": "npc_dota_hero_lion"},
        }))
    report = gsi_summary.from_directory(tmp_path, demo_dataset())
    text = gsi_summary.format_report(report)
    assert report.payloads == 3
    assert not report.draft_block_seen
    assert "No 'draft' block ever arrived" in text
    assert "clicked in by hand" in text
    assert "MISSING" in text          # the spectator components are named


def test_recording_verdict_reports_a_real_draft_block(tmp_path):
    ds = demo_dataset()
    ids = list(ds.heroes)[:10]
    assert len(ids) == 10
    draft = {"team2": {f"pick{i}_id": hid for i, hid in enumerate(ids[:5])},
             "team3": {f"pick{i}_id": hid for i, hid in enumerate(ids[5:])}}
    (tmp_path / "gsi_00001.json").write_text(json.dumps({
        "provider": {"name": "Dota 2"},
        "map": {"game_state": "DOTA_GAMERULES_STATE_HERO_SELECTION"},
        "player": {"name": "Bijson", "team_name": "radiant"},
        "draft": draft,
    }))
    from draft_assist.gsi import summary as gsi_summary
    report = gsi_summary.from_directory(tmp_path, ds)
    assert report.draft_block_seen
    assert report.best_picks >= 9
    assert "GSI DOES report the full draft" in gsi_summary.format_report(report)


def test_recording_verdict_survives_a_corrupt_file(tmp_path):
    (tmp_path / "gsi_00001.json").write_text("{not json")
    (tmp_path / "gsi_00002.json").write_text(json.dumps(
        {"map": {"game_state": "DOTA_GAMERULES_STATE_HERO_SELECTION"}}))
    from draft_assist.gsi import summary as gsi_summary
    report = gsi_summary.from_directory(tmp_path, demo_dataset())
    assert report.unreadable == 1 and report.payloads == 1


def test_recording_verdict_refuses_to_answer_without_a_draft(tmp_path):
    """A recording made after the draft cannot settle the question, and
    must not be read as evidence that GSI is silent."""
    (tmp_path / "gsi_00001.json").write_text(json.dumps({
        "map": {"game_state": "DOTA_GAMERULES_STATE_GAME_IN_PROGRESS"},
        "player": {"name": "Bijson"}}))
    from draft_assist.gsi import summary as gsi_summary
    text = gsi_summary.format_report(
        gsi_summary.from_directory(tmp_path, demo_dataset()))
    assert "does not cover a draft" in text


def test_label_distinguishes_an_unreadable_draft_block_from_an_empty_one():
    """A real recording showed "0 radiant, 0 dire", which reads as "nobody
    has picked" when it may equally mean "the block is shaped differently".
    The label must not settle that question silently."""
    from draft_assist.gsi import simulate

    label = simulate.describe_payload({
        "map": {"game_state": "DOTA_GAMERULES_STATE_HERO_SELECTION"},
        "draft": {"activeteam": 2, "pick": True, "activeteam_time": 12}})
    assert "NO picks read from it" in label
    assert "activeteam" in label
    assert "0 radiant" not in label


def test_verdict_prints_the_shape_of_an_unparsed_draft_block(tmp_path):
    """When a block arrives that yields no picks, the report has to hand
    over its real keys — that is the only thing that can distinguish an
    empty block from an unknown shape."""
    from draft_assist.gsi import summary as gsi_summary

    (tmp_path / "gsi_00001.json").write_text(json.dumps({
        "map": {"game_state": "DOTA_GAMERULES_STATE_HERO_SELECTION"},
        "draft": {"activeteam": 2, "radiant": {"pick0": "npc_dota_hero_lion"}},
    }))
    (tmp_path / "gsi_00002.json").write_text(json.dumps({
        "map": {"game_state": "DOTA_GAMERULES_STATE_HERO_SELECTION"},
        "draft": {"activeteam": 2},
    }))
    text = gsi_summary.format_report(
        gsi_summary.from_directory(tmp_path, demo_dataset()))
    assert "The 'draft' key arrived in" in text
    assert "activeteam" in text and "radiant" in text
    # the fullest block is the one worth showing, not merely the first
    assert "npc_dota_hero_lion" in text
    assert "shape this parser does not know" in text


def test_verdict_reports_a_draft_key_that_is_not_an_object(tmp_path):
    """A real recording had the draft key in all 8493 payloads while the
    report said nothing about it, because the inspector only looked inside
    dicts. Whatever Dota puts there has to be shown."""
    from draft_assist.gsi import summary as gsi_summary

    for i, value in enumerate([[], None, ["something"]]):
        (tmp_path / f"gsi_{i:05d}.json").write_text(json.dumps({
            "map": {"game_state": "DOTA_GAMERULES_STATE_HERO_SELECTION"},
            "draft": value}))
    report = gsi_summary.from_directory(tmp_path, demo_dataset())
    text = gsi_summary.format_report(report)
    assert report.draft_key_present == 3
    assert "The 'draft' key arrived in 3 payloads" in text
    assert "list" in text and "NoneType" in text
    assert "something" in text          # the fullest value, not the first


def test_verdict_calls_an_empty_draft_block_what_it_is(tmp_path):
    from draft_assist.gsi import summary as gsi_summary

    (tmp_path / "gsi_00001.json").write_text(json.dumps({
        "map": {"game_state": "DOTA_GAMERULES_STATE_HERO_SELECTION"},
        "draft": {}}))
    text = gsi_summary.format_report(
        gsi_summary.from_directory(tmp_path, demo_dataset()))
    assert "really is sending an empty draft block" in text


def test_verdict_surfaces_components_the_codebase_did_not_expect(tmp_path):
    """The recording that settled the draft question also carried blocks
    this codebase had not predicted; unknown keys must not be dropped."""
    from draft_assist.gsi import summary as gsi_summary

    (tmp_path / "gsi_00001.json").write_text(json.dumps({
        "map": {"game_state": "DOTA_GAMERULES_STATE_HERO_SELECTION"},
        "wearables": {"player0": {}}, "abilities": {}, "auth": {}}))
    report = gsi_summary.from_directory(tmp_path, demo_dataset())
    text = gsi_summary.format_report(report)
    assert "wearables" in text and "abilities" in text
    assert "map" not in report.other_keys


def test_empty_draft_block_shows_as_empty_not_null(tmp_path):
    """Every block being {} weighed zero against a None start, so a key seen
    8493 times was reported as "null" — which reads as "never seen"."""
    from draft_assist.gsi import summary as gsi_summary

    for i in range(3):
        (tmp_path / f"gsi_{i:05d}.json").write_text(json.dumps({
            "map": {"game_state": "DOTA_GAMERULES_STATE_HERO_SELECTION"},
            "draft": {}}))
    report = gsi_summary.from_directory(tmp_path, demo_dataset())
    text = gsi_summary.format_report(report)
    assert report.draft_sample == {}
    assert "null" not in text
    assert "really is sending an empty draft block" in text
    assert "Dota sends an EMPTY draft block" in text


def test_hero_mention_scan_finds_heroes_anywhere_in_a_payload():
    """The last question worth asking a feed that will not report a draft:
    is a hero named anywhere in it at all? Walk it, do not guess."""
    from draft_assist.gsi import summary as gsi_summary

    paths = gsi_summary.hero_mentions({
        "hero": {"name": "npc_dota_hero_lion"},
        "wearables": {"player3": {"wearable0": 4242}},
        "minimap": {"o1": {"unitname": "npc_dota_hero_axe", "xpos": 10}},
        "events": [{"hero_id": 7}, {"hero_id": 0}],
        "map": {"matchid": "123"},
    })
    assert set(paths) == {"hero.name", "minimap.o1.unitname", "events[0].hero_id"}


def test_verdict_reports_where_heroes_are_named_while_drafting(tmp_path):
    from draft_assist.gsi import summary as gsi_summary

    (tmp_path / "gsi_00001.json").write_text(json.dumps({
        "map": {"game_state": "DOTA_GAMERULES_STATE_HERO_SELECTION"},
        "draft": {}, "hero": {}}))
    (tmp_path / "gsi_00002.json").write_text(json.dumps({
        "map": {"game_state": "DOTA_GAMERULES_STATE_GAME_IN_PROGRESS"},
        "draft": {}, "hero": {"name": "npc_dota_hero_lion"}}))
    text = gsi_summary.format_report(
        gsi_summary.from_directory(tmp_path, demo_dataset()))
    assert "hero.name" in text
    assert "while drafting, this feed names no hero at all" in text


def test_verdict_says_when_the_recording_was_made(tmp_path):
    """Recording appends, so a folder can hold an old match; the report must
    not let a stale archive read as evidence about the game just played."""
    import os
    import time as time_mod
    from draft_assist.gsi import summary as gsi_summary

    path = tmp_path / "gsi_00001.json"
    path.write_text(json.dumps({
        "map": {"game_state": "DOTA_GAMERULES_STATE_HERO_SELECTION",
                "matchid": "8123456789"},
        "draft": {}}))
    old = time_mod.time() - 12 * 86400
    os.utime(path, (old, old))

    text = gsi_summary.format_report(
        gsi_summary.from_directory(tmp_path, demo_dataset()))
    assert "Recorded:" in text
    assert "12 days old" in text
    assert "ARCHIVE, not the game you just played" in text
    assert "8123456789" in text


def test_verdict_warns_when_several_matches_are_mixed_together(tmp_path):
    from draft_assist.gsi import summary as gsi_summary

    for i, match in enumerate(["111", "111", "222"]):
        (tmp_path / f"gsi_{i:05d}.json").write_text(json.dumps({
            "map": {"game_state": "DOTA_GAMERULES_STATE_HERO_SELECTION",
                    "matchid": match},
            "draft": {}}))
    report = gsi_summary.from_directory(tmp_path, demo_dataset())
    text = gsi_summary.format_report(report)
    assert len(report.match_ids) == 2
    assert "separate games pooled together" in text
    assert "--match" in text


def test_hero_objects_keeps_the_team_beside_the_name():
    """A hero name is only useful with the side it is on."""
    from draft_assist.gsi import summary as gsi_summary

    found = sorted((path, hero, team) for path, hero, team, _obj
                   in gsi_summary.hero_objects({
        "minimap": {"o0": {"unitname": "npc_dota_hero_lion", "team": 2,
                           "name": "npc_dota_hero_lion"},
                    "o1": {"unitname": "npc_dota_hero_axe", "team": 3},
                    "o2": {"unitname": "npc_dota_creep", "team": 2}},
        "hero": {"name": "npc_dota_hero_lion"}}))
    assert ("hero", "npc_dota_hero_lion", "?") in found
    assert ("minimap.o0", "npc_dota_hero_lion", "2") in found
    assert ("minimap.o1", "npc_dota_hero_axe", "3") in found
    assert not any(hero == "npc_dota_creep" for _p, hero, _t in found)


def test_verdict_reports_both_teams_when_the_draft_phase_names_them(tmp_path):
    from draft_assist.gsi import summary as gsi_summary

    (tmp_path / "gsi_00001.json").write_text(json.dumps({
        "map": {"game_state": "DOTA_GAMERULES_STATE_HERO_SELECTION"},
        "draft": {},
        "minimap": {"o0": {"unitname": "npc_dota_hero_lion", "team": 2},
                    "o1": {"unitname": "npc_dota_hero_axe", "team": 3}}}))
    text = gsi_summary.format_report(
        gsi_summary.from_directory(tmp_path, demo_dataset()))
    assert "team 2: npc_dota_hero_lion" in text
    assert "team 3: npc_dota_hero_axe" in text
    assert "BOTH sides are named" in text
    assert "'2', '3'" in text


def test_verdict_calls_out_a_one_sided_draft_phase(tmp_path):
    from draft_assist.gsi import summary as gsi_summary

    (tmp_path / "gsi_00001.json").write_text(json.dumps({
        "map": {"game_state": "DOTA_GAMERULES_STATE_HERO_SELECTION"},
        "draft": {},
        "minimap": {"o0": {"unitname": "npc_dota_hero_lion", "team": 2},
                    "o1": {"unitname": "npc_dota_hero_axe", "team": 2}}}))
    text = gsi_summary.format_report(
        gsi_summary.from_directory(tmp_path, demo_dataset()))
    assert "Only team 2 is ever named" in text
    assert "BOTH sides are named" not in text


def test_strategy_time_is_never_pooled_with_hero_selection(tmp_path):
    """Heroes named at strategy time are worthless — the draft is over and
    everyone has spawned. Pooling them inflated the one number that
    matters, and made a one-sided draft phase look like both teams."""
    from draft_assist.gsi import summary as gsi_summary

    (tmp_path / "gsi_00001.json").write_text(json.dumps({
        "map": {"game_state": "DOTA_GAMERULES_STATE_HERO_SELECTION"},
        "minimap": {"o0": {"unitname": "npc_dota_hero_lion", "team": 2}}}))
    (tmp_path / "gsi_00002.json").write_text(json.dumps({
        "map": {"game_state": "DOTA_GAMERULES_STATE_STRATEGY_TIME"},
        "minimap": {"o0": {"unitname": "npc_dota_hero_lion", "team": 2},
                    "o1": {"unitname": "npc_dota_hero_axe", "team": 3}}}))
    report = gsi_summary.from_directory(tmp_path, demo_dataset())
    selection = report.phase_heroes["DOTA_GAMERULES_STATE_HERO_SELECTION"]
    assert set(selection) == {"team 2: npc_dota_hero_lion"}
    text = gsi_summary.format_report(report)
    assert "HERO_SELECTION: 1 payloads" in text
    assert "STRATEGY_TIME: 1 payloads" in text
    assert "the draft is already over here" in text
    # the one-sided hero-selection phase must not borrow strategy time's
    # second team
    before = text.index("HERO_SELECTION: 1 payloads")
    after = text.index("STRATEGY_TIME: 1 payloads")
    assert "Only team 2 is ever named" in text[before:after]


def test_a_missing_team_field_is_not_a_second_team(tmp_path):
    """"?" means no team field. Counted as a team it reported BOTH TEAMS
    APPEAR over data that was entirely one side."""
    from draft_assist.gsi import summary as gsi_summary

    (tmp_path / "gsi_00001.json").write_text(json.dumps({
        "map": {"game_state": "DOTA_GAMERULES_STATE_HERO_SELECTION"},
        "hero": {"name": "npc_dota_hero_magnataur"},
        "minimap": {"o0": {"unitname": "npc_dota_hero_magnataur",
                           "team": 2}}}))
    text = gsi_summary.format_report(
        gsi_summary.from_directory(tmp_path, demo_dataset()))
    assert "team ?: npc_dota_hero_magnataur" in text
    assert "Only team 2 is ever named" in text
    assert "BOTH sides are named" not in text


def test_one_match_can_be_isolated_from_a_pooled_folder(tmp_path):
    from draft_assist.gsi import summary as gsi_summary

    for i, (match, hero) in enumerate([("111", "npc_dota_hero_lion"),
                                       ("222", "npc_dota_hero_axe")]):
        (tmp_path / f"gsi_{i:05d}.json").write_text(json.dumps({
            "map": {"game_state": "DOTA_GAMERULES_STATE_HERO_SELECTION",
                    "matchid": match},
            "minimap": {"o0": {"unitname": hero, "team": 2}}}))
    report = gsi_summary.from_directory(tmp_path, demo_dataset(), match="111")
    assert list(report.match_ids) == ["111"]
    assert set(report.phase_heroes["DOTA_GAMERULES_STATE_HERO_SELECTION"]) \
        == {"team 2: npc_dota_hero_lion"}


def test_the_richest_payload_dump_names_its_file(tmp_path):
    """A dump you cannot go back to is not evidence."""
    from draft_assist.gsi import summary as gsi_summary

    (tmp_path / "gsi_00007.json").write_text(json.dumps({
        "map": {"game_state": "DOTA_GAMERULES_STATE_HERO_SELECTION",
                "matchid": "8981992551"},
        "minimap": {"o0": {"unitname": "npc_dota_hero_lion", "team": 2,
                           "xpos": -1000, "ypos": 500}}}))
    text = gsi_summary.format_report(
        gsi_summary.from_directory(tmp_path, demo_dataset()))
    assert "gsi_00007.json" in text
    assert "8981992551" in text
    assert '"xpos": -1000' in text      # the whole object, not just the name


# ---- reading both line-ups out of the minimap ---------------------------

def real_strategy_payload():
    path = (Path(__file__).parent / "fixtures" / "gsi"
            / "strategy_time_minimap.json")
    return json.loads(path.read_text())


def minimap_dataset():
    """A dataset carrying exactly the ten heroes of the recorded match."""
    # Real Dota hero ids: the payload's hero block says {"id": 86}, and the
    # parser trusts that id directly, so a dataset with invented numbering
    # would fail to find the player's own hero among the ten.
    names = {75: "silencer", 86: "rubick", 21: "windrunner", 102: "abaddon",
             72: "gyrocopter", 11: "nevermore", 47: "viper", 22: "zuus",
             35: "sniper", 136: "marci"}
    heroes = {hid: {"name": name.title(),
                    "internal_name": f"npc_dota_hero_{name}",
                    "roles": []}
              for hid, name in names.items()}
    ds = demo_dataset()
    ds.heroes = heroes
    return ds


def test_both_lineups_read_from_a_real_strategy_time_payload():
    """The payload is one the user actually recorded (match 8983145525).
    They played Rubick on Dire; the minimap names all ten heroes."""
    ds = minimap_dataset()
    parsed = gsi_state.parse(real_strategy_payload(), ds)
    assert parsed.lineup_source == "minimap"
    assert parsed.has_full_draft
    assert [ds.name(h) for h in parsed.allies] == [
        "Silencer", "Rubick", "Windrunner", "Abaddon", "Gyrocopter"]
    assert [ds.name(h) for h in parsed.enemies] == [
        "Nevermore", "Viper", "Zuus", "Sniper", "Marci"]
    # your own hero must not be duplicated into the ally list a second time
    assert parsed.allies.count(parsed.my_hero_id) == 1


def test_your_team_is_decided_by_your_own_hero_not_by_order():
    """Same payload, read as a player on the other side: the run containing
    your hero is yours, whichever run that is."""
    ds = minimap_dataset()
    payload = real_strategy_payload()
    payload["hero"] = {"id": 22, "name": "npc_dota_hero_zuus"}
    parsed = gsi_state.parse(payload, ds)
    assert [ds.name(h) for h in parsed.allies] == [
        "Nevermore", "Viper", "Zuus", "Sniper", "Marci"]
    assert ds.name(parsed.enemies[0]) == "Silencer"


def test_the_team_field_is_not_trusted():
    """Every minimap object in the recorded payload says team 2 while the
    player was on Dire. Believing it would put all ten on one side."""
    payload = real_strategy_payload()
    assert {o["team"] for o in payload["minimap"].values()} == {2}
    assert payload["player"]["team_name"] == "dire"
    parsed = gsi_state.parse(payload, minimap_dataset())
    assert len(parsed.allies) == 5 and len(parsed.enemies) == 5


def test_minimap_is_not_read_when_your_hero_is_unknown():
    """Without your own hero there is nothing to anchor the split to, and
    a coin flip between two line-ups is worse than none."""
    ds = minimap_dataset()
    payload = real_strategy_payload()
    payload.pop("hero")
    parsed = gsi_state.parse(payload, ds)
    assert not parsed.allies and not parsed.enemies
    assert any("which five are your team is unknown" in n
               for n in parsed.notes)


def test_minimap_refuses_a_split_the_positions_contradict():
    """Two heroes from the same run sharing a lane position says the runs
    are not teams. One contradiction is disqualifying."""
    from draft_assist.gsi import minimap as gsi_minimap

    ds = minimap_dataset()
    name_to_id = {info["internal_name"]: hid
                  for hid, info in ds.heroes.items()}
    payload = real_strategy_payload()
    # put silencer (run one) on top of windrunner (also run one)
    payload["minimap"]["o0"]["xpos"] = 752
    payload["minimap"]["o0"]["ypos"] = -144
    payload["minimap"]["o9"]["xpos"] = 4242      # displace viper
    out = gsi_minimap.read_lineups(payload, name_to_id, my_hero_id=86)
    assert not out.complete
    assert any("contradict it" in note for note in out.notes)


def test_minimap_ignores_a_payload_with_fewer_than_ten_heroes():
    from draft_assist.gsi import minimap as gsi_minimap

    ds = minimap_dataset()
    name_to_id = {info["internal_name"]: hid
                  for hid, info in ds.heroes.items()}
    payload = real_strategy_payload()
    for key in ("o12", "o11"):
        payload["minimap"].pop(key)
    out = gsi_minimap.read_lineups(payload, name_to_id, my_hero_id=86)
    assert not out.complete
    assert any("not ten" in note for note in out.notes)


def test_hero_selection_payloads_still_yield_nothing():
    """58 recorded HERO_SELECTION payloads named no hero at all. The
    minimap reader must not invent one from an empty block."""
    parsed = gsi_state.parse({
        "map": {"game_state": "DOTA_GAMERULES_STATE_HERO_SELECTION"},
        "player": {"name": "Bijson", "team_name": "dire"},
        "draft": {}, "minimap": {}}, minimap_dataset())
    assert not parsed.allies and not parsed.enemies
    assert not parsed.has_full_draft
    assert parsed.lineup_source == ""


# ---- game data for the phase, the screen for the picks ------------------

class FakeVision:
    """Stands in for the capture session, which needs Windows and Dota."""

    def __init__(self, radiant=(), dire=(), unknown=0):
        from draft_assist.ui.providers import Snapshot
        self.snap = Snapshot(source="capturing 'Dota 2'")
        self.radiant, self.dire, self.unknown = (list(radiant), list(dire),
                                                 unknown)
        self.forced = False
        self.started = False

    class _Read:
        def __init__(self, radiant, dire, unknown):
            self._r, self._d, self._u = radiant, dire, unknown

        def team_ids(self, team):
            return list(self._r if team == "radiant" else self._d)

        def unknown_count(self):
            return self._u

    def start(self):
        self.started = True
        return "capturing window 'Dota 2'"

    def stop(self):
        pass

    def set_forced(self, forced):
        self.forced = forced

    def poll(self):
        snap = self.snap
        snap.read = self._Read(self.radiant, self.dire, self.unknown)
        snap.read_raw = snap.read
        return snap


def hybrid(payload, radiant=(), dire=(), unknown=0, manual=None):
    from draft_assist.ui.providers import HybridProvider
    ds = minimap_dataset()
    manual = manual if manual is not None else ManualDraft()
    gsi = GsiProvider(ds, FakeServer(payload), manual)
    return HybridProvider(gsi, FakeVision(radiant, dire, unknown)), ds


def hero_selection_payload(team="dire"):
    return {"map": {"game_state": "DOTA_GAMERULES_STATE_HERO_SELECTION"},
            "player": {"name": "Bijson", "team_name": team},
            "draft": {}, "minimap": {}}


def test_screen_fills_the_picks_gsi_never_sends_during_hero_selection():
    """The whole point: GSI names no hero while picking, so without the
    screen the app is blind for the only moment that matters."""
    provider, ds = hybrid(hero_selection_payload("dire"),
                          radiant=[75, 21], dire=[86, 102])
    snap = provider.poll()
    assert snap.lineup_source == "screen"
    assert snap.game_state.endswith("HERO_SELECTION")
    # dire is the player's side, so the dire bank is the ally bank
    assert snap.left == [86, 102]
    assert snap.right == [75, 21]
    assert snap.sides_known


def test_the_game_says_which_bank_is_yours():
    """Same screen read, the other side: the banks swap without the user
    ever being asked which side they are on."""
    provider, _ds = hybrid(hero_selection_payload("radiant"),
                           radiant=[75, 21], dire=[86, 102])
    snap = provider.poll()
    assert snap.left == [75, 21] and snap.right == [86, 102]


def test_sides_stay_a_question_when_the_game_has_not_said():
    payload = hero_selection_payload("")
    payload["player"] = {"name": "Bijson"}
    provider, _ds = hybrid(payload, radiant=[75], dire=[86])
    snap = provider.poll()
    assert not snap.sides_known


def test_game_reported_lineups_beat_the_screen():
    """Precedence is strict and never a blend: what the game reports
    outright wins over pixels."""
    provider, ds = hybrid(real_strategy_payload(),
                          radiant=[999], dire=[998])
    snap = provider.poll()
    assert snap.lineup_source == "minimap"
    assert [ds.name(h) for h in snap.left] == [
        "Silencer", "Rubick", "Windrunner", "Abaddon", "Gyrocopter"]


def test_hand_entered_slots_fill_what_the_screen_could_not_read():
    manual = ManualDraft()
    manual.set_slot("enemy", 0, 47)
    provider, _ds = hybrid(hero_selection_payload("dire"),
                           radiant=[75], dire=[86], manual=manual)
    snap = provider.poll()
    assert snap.right == [75, 47]          # screen first, then the typed one
    assert snap.left == [86]


def test_the_debug_view_still_sees_the_frame_when_picks_came_elsewhere():
    """A recognition problem is diagnosed from the Debug tab, so it must
    show what the app is looking at even when the picks came from GSI."""
    provider, _ds = hybrid(real_strategy_payload(), radiant=[75], dire=[86])
    snap = provider.poll()
    assert snap.lineup_source == "minimap"
    assert snap.read is not None


def test_without_a_capture_session_it_behaves_exactly_like_gsi_alone():
    from draft_assist.ui.providers import HybridProvider
    ds = minimap_dataset()
    gsi = GsiProvider(ds, FakeServer(hero_selection_payload()), ManualDraft())
    provider = HybridProvider(gsi, None)
    snap = provider.poll()
    assert snap.lineup_source == ""
    assert snap.needs_manual


def test_forcing_recognition_reaches_the_capture_session():
    provider, _ds = hybrid(hero_selection_payload(), radiant=[75])
    provider.set_forced(True)
    assert provider.vision.forced
