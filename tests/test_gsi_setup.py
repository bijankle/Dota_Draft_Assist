"""Setting up game data: the half the app does, and the half it cannot.

GSI has exactly two requirements and they are not alike. The config file
in the Dota install has nothing in it for anybody to decide, so the app
writes it — at first run and again at every start. The launch option in
Steam cannot be automated at all, because Steam holds that file in
memory and rewrites it on exit, so what the app owes there is a
procedure rather than the option's name.

Until this existed the app did NEITHER at setup and put a banner up
sending people to a menu item for the half it could have done itself:
"why is it not just auto run at setup with all the other crap like
portraits". These hold both halves in place.
"""

import os

import pytest

pytest.importorskip("PyQt6")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication              # noqa: E402

from draft_assist.gsi import install as gsi_install   # noqa: E402


@pytest.fixture(scope="module")
def qapp():
    yield QApplication.instance() or QApplication([])


@pytest.fixture()
def dota(tmp_path):
    """A Dota install just real enough for `find_dota_dir` to accept."""
    root = tmp_path / "dota 2 beta"
    (root / "game" / "dota").mkdir(parents=True)
    return root


# ------------------------------------------------------- the config file ----

def test_ensure_writes_the_config_when_there_is_none(dota):
    result = gsi_install.ensure(port=53000, dota_dir=dota)
    assert result.created
    written = result.config_path.read_text(encoding="utf-8")
    assert '"uri"        "http://127.0.0.1:53000/"' in written
    assert result.token in written


def test_ensure_is_idempotent_so_it_can_run_at_every_start(dota):
    """THE TOKEN IS THE WHOLE DIFFERENCE from `install`, and it is what
    makes this safe to run automatically.

    `install` mints a fresh token whenever it is not handed one, so its
    text never matches what is on disk and it rewrites on every call. Run
    that at startup and a Dota already in a match keeps sending the token
    it was given at launch, which this app would then reject — silently,
    because a rejected payload looks exactly like no payload at all.
    """
    first = gsi_install.ensure(port=53000, dota_dir=dota)
    stamped = first.config_path.stat().st_mtime_ns

    again = gsi_install.ensure(port=53000, dota_dir=dota)
    assert not again.created, "it rewrote a config that was already right"
    assert again.token == first.token, "the token churned under a live Dota"
    assert again.config_path.stat().st_mtime_ns == stamped

    # And the contrast, so the reason for a second function is on record.
    minted = gsi_install.install(port=53000, dota_dir=dota)
    assert minted.created and minted.token != first.token


def test_ensure_rewrites_when_the_port_moved(dota):
    """The listener binding elsewhere is the case it MUST act on: a
    config pointing at a port nothing is listening on is silence."""
    first = gsi_install.ensure(port=53000, dota_dir=dota)
    moved = gsi_install.ensure(port=53001, dota_dir=dota)
    assert moved.created
    assert "53001" in moved.config_path.read_text(encoding="utf-8")
    assert moved.token == first.token, "only the port needed to change"


def test_a_missing_dota_is_reported_rather_than_guessed(tmp_path, monkeypatch):
    monkeypatch.delenv("DOTA_DIR", raising=False)
    monkeypatch.setattr(gsi_install, "_steam_roots", lambda: [tmp_path])
    with pytest.raises(gsi_install.DotaNotFound):
        gsi_install.ensure(port=53000)


# ------------------------------------------------------- the launch option ----

def test_the_steps_name_the_option_and_the_restart():
    """Somebody following these must end up with the option in the right
    box and Dota restarted; both have been the thing people missed."""
    joined = " ".join(gsi_install.LAUNCH_STEPS).lower()
    assert gsi_install.LAUNCH_OPTION in " ".join(gsi_install.LAUNCH_STEPS)
    for fact in ("steam", "right-click dota 2", "properties",
                 "launch options", "restart dota"):
        assert fact in joined, f"the procedure lost {fact!r}"


def test_no_step_is_a_paragraph():
    """A procedure is scanned a line at a time. The moment a step needs
    two sentences of preamble it has become the prose this screen was cut
    back from, and nobody reads it."""
    for step in gsi_install.LAUNCH_STEPS:
        assert len(step) <= 100, f"step is an essay: {step!r}"


