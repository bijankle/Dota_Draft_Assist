"""What did Dota actually send? A verdict over a set of GSI payloads.

The one open question in this project is whether a player's own feed carries
the enemy line-up. Memory cannot settle it and neither can this codebase's
own beliefs — only payloads Dota really sent. This module turns a pile of
them into an answer, and is shared by the live probe and by the offline
inspector so both can never disagree.
"""

import json
import time
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

from . import state as gsi_state


class _Unset:
    """Distinguishes 'no sample yet' from a sample that is genuinely empty."""

    def __repr__(self) -> str:
        return "<none seen>"


_UNSET = _Unset()

HERO_PREFIX = "npc_dota_hero_"


def hero_mentions(value: object, path: str = "") -> list[str]:
    """Every place in a payload where something names a hero.

    The last question worth asking of a feed that will not report the
    draft: is a hero named ANYWHERE in it? Answered by walking the whole
    payload rather than by knowing where to look, so a block this codebase
    has never heard of still gets found.
    """
    found = []
    if isinstance(value, dict):
        for key, item in value.items():
            found += hero_mentions(item, f"{path}.{key}" if path else key)
    elif isinstance(value, (list, tuple)):
        for index, item in enumerate(value):
            found += hero_mentions(item, f"{path}[{index}]")
    elif isinstance(value, str) and value.startswith(HERO_PREFIX):
        found.append(path)
    elif isinstance(value, int) and not isinstance(value, bool) and value > 0 \
            and path.rsplit(".", 1)[-1] in ("hero_id", "heroid"):
        found.append(path)
    return found


def hero_objects(value: object, path: str = ""):
    """Yield (path, hero internal name, team) for every object in a payload
    that names a hero.

    The minimap turned out to name heroes during hero selection, which the
    draft block never does. Whether that is usable depends entirely on WHICH
    heroes and WHOSE — so the object around the name is collected too,
    rather than the name alone.
    """
    if isinstance(value, dict):
        named = [v for v in value.values()
                 if isinstance(v, str) and v.startswith(HERO_PREFIX)]
        if named:
            team = value.get("team")
            yield (path, named[0],
                   str(team) if team is not None else "?", value)
        for key, item in value.items():
            yield from hero_objects(item, f"{path}.{key}" if path else key)
    elif isinstance(value, (list, tuple)):
        for index, item in enumerate(value):
            yield from hero_objects(item, f"{path}[{index}]")


