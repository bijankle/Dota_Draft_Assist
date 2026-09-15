"""One run of the analyser: what was asked for, what came back, what it says.

The container both the tab and the workbook read, so the screen and the
spreadsheet cannot disagree about a number — which they would within a
week if each computed its own.
"""

from dataclasses import dataclass, field
from datetime import datetime

from . import analyse

# What the window control offers. `days` is what OpenDota's `date`
# parameter takes; None asks for everything it will give.
WINDOWS = [("1m", "Last 1 month", 30), ("3m", "Last 3 months", 91),
           ("6m", "Last 6 months", 182), ("12m", "Last 12 months", 365),
           ("all", "All history", None)]
CAPS = [100, 250, 500, 1000, 1500, 2000, 3000, 5000]


@dataclass
class Options:
    account_id: int = 0
    window: str = "12m"
    cap: int = 1000
    no_turbo: bool = True
    # TICKED BY DEFAULT, at the user's request: the question the tab asks
    # is what goes with winning RANKED games, and turbo and unranked
    # answer a different one.
    ranked_only: bool = True
    picked: dict = field(default_factory=dict)

    @property
    def days(self):
        for key, _label, days in WINDOWS:
            if key == self.window:
                return days
        return None

    @property
    def window_label(self) -> str:
        for key, label, _days in WINDOWS:
            if key == self.window:
                return label
        return self.window

    @property
    def window_short(self) -> str:
        """"6 months", not "Last 6 months".

        The title bar's profile button reads "Bijson (6 months)", at the
        user's request, and the word "Last" is four characters of a label
        that only has to work inside brackets after a name. "All history"
        has no prefix to drop and keeps its own words.
        """
        label = self.window_label
        return label[5:] if label.startswith("Last ") else label

    def as_dict(self) -> dict:
        return {"window": self.window, "cap": self.cap,
                "no_turbo": self.no_turbo, "ranked_only": self.ranked_only,
                "picked": dict(self.picked)}

    @classmethod
    def from_dict(cls, raw: dict, account_id: int = 0) -> "Options":
        raw = raw if isinstance(raw, dict) else {}
        from .analyse import DEFAULT_ON
        picked = dict(DEFAULT_ON)
        picked.update({k: bool(v) for k, v in
                       (raw.get("picked") or {}).items() if k in DEFAULT_ON})
        return cls(account_id=account_id,
                   window=raw.get("window", "12m"),
                   cap=int(raw.get("cap", 1000)),
                   no_turbo=bool(raw.get("no_turbo", True)),
                   ranked_only=bool(raw.get("ranked_only", True)),
                   picked=picked)


@dataclass
class Before:
    """How the equal-length stretch IMMEDIATELY BEFORE this window went.

    Two numbers and nothing else, because that is all anything asks of
    it: the profile callout prints this window's win rate and games with
    a delta after each, at the user's request — "if 1 year is selected it
    sohudl be XXX % (+ YYY%) where XXX is the winr rate for the last year
    and YYY is the win rate % increase or decrease since the year before
    that... and below those two i want games played (with a delta also,
    qty)".

    IT IS NOT AN ANALYSIS AND MUST NOT BECOME ONE. Everything in this
    module is measured against the matches in `Report.matches`, which are
    the window's own; these two figures come from a stretch that is
    deliberately NOT in that list, so letting a block reach them would
    mean a finding computed over a sample the rest of the tab cannot see.

    ABSENT IS A REAL ANSWER, which is why `Report.before` is None rather
    than a zeroed one of these. "All history" has nothing before it, the
    fetch can fail, and it can come back clipped by the cap — in all
    three cases the honest thing to draw is no delta at all, and a zero
    would read as "exactly the same as last time".
    """

    matches: int = 0
    wins: int = 0

    @property
    def rate(self) -> float | None:
        """None with no games in it: a rate over nothing is not 0%."""
        return self.wins / self.matches if self.matches else None

    def as_dict(self) -> dict:
        return {"matches": int(self.matches), "wins": int(self.wins)}

    @classmethod
    def from_dict(cls, raw) -> "Before | None":
        if not isinstance(raw, dict):
            return None
        try:
            return cls(matches=int(raw.get("matches") or 0),
                       wins=int(raw.get("wins") or 0))
        except (TypeError, ValueError):
            return None


