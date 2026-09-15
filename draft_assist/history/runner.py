"""One run, start to finish, off the UI thread.

`run` takes a progress callback and a cancel check and returns a `Report`.
Everything slow is here rather than in the widget, because a draft window
that stops answering while a thousand matches are fetched is worse than no
analyser at all — and because the app's live loop is not allowed anywhere
near a network call.
"""

import time
from datetime import datetime

from . import analyse, avatars, cache, opendota, shape
from .report import Before, Options, Report


class Refused(Exception):
    """The run cannot honestly be done. The message says why."""


# AN EMPTY MATCH LIST HAS THREE CAUSES AND ONE APPEARANCE, so the profile
# lookup is what tells them apart — see `opendota.profile`. Answering all
# three with the same paragraph made the commonest one (a Dota privacy
# setting, which the user can fix in ten seconds) read as a fault in the
# app. Each is two sentences: what is wrong, and what to do about it.
PRIVATE = (
    "This account's match history is private. Turn on Expose Public Match "
    "Data in Dota 2 (Settings ▸ Options), play a game, and run this again.")

UNKNOWN_ACCOUNT = (
    "OpenDota has never seen this account, so the ID is probably not the "
    "one you meant. Check the Friend ID on your Dota 2 profile — it is not "
    "the 17 digit Steam ID.")

