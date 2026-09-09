"""One run, start to finish, off the UI thread.

`run` takes a progress callback and a cancel check and returns a `Report`.
Everything slow is here rather than in the widget, because a draft window
that stops answering while a thousand matches are fetched is worse than no
analyser at all — and because the app's live loop is not allowed anywhere
near a network call.
"""

from datetime import datetime

from . import analyse, opendota, shape
from .report import Options, Report


class Refused(Exception):
    """The run cannot honestly be done. The message says why."""


def run(options: Options, say=None, cancelled=None) -> Report:
    say = say or (lambda text, done=0, total=0: None)
    cancelled = cancelled or (lambda: False)

    # THE DISPLAY NAME FIRST, because everything after it can then say
    # whose history it is reading — and because the remembered-accounts
    # list is written from this report, so a run is the one moment the
    # name can be resolved without the tab making a network call of its
    # own. Cosmetic: "" is a perfectly good answer and the number stands
    # on its own, exactly as it did before.
    say("Looking up the account…")
    name = opendota.persona(options.account_id)
    if cancelled():
        raise Refused("Stopped.")

    say(f"Reading the hero list… ({name})" if name
        else "Reading the hero list…")
    heroes = opendota.heroes()
    if cancelled():
        raise Refused("Stopped.")

    say("Asking OpenDota for the match list…")
    rows = opendota.matches(options.account_id, options.cap, options.days)
    if not rows:
        # The commonest cause by a distance, and the app must say it
        # outright rather than drawing an empty report that looks broken.
        raise Refused(
            "OpenDota returned no matches for that account. That almost "
            "always means Expose Public Match Data is switched off in the "
            "Dota 2 settings — turn it on, play a game, and try again. It "
            "can also mean the account ID belongs to somebody who has not "
            "played.")

    say("Shaping the matches…")
    shaped = shape.shape(rows, heroes, days=options.days,
                         no_turbo=options.no_turbo,
                         ranked_only=options.ranked_only)
    if len(shaped.matches) < analyse.MIN_SAMPLE:
        raise Refused(
            f"Only {len(shaped.matches)} matches survived the filters, and "
            f"{analyse.MIN_SAMPLE} is the fewest this will analyse. Widen "
            "the window, raise the cap, or turn off Ranked only.")

    item_names = {}
    if options.picked.get("items"):
        say("Reading the item list…")
        item_names = opendota.item_names()

    say("Measuring…")
    blocks = analyse.build_blocks(shaped.matches, shaped.baseline,
                                  options.picked, item_names)
    return Report(options=options, how="", name=name, matches=shaped.matches,
                  blocks=blocks, dropped=shaped.dropped,
                  sessions=shaped.sessions, returned=shaped.returned,
                  ran_at=datetime.now())


def enrich_items(report: Report, say=None, cancelled=None) -> int:
    """Fill in the final inventory a match at a time, for the top heroes.

    Items are only guaranteed on the SINGLE MATCH endpoint, which is one
    request per match against a free API — so this is opt-in, paced to
    about fifty a minute, interruptible, and backs off when it is told to
    slow down rather than hammering. Returns how many matches were read.
    """
    say = say or (lambda text, done=0, total=0: None)
    cancelled = cancelled or (lambda: False)

    block = next((b for b in report.blocks if b.kind == "items"), None)
    if block is None:
        return 0
    top = {group.hero for group in block.groups}
    targets = [m for m in report.matches
               if m.hero in top and not m.items and m.match_id is not None]
    if not targets:
        return 0

    read = strikes = 0
    index = 0
    while index < len(targets):
        if cancelled():
            break
        match = targets[index]
        try:
            payload = opendota.one_match(match.match_id)
            strikes = 0
            for player in (payload or {}).get("players") or []:
                if isinstance(player, dict) \
                        and player.get("player_slot") == match.slot:
                    match.items = shape._items(player)
                    break
            if match.items:
                read += 1
        except opendota.ApiError as error:
            if error.kind == "rate":
                strikes += 1
                if strikes > opendota.ITEM_STRIKES:
                    say("OpenDota kept rate limiting. Stopped.",
                        index, len(targets))
                    break
                say("Rate limited — waiting…", index, len(targets))
                opendota.sleep(opendota.ITEM_BACKOFF)
                continue        # the same match again, after the backoff
        index += 1
        say("Reading final inventories…", index, len(targets))
        opendota.sleep(opendota.ITEM_PACE)

    # Rebuild the item block against what is now known.
    from .opendota import item_names as fetch_names
    names = fetch_names() if read else {}
    rebuilt = analyse.item_analysis(report.matches, names)
    report.blocks = [rebuilt if b.kind == "items" else b
                     for b in report.blocks]
    return read
