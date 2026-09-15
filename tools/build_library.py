"""Download hero portraits (via OpenDota constants -> Steam CDN) into
assets/portraits/base/ and build the perceptual-hash library.

Persona/arcana variant portraits are not on the CDN in a discoverable form;
they accumulate instead in assets/portraits/variants/<hero_id>/ — harvested
from real frames by tools/replay.py --harvest or dropped in by hand — and
are picked up automatically on every rebuild (many-to-one, same hero id).

Needs network. Re-run after a patch adds a hero.
"""

import concurrent.futures as futures
import sys
import threading
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from draft_assist import console                        # noqa: E402
from draft_assist.data.opendota import fetch_heroes, fetch_items  # noqa: E402
from draft_assist.config import ITEMS_DIR, item_slug  # noqa: E402
from draft_assist.vision import library  # noqa: E402

CDN = "https://cdn.cloudflare.steamstatic.com"

# HOW MANY PICTURES ARE IN FLIGHT AT ONCE, at the user's request:
# "loading in all of the hero portraits, item portraits, etc is very
# slow". It was 127 portraits and ~484 item icons fetched ONE AT A TIME,
# each one a fresh TCP and TLS handshake because every call was a bare
# `requests.get`, with a courtesy `sleep` between them - 37 seconds of
# the run was the sleeps alone. The cost here is almost entirely round
# trips rather than bytes (an icon is a few kilobytes), so the fix is to
# have several in the air and to reuse the connection.
# EIGHT rather than as many as the machine will take: this is Valve's
# own CDN, which serves the game client, and the difference between 8
# and 32 is small against the difference between 1 and 8.
WORKERS = 8

# A SESSION IS NOT THREAD-SAFE, so each worker gets its own - which is
# also what keeps the connection open for the fifty or so files that
# worker will fetch. One shared Session would undo most of the gain and
# occasionally corrupt a response.
_mine = threading.local()


def session() -> requests.Session:
    got = getattr(_mine, "session", None)
    if got is None:
        got = _mine.session = requests.Session()
    return got


def fetch_one(url: str, dest: Path) -> str:
    """Download one picture; answer "" or why not.

    **WRITTEN ASIDE AND RENAMED**, never straight to `dest`. Every
    caller here skips a file that already EXISTS, so a half-written
    picture from a run that was closed mid-download is skipped for ever
    after and draws as a blank tile - which is one of the four causes
    `item_icons.why_missing` exists to tell apart, and the only one the
    download itself can prevent. A rename is atomic on both platforms
    this runs on.
    """
    part = dest.with_name(dest.name + ".part")
    try:
        resp = session().get(url, timeout=30)
        resp.raise_for_status()
        part.write_bytes(resp.content)
        part.replace(dest)
        return ""
    except (requests.RequestException, OSError) as bad:
        part.unlink(missing_ok=True)
        return f"{type(bad).__name__}: {bad}"


def fetch_many(jobs: list, what: str, share=None) -> tuple:
    """Download a list of (url, dest, label); answer (done, failures).

    `share` maps a fraction of THIS batch onto a fraction of the whole
    run, so two batches can drive one bar. Progress is reported per
    picture from the thread that finishes it, which is the only place
    that knows - `as_completed` hands them back in whatever order they
    land rather than in the order they were asked for.
    """
    done, failed = 0, []
    if not jobs:
        return 0, failed
    with futures.ThreadPoolExecutor(max_workers=WORKERS) as pool:
        waiting = {pool.submit(fetch_one, url, dest): label
                   for url, dest, label in jobs}
        for finished in futures.as_completed(waiting):
            label = waiting[finished]
            why = finished.result()
            if why:
                failed.append(f"{label}: {why}")
            else:
                done += 1
            if share is not None:
                console.progress(share((done + len(failed)) / len(jobs)),
                                 f"{what} {done + len(failed)} of {len(jobs)}")
    return done, failed


def main() -> None:
    heroes = fetch_heroes()
    library.BASE_DIR.mkdir(parents=True, exist_ok=True)
    library.VARIANTS_DIR.mkdir(parents=True, exist_ok=True)
    (library.VARIANTS_DIR / "empty").mkdir(exist_ok=True)

    jobs, skipped = [], 0
    for hid, h in sorted(heroes.items()):
        img_path = h.get("img", "")
        if not img_path:
            print(f"  hero {hid} ({h['name']}): no img path in constants, skipping")
            continue
        short = h["internal_name"].removeprefix("npc_dota_hero_") or str(hid)
        dest = library.BASE_DIR / f"{hid}_{short}.png"
        if dest.exists():
            skipped += 1
            continue
        url = img_path if img_path.startswith("http") else CDN + img_path
        jobs.append((url, dest, f"hero {hid} ({h['name']})"))
    # THE PORTRAITS TAKE THE FIRST FIFTH OF THE BAR. There are about
    # 127 of them against 484 icons, so an even split would stall at
    # 50% for four fifths of the wait — the same silence wearing a
    # number that the updater's own bar was fixed for.
    downloaded, failed = fetch_many(jobs, "portraits",
                                    share=lambda part: part * 0.2)
    print(f"Portraits: {downloaded} downloaded, {skipped} already present"
          + (f", {len(failed)} failed" if failed else ""))
    for why in failed:
        print(f"  {why}")

    download_item_icons(share=lambda part: 0.2 + part * 0.8)

    params = library.load_params()
    lib = library.rebuild(params.hash_size)
    print(f"Library rebuilt: {len(lib)} entries at hash_size="
          f"{params.hash_size} -> {library.LIBRARY_FILE}")
    print("Next: `python -m draft_assist.proving.tune` to pick the "
          "recognition operating point against these portraits.")


def download_item_icons(verbose: bool = False, share=None) -> None:
    """Item art for the draft screen's item row.

    Named by a slug of the DISPLAY name, so `rules/items.yaml` needs no
    internal keys and the loader needs no lookup table. Failures here are
    reported and skipped: an item without a picture falls back to its name,
    and losing the whole portrait build over one 404 would be absurd.
    """
    ITEMS_DIR.mkdir(parents=True, exist_ok=True)
    items = fetch_items()
    print(f"  {len(items)} items listed; writing into {ITEMS_DIR}")
    jobs, skipped = [], 0
    for name, img_path in sorted(items.items()):
        dest = ITEMS_DIR / f"{item_slug(name)}.png"
        if dest.exists():
            skipped += 1
            continue
        url = img_path if img_path.startswith("http") else CDN + img_path
        if verbose and not jobs:
            print(f"  first URL: {url}")
        jobs.append((url, dest, f"item '{name}'"))
    downloaded, failed = fetch_many(jobs, "item icons", share=share)
    print(f"Item icons: {downloaded} downloaded, {skipped} already present"
          + (f", {len(failed)} failed" if failed else ""))
    for why in failed:
        print(f"  {why}")


if __name__ == "__main__":
    main()
