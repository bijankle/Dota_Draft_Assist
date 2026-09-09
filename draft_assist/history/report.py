"""One run of the analyser: what was asked for, what came back, what it says.

The container both the tab and the workbook read, so the screen and the
spreadsheet cannot disagree about a number — which they would within a
week if each computed its own.
"""

from dataclasses import dataclass, field
from datetime import datetime

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

    @property
    def n(self) -> int:
        return len(self.matches)

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