def test_every_surface_renders_the_shared_steps(qapp, tmp_path,
                                                monkeypatch):
    """Three places show this procedure — the wizard's third card, the
    banner's dialog and the confirmation after the menu item — and all
    three must RENDER `LAUNCH_STEPS` rather than carry a list of their
    own. Three tellings is two of them going stale, which is the fault
    `test_no_stale_menu_trails` catches one layer up.

    Checked by driving each surface and reading what it produced, not by
    grepping for the constant's name: a file can mention `LAUNCH_STEPS`
    and still print something else. A scan for a distinctive PHRASE was
    tried first and is not the check — "there is no OK button" also
    appears in the manual's page about the Settings window, and a
    one-line breadcrumb in `diagnose`'s report is not a copy of the
    procedure either.
    """
    from pathlib import Path
    root = Path(__file__).resolve().parent.parent
    last = gsi_install.LAUNCH_STEPS[-1]

    # 1. The wizard's card, rendered.
    from draft_assist import config
    from draft_assist.ui.setup_wizard import SetupWizard
    monkeypatch.setattr(config, "ENV_FILE", tmp_path / ".env")
    monkeypatch.setattr(config, "PREFS_FILE", tmp_path / "prefs.json")
    wizard = SetupWizard()
    card = " ".join(label.text() for label in
                    wizard.findChildren(type(wizard.summary)))
    for step in gsi_install.LAUNCH_STEPS:
        assert step in card, f"the wizard card is missing: {step!r}"
    wizard.deleteLater()

    # 2. and 3. Both dialogs in app.py build their text from the tuple.
    source = (root / "draft_assist/ui/app.py").read_text(encoding="utf-8")
    # The RENDER idiom, so a mention in a docstring does not count.
    assert source.count("enumerate(gsi_install.LAUNCH_STEPS") == 2, (
        "the banner's dialog and the install confirmation should each "
        "render the shared steps, and nothing else should")
    assert last not in source, "app.py has a copy of the steps in it"


# ------------------------------------------------------------ the wizard ----

def test_the_wizard_has_a_step_for_game_data(qapp, tmp_path, monkeypatch):
    """It asked for NEITHER half before, and the app then put a banner up
    about it on the first screen after setup. It is the LAST step, at the
    user's request — everything before it is typing or ticking in this
    window, and that one sends you into another program."""
    from draft_assist import config
    from draft_assist.ui.setup_wizard import SetupWizard
    monkeypatch.setattr(config, "ENV_FILE", tmp_path / ".env")
    monkeypatch.setattr(config, "PREFS_FILE", tmp_path / "prefs.json")

    from draft_assist.ui.setup_wizard import STEPS
    assert STEPS[-1].ident == "gsi", "the annoying step must come last"

    wizard = SetupWizard()
    words = " ".join(label.text() for label
                     in wizard.findChildren(type(wizard.note)))
    assert "Launch Options" in words, "the procedure is not on the dialog"
    assert gsi_install.LAUNCH_OPTION in words
    # The MEANING, not a phrase: the step has to say the app writes the
    # config file, because the whole complaint was that it used to send
    # people off to do the half with nothing in it to decide.
    how = STEPS[-1].how.lower()
    assert "writes" in how and "config file" in how, (
        f"the step must say the app does its own half: {STEPS[-1].how!r}")
    wizard.deleteLater()


def test_the_button_copies_and_opens_steam_in_one_press(qapp, tmp_path,
                                                        monkeypatch):
    """ONE ACTION, not two: the clipboard is loaded by the time the box
    you paste into is in front of you.

    Both halves land somewhere the dialog cannot see — the clipboard, and
    another program's window — so it has to say what it did, or it is a
    press with no visible result.
    """
    from draft_assist import config
    from draft_assist.ui.setup_wizard import SetupWizard
    monkeypatch.setattr(config, "ENV_FILE", tmp_path / ".env")
    monkeypatch.setattr(config, "PREFS_FILE", tmp_path / "prefs.json")
    opened = []
    monkeypatch.setattr(gsi_install, "open_properties",
                        lambda *a, **k: opened.append(a) or True)

    wizard = SetupWizard()
    wizard._copy_launch_option()
    assert QApplication.clipboard().text() == gsi_install.LAUNCH_OPTION
    assert opened, "it copied but did not open Steam"
    assert not wizard.gsi_note.isHidden()
    assert "Steam" in wizard.gsi_note.text()
    wizard.deleteLater()


def test_the_properties_url_is_built_from_the_app_id():
    """A second literal "570" is a second thing to get wrong, and this
    one fails SILENTLY — Steam ignores a verb it cannot parse without
    saying anything, so the button would look like it worked."""
    assert gsi_install.PROPERTIES_URL.endswith("/" + gsi_install.APP_ID)
    assert gsi_install.PROPERTIES_URL.startswith("steam://gameproperties/")


