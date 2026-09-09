"""Download alternative hero portraits (personas, arcanas, custom sets).

The recognition library is built from Valve's ONE base image per hero, so a
hero wearing a persona or an arcana that changes the top-bar picture never
matches — it sits at UNKNOWN while the other nine resolve. This pulls the
community's collection of those images and files them under the right hero.

Downloaded to YOUR disk at runtime, never committed: they are Valve's
artwork, and the repository carrying them would be redistributing them the
moment anybody else clones it. Same rule as `tools/build_library.py`, which
fetches the base portraits the same way.

    python tools/fetch_custom_portraits.py --dry-run   # just the mapping
    python tools/fetch_custom_portraits.py

The files are named "icon" but they are NOT the square hero icon — they are
the same 16:9 top-bar portrait the recogniser crops, published at 128x72,
256x144, 268x151 and 384x216. Aspect is what matters (pHash resizes to a
fixed square), so every one of those is usable as it is.

The hero is read out of the FILENAME, by the longest hero name that appears
in it as whole words. That handles the awkward ones — "Crown of the One
True King Wraith King icon" resolves to Wraith King rather than Monkey
King, "Davion of Dragon Hold Dragon Knight icon" to Dragon Knight — and
anything it cannot place is LISTED rather than filed somewhere arbitrary.
`--dry-run` prints the whole mapping and downloads nothing, which is the
way to check it before it writes anything.

`EXPECTED` is the set of heroes known to have one, so a run can say which
of them ended up with no file. That is the signal that the mapping, or the
category, has missed something, and it is reported on a REAL run as well
as a dry one — a dry run is the check nobody remembers to do, and the
whole point of the list is to notice a miss.

IT HAS NOW RUN AGAINST THE LIVE API, which reverses the warning that used
to stand here. This was written where the network policy blocks the site
outright, so for a long time nothing but `--dry-run` had ever been read.
The first real run, on the user's own machine: **32 files in the
category, 32 mapped, 0 it could not place, and every one of the 23 heroes
in `EXPECTED` covered.** The awkward cases the matcher was built for came
out right — "Crown of the One True King Wraith King" on Wraith King and
not Monkey King, "Davion of Dragon Hold Dragon Knight" on Dragon Knight —
and several heroes correctly took more than one file (Pudge three, and
the "Alt" styles beside their base arcanas). The mapping is confirmed;
what is still unverified is only what a future patch adds to the
category.

NEEDS NO API KEY (see `hero_names`), which is the whole reason it can be
one step of `tools/fetch_assets.py`.

The app also learns an unmatched portrait off your own screen by
elimination while you play, which needs no download at all and produces
exactly the picture your HUD draws.
"""

import argparse
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import requests  # noqa: E402

from draft_assist.console import plain_output, say  # noqa: E402
from draft_assist.data import opendota, store  # noqa: E402
from draft_assist.vision import library  # noqa: E402

# Heroes known to have an alternative top-bar portrait — personas, arcanas
# and the arcana alt styles. Not used to filter anything: it is there so a
# dry run can say which of them came back with no file, which is how a
# mapping miss shows up.
EXPECTED = (
    "Anti-Mage", "Axe", "Crystal Maiden", "Dragon Knight", "Earthshaker",
    "Io", "Invoker", "Juggernaut", "Legion Commander", "Lina",
    "Monkey King", "Ogre Magi", "Phantom Assassin", "Pudge",
    "Queen of Pain", "Rubick", "Shadow Fiend", "Spectre", "Techies",
    "Terrorblade", "Windranger", "Wraith King", "Zeus",
)

API = "https://dota2.fandom.com/api.php"
CATEGORY = "Category:Custom_hero_icons"
# A wiki API asks for a real user agent, and an anonymous scraper hammering
# it is how a project gets blocked. One page of results at a time, and the
# category is a few hundred files at most.
HEADERS = {"User-Agent": "DotaDraftAssist/1.0 (personal tool; batch fetch)"}
PAGE = 200


def hero_names() -> dict[int, str]:
    """Hero id -> name, WITHOUT needing a Stratz key.

    All this tool wants is the list of hero names, to find one inside a
    filename. It used to take them from `store.load()` — the statistics
    dataset — which is built by `pull_data.py` and needs a Stratz key, so
    on a machine that had skipped the key at setup this step raised

        FileNotFoundError: No dataset cache at ...\data_cache\dataset.npz

    and told the user to go and pull statistics they had deliberately not
    asked for. The other two artwork steps beside it need no key at all,
    had already succeeded, and this one took the whole run down with it.

    Hero names are not statistics. `build_library` — the step that
    downloads the base portraits this one supplements — gets them from
    OpenDota's public `constants/heroes`, no account of any kind. So:
    the dataset if it happens to be there (free, offline, already
    parsed), and otherwise the same public constants, which this tool is
    on the network for anyway.
    """
    try:
        ds = store.load()
        return {hid: ds.name(hid) for hid in ds.hero_ids}
    except FileNotFoundError:
        pass                    # no statistics on this machine: fine
    return {hid: h["name"] for hid, h in opendota.fetch_heroes().items()}


