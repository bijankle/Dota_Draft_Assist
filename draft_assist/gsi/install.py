"""Locate the Dota 2 installation and install a Game State Integration
config into it.

GSI is Valve's own, documented mechanism: you drop a config file into
game/dota/cfg/gamestate_integration/ and Dota POSTs JSON about the game to a
local HTTP endpoint you choose. Nothing is injected, no memory is read, no
input is sent — the game volunteers the data. That is strictly safer than
reading pixels and is the sanctioned way to do this.

Two things are required for it to work, and BOTH are easy to forget:
  1. this config file present in the Dota install, and
  2. the launch option -gamestateintegration on Dota itself.

Steam's install layout is discovered rather than assumed: the Steam path
comes from the registry (Windows) or the usual locations, and the Dota
library folder from steamapps/libraryfolders.vdf, because Dota is very often
on a different drive from Steam.
"""

import os
import re
import secrets
import sys
from dataclasses import dataclass
from pathlib import Path

APP_ID = "570"
DOTA_DIR_NAME = "dota 2 beta"
CONFIG_NAME = "gamestate_integration_draft_assist.cfg"
LAUNCH_OPTION = "-gamestateintegration"
DEFAULT_PORT = 53000


class DotaNotFound(RuntimeError):
    """Raised with everything that was searched, so the user can point us at
    the right place instead of guessing."""


def _steam_roots() -> list[Path]:
    roots: list[Path] = []
    if sys.platform == "win32":
        try:
            import winreg
            for hive, key in ((winreg.HKEY_CURRENT_USER, r"Software\Valve\Steam"),
                              (winreg.HKEY_LOCAL_MACHINE,
                               r"SOFTWARE\WOW6432Node\Valve\Steam")):
                try:
                    with winreg.OpenKey(hive, key) as handle:
                        for value in ("SteamPath", "InstallPath"):
                            try:
                                path, _ = winreg.QueryValueEx(handle, value)
                                roots.append(Path(path))
                            except OSError:
                                pass
                except OSError:
                    pass
        except ImportError:
            pass
        roots += [Path(r"C:\Program Files (x86)\Steam"),
                  Path(r"C:\Program Files\Steam")]
    else:
        home = Path.home()
        roots += [home / ".steam/steam", home / ".local/share/Steam",
                  home / "Library/Application Support/Steam"]
    seen, out = set(), []
    for r in roots:
        key = str(r).lower()
        if key not in seen:
            seen.add(key)
            out.append(r)
    return out


def _library_paths(steam_root: Path) -> list[Path]:
    """Every Steam library folder, from libraryfolders.vdf.

    The file is parsed with a tolerant regex rather than a full VDF parser:
    its shape has changed across Steam versions and all we need are the
    "path" values.
    """
    libraries = [steam_root]
    vdf = steam_root / "steamapps" / "libraryfolders.vdf"
    if vdf.exists():
        try:
            text = vdf.read_text(encoding="utf-8", errors="replace")
        except OSError:
            return libraries
        for match in re.finditer(r'"path"\s*"([^"]+)"', text):
            libraries.append(Path(match.group(1).replace("\\\\", "\\")))
    return libraries


def find_dota_dir(explicit: str | Path | None = None) -> Path:
    """The 'dota 2 beta' directory, or DotaNotFound listing what was tried."""
    searched: list[Path] = []
    candidates: list[Path] = []
    if explicit:
        candidates.append(Path(explicit))
    env = os.environ.get("DOTA_DIR")
    if env:
        candidates.append(Path(env))
    for root in _steam_roots():
        for library in _library_paths(root):
            candidates.append(library / "steamapps" / "common" / DOTA_DIR_NAME)
    for candidate in candidates:
        searched.append(candidate)
        if (candidate / "game" / "dota").is_dir():
            return candidate
    raise DotaNotFound(
        "Could not find the Dota 2 installation. Looked in:\n  "
        + "\n  ".join(str(p) for p in searched)
        + "\nSet the DOTA_DIR environment variable to the 'dota 2 beta' "
          "folder, or choose it in the app.")


def config_dir(dota_dir: Path) -> Path:
    return dota_dir / "game" / "dota" / "cfg" / "gamestate_integration"


def render_config(port: int, token: str, name: str = "Dota Draft Assist") -> str:
    """The GSI config in Valve's KeyValues format.

    Components are all requested: which ones Dota actually sends depends on
    whether you are playing or spectating, and the point of this integration
    is to find out from real payloads rather than assume.
    """
    components = ["provider", "map", "player", "hero", "abilities", "items",
                  "draft", "wearables", "buildings", "league", "minimap",
                  "roshan", "couriers", "neutralitems", "events"]
    body = "\n".join(f'        "{c}"  "1"' for c in components)
    return (
        f'"{name}"\n'
        '{\n'
        f'    "uri"        "http://127.0.0.1:{port}/"\n'
        '    "timeout"    "5.0"\n'
        '    "buffer"     "0.1"\n'
        '    "throttle"   "0.1"\n'
        '    "heartbeat"  "10.0"\n'
        '    "data"\n'
        '    {\n'
        f'{body}\n'
        '    }\n'
        '    "auth"\n'
        '    {\n'
        f'        "token"  "{token}"\n'
        '    }\n'
        '}\n'
    )


@dataclass
class InstallResult:
    config_path: Path
    dota_dir: Path
    token: str
    port: int
    created: bool          # False when an identical config already existed


def install(port: int = DEFAULT_PORT, token: str | None = None,
            dota_dir: str | Path | None = None) -> InstallResult:
    dota = find_dota_dir(dota_dir)
    target_dir = config_dir(dota)
    target_dir.mkdir(parents=True, exist_ok=True)
    path = target_dir / CONFIG_NAME
    token = token or secrets.token_urlsafe(18)
    text = render_config(port, token)
    existing = path.read_text(encoding="utf-8") if path.exists() else None
    if existing == text:
        return InstallResult(path, dota, token, port, created=False)
    path.write_text(text, encoding="utf-8")
    return InstallResult(path, dota, token, port, created=True)


def read_installed_token(dota_dir: str | Path | None = None) -> str | None:
    """The token from an already-installed config, so a restart of the app
    keeps accepting payloads from a Dota that is already running."""
    try:
        path = config_dir(find_dota_dir(dota_dir)) / CONFIG_NAME
    except DotaNotFound:
        return None
    if not path.exists():
        return None
    match = re.search(r'"token"\s*"([^"]+)"',
                      path.read_text(encoding="utf-8", errors="replace"))
    return match.group(1) if match else None
