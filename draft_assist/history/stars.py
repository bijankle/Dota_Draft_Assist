"""Which heroes the last History run says you are good on.

The Draft tab's suggestion strip ranks candidates by DRAFT FIT — what the
ten heroes on the board do to this hero — and that number knows nothing
about you. The History tab knows a great deal about you and nothing about
the board. A star is the one place the two meet: it says "this is also a
hero you play a lot and win on", drawn on the same tile the fit is on.

**TWO PERCENTILE FLOORS, BOTH SET BY THE USER**, and the shape of the
rule is theirs: "rank all the hero picks for that period — only the heroes
that rank in the top 30% pick rate would be a candidate for the star, same
goes for win rate, and if both are satisfied they get a star". So a
setting of 70 means the 70th percentile, which is the top 30%.

PERCENTILES RATHER THAN ABSOLUTE COUNTS because the answer has to survive
the window changing: the same "8 games" floor means something quite
different over six months than over two years, and this tab's window is a
dropdown. A percentile is read against whatever was actually measured.

**RANKED BY HERO ID, NEVER BY NAME.** The hero block's buckets are keyed
by the DISPLAY NAME OpenDota gave the match, and the Draft tab knows its
candidates by the numeric id from its own dataset. Matching those two
strings would be one rename away from a strip with no stars on it and
nothing anywhere saying why — so this walks the raw matches, which carry
`hero_id`, and hands back ids.
"""

from __future__ import annotations

from dataclasses import dataclass, field

# A hero needs at least this many games to be starrable at all. The pick
# percentile very nearly does this by itself — a one-game hero sinks to
# the bottom of that ranking — but "nearly" fails in the degenerate case
# the floors in `analyse` exist for: measure three games across three
# heroes and the top third by win rate is a hero you played ONCE, at
# 100%. Same number as `analyse.MIN_DISPLAY`, and the same reason: a rate
# beside an n of one is noise wearing a number.
MIN_GAMES = 2


@dataclass(frozen=True)
class HeroForm:
    """One hero's standing in the run, as the star rule reads it."""
    hero_id: int
    games: int
    wins: int
    rate: float
    # WHERE IT STANDS, and the two are not the same number. `_pct` is
    # "the fraction of heroes at or below this one", which is what the
    # star rule compares against a floor — the top hero scores 1.0.
    # `_top` is "you are in the top this much of them", which is what a
    # person reads — the top hero of ten is in the top 10%.
    pick_pct: float = 0.0
    win_pct: float = 0.0
    pick_top: float = 1.0
    win_top: float = 1.0


@dataclass(frozen=True)
class Stars:
    """The starred ids, and enough to say why on a tooltip."""
    heroes: frozenset = field(default_factory=frozenset)
    form: dict = field(default_factory=dict)     # hero id -> HeroForm
    pick_floor: int = 0
    win_floor: int = 0

    def __contains__(self, hero_id) -> bool:
        return hero_id in self.heroes

    def why(self, hero_id) -> str:
        """The two lines the tile puts in its tooltip. Empty when
        unstarred — a tooltip explaining why something is NOT marked is
        noise.

        TWO LABELLED LINES rather than one sentence, at the user's
        request. Every line of that tooltip now names what it is and
        then gives the figure, so its four numbers are read down a
        column instead of being picked out of prose.

        EACH FIGURE CARRIES ITS OWN STANDING, at the user's request:
        "after 17 games say (top XXX%), and after the win rate say (top
        XXX%)". It used to name the two FLOORS instead and say the hero
        was inside them, which the STAR already says — "having the star
        is evidence of this already" — so the sentence was spending its
        words repeating the mark it was attached to. What it could not
        say before is the one thing a number in brackets is for: how far
        inside.
        """
        row = self.form.get(hero_id)
        if row is None or hero_id not in self.heroes:
            return ""
        # THE PERCENTILE, NOT "TOP X%", at the user's request: every bar
        # and every standing in this app now reads the same way round,
        # with a HIGH number meaning a strong hero. `pick_top` and
        # `win_top` are the old complement and are still carried for the
        # workbook; what a person reads here is the percentile itself.
        return "\n".join((
            f"My Pick Rate = {row.games} games "
            f"({round(row.pick_pct * 100)}th percentile)",
            f"My Win Rate = {row.rate * 100:.0f}% "
            f"({round(row.win_pct * 100)}th percentile)"))


