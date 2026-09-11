"""The statistics, and the sentences they are allowed to produce.

Every analysis asks ONE question: is this bucket far enough off the
player's own rate to be distinguishable from sampling noise? For a
proportion the standard error is sqrt(p(1-p)/k) with p the player's own
rate and k the bucket size, and the reported sigma is how many of those
the bucket sits away.

TWO FLOORS, and they do different jobs. `MIN_BUCKET` is how many games a
bucket needs before it may produce a FINDING; below it the row still
appears, muted, so what was measured is visible without inviting anyone to
act on it. `MIN_DISPLAY` keeps single-game buckets out of the table
entirely — a row reading 0% next to an n of one is noise wearing a number
— while the workbook still carries them and the block header says how many
were hidden.

MANY ANALYSES RUN AT ONCE, so some buckets clear the bar by chance
alone. The report says so on its own front page. A finding is a hypothesis
to test against the next hundred games, not a conclusion.
"""

from dataclasses import dataclass, field
import math

from .shape import WEEKDAY

MIN_BUCKET = 8          # games before a bucket may produce a finding
MIN_DISPLAY = 2         # games before a bucket appears in the table at all
SIGMA_CAT = 1.5         # how far off the datum a bucket must sit
MIN_SAMPLE = 10         # refuse to analyse a sample smaller than this
# EVERY HERO, most played first — there is no cap any more. The block was
# fixed at your three most played and called itself "top 3 heroes"; at the
# user's request the card now has a DROPDOWN and shows one hero at a time,
# so the list it offers has to be the whole list. It costs nothing: each
# group walks only its own hero's matches, so the total work is one pass
# over the sample however many heroes that is.

TOD_ORDER = [f"{h:02d}:00 to {h + 2:02d}:59" for h in range(0, 24, 3)]
LEN_ORDER = ["Under 25 min", "25 to 35 min", "35 to 45 min", "Over 45 min"]
POS_ORDER = ["1st game", "2nd game", "3rd game", "4th game", "5th game",
             "6th game or later"]
TILT_ORDER = ["First of session", "After a win", "After a loss",
              "After 2+ losses"]
PARTY_ORDER = ["Solo", "Party of 2", "Party of 3", "Party of 4", "Party of 5",
               "Unknown"]


@dataclass
class Bucket:
    key: str
    n: int = 0
    wins: int = 0
    rate: float = 0.0
    mean: float = 0.0
    delta: float = 0.0
    se: float = 0.0
    sigma: float = 0.0
    eligible: bool = False
    # A short standing printed beside the figure ("top 12%"). Only the
    # counters block uses it; everything else leaves it empty.
    note: str = ""


@dataclass
class Finding:
    """One bucket that stood out, said twice and measured once.

    `text` is the sentence the workbook carries. `short` is what the
    summary cards on the History tab print — "Tuesday win rate 65%" —
    and `value` is the figure inside it, so the bar drawn beside it can
    put a marker where this bucket sits among its neighbours without
    parsing the words back out of a sentence. Both are built HERE, next
    to the long form: two spellings of one fact assembled in two places
    is how they come to disagree.
    """

    sigma: float
    key: str
    text: str
    short: str = ""
    value: float = 0.0
    n: int = 0


@dataclass
class Block:
    id: str
    name: str
    desc: str
    kind: str                       # "cat", "metric" or "items"
    rows: list = field(default_factory=list)
    shown: list = field(default_factory=list)
    hidden: int = 0
    hidden_games: int = 0
    findings: list = field(default_factory=list)
    no_finding: list = field(default_factory=list)
    datum: float | None = None
    unit: str = ""
    caveat: str = ""
    covered: int = 0
    total: int = 0
    # How far the bar column reaches, when the block knows better than
    # the rows on screen do. The counters block sets it from the WHOLE
    # hero pool rather than from your own heroes, which are a handful of
    # it and never its extremes. Zero means "work it out from the rows",
    # which is what every other block still does.
    scale: float = 0.0
    groups: list = field(default_factory=list)


@dataclass
class ItemGroup:
    hero: str
    games: int
    measured: int
    baseline: float | None
    rows: list
    shown: list
    hidden: int