NO_MATCHES = (
    "OpenDota returned no matches for this account, and could not be asked "
    "whether it knows the account at all. That is usually Expose Public "
    "Match Data switched off in Dota 2 (Settings ▸ Options); it can also "
    "mean the ID belongs to somebody who has not played.")


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
    who = opendota.profile(options.account_id)
    name = who.name
    if cancelled():
        raise Refused("Stopped.")

    # THE PICTURE, ONCE, HERE. The account row on the Draft tab draws it
    # on every repaint and must never make a request, so the one moment
    # it can be fetched is during a run - and `ensure` skips the fetch
    # entirely when the avatar has not changed. Never fatal: no picture
    # means the row draws its fallback, which is a normal state.
    avatars.ensure(options.account_id, who.avatar)

    say(f"Reading the hero list… ({name})" if name
        else "Reading the hero list…")
    heroes = opendota.heroes()
    if cancelled():
        raise Refused("Stopped.")

    # TWICE THE WINDOW IN ONE REQUEST, at the user's request: "when you
    # run it just make the range of data requested double what was
    # selected, so that you haev that data to work with". The endpoint
    # takes one span and returns it newest-first, so asking for double
    # and splitting it here costs the same ONE request the run always
    # made — where asking twice cost two against a free API, for two
    # figures in a callout.
    say("Asking OpenDota for the match list…")
    limit, span = fetch_span(options)
    rows = opendota.matches(options.account_id, limit, span)
    if not rows:
        # Nothing came back, and WHY decides what to say. An account
        # OpenDota holds a profile for is a real account whose matches are
        # hidden; one it has never heard of is a wrong number.
        raise Refused({True: PRIVATE, False: UNKNOWN_ACCOUNT}.get(
            who.known, NO_MATCHES))

    # THE CAP IS THE WINDOW'S, not the doubled fetch's. The limit was
    # doubled to reach behind the window; what the user asked for is at
    # most `cap` matches IN it, and OpenDota returns newest first, so the
    # cut keeps the newest of them.
    recent, earlier = split_window(rows, options.days, options.cap)
    # WAS THE WINDOW ITSELF CUT? See `measure_before`: a window trimmed
    # to the cap is a SHORTER stretch of time than the one behind it, and
    # the delta claims the two are the same length.
    trimmed = len(recent) < len(rows) - len(earlier)

    say("Shaping the matches…")
    shaped = shape.shape(recent, heroes, days=options.days,
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
        # THE BUNDLED MAP UNDERNEATH, always. `opendota.item_names`
        # answers {} on any ApiError, so a fetch that fails used to leave
        # the block printing numeric ids with nothing saying why.
        fetched = opendota.item_names()
        # SAVED, because `cache.rebuild` has no network and every later
        # opening of this run goes through it — an item added since the
        # bundled file was cut is named on the next run and stays named.
        cache.save_item_names(fetched)
        item_names = cache.item_names()
        item_names.update(fetched)

    # HOW THE STRETCH BEFORE THIS ONE WENT, for the two deltas in the
    # profile callout — out of the same rows, at no extra cost.
    before = measure_before(earlier, options, heroes,
                            clipped=trimmed or clipped(rows, options, limit))

    say("Measuring…")
    blocks = analyse.build_blocks(shaped.matches, shaped.baseline,
                                  options.picked, item_names,
                                  ds=analyse.ranked_dataset())
    return Report(options=options, how="", name=name, matches=shaped.matches,
                  blocks=blocks, dropped=shaped.dropped,
                  sessions=shaped.sessions, returned=shaped.returned,
                  ran_at=datetime.now(), before=before)


def fetch_span(options: Options) -> tuple[int, int | None]:
    """What to ask OpenDota for: twice the window, and twice the cap.

    ONE REQUEST FOR BOTH HALVES, at the user's request — "just make the
    range of data requested double what was selected, so that you haev
    that data to work with". The run needs the window itself and the
    equal-length stretch behind it (see `measure_before`), and the
    endpoint only takes "the last N days" — so the choice was two
    requests or one twice as long, and one is free where two are not.

    The LIMIT doubles with the span for a reason: a limit keeps the most
    RECENT rows, so leaving it at `cap` while doubling the days would
    clip away exactly the older half being reached for.

    "All history" asks for everything and has nothing behind it.
    """
    days = options.days
    if not days:
        return options.cap, None
    return options.cap * 2, days * 2


def split_window(rows, days: int | None, cap: int,
                 now: float | None = None) -> tuple[list, list]:
    """The window's own matches, and the ones behind it.

    Cut by `start_time` rather than by position, because the two halves
    are defined by the DATE the user chose and the row order is only
    incidentally the same thing.
    """
    if not days:
        return list(rows)[:cap], []
    cutoff = (time.time() if now is None else now) - days * 86400
    recent, earlier = [], []
    for row in rows:
        if not isinstance(row, dict):
            continue
        (recent if (row.get("start_time") or 0) >= cutoff
         else earlier).append(row)
    return recent[:cap], earlier


def clipped(rows, options: Options, limit: int,
            now: float | None = None) -> bool:
    """Did the fetch stop before it had given us everything we asked for?

    IT MATTERS MORE HERE THAN ANYWHERE ELSE, because a limit keeps the
    most RECENT rows: the half that gets dropped is exactly the older
    half the delta is measured against. A clipped fetch would report that
    the account played far less last year, which is a claim about the cap
    rather than about them.

    TWO TESTS, because one of them is about a limit we do not control.
    The first is ours: as many rows back as we asked for means there were
    probably more. The second is for a SERVER-SIDE cap — OpenDota does
    not document a ceiling on `limit` and could apply one silently, which
    the first test would sail straight past — so a fetch that came back
    substantial and STILL did not reach behind the window is treated as
    cut off. An account whose whole history is shorter than the window is
    not caught by that, and must not be: its `earlier` is empty because
    it was not playing, which is a real answer.
    """
    if len(rows) >= limit:
        return True
    days = options.days
    if not days or len(rows) < max(1, int(options.cap)):
        return False
    stamps = [row.get("start_time") or 0 for row in rows
              if isinstance(row, dict)]
    oldest = min(stamps) if stamps else 0
    return oldest > (time.time() if now is None else now) - days * 86400


def measure_before(rows, options: Options, heroes: dict,
                   clipped: bool = False) -> Before | None:
    """How the equal-length stretch before the window went.

    FILTERED THE SAME WAY the window itself is, through `shape`, or the
    delta would compare a ranked, turbo-free sample against everything
    the account has played and report a change that is entirely the
    filters.

    **NONE IN EVERY DOUBTFUL CASE, and that is the point of it being
    three-valued.** "All history" has nothing before it; the fetch can
    come back CLIPPED (see `clipped`); and the window itself can be cut
    to the cap, which is the subtler one — a window trimmed to its
    newest `cap` matches covers LESS TIME than the stretch behind it,
    so the delta would be comparing four months against six while
    saying it compared six against six. Both come in as `clipped`,
    because the honest answer to all of them is the same: no delta.

    An EMPTY stretch is a different answer and is kept: a new account has
    a window's worth of history and nothing behind it, so both figures
    are up from nothing and the deltas say so.
    """
    if not options.days or clipped:
        return None
    if not rows:
        return Before()
    shaped = shape.shape(rows, heroes, days=None,
                         no_turbo=options.no_turbo,
                         ranked_only=options.ranked_only)
    return Before(matches=len(shaped.matches),
                  wins=sum(1 for m in shaped.matches if m.win))


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
    fetched = fetch_names() if read else {}
    if fetched:
        cache.save_item_names(fetched)
    names = cache.item_names()
    names.update(fetched)
    rebuilt = analyse.item_analysis(report.matches, names)
    report.blocks = [rebuilt if b.kind == "items" else b
                     for b in report.blocks]
    return read