def test_opening_steam_never_raises(monkeypatch):
    """It is a convenience beside seven steps that still work by hand, so
    a missing protocol handler must cost the shortcut and nothing else."""
    def explode(*args, **kwargs):
        raise OSError("no handler for steam://")
    monkeypatch.setattr("webbrowser.open", explode)
    assert gsi_install.open_properties() is False


# ------------------------------------------------------------ the window ----

@pytest.fixture()
def window(qapp, tmp_path, monkeypatch):
    """The real window on demo state, with Dota's install redirected into
    tmp_path so nothing here can write into a real one."""
    from draft_assist.config import RULES_FILE
    from draft_assist.model import items as items_mod
    from draft_assist.ui import settings as ui_settings
    from draft_assist.ui.app import MainWindow
    from draft_assist.ui.demo import demo_dataset
    from draft_assist.ui.providers import DemoProvider

    root = tmp_path / "dota 2 beta"
    (root / "game" / "dota").mkdir(parents=True)
    monkeypatch.setenv("DOTA_DIR", str(root))
    monkeypatch.setattr(ui_settings, "SETTINGS_FILE", tmp_path / "ui.json")

    ds = demo_dataset()
    rules, meta = items_mod.load_rules(RULES_FILE)
    win = MainWindow(ds, DemoProvider(ds), rules, meta)
    win.timer.stop()
    win.dota_dir = root
    yield win
    win.close()


def test_the_config_is_written_without_anybody_asking(window):
    """The whole complaint: this is a mkdir and a write with nothing in
    it to decide, and it was a menu item somebody had to go and find."""
    path = (gsi_install.config_dir(window.dota_dir) / gsi_install.CONFIG_NAME)
    assert not path.exists()
    assert window._ensure_gsi_config() == "Game data config installed"
    assert path.exists()
    # And again changes nothing, because it runs at every start.
    assert window._ensure_gsi_config() == ""


def test_a_skipped_gsi_step_is_not_written_for(window):
    """Somebody who has not been through that step has not agreed to a
    file being written into their Dota install. The banner is where they
    say otherwise, and pressing its button clears the step."""
    window.settings["setup_pending"] = ["gsi"]
    assert window._ensure_gsi_config() == ""
    assert not (gsi_install.config_dir(window.dota_dir)
                / gsi_install.CONFIG_NAME).exists()


def test_the_listener_gets_the_token_in_the_same_breath(window):
    """A config written now and a listener still expecting the old token
    rejects every payload Dota sends — and a rejected payload is
    indistinguishable from a silent game."""
    class Listener:
        port = 53000
        token = None

    listener = Listener()
    window.provider.server = listener
    window._ensure_gsi_config()
    installed = gsi_install.read_installed_token(window.dota_dir)
    assert installed and listener.token == installed


def test_a_missing_dota_costs_the_config_and_not_the_app(window, monkeypatch):
    """Setting the app up before installing Dota is an ordinary order to
    do it in. It must not raise out of startup."""
    monkeypatch.delenv("DOTA_DIR", raising=False)
    monkeypatch.setattr(gsi_install, "_steam_roots", lambda: [])
    assert window._ensure_gsi_config() == ""


def test_the_banner_offers_the_install_rather_than_naming_a_menu(window):
    """"check game data should not jsut give an error and instruct you to
    download game data... instead it should just facilitate the
    installation directly." """
    class Silent:
        gsi_setup_broken = True
        warning = "no data from Dota yet — GSI config installed: no file"
        crop_boxes_wrong = False

    window.settings["setup_skipped"] = True          # so nothing is written
    window._update_first_run_banner(Silent())
    assert not window.banner.isHidden()
    assert window.banner_button.text() == "Install it"
    assert "Settings" not in window.banner_label.text(), (
        "the strip is sending people to a menu again")

    # With the file there, the only half left is the user's. The cache
    # has to be dropped by hand here because this write went round the
    # window; every path inside the app that writes it calls that itself.
    gsi_install.ensure(port=53000, dota_dir=window.dota_dir)
    window._forget_gsi_config()
    window._update_first_run_banner(Silent())
    assert window.banner_button.text() == "Show me how"
    assert gsi_install.LAUNCH_OPTION in window.banner_label.text()