# THE NAMES ARE SHORT AND OF A LENGTH, at the user's request: "make them
# concise as possible generally, and similar character length so it looks
# proportionally right". They were 11 to 30 characters, and the summary
# lines now print the block's name in a column of its own beside every
# finding — so "Hero damage per minute by hero" set that column's width
# for the whole card while "Day of week" left two thirds of it blank.
# They are 10 to 15 now. This ONE list is what the sidebar lists, what
# each card is headed, and what that column prints, so the three cannot
# disagree; `DESCS` still carries the full explanation, as the tick box's
# tooltip and in the workbook, so nothing was lost by shortening them.
ANALYSES = [
    ("hero", "Hero win rates", True,
     "Your win rate on each hero you played."),
    ("length", "Match length", True,
     "Your win rate by how long the game ran."),
    ("tod", "Time of day", True,
     "Your win rate by three-hour band, on this machine's local clock."),
    ("dow", "Day of week", True,
     "Your win rate by the local day the match started."),
    ("session", "Game in session", True,
     "Your win rate by how many games into a session you were. A gap of "
     "over three hours starts a new one."),
    ("tilt", "Previous result", True,
     "Your win rate by what the previous game in the same session did."),
    ("side", "Radiant or Dire", True,
     "Your win rate on Radiant against Dire."),
    ("party", "Party size", True,
     "Your win rate by how many of you queued together."),
    ("herodmg", "Hero dmg/min", True,
     "Hero dmg/min on each hero, relative to the average."),
    ("herokda", "Weighted KDA", True,
     "Kills plus three tenths of assists over deaths, relative to the "
     "average."),
    # PER MINUTE, AND THE NAME HAS TO SAY SO. It read "Building dmg"
    # beside a figure of 116, which invites reading it as a whole game's
    # damage — "that can't be total building dmg, right?" The field is
    # `tower_per_min` and always has been; only the label was ambiguous.
    # SIEGE rather than BUILDING because it is a syllable shorter and
    # fits the column on one line, which "Building dmg/min" did not.
    ("towerdmg", "Siege dmg/min", True,
     "Siege dmg/min on each hero, relative to the average."),
    # THE FARM FOUR. Gold and XP arrive from OpenDota ALREADY per minute,
    # so those two are read straight off the row; CS and denies are totals
    # and are divided here, because a raw total measures how long the game
    # ran at least as much as how it was played.
    ("gold", "Gold/min", True,
     "Gold per minute on each hero, relative to the average."),
    ("xp", "XP/min", True,
     "Experience per minute on each hero, relative to the average."),
    ("cs", "CS/min", True,
     "Last hits per minute on each hero, relative to the average."),
    ("denies", "Denies/game", True,
     "Denies per game on each hero, relative to the average."),
    # NOT MEASURED FROM YOUR GAMES, and the only section here that is
    # not. Counterability is a property of the HERO, read out of the
    # ranked dataset; your history only decides which heroes appear. So
    # there is no "against your win rate" column and no sigma - it is the
    # same figure for everybody who plays that hero.
    ("counters", "Hero Counters", True,
     "How each of your heroes fares against the whole hero pool, weighted "
     "by how often each opponent is picked. The bar is its ranking among "
     "every hero in the game."),
    ("items", "Items by hero", True,
     "Win rate in games that ended with each item in your inventory, "
     "against that hero's own win rate."),
]
NAMES = {key: name for key, name, _, _ in ANALYSES}
DESCS = {key: desc.replace("{min}", str(MIN_BUCKET))
         for key, _, _, desc in ANALYSES}
DEFAULT_ON = {key: on for key, _, on, _ in ANALYSES}

# How each split reads in a sentence, so a finding is English rather than a
# bucket label bolted onto a number.
PHRASE = {
    "hero": lambda k: f"playing {k}",
    "length": lambda k: f"when games run {k.lower()}",
    "tod": lambda k: f"starting between {k}",
    "dow": lambda k: f"on {k}s",
    "session": lambda k: f"on the {k.lower()} of a session",
    "tilt": lambda k: k.lower(),
    "side": lambda k: f"playing {k}",
    "party": lambda k: ("playing solo" if k == "Solo"
                        else f"playing in a {k.lower()}"),
}


def _pct(value: float) -> str:
    return f"{value * 100:.0f}%"


SIG_FIGURES = 2

NO_DATASET = (
    "No hero statistics on this machine yet, so there is nothing to "
    "measure a hero against. Settings > Downloads fetches them.")
COUNTER_CAVEAT = (
    "This is a property of the HERO, not of your play: it is the same "
    "figure for everybody who picks it, and your history only decides "
    "which heroes are listed. It reads at whichever ranks the statistics "
    "were built for, which is not necessarily your own. And it counts "
    "matchups only - a hero nothing counters can still be a poor pick "
    "because of what it fails to do for a line-up.")