@dataclass
class Report:
    payloads: int = 0
    components: Counter = field(default_factory=Counter)
    states: Counter = field(default_factory=Counter)
    best_picks: int = 0
    draft_block_seen: bool = False
    player_names: set = field(default_factory=set)
    unreadable: int = 0
    # A draft block that arrives but yields no picks is the interesting
    # case: either Dota really sends an empty one, or its shape is not the
    # team2/team3 + pickN_id this parser assumes. Guessing between those is
    # exactly what this project refuses to do, so keep the raw evidence.
    draft_keys: Counter = field(default_factory=Counter)
    draft_types: Counter = field(default_factory=Counter)
    draft_sample: object = _UNSET
    draft_sample_state: str = ""
    draft_key_present: int = 0
    # Top-level keys neither component list knows about. The
    # recording that settled the draft question also showed
    # components this codebase did not expect, so anything
    # unrecognised is surfaced rather than dropped.
    other_keys: Counter = field(default_factory=Counter)
    hero_paths: Counter = field(default_factory=Counter)
    # Recording resumes past whatever a previous session left,
    # so one folder can hold several matches from different
    # days. Say so rather than let a stale archive be read as
    # evidence about the game just played.
    match_ids: Counter = field(default_factory=Counter)
    first_written: float = 0.0
    last_written: float = 0.0
    files: int = 0
    # Hero names found during the drafting states, with the
    # team recorded beside them. This is the only lead left
    # for reading a draft automatically.
    # Per game state, never merged: heroes named during STRATEGY_TIME are
    # useless (the draft is over and everyone has spawned), so pooling them
    # with hero selection inflates the only number that matters.
    phase_heroes: dict = field(default_factory=dict)
    phase_payloads: Counter = field(default_factory=Counter)
    phase_best: dict = field(default_factory=dict)
    draft_hero_paths: Counter = field(default_factory=Counter)

    def add(self, payload: dict, dataset, source: str = "") -> None:
        parsed = gsi_state.parse(payload, dataset)
        self.payloads += 1
        paths = hero_mentions(payload)
        self.hero_paths.update(paths)
        if parsed.game_state in gsi_state.DRAFTING_STATES:
            self.draft_hero_paths.update(paths)
            state = parsed.game_state
            self.phase_payloads[state] += 1
            found = list(hero_objects(payload))
            seen = {(hero, team) for _p, hero, team, _o in found}
            self.phase_heroes.setdefault(state, Counter()).update(
                f"team {team}: {hero}" for hero, team in seen)
            # Keyed by WHICH heroes, not just the state: one session can
            # hold two drafts (a game after a game), and dumping only the
            # fullest payload in the session means the other draft -- the
            # one being asked about -- is never shown.
            distinct = {hero for hero, _t in seen}
            key = frozenset(distinct)
            slot = self.phase_best.setdefault(state, {})
            best = slot.get(key)
            if best is None or len(distinct) > best["distinct"]:
                slot[key] = {
                    "distinct": len(distinct),
                    "match": parsed.match_id,
                    "source": source,
                    "objects": [(path, obj) for path, _h, _t, obj in
                                sorted(found)],
                }

        known = set(gsi_state.PLAYER_COMPONENTS
                    + gsi_state.SPECTATOR_COMPONENTS)
        self.other_keys.update(k for k in payload if k not in known)
        if "draft" in payload:
            # Type-agnostic on purpose. An earlier version only looked
            # inside dicts, so a real recording reported the draft key
            # present 8493 times and then printed nothing about it.
            block = payload["draft"]
            self.draft_key_present += 1
            self.draft_types[type(block).__name__] += 1
            if isinstance(block, dict):
                self.draft_keys.update(block.keys())
            # A sentinel, not None: every block being {} weighs zero, and
            # against a None start that never wins, so the report showed
            # "null" for a key it had seen 8493 times.
            if (self.draft_sample is _UNSET
                    or _weight(block) > _weight(self.draft_sample)):
                self.draft_sample = block
                self.draft_sample_state = (
                    (payload.get("map") or {}).get("game_state", ""))
        for name, present in parsed.capabilities.items():
            if present:
                self.components[name] += 1
        if parsed.capabilities.get("draft"):
            self.draft_block_seen = True
        if parsed.game_state:
            self.states[parsed.game_state] += 1
        if parsed.my_name:
            self.player_names.add(parsed.my_name)
        if parsed.match_id and parsed.match_id != "0":
            self.match_ids[parsed.match_id] += 1
        self.best_picks = max(self.best_picks,
                              len(parsed.allies) + len(parsed.enemies))


def _weight(value: object) -> int:
    """How much a value actually carries, shape-agnostically, so the fullest
    sample wins whatever shape the block turns out to be."""
    if isinstance(value, dict):
        return sum(1 + _weight(v) for v in value.values())
    if isinstance(value, (list, tuple)):
        return sum(1 + _weight(v) for v in value)
    if value in (None, "", 0, "0", -1, False):
        return 0
    return 1


def from_directory(directory: Path, dataset, match: str = "") -> Report:
    """Read an archive. `match` keeps only payloads from one match id —
    recording appends, so a folder routinely holds several games and
    pooling them makes every per-phase count meaningless."""
    report = Report()
    for path in sorted(directory.glob("gsi_*.json")):
        report.files += 1
        try:
            written = path.stat().st_mtime
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            report.unreadable += 1
            continue
        report.first_written = min(report.first_written or written, written)
        report.last_written = max(report.last_written, written)
        if isinstance(payload, dict):
            if match and str((payload.get("map") or {}).get("matchid", "")) \
                    != match:
                continue
            report.add(payload, dataset, source=path.name)
        else:
            report.unreadable += 1
    return report