def rank_fraction(values: dict) -> dict:
    """hero id -> where it stands, 1.0 at the top and 1/N at the bottom.

    TIES SHARE THE GENEROUS ANSWER. Two heroes on the same number of
    games are the same hero as far as this rule is concerned, so both
    take the rank of the better placed of them — splitting them by
    whatever `sorted` happened to do would star one and not the other on
    identical evidence.
    """
    if not values:
        return {}
    total = len(values)
    ordered = sorted(values.values())
    out = {}
    for hero_id, value in values.items():
        # How many are at or below this one — so the largest scores 1.0.
        at_or_below = sum(1 for other in ordered if other <= value)
        out[hero_id] = at_or_below / total
    return out


def measure(matches, pick_floor: int = 0, win_floor: int = 0) -> Stars:
    """Rank a run's heroes and star the ones clearing both floors.

    `pick_floor` and `win_floor` are PERCENTILES as whole numbers, so 70
    means "must stand at or above the 70th percentile", which is the top
    30%. Nought lets everything through on that axis, which is the honest
    reading of "no bar" rather than a special case.
    """
    played: dict = {}
    for match in matches or ():
        hero_id = getattr(match, "hero_id", None)
        if hero_id is None:
            continue
        games, wins = played.get(int(hero_id), (0, 0))
        played[int(hero_id)] = (games + 1, wins + (1 if match.win else 0))
    if not played:
        return Stars(pick_floor=pick_floor, win_floor=win_floor)

    # RANKED AGAINST EVERY HERO PLAYED, including the one-game ones: they
    # are part of "all the hero picks for that period", and leaving them
    # out would quietly raise everybody else's standing.
    picks = rank_fraction({h: n for h, (n, _w) in played.items()})
    rates = rank_fraction({h: (w / n if n else 0.0)
                           for h, (n, w) in played.items()})

    form, starred = {}, set()
    # "IN THE TOP X%" IS NOT ONE MINUS THE PERCENTILE. A hero at the top
    # of ten has every hero at or below it, so its percentile is 1.0 and
    # the naive complement reads "top 0%" — a claim about nobody. It is
    # in the top ONE of ten, so the share is 1/N; the hero ranked third
    # is in the top 3/10. Adding that one step back is the whole
    # correction, and ties keep the generous answer they already share.
    step = 1.0 / len(played)
    for hero_id, (games, wins) in played.items():
        row = HeroForm(hero_id=hero_id, games=games, wins=wins,
                       rate=(wins / games if games else 0.0),
                       pick_pct=picks[hero_id], win_pct=rates[hero_id],
                       pick_top=min(1.0, 1.0 - picks[hero_id] + step),
                       win_top=min(1.0, 1.0 - rates[hero_id] + step))
        form[hero_id] = row
        # STRICTLY ABOVE THE FLOOR. Standing AT the 70th percentile means
        # 70% of the heroes are at or below you — which puts you at the
        # top of the bottom 70%, not in the top 30%. With ten heroes the
        # fourth best sits exactly on 0.70, and `>=` starred it, so "top
        # 30%" quietly meant four heroes out of ten. Ties still move
        # together: they share one percentile, so a tied group is in or
        # out as a group.
        if (games >= MIN_GAMES
                and row.pick_pct > pick_floor / 100.0
                and row.win_pct > win_floor / 100.0):
            starred.add(hero_id)
    return Stars(heroes=frozenset(starred), form=form,
                 pick_floor=pick_floor, win_floor=win_floor)