def sig(value, figures: int = SIG_FIGURES) -> str:
    """A figure to `figures` significant figures, at the user's request —
    "I basically want all numbers in this analysis to be to two
    significant figures".

    SIGNIFICANT FIGURES RATHER THAN DECIMAL PLACES, because these blocks
    span four orders of magnitude: gold runs in the hundreds, CS in
    single figures and denies in hundredths. One decimal-place setting
    per block was the old answer and it had to be chosen by hand for
    each, which is a number to get wrong every time a section is added —
    and getting it wrong is not cosmetic. Denies at nought decimal places
    is 0 for every hero in the list.

    NEVER SCIENTIFIC NOTATION. `f"{614.7:.2g}"` is "6.1e+02", which is
    the right number and an unreadable one on a card read at a glance.
    """
    if value is None:
        return ""
    value = float(value)
    if not math.isfinite(value):
        return ""
    if value == 0:
        return "0"
    places = figures - 1 - math.floor(math.log10(abs(value)))
    rounded = round(value, places)
    # ROUNDING CAN CROSS A POWER OF TEN. 9.99 to two figures is 10, but
    # the places were worked out from 9.99's magnitude, so it would print
    # "10.0" — three figures, from the one line that exists to give two.
    if rounded:
        places = figures - 1 - math.floor(math.log10(abs(rounded)))
        rounded = round(value, places)
    # NO TRAILING ".0", at the user's request — "if it's something that
    # is inherently a whole number don't add a .0 to the end". A weighted
    # KDA of 3.04 reads "3" rather than "3.0". The trade is real and is
    # theirs: "3" claims one significant figure where "3.0" claimed two.
    # It does NOT reach inside the decimals — 0.30 is not a whole number
    # and keeps its second figure, or the block would lose the precision
    # it is drawn at.
    if places <= 0 or rounded == int(rounded):
        return f"{int(round(rounded)):d}"
    return f"{rounded:.{places}f}"


def categorical(matches, baseline: float, key_of, order=None) -> list:
    """Win rate per bucket, with the sigma against the player's own rate."""
    tally = {}
    for match in matches:
        key = key_of(match)
        if key is None:
            continue
        bucket = tally.setdefault(key, Bucket(key=key))
        bucket.n += 1
        bucket.wins += 1 if match.win else 0

    rows = []
    for bucket in tally.values():
        bucket.rate = bucket.wins / bucket.n
        bucket.delta = bucket.rate - baseline
        bucket.se = math.sqrt(baseline * (1 - baseline) / bucket.n)
        bucket.sigma = bucket.delta / bucket.se if bucket.se > 0 else 0.0
        bucket.eligible = bucket.n >= MIN_BUCKET
        rows.append(bucket)

    if order == "count":
        rows.sort(key=lambda b: (-b.n, b.key))
    elif callable(order):
        rows.sort(key=order)
    elif order:
        index = {key: i for i, key in enumerate(order)}
        rows.sort(key=lambda b: (index.get(b.key, 999), -b.n))
    return rows


def metric_split(matches, key_of, value_of) -> tuple:
    """A continuous metric split by category.

    The standard error uses the OVERALL spread rather than each bucket's
    own, exactly as the proportion splits use the overall win rate — a thin
    bucket must not be able to manufacture a tight interval for itself.
    """
    values, by_key = [], {}
    for match in matches:
        value = value_of(match)
        key = key_of(match)
        if value is None or key is None or not math.isfinite(value):
            continue
        values.append(value)
        by_key.setdefault(key, []).append(value)
    if len(values) < 2:
        return None, 0.0, [], len(values), len(matches)

    datum = sum(values) / len(values)
    spread = math.sqrt(sum((v - datum) ** 2 for v in values)
                       / (len(values) - 1))
    # A degenerate spread is rounding dust; dividing noise by noise would
    # report a sigma for nothing at all.
    if not spread > max(abs(datum), 1) * 1e-9:
        spread = 0.0

    rows = []
    for key, group in by_key.items():
        mean = sum(group) / len(group)
        se = spread / math.sqrt(len(group)) if spread > 0 else 0.0
        rows.append(Bucket(key=key, n=len(group), mean=mean,
                           delta=mean - datum, se=se,
                           sigma=(mean - datum) / se if se > 0 else 0.0,
                           eligible=len(group) >= MIN_BUCKET))
    rows.sort(key=lambda b: -b.mean)
    return datum, spread, rows, len(values), len(matches)


def cat_findings(rows, block_id: str, no_finding=()) -> list:
    say = PHRASE.get(block_id, lambda k: k)
    hits = [r for r in rows
            if r.eligible and r.key not in no_finding
            and abs(r.sigma) >= SIGMA_CAT]
    # Radiant and Dire are ONE fact, not two: on a two-sided split the
    # unfavourable half is the mirror of the favourable one and says
    # nothing new.
    if len(rows) == 2 and len(hits) == 2:
        hits = [r for r in hits if r.sigma > 0]
    hits.sort(key=lambda r: -abs(r.sigma))
    return [Finding(r.sigma, r.key,
                    ("More likely to win " if r.sigma > 0
                     else "Less likely to win ")
                    + say(r.key) + f": {_pct(r.rate)} from {r.n} games",
                    short=f"{r.key} win rate {_pct(r.rate)}",
                    value=r.rate, n=r.n)
            for r in hits]


def metric_findings(rows, datum, more, less, short="") -> list:
    hits = [r for r in rows if r.eligible and abs(r.sigma) >= SIGMA_CAT]
    hits.sort(key=lambda r: -abs(r.sigma))
    return [Finding(r.sigma, r.key,
                    f"{more if r.sigma > 0 else less} on {r.key}: "
                    f"{sig(r.mean)} against your usual {sig(datum)}, "
                    f"from {r.n} games",
                    short=f"{r.key} {short} {sig(r.mean)}".replace("  ", " "),
                    value=r.mean, n=r.n)
            for r in hits]