def format_report(report: Report, archive: Path | None = None) -> str:
    lines = ["=" * 68, f"Payloads examined: {report.payloads}"]
    if report.unreadable:
        lines.append(f"Unreadable files: {report.unreadable}")
    if not report.payloads:
        lines += [
            "",
            "NOTHING TO EXAMINE. Record a draft first: tick",
            "Game > Record game data, then sit through hero selection.",
        ]
        return "\n".join(lines)

    if report.first_written:
        span = (f"{_when(report.first_written)}  to  "
                f"{_when(report.last_written)}")
        lines.append(f"Recorded: {span}")
        age = (time.time() - report.last_written) / 86400
        if age >= 1:
            lines.append(f"  (the newest payload here is {age:.0f} days old — "
                         "this is an ARCHIVE, not the game you just played)")
    if report.match_ids:
        lines.append(f"Matches examined: {len(report.match_ids)} "
                     "(" + ", ".join(
                         f"{mid} ×{count}" for mid, count
                         in report.match_ids.most_common(5)) + ")")
        if len(report.match_ids) > 1:
            lines.append("  Recording appends, so these are separate games "
                         "pooled together, which makes the per-phase counts "
                         "below meaningless.")
            lines.append("  Re-run with --match <id> for one game, or empty "
                         "the folder before recording to start clean.")
    if report.player_names:
        lines.append("Reported as: " + ", ".join(sorted(report.player_names)))
    lines.append("")
    lines.append("Components seen (payload counts):")
    for name in (gsi_state.PLAYER_COMPONENTS
                 + gsi_state.SPECTATOR_COMPONENTS):
        seen = report.components.get(name, 0)
        mark = " " if seen else "MISSING"
        lines.append(f"  {seen:6d}  {name:<14s}{mark}")
    if report.other_keys:
        lines += ["", "Other top-level keys (not in either component list):"]
        for name, count in report.other_keys.most_common(20):
            lines.append(f"  {count:6d}  {name}")
    lines.append("")
    lines.append("Game states seen:")
    for name, count in report.states.most_common():
        lines.append(f"  {count:6d}  {name}")
    if gsi_state.STATE_HERO_SELECTION not in report.states:
        lines.append("  (no HERO_SELECTION payload — this recording does not "
                     "cover a draft, so it cannot answer the question)")

    if report.draft_key_present:
        lines += ["", f"The 'draft' key arrived in "
                      f"{report.draft_key_present} payloads. It held:"]
        for name, count in report.draft_types.most_common():
            lines.append(f"  {count:6d}  {name}")
        if report.draft_keys:
            lines += ["", "Keys inside it, and how many payloads had each:"]
            for name, count in report.draft_keys.most_common(30):
                lines.append(f"  {count:6d}  {name}")
        lines += ["",
                  "Fullest draft value seen"
                  + (f" (during {report.draft_sample_state})"
                     if report.draft_sample_state else "") + ":",
                  _indent(json.dumps(report.draft_sample, indent=2,
                                     sort_keys=True, default=repr)[:4000])]
        if _weight(report.draft_sample) == 0:
            lines.append("  ^ carries nothing: Dota really is sending an "
                         "empty draft block.")

    lines += ["", "Everywhere a hero is named, ACROSS THE WHOLE PAYLOAD:"]
    if report.hero_paths:
        for name, count in report.hero_paths.most_common(20):
            lines.append(f"  {count:6d}  {name}")
    else:
        lines.append("  nowhere — no hero is named anywhere in this feed")
    lines += ["", "...and the same during hero selection and strategy time, "
                  "which is the only part that could help a draft:"]
    if report.draft_hero_paths:
        for name, count in report.draft_hero_paths.most_common(20):
            lines.append(f"  {count:6d}  {name}")
    else:
        lines.append("  nowhere — while drafting, this feed names no hero "
                     "at all, not even your own")

    for state in (gsi_state.STATE_HERO_SELECTION, gsi_state.STATE_STRATEGY):
        heroes = report.phase_heroes.get(state)
        short = state.replace("DOTA_GAMERULES_STATE_", "")
        count = report.phase_payloads.get(state, 0)
        lines += ["", "=" * 68,
                  f"{short}: {count} payloads"]
        if state == gsi_state.STATE_STRATEGY:
            lines.append("(the draft is already over here — shown only for "
                         "comparison)")
        if not heroes:
            lines.append("  no hero named anywhere in these payloads")
            continue
        lines.append("")
        lines.append("Heroes named, with the team field beside them "
                     "(2 = Radiant, 3 = Dire, ? = no team field):")
        for name, seen in heroes.most_common(30):
            lines.append(f"  {seen:6d}  {name}")

        drafts = sorted(report.phase_best.get(state, {}).values(),
                        key=lambda entry: -entry["distinct"])
        drafts = drafts[:3]
        for number, best in enumerate(drafts, start=1):
            label = (f"DRAFT {number} of {len(drafts)} — " if len(drafts) > 1
                     else "")
            lines += ["",
                      f"{label}the fullest payload ({best['distinct']} "
                      f"distinct heroes) was {best['source']} "
                      f"(match {best['match'] or '?'}). Every hero-bearing "
                      f"object in it, in full:"]
            for path, obj in best["objects"][:24]:
                lines.append(f"  {path}")
                lines.append(_indent(json.dumps(obj, sort_keys=True,
                                                default=repr)[:400],
                                     "      "))
            if len(best["objects"]) > 24:
                lines.append(f"  ... and {len(best['objects']) - 24} more")

        # "?" is the absence of a team field, not a second team. Counting it
        # as one reported BOTH TEAMS APPEAR over data that was entirely one
        # side.
        teams = {t.split(":")[0].removeprefix("team ").strip()
                 for t in heroes}
        teams = {t for t in teams if t not in ("?", "")}
        lines.append("")
        if len(teams) >= 2:
            lines.append(f"  Teams present: {sorted(teams)} — BOTH sides are "
                         "named, so this phase can be read automatically.")
        elif teams:
            lines.append(f"  Only team {teams.pop()} is ever named. That is "
                         "what vision-limited data looks like: your own "
                         "side only.")
        else:
            lines.append("  No object carried a team field at all.")

    lines += ["", "VERDICT"]
    if report.draft_block_seen and report.best_picks >= 9:
        lines += [
            "  Both line-ups were read — but from the MINIMAP at strategy "
            "time, not from the draft block,",
            "  which is empty as always. That is after the picking is over: "
            "in time for items and lane",
            "  matchups, too late to choose a hero. The picks during hero "
            "selection still come from the screen.",
        ]
    elif report.draft_key_present and _weight(report.draft_sample) == 0:
        lines += [
            "  Dota sends an EMPTY draft block. Not a shape this parser "
            "misreads — there is nothing in it.",
            "  GSI does not report the line-ups for your own match, and the "
            "hero-mention scan above says",
            "  whether anything else in the feed does. The picks have to be "
            "typed in (quick-entry bar:",
            "  type, Enter, Tab to flip side) or read from the screen with "
            "--vision.",
        ]
    elif report.draft_block_seen:
        lines += [
            f"  A 'draft' block arrived but only {report.best_picks} picks "
            "were read out of it.",
            "  That is either an empty block or a shape this parser does "
            "not know. The keys printed above",
            "  say which — paste them to Claude rather than guessing.",
        ]
    else:
        lines += [
            "  No 'draft' block ever arrived, so GSI does NOT report the "
            "line-ups for your own match.",
            "  This is the expected answer: 'draft' is a spectator "
            "component. Your own hero, your name,",
            "  your team and the game state ARE reported, which is how the "
            "app knows a draft is happening",
            "  and which side you are on. The other nine picks have to be "
            "clicked in by hand (or read from",
            "  the screen with --vision).",
        ]
    if archive is not None:
        lines += ["", f"Recording: {archive}"]
    return "\n".join(lines)


def _indent(text: str, prefix: str = "  ") -> str:
    return "\n".join(prefix + line for line in text.splitlines())


def _when(stamp: float) -> str:
    return time.strftime("%Y-%m-%d %H:%M", time.localtime(stamp))
