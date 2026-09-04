"""Pretend to be Dota: POST Game State Integration payloads to the app.

Lets the whole GSI path be exercised — listener, auth check, parser,
provider, UI, overlay — with the game closed. Start the app first, then run
this; the app should light up exactly as if a match were running.

    python tools/simulate_gsi.py                  # a ranked All Pick draft
    python tools/simulate_gsi.py --with-draft     # pretend GSI reports both
                                                  # line-ups (it probably
                                                  # does not — rehearsal only)
    python tools/simulate_gsi.py --from data_cache/gsi   # replay REAL
                                                  # payloads recorded earlier
    python tools/simulate_gsi.py --speed 4 --loop

Recorded payloads are the better test: modelled ones can only confirm what
this codebase already believes about the format.
"""

import argparse
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from draft_assist.config import DATA_CACHE  # noqa: E402
from draft_assist.data import store  # noqa: E402
from draft_assist.gsi import install as gsi_install  # noqa: E402
from draft_assist.gsi import simulate  # noqa: E402

import json  # noqa: E402


def send(port: int, payload: dict, timeout: float = 5.0) -> None:
    request = urllib.request.Request(
        f"http://127.0.0.1:{port}/",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    urllib.request.urlopen(request, timeout=timeout).read()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=gsi_install.DEFAULT_PORT)
    parser.add_argument("--speed", type=float, default=1.0,
                        help="time multiplier; 4 runs a draft four times faster")
    parser.add_argument("--loop", action="store_true",
                        help="repeat the scenario until interrupted")
    parser.add_argument("--with-draft", action="store_true",
                        help="include the spectator 'draft' block, to "
                             "rehearse what the app does if GSI ever does "
                             "report both line-ups")
    parser.add_argument("--from", dest="replay", metavar="DIR",
                        nargs="?", const=str(DATA_CACHE / "gsi"),
                        help="replay real payloads archived by probe_gsi "
                             "instead of modelled ones")
    args = parser.parse_args()

    token = gsi_install.read_installed_token()
    print(f"Sending to http://127.0.0.1:{args.port}/"
          + (" with the installed auth token" if token else
             " with no auth token (none installed)"))

    if args.replay:
        try:
            steps = simulate.replay_scenario(Path(args.replay), token=token)
        except (FileNotFoundError, ValueError) as exc:
            raise SystemExit(str(exc))
        print(f"Replaying {len(steps)} RECORDED payloads from {args.replay}")
    else:
        dataset = store.load_or_empty()
        if dataset.is_empty:
            print("No hero data downloaded — using built-in hero ids.")
        steps = simulate.all_pick_scenario(
            dataset, token=token, include_draft_block=args.with_draft,
            speed=args.speed)
        print(f"Simulating {len(steps)} MODELLED payloads"
              + (" including the spectator draft block" if args.with_draft
                 else " (no draft block, as a player's own feed is expected)"))
    print("Start the app first if you have not. Ctrl+C to stop.\n")

    sent = 0
    try:
        while True:
            for step in steps:
                time.sleep(step.delay)
                try:
                    send(args.port, step.payload)
                    sent += 1
                    print(f"  sent #{sent:4d}  {step.label}")
                except urllib.error.URLError as exc:
                    raise SystemExit(
                        f"\nCould not reach the app on port {args.port}: "
                        f"{exc}\nIs it running, and is the source set to "
                        "game data (Capture > Use game data)?")
            if not args.loop:
                break
            print("  --- looping ---")
    except KeyboardInterrupt:
        print("\nstopped.")

    print(f"\nDone: {sent} payloads sent.")
    if not args.replay:
        print("Reminder: these were MODELLED on what this codebase expects "
              "Dota to send.\nRecord real ones with Game > Record game data "
              "for a stronger test.")


if __name__ == "__main__":
    main()