@dataclass
class Spread:
    """A whole section's buckets on one scale, with its two extremes named.

    The summary prints ONE line per section now, at the user's request —
    "I don't need so many results for day of the week, or time of day;
    just put the most significant, and make sure there is 1 key result
    from each section", then "include the best and worst mentality for
    all headers in the left sidebar, even if they seem insignificant".

    Which changes what the bar has to be. Marking only the best and the
    worst against a range those same two define puts one marker hard
    against each end for ever, and a bar whose marks never move carries
    nothing. So `points` is EVERY eligible bucket, drawn as a faint tick,
    with `best` and `worst` picked out in colour and the datum where it
    falls among them. That is the distribution the bar was always meant
    to show, now for a section at a time rather than for one bucket.

    Every figure is in the block's own units, so the widget drawing it
    needs to know nothing about win rates or damage per minute.
    """

    low: float
    high: float
    datum: float
    points: list
    best: float
    worst: float

    def at(self, figure: float) -> float:
        """`figure` as a fraction from 0 (low) to 1 (high)."""
        span = self.high - self.low
        return 0.5 if span <= 0 else (figure - self.low) / span


def format_figure(block: "Block", value: float) -> str:
    """One figure, written the way its own block writes them.

    A win-rate block prints "65%" and a contribution block prints the
    mean at its own precision. The bar's end labels go through this so
    they cannot disagree with the finding's own text about what a number
    in this block looks like.
    """
    if block.kind == "cat":
        return _pct(value)
    return sig(value)


def section_spread(block: "Block", baseline: float):
    """(spread, best bucket, worst bucket) for a whole section, or None.

    **A WIN RATE IS SCALED 0 TO 100%**, at the user's request, rather than
    to its own section's range. A bar that spanned only the buckets it
    drew made every section look equally spread — Radiant 55% against
    Dire 44% filled the same track as a hero list running 25% to 61%, so
    the picture said nothing about how much was actually at stake. On a
    fixed scale the DISTANCE between the two dots is the size of the
    effect, and it means the same thing on every row and in every run.
    The cost is real and is the trade that was chosen: most win rates
    live between 30% and 70%, so the dots sit in the middle third and the
    ends are usually empty.

    **A CONTRIBUTION SECTION KEEPS ITS OWN RANGE**, also at the user's
    request — "damage per minute is an average, so it should be somewhere
    in the middle". There is no 100 to scale it against: damage runs in
    the hundreds and weighted KDA in single figures, and inventing a
    ceiling for either would be a number nobody measured with a real
    game able to run off the end of it.

    **ONLY BUCKETS WITH ENOUGH GAMES** either way — `MIN_BUCKET`, the
    same floor that decides whether a bucket may produce a finding at
    all. A two-game bucket at 100% would be the "best" of every section
    it appeared in, which is the same reason those rows are muted and
    sink to the bottom of the tables.

    **EVERY SECTION GETS ONE, significant or not**: "include the best and
    worst mentality for all headers seen in the left sidebar, even if
    they seem insignificant, like Radiant/Dire win rate or whatever". So
    nothing here consults the sigma.

    None when fewer than two eligible buckets survive. A section with one
    bucket has no best and no worst — only a figure.
    """
    figure = (lambda row: row.rate) if block.kind == "cat" else (
        lambda row: row.mean)
    datum = baseline if block.kind == "cat" else (block.datum or 0.0)
    rows = [row for row in block.rows if row.eligible]
    if len(rows) < 2:
        return None
    points = sorted(figure(row) for row in rows)
    best = max(rows, key=figure)
    worst = min(rows, key=figure)
    if block.kind == "cat":
        low, high = 0.0, 1.0
    else:
        # The scale still has to CONTAIN the datum: your usual figure can
        # sit outside the eligible buckets' range, because the thin ones
        # left out still counted towards it, and a tick painted off the
        # end of its own bar is worse than a slightly wider bar.
        low, high = min(points[0], datum), max(points[-1], datum)
        if high - low <= 0:
            return None
    spread = Spread(low=low, high=high, datum=datum, points=points,
                    best=figure(best), worst=figure(worst))
    return spread, best, worst


