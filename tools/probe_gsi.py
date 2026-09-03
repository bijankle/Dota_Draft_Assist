"""Record what Dota's Game State Integration actually sends.

Valve documents GSI thinly and community knowledge says the `draft`
component is spectator-only — meaning a player's own feed probably does not
carry the enemy line-up. That is a claim about reality, so this tool settles
it with evidence instead of memory: it listens for payloads, archives every
one to data_cache/gsi/, and prints which components arrive and whether any
picks are visible.

Run it, then sit through a draft. The summary at the end says plainly
whether GSI can see the line-ups.

    python tools/probe_gsi.py [--minutes 10] [--port 53000]
"""

import argparse
import sys
import time
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from draft_assist.config import DATA_CACHE  # noqa: E402
from draft_assist.data import store  # noqa: E402
from draft_assist.gsi import install as gsi_install  # noqa: E402
from draft_assist.gsi import state as gsi_state  # noqa: E402
from draft_assist.gsi.server import GsiServer  # noqa: E402

ARCHIVE = DATA_CACHE / "gsi"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--minutes", type=float, default=10.0)
    parser.add_argument("--port", type=int, default=gsi_install.DEFAULT_PORT)
    parser.add_argument("--no-archive", action="store_true")
    args = parser.parse_args()

    dataset = store.load_or_empty()
    if dataset.is_empty:
        print("NOTE: no hero data downloaded yet, so hero names will be "
              "blank. Run the data update for readable output.\n")

    token = gsi_install.read_installed_token()
    if token is None:
        print("No GSI config found in the Dota install.")
        print("Install it from the app (Game > Set up game data), or the "
              "probe will accept unauthenticated payloads.\n")

    server = GsiServer(args.port, token=token,
                       archive_dir=None if args.no_archive else ARCHIVE)
    server.start()
    print(f"Listening on http://127.0.0.1:{args.port}/ for "
          f"{args.minutes:.0f} minutes.")
    print(f"Dota needs the launch option {gsi_install.LAUNCH_OPTION} and a "
          "restart.")
    if not args.no_archive:
        print(f"Archiving payloads to {ARCHIVE}")
    print("\nGo into a game and sit through the draft. Ctrl+C to stop.\n")

    seen_components: Counter = Counter()
    states_seen: Counter = Counter()
    best_picks = 0
    draft_block_seen = False
    last_report = 0.0
    deadline = time.monotonic() + args.minutes * 60

    try:
        while time.monotonic() < deadline:
            time.sleep(0.5)
            reception = server.snapshot()
            if reception.payload is None:
                if time.monotonic() - last_report > 10:
                    last_report = time.monotonic()
                    print("waiting for the first payload...")
                continue

            parsed = gsi_state.parse(reception.payload, dataset)
            for name, present in parsed.capabilities.items():
                if present:
                    seen_components[name] += 1
            if parsed.capabilities.get("draft"):
                draft_block_seen = True
            if parsed.game_state:
                states_seen[parsed.game_state] += 1
            picks = len(parsed.allies) + len(parsed.enemies)
            best_picks = max(best_picks, picks)

            if time.monotonic() - last_report > 3:
                last_report = time.monotonic()
                print(f"[{reception.count:5d} payloads] {parsed.summary()}")
    except KeyboardInterrupt:
        print("\nstopped.")
    finally:
        server.stop()

    reception = server.snapshot()
    print("\n" + "=" * 68)
    print(f"Payloads received: {reception.count}   "
          f"rejected: {reception.rejected}")
    if not reception.count:
        print("\nNOTHING WAS RECEIVED. Check, in order:")
        print("  1. Game > Set up game data installed the config")
        print(f"  2. Dota launch options contain {gsi_install.LAUNCH_OPTION}")
        print("  3. Dota was restarted after adding it")
        return

    print("\nComponents seen (payload counts):")
    for name in (gsi_state.PLAYER_COMPONENTS + gsi_state.SPECTATOR_COMPONENTS):
        print(f"  {seen_components.get(name, 0):6d}  {name}")
    print("\nGame states seen:")
    for name, count in states_seen.most_common():
        print(f"  {count:6d}  {name}")

    print("\nVERDICT")
    if draft_block_seen and best_picks >= 9:
        print("  GSI DOES report the full draft in your own games.")
        print("  Manual entry is unnecessary — tell Claude, and the app can "
              "rely on it entirely.")
    elif draft_block_seen:
        print(f"  A 'draft' block arrived but only {best_picks} picks were "
              "ever visible.")
        print("  Send data_cache/gsi/ to Claude to see what it does carry.")
    else:
        print("  No 'draft' block ever arrived: GSI does NOT report the "
              "line-ups for a player's own match.")
        print("  Your own hero and game state ARE reported, so the app knows "
              "when a draft is happening and who you are;")
        print("  enemy picks have to be clicked in (or read from the screen "
              "with --vision).")
    print(f"\nArchived payloads: {ARCHIVE}")


if __name__ == "__main__":
    main()