@dataclass
class Report:
    options: Options
    how: str
    name: str
    matches: list
    blocks: list
    dropped: dict
    sessions: int
    returned: int
    ran_at: datetime = field(default_factory=datetime.now)
    # See `Before`. None means "not measured", never "no change".
    before: "Before | None" = None

    @property
    def n(self) -> int:
        return len(self.matches)

    @property
    def win_rate(self) -> float | None:
        """This window's own win rate, or None with nothing in it.

        `baseline` is the same number as a float that answers 0.0 for an
        empty run, because every analysis divides by it and a None there
        would be an exception per block. This one is for DISPLAY, where
        "0%" and "we did not measure" must not look the same.
        """
        return self.wins / self.n if self.n else None

    @property
    def win_rate_delta(self) -> float | None:
        """Points, not a ratio: 53% against 51% is +2, never +0.039."""
        was = self.before.rate if self.before else None
        now = self.win_rate
        if was is None or now is None:
            return None
        return (now - was) * 100

    @property
    def games_delta(self) -> int | None:
        if self.before is None:
            return None
        return self.n - self.before.matches

    @property
    def wins(self) -> int:
        return sum(1 for m in self.matches if m.win)

    @property
    def baseline(self) -> float:
        return self.wins / self.n if self.n else 0.0

    @property
    def period(self) -> tuple:
        if not self.matches:
            return ("", "")
        return (self.matches[0].when.strftime("%Y-%m-%d"),
                self.matches[-1].when.strftime("%Y-%m-%d"))

    @property
    def findings(self) -> list:
        """Every finding, biggest deviation first.

        The two FAMILIES are headlined apart where this is drawn, because
        contribution metrics separate far harder than win-rate splits —
        they are partly structural, a mid laner out-damages a hard support
        by construction — so one merged ranking by sigma would be nothing
        but damage rows with every behavioural finding buried under them.
        """
        out = []
        for block in self.blocks:
            for finding in block.findings:
                out.append((block, finding))
        out.sort(key=lambda pair: -abs(pair[1].sigma))
        return out

    # How many contribution rankings the summary shows PER METRIC, at
    # the user's request: "I only want the top 3 hero damage and top 3
    # weighted KDA". It was three at each END of the two metrics POOLED,
    # which is a different cut and a worse one to read — damage and KDA
    # separate by different amounts, so the pooled ends were usually all
    # damage rows with the KDA ranking crowded out of its own summary.
    # Per metric, both get their three whatever the other is doing.
    SUMMARY_PER_METRIC = 3

    def split_findings(self) -> tuple:
        """(win rate splits, contribution rankings) — see `findings`.

        **ITEMS ARE NOT IN THE SUMMARY**, at the user's request. Every
        block still appears in full further down the tab; what comes out
        here is the headline, and item findings crowded it — there are
        three heroes' worth of them, they separate easily because an
        expensive item is partly a CONSEQUENCE of the game going well, and
        the tab already says to read that block with more suspicion than
        the rest. A summary is the handful of things worth a second look,
        not everything that cleared a floor.
        """
        rates = [pair for pair in self.findings
                 if pair[0].kind not in ("metric", "items")]
        contributions = [pair for pair in self.findings
                         if pair[0].kind == "metric"]
        return rates, self._per_metric(contributions)

    def summary_rows(self) -> tuple:
        """(win-rate sections, contribution sections) — ONE row each.

        At the user's request the summary is no longer a ranked list of
        whatever cleared the significance floor: "I don't need so many
        results for day of the week, or time of day — just put the most
        significant, and make sure there is 1 key result from each
        section", and then "include the best and worst mentality for all
        headers seen in the left sidebar, even if they seem
        insignificant". Four Hero win rate lines pushing Party size off
        the card entirely was the complaint, and "where is hero win
        rate??" was the other half of it — a section with a real story
        could be absent because a different section had four louder ones.

        So the shape is fixed: every section that has buckets to compare
        gets exactly one line, IN SECTION ORDER, carrying that section's
        best and worst. The card reads the same on every run, which is
        what makes two runs comparable, and no section can crowd out
        another.

        **IN `BLOCK_ORDER`, not by sigma**, also at the user's request.
        A ranked list needs a top row that means something; a fixed list
        of ten sections is read by finding the section you want, and
        that is the order the sidebar and the page below already use.

        **ITEMS ARE STILL OUT, and this one is statistics rather than
        taste.** Every item bucket is measured against THAT HERO'S own
        win rate, so the best item on Pudge and the worst on Lion are
        figures against two different datums — putting them on one scale
        would draw a comparison that is not there. The block keeps its
        card further down, where each hero is read against its own rate.
        """
        rates, contributions = [], []
        by_id = {block.id: block for block in self.blocks}
        for block_id in analyse.BLOCK_ORDER:
            block = by_id.get(block_id)
            if block is None or block.kind == "items":
                continue
            found = analyse.section_spread(block, self.baseline)
            if found is None:
                continue
            spread, best, worst = found
            row = (block, spread, best, worst)
            (contributions if block.kind == "metric" else rates).append(row)
        return rates, contributions

    @classmethod
    def _per_metric(cls, pairs: list) -> list:
        """The strongest few of EACH metric, in one list, order kept.

        `findings` is already sorted by |sigma|, so taking the head of
        each block's share is taking the strongest — the sigma drives the
        pick, which is what it is for. It is never SHOWN: a number of
        standard errors means nothing to somebody reading how they play,
        and the tab says the same thing in words and in colour.

        Biggest deviation either way rather than the good end alone,
        which is the rule this block has always followed: where you are
        worst on a hero is as much the point as where you are best, and a
        list cut to its top only ever flatters.
        """
        taken: dict = {}
        keep = []
        for pair in pairs:
            block = pair[0]
            count = taken.get(block.id, 0)
            if count < cls.SUMMARY_PER_METRIC:
                taken[block.id] = count + 1
                keep.append(pair)
        return keep