def field_deltas(ds) -> dict:
    """Every hero's matchup delta against the WHOLE POOL, pick-weighted.

    For hero i this is the mean of `delta_vs[i, j]` over every other hero
    j, weighted by how often j is actually picked. Positive means the
    field struggles against this hero; negative means the field beats it,
    which is what "counterable" means.

    WEIGHTED, at the user's request - "this should be driven by the
    community data of hero pick rate". A hero countered hard by three
    heroes nobody plays is not countered in practice, and an unweighted
    sum cannot tell that apart from one countered by three heroes in
    every other game.

    A MEAN, not the raw sum the request described. The ORDERING is
    identical either way, but a weighted sum's magnitude is whatever the
    weights happen to add up to, while the mean is in percentage points -
    the same unit as every other figure in the matrix, so "-1.8" can be
    read rather than merely ranked.

    The self term needs no special case: `delta_vs` is antisymmetrised at
    ingestion, so its diagonal is zero. Only the DIVISOR drops the hero's
    own weight.
    """
    import numpy as np

    if ds is None or getattr(ds, "is_empty", True):
        return {}
    weights = np.asarray(ds.picks, dtype=float)
    if weights.size != len(ds.hero_ids) or not float(weights.sum()):
        return {}
    totals = np.asarray(ds.delta_vs, dtype=float) @ weights
    divisors = weights.sum() - weights
    out = {}
    for hero_id, index in ds.index.items():
        divisor = float(divisors[index])
        if divisor > 0:
            out[int(hero_id)] = float(totals[index]) / divisor
    return out


def counter_standings(ds) -> tuple:
    """(delta per hero, "top X%" per hero, the pool's own average).

    RANKED AGAINST EVERY HERO IN THE GAME, at the user's request, not
    against the handful the player happens to pick: "Sniper is the 12th
    least counterable hero in Dota" means something on its own and stays
    comparable between runs, where a percentile inside a pool of fifteen
    is self-referential - your least counterable hero tops it by
    definition.
    """
    deltas = field_deltas(ds)
    if not deltas:
        return {}, {}, 0.0
    order = sorted(deltas, key=lambda h: -deltas[h])
    count = len(order)
    standing = {}
    for place, hero_id in enumerate(order, start=1):
        share = max(1, round(100.0 * place / count))
        standing[hero_id] = f"top {share}%"
    # The pool's own pick-weighted average, which is what a hero is read
    # against. Near zero by construction (the matrix is antisymmetric),
    # but computed rather than assumed to be.
    datum = sum(deltas.values()) / count
    return deltas, standing, datum


def ranked_dataset():
    """The hero statistics the counters block reads, or an empty one.

    LOADED HERE rather than threaded down from the window, because the
    two places that build blocks are a worker thread and a cache rebuild
    and neither has ever needed the window for anything. It is one npz
    off disk, on a path that already costs a network round trip or a full
    recompute - and `load_or_empty` answers with an empty dataset rather
    than raising when nothing has been downloaded, which is the state a
    fresh install is in.
    """
    from ..data.store import load_or_empty
    try:
        return load_or_empty()
    except Exception:                      # noqa: BLE001 - never fatal
        return None


def shielded(ds, floor_pct: int = 70) -> dict:
    """{hero id: why} for every hero the field struggles to counter.

    NOT ABOUT THE PLAYER, which is the whole difference between this mark
    and the heart. It needs no match history at all - only the ranked
    dataset - so it appears on heroes nobody has ever picked, which is
    exactly where it says something the strip could not otherwise.

    STRICTLY ABOVE THE FLOOR, the same rule the stars follow: standing AT
    the 70th percentile means 70% are at or below you, which is the top
    of the bottom 70% rather than the top 30%.
    """
    deltas, standing, _datum = counter_standings(ds)
    if not deltas:
        return {}
    order = sorted(deltas, key=lambda h: -deltas[h])
    count = len(order)
    out = {}
    for place, hero_id in enumerate(order, start=1):
        # `place` 1 is the least counterable, so the fraction AT OR BELOW
        # this hero is (count - place) / count.
        below = (count - place) / count
        if below * 100 > float(floor_pct):
            out[hero_id] = (f"Hard to counter = {sig(deltas[hero_id])} "
                            f"vs the field ({standing[hero_id]})")
    return out


