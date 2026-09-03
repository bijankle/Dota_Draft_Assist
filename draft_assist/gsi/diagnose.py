"""Check every precondition for Game State Integration and say which one is
failing.

GSI has several independent requirements and no feedback when one is
missing: Dota simply says nothing. The failure mode is therefore always the
same unhelpful symptom — "no data" — whichever link is broken. This module
tests each link separately so the answer is a specific broken step rather
than a checklist to guess through.

Notably, the launch option ALONE does nothing: it tells Dota to look for
config files, so without a config installed there is nothing to send.
"""

import re
import socket
import sys
from dataclasses import dataclass
from pathlib import Path

from . import install as gsi_install


@dataclass
class Check:
    name: str
    ok: bool | None          # None = could not be determined
    detail: str
    fix: str = ""

    @property
    def mark(self) -> str:
        return {True: "OK  ", False: "FAIL", None: "??  "}[self.ok]


def _steam_userdata_launch_options(app_id: str = gsi_install.APP_ID
                                   ) -> str | None:
    """Dota's launch options as Steam stored them, or None if not readable.

    Best effort by design: the file is per-Steam-account and its layout has
    changed over the years, so an unreadable file reports "unknown" rather
    than claiming the option is missing.
    """
    for root in gsi_install._steam_roots():
        userdata = root / "userdata"
        if not userdata.is_dir():
            continue
        for account in userdata.iterdir():
            config = account / "config" / "localconfig.vdf"
            if not config.exists():
                continue
            try:
                text = config.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            # Find the app block, then the LaunchOptions inside it.
            match = re.search(r'"%s"\s*\{(.{0,4000}?)\}' % app_id, text,
                              re.DOTALL)
            if not match:
                continue
            opts = re.search(r'"LaunchOptions"\s*"([^"]*)"', match.group(1))
            if opts:
                return opts.group(1)
    return None


def _port_is_listening(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.settimeout(0.4)
        return probe.connect_ex(("127.0.0.1", port)) == 0


def run_checks(server=None, port: int | None = None) -> list[Check]:
    port = port or getattr(server, "port", gsi_install.DEFAULT_PORT)
    checks: list[Check] = []

    # 1. Dota installation
    dota_dir = None
    try:
        dota_dir = gsi_install.find_dota_dir()
        checks.append(Check("Dota installation", True, str(dota_dir)))
    except gsi_install.DotaNotFound as exc:
        checks.append(Check(
            "Dota installation", False, str(exc).splitlines()[0],
            "Set the DOTA_DIR environment variable to your 'dota 2 beta' "
            "folder."))

    # 2. The config file — the step the launch option is useless without
    config_port = None
    if dota_dir is not None:
        path = gsi_install.config_dir(dota_dir) / gsi_install.CONFIG_NAME
        if path.exists():
            text = path.read_text(encoding="utf-8", errors="replace")
            found = re.search(r'"uri"\s*"http://127\.0\.0\.1:(\d+)/"', text)
            config_port = int(found.group(1)) if found else None
            checks.append(Check("GSI config installed", True, str(path)))
        else:
            checks.append(Check(
                "GSI config installed", False,
                f"no file at {path}",
                "Run Game > Set up game data (GSI). The launch option alone "
                "does nothing — without this file Dota has nothing to send."))

    # 3. Config and listener must agree on the port
    if config_port is not None:
        agree = config_port == port
        checks.append(Check(
            "Config port matches listener", agree,
            f"config says {config_port}, app is listening on {port}",
            "" if agree else "Re-run Game > Set up game data (GSI) to "
                             "rewrite the config with the current port."))

    # 4. Launch option
    opts = _steam_userdata_launch_options()
    if opts is None:
        checks.append(Check(
            "Dota launch options", None,
            "could not read Steam's stored launch options",
            "Check by hand: Steam > right-click Dota 2 > Properties > "
            f"Launch Options should contain {gsi_install.LAUNCH_OPTION}"))
    else:
        has = gsi_install.LAUNCH_OPTION in opts
        checks.append(Check(
            "Dota launch options", has,
            f"currently: {opts or '(empty)'}",
            "" if has else f"Add {gsi_install.LAUNCH_OPTION} in Steam > "
                           "Dota 2 > Properties > Launch Options."))

    # 5. Our listener — and whether it is OURS
    listening = _port_is_listening(port)
    bind_error = getattr(server, "_bind_error", "") if server else ""
    if bind_error:
        checks.append(Check(
            "GSI port owned by this app", False,
            f"127.0.0.1:{port} is held by another process",
            "Another copy of this app is probably running. Close every "
            "other copy, then use Capture > Use game data (GSI). Two copies "
            "cannot share the port: one receives everything and the other "
            "receives nothing."))
    else:
        checks.append(Check(
            "Listener accepting connections", listening,
            f"127.0.0.1:{port} {'is' if listening else 'is not'} accepting "
            "connections",
            "" if listening else "Switch the source back to game data: "
                                 "Capture > Use game data (GSI)."))

    # 6. Is Dota even running?
    from ..capture.window import DOTA_TITLE, find_dota_window_title
    if sys.platform == "win32":
        running = find_dota_window_title() is not None
        checks.append(Check(
            "Dota is running", running,
            f"window titled {DOTA_TITLE!r} "
            f"{'found' if running else 'not found'}",
            "" if running else "Start Dota. GSI only sends data while the "
                               "game is running."))

    # 7. What actually arrived
    if server is not None:
        snap = server.snapshot()
        if snap.count:
            checks.append(Check(
                "Payloads received", True,
                f"{snap.count} received, last {snap.age:.1f}s ago"))
        elif snap.rejected:
            checks.append(Check(
                "Payloads received", False,
                f"{snap.rejected} rejected: {snap.last_error}",
                "Re-run Game > Set up game data (GSI) so the app and the "
                "config share a token, then restart Dota."))
        else:
            checks.append(Check(
                "Payloads received", False, "nothing received yet",
                "If every check above passes, note that Dota sends GSI data "
                "only while you are IN a match (including the draft) — the "
                "main menu sends nothing. Load a game and watch again."))
    return checks


def format_report(checks: list[Check]) -> str:
    lines = []
    for check in checks:
        lines.append(f"[{check.mark}] {check.name}: {check.detail}")
        if check.fix:
            lines.append(f"         -> {check.fix}")
    failing = [c for c in checks if c.ok is False]
    lines.append("")
    if failing:
        lines.append(f"First thing to fix: {failing[0].name} — "
                     f"{failing[0].fix or failing[0].detail}")
    else:
        lines.append("Every check passed. Dota sends GSI data only while you "
                     "are in a match; the main menu sends nothing.")
    return "\n".join(lines)


def headline(checks: list[Check]) -> str:
    failing = [c for c in checks if c.ok is False]
    if not failing:
        return "Everything is set up correctly."
    return f"{len(failing)} problem(s) found — first: {failing[0].name}."
