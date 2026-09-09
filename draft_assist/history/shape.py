"""One API row per match, turned into something the analyses can bucket.

EVERY FIELD IS READ DEFENSIVELY. OpenDota populates the parsed fields —
`lane_role` above all — on a minority of matches, and frequently returns a
null `party_size`. Nothing is inferred to fill a gap: an unknown goes into
its own bucket and never produces a finding, because a guess dressed as a
measurement is the one thing an instrument must not do.
"""

from dataclasses import dataclass, field
from datetime import datetime

# Five minutes. Shorter than that is an abandon, and an abandon is not a
# game whose result means anything.
MIN_DURATION = 300
# Three hours of silence between the end of one match and the start of the
# next opens a new play session.
SESSION_GAP = 3 * 3600

LANE_ROLE = {1: "Safe lane", 2: "Mid lane", 3: "Off lane", 4: "Jungle"}
WEEKDAY = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday",
           "Saturday", "Sunday"]
GAME_MODE = {
    0: "Unknown", 1: "All Pick", 2: "Captains Mode", 3: "Random Draft",
    4: "Single Draft", 5: "All Random", 6: "Intro", 7: "Diretide",
    8: "Reverse CM", 9: "Greeviling", 10: "Tutorial", 11: "Mid Only",
    12: "Least Played", 13: "Limited Heroes", 14: "Compendium", 15: "Custom",
    16: "Captains Draft", 17: "Balanced Draft", 18: "Ability Draft",
    19: "Event", 20: "All Random Deathmatch", 21: "1v1 Mid", 22: "All Draft",
    23: "Turbo", 24: "Mutation"}
LOBBY_TYPE = {0: "Unranked", 1: "Practice", 2: "Tournament", 3: "Tutorial",
              4: "Co-op bots", 5: "Ranked team", 6: "Ranked solo", 7: "Ranked",
              8: "1v1 mid", 9: "Battle cup"}
TURBO_MODE = 23
RANKED_LOBBY = 7


@dataclass
class Match:
    match_id: int | None
    start: int
    when: datetime
    duration: int
    slot: int
    radiant: bool
    win: bool
    hero_id: int | None
    hero: str
    kills: int | None = None
    deaths: int | None = None
    assists: int | None = None
    gold_per_min: int | None = None
    xp_per_min: int | None = None
    last_hits: int | None = None
    denies: int | None = None
    level: int | None = None
    hero_damage: int | None = None
    tower_damage: int | None = None
    lane_role: int | None = None
    party_size: int | None = None
    lobby_type: int | None = None
    game_mode: int | None = None
    items: list | None = None
    session: int = 0
    position: int = 0
    previous: str = ""

    @property
    def minutes(self) -> float:
        return self.duration / 60

    @property
    def damage_per_min(self):
        return None if self.hero_damage is None else self.hero_damage / self.minutes

    @property
    def kda(self):
        """Kills plus three tenths of assists, over deaths.

        Deaths are FLOORED AT ONE so a deathless game reads as its own kill
        contribution rather than becoming infinity and taking the mean with
        it. That flatters low-death games slightly and it is said so where
        the block is drawn.
        """
        if self.kills is None or self.deaths is None or self.assists is None:
            return None
        return (self.kills + 0.3 * self.assists) / max(1, self.deaths)


@dataclass
class Shaped:
    matches: list
    dropped: dict = field(default_factory=dict)
    sessions: int = 0
    returned: int = 0

    @property
    def wins(self) -> int:
        return sum(1 for m in self.matches if m.win)

    @property
    def baseline(self):
        """The player's own win rate — the datum every analysis measures
        against. Not a global average, not a rank average: the question is
        always "is this bucket different from how this player usually
        does", and any other datum answers a different one."""
        return (self.wins / len(self.matches)) if self.matches else None


def _num(value):
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return value
    if isinstance(value, str) and value.strip():
        try:
            return float(value)
        except ValueError:
            return None
    return None