def counter_analysis(matches, ds) -> Block:
    """Your most played heroes, ranked by how counterable they are.

    THE ONLY SECTION HERE THAT IS NOT MEASURED FROM YOUR GAMES. Your
    history decides WHICH heroes appear and how many games sit behind
    each; the figure itself comes out of the ranked dataset and is the
    same for everybody who plays that hero. So there is no win rate
    column, no baseline and no sigma - a hero cannot be significantly
    counterable for you in particular.
    """
    name, desc = NAMES["counters"], DESCS["counters"]
    deltas, standing, datum = counter_standings(ds)
    if not deltas:
        # No statistics pulled, or a dataset with no matchups in it. Say
        # so rather than draw an empty table, which reads as "you have no
        # counterable heroes" - a measurement nobody made.
        return Block(id="counters", name=name, desc=desc, kind="counters",
                     rows=[], shown=[], caveat=NO_DATASET)

    played: dict = {}
    for match in matches:
        if match.hero_id is None:
            continue
        bucket = played.setdefault(
            match.hero_id, Bucket(key=match.hero))
        bucket.n += 1
        bucket.wins += 1 if match.win else 0

    # THE BAR PLOTS THE RANKING, not the raw figure, at the user's
    # request: "if Sniper is in the top 9% in terms of being hard to
    # counter then his score is 91%, a lot of green".
    #
    # It is the better measure and it fixes the column at the root.
    # Counterability is clustered - a pick-weighted average over ~126
    # heroes sits within about half a percentage point either side of
    # neutral - so a bar scaled to those raw figures is a few pixels for
    # everybody and says nothing. Percentiles are UNIFORM by
    # construction, so the column always uses its full width however
    # tightly the underlying numbers bunch up.
    order = sorted(deltas, key=lambda h: -deltas[h])
    count = len(order)
    # Place 1 is the hardest to counter, so the share AT OR BELOW it is
    # (count - place) / count - which is the "91%" in the request.
    percentile = {hero_id: 100.0 * (count - place) / count
                  for place, hero_id in enumerate(order, start=1)}

    rows = []
    for hero_id, bucket in played.items():
        if hero_id not in deltas:
            continue                      # a hero the dataset does not know
        bucket.mean = deltas[hero_id]
        # Centred on the MEDIAN hero, so the delegate's datum line is the
        # middle of the field and green means "harder to counter than
        # most" rather than "above an average nobody can picture".
        bucket.delta = percentile[hero_id] - 50.0
        bucket.note = standing[hero_id]
        bucket.eligible = bucket.n >= MIN_BUCKET
        rows.append(bucket)
    # Least counterable first, which is the table's resting order; the
    # cut and the sort above it still do what they do everywhere else.
    rows.sort(key=lambda r: -r.mean)
    shown = [r for r in rows if r.n >= MIN_DISPLAY]
    # THE BAR REACHES AS FAR AS THE WHOLE POOL DOES, at the user's
    # request: "the min / max is the most and least counterable hero's
    # score... it's likely that there is an easily or difficultly
    # counterable hero that I just don't happen to pick". Every hero in
    # the game is ranked, so the pool's own extremes ARE 100 and 0 and
    # the reach is half of that, the delegate drawing outward from the
    # median line.
    #
    # FIXED rather than measured, which is what makes two runs
    # comparable: the percentile range is 0 to 100 whatever the figures
    # do, so a bar means the same thing in every run and under every cut.
    # Scaling to the rows on screen would instead make a pool of three
    # heroes look as spread as the entire game, and would move the scale
    # every time the count box was stepped.
    reach = 50.0
    return Block(id="counters", name=name, desc=desc, kind="counters",
                 rows=rows, shown=shown, hidden=len(rows) - len(shown),
                 hidden_games=sum(r.n for r in rows if r.n < MIN_DISPLAY),
                 datum=datum, unit="percentage points",
                 covered=len(rows), total=len(played), scale=reach,
                 caveat=COUNTER_CAVEAT)


def item_analysis(matches, item_names: dict) -> Block:
    """Final inventory against THAT HERO'S own win rate.

    The hero is the datum, not the player: comparing a Pudge item against
    an overall rate dominated by other heroes would measure the hero and
    not the item. Read the whole block with more suspicion than the rest —
    items are the final inventory, and an expensive one is partly a
    consequence of the game going well rather than a cause of it.
    """
    by_hero = {}
    for match in matches:
        by_hero.setdefault(match.hero, []).append(match)
    # Most played first, which is the order the dropdown offers.
    top = sorted(by_hero, key=lambda h: (-len(by_hero[h]), h))

    groups, findings = [], []
    for hero in top:
        games = by_hero[hero]
        measured = [m for m in games if m.items]
        baseline = (sum(1 for m in measured if m.win) / len(measured)
                    if measured else None)
        tally = {}
        for match in measured:
            for item in match.items:
                bucket = tally.setdefault(item, Bucket(key=str(item)))
                bucket.n += 1
                bucket.wins += 1 if match.win else 0
        rows = []
        for item, bucket in tally.items():
            bucket.key = item_names.get(item) or f"Item {item}"
            bucket.rate = bucket.wins / bucket.n
            if baseline is not None:
                bucket.delta = bucket.rate - baseline
                bucket.se = math.sqrt(baseline * (1 - baseline) / bucket.n)
                bucket.sigma = (bucket.delta / bucket.se
                                if bucket.se > 0 else 0.0)
            bucket.eligible = bucket.n >= MIN_BUCKET
            rows.append(bucket)
        rows.sort(key=lambda b: (-b.n, b.key))
        shown = [r for r in rows if r.n >= MIN_DISPLAY]
        hits = ([r for r in rows
                 if r.eligible and abs(r.sigma) >= SIGMA_CAT]
                if baseline is not None else [])
        hits.sort(key=lambda r: -abs(r.sigma))
        for row in hits:
            findings.append(Finding(
                row.sigma, row.key,
                ("Better" if row.sigma > 0 else "Worse")
                + f" with {row.key} on {hero}: {_pct(row.rate)} against "
                f"{_pct(baseline)} on that hero, from {row.n} games",
                short=f"{row.key} on {hero} win rate {_pct(row.rate)}",
                value=row.rate, n=row.n))
        groups.append(ItemGroup(hero=hero, games=len(games),
                                measured=len(measured), baseline=baseline,
                                rows=rows, shown=shown,
                                hidden=len(rows) - len(shown)))

    findings.sort(key=lambda f: -abs(f.sigma))
    covered = sum(1 for m in matches if m.items)
    return Block(id="items", name=NAMES["items"], desc=DESCS["items"],
                 kind="items", groups=groups, covered=covered,
                 total=len(matches), findings=findings)