def test_setting_up_gsi_no_longer_raises_out_of_its_own_method():
    """REGRESSION. Five lines of the status line's vision note landed
    inside `_install_gsi` in cd0e72c, where neither `snap` nor `parts`
    exists — so the menu item wrote the config and then raised NameError
    before handing the token to the listener. The write was real and
    useless, and nothing on screen said so."""
    import ast
    from pathlib import Path
    root = Path(__file__).resolve().parent.parent
    tree = ast.parse((root / "draft_assist/ui/app.py").read_text(
        encoding="utf-8"))
    for node in ast.walk(tree):
        if not (isinstance(node, ast.FunctionDef)
                and node.name == "_install_gsi"):
            continue
        loaded = {n.id for n in ast.walk(node)
                  if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Load)}
        stored = {n.id for n in ast.walk(node)
                  if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Store)}
        assert not {"snap", "parts"} & (loaded - stored), (
            "the status line's note is back inside the GSI installer")
        return
    raise AssertionError("_install_gsi has gone; this guard needs rewriting")


def test_the_banner_does_not_walk_steam_four_times_a_second(window,
                                                            monkeypatch):
    """`_update_first_run_banner` runs inside `refresh`, and the rung that
    asks this is the one a fresh install sits under for a whole session —
    so an uncached answer is a registry read and a walk of every Steam
    library, four times a second, at exactly the wrong moment. Same trap
    as the gate's signature and the smooth-scaled hidden debug view."""
    from draft_assist.gsi import install as gsi_mod
    walks = []
    real = gsi_mod.find_dota_dir
    monkeypatch.setattr(gsi_mod, "find_dota_dir",
                        lambda *a, **k: (walks.append(1), real(*a, **k))[1])

    window._forget_gsi_config()
    for _ in range(40):                    # ten seconds of ticks
        window._gsi_config_installed()
    assert len(walks) == 1, f"walked Steam {len(walks)} times"

    # And a write is seen at once rather than after the TTL.
    assert not window._gsi_config_installed()
    window._ensure_gsi_config()
    assert window._gsi_config_installed(), (
        "the banner would go on reporting a fault it had just fixed")


def test_nothing_on_the_wizard_is_clipped_at_any_width(qapp, tmp_path,
                                                       monkeypatch):
    """Both long paragraphs on this dialog were once drawn ON TOP of the
    controls under them, because a word-wrapped QLabel's size hint is one
    line until something tells it how wide it will be.

    Putting the cards inside a scroll area re-opens that question from a
    new direction: the vertical scrollbar takes width out of the
    viewport, so every label is laid out NARROWER than the `TEXT_WIDTH`
    its minimum height was measured at — and narrower means more lines,
    not fewer. Measured rather than argued, at the dialog's minimum width
    and above.
    """
    from PyQt6.QtWidgets import QLabel
    from draft_assist import config
    from draft_assist.ui.setup_wizard import SetupWizard
    monkeypatch.setattr(config, "ENV_FILE", tmp_path / ".env")
    monkeypatch.setattr(config, "PREFS_FILE", tmp_path / "prefs.json")

    for width in (640, 660, 900):
        dialog = SetupWizard()
        dialog.resize(width, 700)
        dialog.show()
        for _ in range(3):
            qapp.processEvents()
        for label in dialog.findChildren(QLabel):
            if label.isHidden() or not label.text() or not label.wordWrap():
                continue
            assert label.heightForWidth(label.width()) <= label.height(), (
                f"clipped at {width}px: {label.text()[:50]!r}")
        dialog.close()
        dialog.deleteLater()


def test_the_buttons_do_not_scroll_away_with_the_page(qapp, tmp_path,
                                                     monkeypatch):
    """Next below the bottom edge with no way to reach it is the fault
    the scroll area was added for; putting the buttons INSIDE it would be
    a smaller version of the same thing. The sidebar stays put too — it
    is the progress indicator, so scrolling it out of view would take
    away the one thing saying where you are."""
    from PyQt6.QtWidgets import QScrollArea
    from draft_assist import config
    from draft_assist.ui.setup_wizard import SetupWizard
    monkeypatch.setattr(config, "ENV_FILE", tmp_path / ".env")
    monkeypatch.setattr(config, "PREFS_FILE", tmp_path / "prefs.json")

    dialog = SetupWizard()
    dialog.resize(660, 560)            # short enough that it must scroll
    dialog.show()
    qapp.processEvents()
    # NOT `findChild(QScrollArea)`: the sidebar is a QScrollArea too, so
    # that returns whichever Qt lists first. The page area is the one
    # holding the steps.
    area = next(a for a in dialog.findChildren(QScrollArea)
                if a.isAncestorOf(dialog.pages))
    assert not area.isAncestorOf(dialog.next), "Next scrolls away"
    assert not area.isAncestorOf(dialog.skip), "Skip scrolls away"
    assert not area.isAncestorOf(dialog.sections), "the sidebar scrolls away"
    # And the dialog can be made shorter than its content at all.
    assert dialog.minimumSizeHint().height() < 560
    dialog.close()
    dialog.deleteLater()
