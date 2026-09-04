"""What did Dota actually send? A verdict over a set of GSI payloads.

The one open question in this project is whether a player's own feed carries
the enemy line-up. Memory cannot settle it and neither can this codebase's
own beliefs — only payloads Dota really sent. This module turns a pile of
them into an answer, and is shared by the live probe and by the offline
inspector so both can never disagree.
"""

import json
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

from . import state as gsi_state


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
    draft_sample: object = None
    draft_sample_state: str = ""
    draft_key_present: int = 0
    # Top-level keys neither component list knows about. The
    # recording that settled the draft question also showed
    # components this codebase did not expect, so anything
    # unrecognised is surfaced rather than dropped.
    other_keys: Counter = field(default_factory=Counter)

    def add(self, payload: dict, dataset) -> None:
        parsed = gsi_state.parse(payload, dataset)
        self.payloads += 1
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
            if _weight(block) > _weight(self.draft_sample):
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


def from_directory(directory: Path, dataset) -> Report:
    report = Report()
    for path in sorted(directory.glob("gsi_*.json")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            report.unreadable += 1
            continue
        if isinstance(payload, dict):
            report.add(payload, dataset)
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

    lines += ["", "VERDICT"]
    if report.draft_block_seen and report.best_picks >= 9:
        lines += [
            "  GSI DOES report the full draft in your own games.",
            "  Manual entry is unnecessary — tell Claude and the app can "
            "rely on it entirely.",
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