def _length_band(match) -> str:
    minutes = match.minutes
    if minutes < 25:
        return LEN_ORDER[0]
    if minutes < 35:
        return LEN_ORDER[1]
    if minutes < 45:
        return LEN_ORDER[2]
    return LEN_ORDER[3]


def _party(match) -> str:
    size = match.party_size
    if size is None or size < 1:
        return "Unknown"
    if size == 1:
        return "Solo"
    return "Party of 5" if size >= 5 else f"Party of {size}"


SPLITS = {
    "hero": (lambda m: m.hero, "count", ()),
    "length": (_length_band, LEN_ORDER, ()),
    "tod": (lambda m: TOD_ORDER[m.when.hour // 3], TOD_ORDER, ()),
    "dow": (lambda m: WEEKDAY[m.when.weekday()], WEEKDAY, ()),
    "session": (lambda m: POS_ORDER[min(m.position, 6) - 1], POS_ORDER, ()),
    "tilt": (lambda m: m.previous, TILT_ORDER, ("First of session",)),
    "side": (lambda m: "Radiant" if m.radiant else "Dire",
             ["Radiant", "Dire"], ()),
    "party": (_party, PARTY_ORDER, ("Unknown",)),
}

METRICS = {
    "herodmg": dict(
        field="damage_per_min", unit="hero damage per minute",
        # SHORT enough for a summary line, where the block's own name is
        # already printed in the column to the left of it.
        short="damage/min",
        more="More damage", less="Less damage",
        caveat="This ranks heroes, not your play. Damage per minute is set "
               "mostly by what a hero does: a mid laner out-damages a hard "
               "support by construction, and a pusher trades hero damage for "
               "buildings. It is worth reading when a hero sits far from "
               "where its role would put it."),
    "herokda": dict(
        field="kda", unit="weighted KDA", short="KDA",
        more="Better trades", less="Worse trades",
        caveat="Deaths are floored at one, so a deathless game reads as its "
               "own kill contribution rather than infinity, which flatters "
               "low-death games slightly. And this is the mean of each "
               "game's ratio, not the ratio of your totals."),
    "towerdmg": dict(
        field="tower_per_min", unit="building damage per minute",
        short="siege dmg/min",
        more="More pushing", less="Less pushing",
        caveat="This ranks heroes at least as much as your play, the way "
               "hero damage does: a pusher and a support are not doing the "
               "same job. It also rises with a game going WELL — you cannot "
               "hit a building you never reach — so read a high figure as "
               "partly a consequence rather than only a cause."),
    # GOLD AND XP ARE ALREADY RATES. OpenDota reports `gold_per_min` and
    # `xp_per_min` per minute itself, so these two name the row's own
    # field; CS and denies name a property that does the division. Do not
    # "fix" the inconsistency by dividing gold again.
    "gold": dict(
        field="gold_per_min", unit="gold per minute",
        short="gold/min",
        more="More gold", less="Less gold",
        caveat="This ranks ROLES before it ranks your play. A safe lane "
               "carry out-earns a hard support by construction, on the "
               "same night and the same skill. It also rises with a game "
               "going well, so a high figure is partly a consequence. Read "
               "it where a hero sits far from where its role would put it."),
    "xp": dict(
        field="xp_per_min", unit="experience per minute",
        short="XP/min",
        more="More XP", less="Less XP",
        caveat="Role-bound the same way gold is, and with one of its own: "
               "experience is SHARED, so a solo lane gains faster than two "
               "players in the same lane whatever either of them does."),
    "cs": dict(
        field="cs_per_min", unit="last hits per minute",
        short="CS/min",
        more="More farm", less="Less farm",
        caveat="The most role-bound figure on this card. A support is not "
               "trying to last hit and will sit at the bottom of every "
               "run; the question this answers is how you farm on ONE "
               "hero against how you usually farm on it, never how one "
               "hero compares with another."),
    # PER GAME, AND IT IS THE ONLY ONE HERE THAT IS NOT A RATE. Denying
    # happens almost entirely in the laning stage, so a 25 minute game and
    # a 50 minute game hold about the same number — per minute would make
    # a long game read as worse denying with nothing about the laning
    # changed. It also prints whole numbers, which per minute could not:
    # denies run at tenths of one a minute, so rounding those to integers
    # gives 0 for every hero and a section that says nothing at all.
    "denies": dict(
        field="denies", unit="denies per game",
        short="denies/game",
        more="More denies", less="Fewer denies",
        caveat="Role-bound like the rest, and thin: the counts are small, "
               "so a couple of games move a hero a long way. It is per "
               "GAME rather than per minute because denying is a laning "
               "stage act — a long game does not dilute it, so dividing "
               "by the length would measure the length."),
}


# THE ORDER A REPORT IS READ IN, AND THERE IS ONLY ONE OF IT.
# `build_blocks` walks this and so does the History tab's sidebar, which
# lists these same sections down the left of the page they are on. It
# used to be a tuple inlined in the loop below plus the order of `METRICS`
# plus wherever `items` happened to be appended — three places, agreeing by
# luck, and they did NOT agree with `ANALYSES` (which has items last, where
# the page puts it before the two metric blocks). A bookmark list in a
# different order from the page it maps to is a bookmark list that lies, so
# the order is stated once and read from here.
# `ANALYSES` still decides what each is CALLED and whether it starts
# ticked; this decides only where it sits. A test holds the two to the
# same set of keys.
# ORDERED BY WHAT YOU CAN ACT ON, at the user's request — "if you think
# certain sections are more insightful than others, re-order to show the
# most essential at the top", with two worked examples: "Radiant and Dire
# is silly because it's random, I can't choose the side, so it should be
# somewhere at the bottom", and "hero win rate means a lot because I can
# choose the heroes that I do better at more often and that will improve
# my overall win rate".
#
# So the rule is whether a section names a DECISION or an OUTCOME. Which
# hero and what to build on it are the two biggest levers anybody has, so
# they lead. When to queue, when to stop, whether to re-queue after a
# loss, which day, who with — all things you choose, in roughly the order
# they change a session. Then the two that are not choices at all: match
# length is a CONSEQUENCE of how a game went rather than something you
# set, and the side is assigned by the matchmaker, so a deviation there
# is a coincidence you cannot use. The two contribution rankings sit last
# because they are the most caveated in the whole tab: damage per minute
# is set mostly by what a hero DOES, so they rank heroes as much as they
# rank your play.
#
# This is the one list, so the sidebar, the summary's rows and the cards
# down the page all take this order together — "they should all agree".
# The FARM FOUR are appended to the contribution family rather than
# threaded through it: they are outcomes, not decisions, so they belong
# where the caveated rankings already sit, and the three that were here
# first keep the positions they were given.
BLOCK_ORDER = ("hero", "counters", "items", "tod", "session", "tilt", "dow", "party",
               "length", "side", "herodmg", "herokda", "towerdmg",
               "gold", "xp", "cs", "denies")


def build_blocks(matches, baseline: float, picked: dict,
                 item_names: dict | None = None, ds=None) -> list:
    """Every analysis the user asked for, in the order they are read in."""
    blocks = []

    def add_cat(block_id):
        key_of, order, no_finding = SPLITS[block_id]
        rows = categorical(matches, baseline, key_of, order)
        shown = [r for r in rows if r.n >= MIN_DISPLAY]
        blocks.append(Block(
            id=block_id, name=NAMES[block_id], desc=DESCS[block_id],
            kind="cat", rows=rows, shown=shown,
            hidden=len(rows) - len(shown),
            hidden_games=sum(r.n for r in rows if r.n < MIN_DISPLAY),
            no_finding=list(no_finding),
            findings=cat_findings(rows, block_id, no_finding)))

    def add_metric(block_id):
        spec = METRICS[block_id]
        datum, _spread, rows, covered, total = metric_split(
            matches, lambda m: m.hero,
            lambda m, f=spec["field"]: getattr(m, f))
        shown = [r for r in rows if r.n >= MIN_DISPLAY]
        blocks.append(Block(
            id=block_id, name=NAMES[block_id], desc=DESCS[block_id],
            kind="metric", rows=rows, shown=shown,
            hidden=len(rows) - len(shown),
            hidden_games=sum(r.n for r in rows if r.n < MIN_DISPLAY),
            datum=datum, unit=spec["unit"],
            caveat=spec["caveat"], covered=covered, total=total,
            findings=([] if datum is None else metric_findings(
                rows, datum, spec["more"], spec["less"], spec["short"]))))

    for block_id in BLOCK_ORDER:
        if not picked.get(block_id):
            continue
        if block_id == "items":
            blocks.append(item_analysis(matches, item_names or {}))
        elif block_id == "counters":
            # `ds` is the ranked dataset, which this tab has never needed
            # before. None is a perfectly good answer - a machine with no
            # statistics pulled gets the block saying so.
            blocks.append(counter_analysis(matches, ds))
        elif block_id in METRICS:
            add_metric(block_id)
        else:
            add_cat(block_id)

    return blocks
