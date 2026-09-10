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

ELEVEN ANALYSES RUN AT ONCE, so some buckets clear the bar by chance
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


@dataclass
class Finding:
    sigma: float
    key: str
    text: str


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
    dp: int = 0
    caveat: str = ""
    covered: int = 0
    total: int = 0
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


ANALYSES = [
    ("hero", "Hero win rates", True,
     "Win rate by hero played. Heroes under {min} games are muted and "
     "excluded from findings."),
    ("length", "Match length", True,
     "Duration bands. Reads as a proxy for whether you close games out or "
     "get dragged long."),
    ("tod", "Time of day", True,
     "Three hour bands on this machine's local clock, from each match's "
     "start time."),
    ("dow", "Day of week", True, "Local calendar day of the match start."),
    ("session", "Position within session", True,
     "A gap of more than three hours between the end of one match and the "
     "start of the next opens a new session."),
    ("tilt", "Previous game result", True,
     "The tilt check. The previous result only counts inside the same "
     "session, so a loss you slept on is not charged against the next "
     "morning."),
    ("side", "Radiant against Dire", True,
     "Side is assigned by the matchmaker, so a real deviation here is "
     "either map preference or a very lucky sample."),
    ("party", "Solo against stack", True,
     "Party size as reported. OpenDota leaves this null on many matches, so "
     "those sit in an explicit unknown bucket and never produce a finding."),
    ("herodmg", "Hero damage per minute by hero", True,
     "Mean hero damage per minute on each hero, against your own overall "
     "rate."),
    ("herokda", "Weighted KDA by hero", True,
     "Kills plus three tenths of assists over deaths, averaged across your "
     "games on each hero."),
    ("items", "Items and win rate by hero", True,
     "One hero at a time, chosen on the card: the win rate in games that "
     "ended with each item in your inventory, against that hero's own "
     "win rate."),
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
                    + say(r.key) + f": {_pct(r.rate)} from {r.n} games")
            for r in hits]


def metric_findings(rows, datum, more, less, dp) -> list:
    hits = [r for r in rows if r.eligible and abs(r.sigma) >= SIGMA_CAT]
    hits.sort(key=lambda r: -abs(r.sigma))
    return [Finding(r.sigma, r.key,
                    f"{more if r.sigma > 0 else less} on {r.key}: "
                    f"{r.mean:.{dp}f} against your usual {datum:.{dp}f}, "
                    f"from {r.n} games")
            for r in hits]


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
                f"{_pct(baseline)} on that hero, from {row.n} games"))
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
        field="damage_per_min", unit="hero damage per minute", dp=0,
        more="More damage", less="Less damage",
        caveat="This ranks heroes, not your play. Damage per minute is set "
               "mostly by what a hero does: a mid laner out-damages a hard "
               "support by construction, and a pusher trades hero damage for "
               "buildings. It is worth reading when a hero sits far from "
               "where its role would put it."),
    "herokda": dict(
        field="kda", unit="weighted KDA", dp=2,
        more="Better trades", less="Worse trades",
        caveat="Deaths are floored at one, so a deathless game reads as its "
               "own kill contribution rather than infinity, which flatters "
               "low-death games slightly. And this is the mean of each "
               "game's ratio, not the ratio of your totals."),
}


# THE ORDER A REPORT IS READ IN, AND THERE IS ONLY ONE OF IT.
# `build_blocks` walks this and so does the Analysis tab's sidebar, which
# lists the same eleven sections down the left of the page they are on. It
# used to be a tuple inlined in the loop below plus the order of `METRICS`
# plus wherever `items` happened to be appended — three places, agreeing by
# luck, and they did NOT agree with `ANALYSES` (which has items last, where
# the page puts it before the two metric blocks). A bookmark list in a
# different order from the page it maps to is a bookmark list that lies, so
# the order is stated once and read from here.
# `ANALYSES` still decides what each is CALLED and whether it starts
# ticked; this decides only where it sits. A test holds the two to the
# same set of keys.
BLOCK_ORDER = ("hero", "length", "tod", "dow", "session", "tilt", "side",
               "party", "items", "herodmg", "herokda")


def build_blocks(matches, baseline: float, picked: dict,
                 item_names: dict | None = None) -> list:
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
            datum=datum, unit=spec["unit"], dp=spec["dp"],
            caveat=spec["caveat"], covered=covered, total=total,
            findings=([] if datum is None else metric_findings(
                rows, datum, spec["more"], spec["less"], spec["dp"]))))

    for block_id in BLOCK_ORDER:
        if not picked.get(block_id):
            continue
        if block_id == "items":
            blocks.append(item_analysis(matches, item_names or {}))
        elif block_id in METRICS:
            add_metric(block_id)
        else:
            add_cat(block_id)

    return blocks