def _int(value):
    got = _num(value)
    return None if got is None else int(got)


def _bool(value):
    if isinstance(value, bool):
        return value
    if value in (1, "1", "true", "True"):
        return True
    if value in (0, "0", "false", "False"):
        return False
    return None


def _items(row) -> list | None:
    """The final inventory, de-duplicated. Slot 0 means an empty slot."""
    out, seen = [], set()
    for slot in range(6):
        value = row.get(f"item_{slot}")
        if isinstance(value, int) and value > 0 and value not in seen:
            seen.add(value)
            out.append(value)
    return out or None


def shape(rows, heroes: dict, *, days: int | None = None, no_turbo=False,
          ranked_only=False, now: float | None = None) -> Shaped:
    """API rows to matches, with the sessions walked and the drops counted."""
    import time as _time
    now = _time.time() if now is None else now
    cutoff = (now - days * 86400) if days else None
    dropped = {"short": 0, "window": 0, "turbo": 0, "unranked": 0,
               "malformed": 0}
    out = []

    for row in rows if isinstance(rows, list) else []:
        if not isinstance(row, dict):
            dropped["malformed"] += 1
            continue
        slot = _int(row.get("player_slot"))
        radiant_win = _bool(row.get("radiant_win"))
        duration = _int(row.get("duration"))
        start = _int(row.get("start_time"))
        if None in (slot, radiant_win, duration, start):
            dropped["malformed"] += 1
            continue
        if duration < MIN_DURATION:
            dropped["short"] += 1
            continue
        if cutoff is not None and start < cutoff:
            dropped["window"] += 1
            continue
        mode = _int(row.get("game_mode"))
        if no_turbo and mode == TURBO_MODE:
            dropped["turbo"] += 1
            continue
        lobby = _int(row.get("lobby_type"))
        if ranked_only and lobby != RANKED_LOBBY:
            dropped["unranked"] += 1
            continue

        radiant = slot < 128
        hero_id = _int(row.get("hero_id"))
        out.append(Match(
            match_id=_int(row.get("match_id")),
            start=start, when=datetime.fromtimestamp(start), duration=duration,
            slot=slot, radiant=radiant, win=(radiant == radiant_win),
            hero_id=hero_id,
            hero=heroes.get(hero_id) or (f"Hero {hero_id}" if hero_id
                                         else "Unknown hero"),
            kills=_int(row.get("kills")), deaths=_int(row.get("deaths")),
            assists=_int(row.get("assists")),
            gold_per_min=_int(row.get("gold_per_min")),
            xp_per_min=_int(row.get("xp_per_min")),
            last_hits=_int(row.get("last_hits")),
            denies=_int(row.get("denies")), level=_int(row.get("level")),
            hero_damage=_int(row.get("hero_damage")),
            tower_damage=_int(row.get("tower_damage")),
            lane_role=_int(row.get("lane_role")),
            party_size=_int(row.get("party_size")),
            lobby_type=lobby, game_mode=mode, items=_items(row)))

    out.sort(key=lambda m: m.start)
    sessions = walk_sessions(out)
    return Shaped(matches=out, dropped=dropped, sessions=sessions,
                  returned=len(rows) if isinstance(rows, list) else 0)


def walk_sessions(matches) -> int:
    """Number the sessions, the position in each, and what came before.

    The previous result only counts INSIDE a session, so a loss you slept
    on is not charged against the next morning — which is the whole point
    of the tilt check.
    """
    session = 0
    position = 0
    previous_end = None
    for index, match in enumerate(matches):
        if previous_end is None or (match.start - previous_end) > SESSION_GAP:
            session += 1
            position = 1
        else:
            position += 1
        match.session = session
        match.position = position
        previous_end = match.start + match.duration
        if position == 1:
            match.previous = "First of session"
        elif matches[index - 1].win:
            match.previous = "After a win"
        elif position >= 3 and not matches[index - 2].win:
            match.previous = "After 2+ losses"
        else:
            match.previous = "After a loss"
    return session