def _norm(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", text.lower()).strip()


def hero_matcher(names: dict[int, str]):
    """filename -> hero id, by the LONGEST hero name inside it.

    Longest wins because several heroes' names contain another's: a file
    naming "Nature's Prophet" also contains "Prophet", and "Death Prophet"
    is a different hero. Matching on the longest name that appears, as
    whole words, is what keeps those apart.
    """
    ordered = sorted(((hid, _norm(name)) for hid, name in names.items()),
                     key=lambda pair: -len(pair[1]))

    def match(title: str) -> int | None:
        haystack = f" {_norm(title)} "
        for hid, needle in ordered:
            if f" {needle} " in haystack:
                return hid
        return None
    return match


def category_files(session) -> list[str]:
    titles, carry_on = [], None
    while True:
        params = {"action": "query", "list": "categorymembers",
                  "cmtitle": CATEGORY, "cmtype": "file", "cmlimit": PAGE,
                  "format": "json"}
        if carry_on:
            params["cmcontinue"] = carry_on
        data = session.get(API, params=params, timeout=30).json()
        titles += [m["title"] for m
                   in data.get("query", {}).get("categorymembers", [])]
        carry_on = data.get("continue", {}).get("cmcontinue")
        if not carry_on:
            return titles


def image_urls(session, titles: list[str]) -> dict[str, str]:
    """File title -> direct image URL, asked 50 at a time."""
    out: dict[str, str] = {}
    for start in range(0, len(titles), 50):
        chunk = titles[start:start + 50]
        data = session.get(API, timeout=30, params={
            "action": "query", "titles": "|".join(chunk),
            "prop": "imageinfo", "iiprop": "url", "format": "json"}).json()
        for page in data.get("query", {}).get("pages", {}).values():
            info = page.get("imageinfo") or []
            if info and info[0].get("url"):
                out[page["title"]] = info[0]["url"]
    return out


def report_missing(got: set[str]) -> None:
    """Say which of `EXPECTED` came back with nothing.

    On a REAL run as well as a dry one. It used to be inside the dry-run
    branch, which is the check nobody runs — and the point of the list is
    to notice that the category or the matcher has drifted, which shows up
    on whichever run somebody happens to do. Silence here is the good
    answer and the first real run gave it: all 23 covered.
    """
    missing = [name for name in EXPECTED if name not in got]
    if missing:
        say("\nExpected an alternative portrait for these and found none - "
            "the mapping or the category has missed them:\n  "
            + ", ".join(missing))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true",
                        help="print the mapping and download nothing")
    parser.add_argument("--limit", type=int, default=0,
                        help="stop after this many downloads (0 = all)")
    args = parser.parse_args()

    plain_output()
    names = hero_names()
    match = hero_matcher(names)

    session = requests.Session()
    session.headers.update(HEADERS)
    titles = category_files(session)
    print(f"{len(titles)} files in {CATEGORY}")

    mapped, unmapped = [], []
    for title in titles:
        stem = title.removeprefix("File:")
        hid = match(stem)
        (mapped if hid is not None else unmapped).append((hid, stem, title))

    print(f"mapped {len(mapped)}, could not place {len(unmapped)}")
    for _hid, stem, _t in unmapped:
        print(f"  unmapped: {stem}")
    report_missing({names[hid] for hid, _s, _t in mapped})
    if args.dry_run:
        for hid, stem, _t in mapped:
            print(f"  {names[hid]:22s} <- {stem}")
        print("\nDry run: nothing downloaded. Check those mappings, then "
              "run again without --dry-run.")
        return

    urls = image_urls(session, [t for _h, _s, t in mapped])
    written = skipped = 0
    for hid, stem, title in mapped:
        url = urls.get(title)
        if not url:
            print(f"  no URL for {stem}")
            continue
        folder = library.VARIANTS_DIR / str(hid)
        folder.mkdir(parents=True, exist_ok=True)
        dest = folder / (re.sub(r"[^A-Za-z0-9_.-]+", "_", stem) or "custom")
        dest = dest.with_suffix(".png")
        if dest.exists():
            skipped += 1
            continue
        resp = session.get(url, timeout=60)
        resp.raise_for_status()
        dest.write_bytes(resp.content)
        written += 1
        print(f"  {names[hid]:22s} <- {stem}")
        if args.limit and written >= args.limit:
            break

    print(f"\n{written} downloaded, {skipped} already had.")
    # Where they went, always — they are filed under the hero's numeric id
    # rather than its name, so an empty-looking `variants` folder is what a
    # user sees when they go to check.
    print(f"They are filed by hero id under {library.VARIANTS_DIR}"
          f"{os.sep}<hero id>{os.sep}, e.g. "
          f"{library.VARIANTS_DIR}{os.sep}14{os.sep}Feast_of_Abscession"
          "_Pudge_icon.png for Pudge.")
    if written:
        print("The app rebuilds its library when a file there is newer "
              "than the cache, so they are searchable at the next start.")


if __name__ == "__main__":
    main()
