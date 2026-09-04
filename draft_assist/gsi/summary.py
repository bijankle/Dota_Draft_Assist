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

    def add(self, payload: dict, dataset) -> None:
        parsed = gsi_state.parse(payload, dataset)
        self.payloads += 1
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
    lines.append("")
    lines.append("Game states seen:")
    for name, count in report.states.most_common():
        lines.append(f"  {count:6d}  {name}")
    if gsi_state.STATE_HERO_SELECTION not in report.states:
        lines.append("  (no HERO_SELECTION payload — this recording does not "
                     "cover a draft, so it cannot answer the question)")

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
            "were ever visible.",
            "  Send the recording to Claude to see what it does carry.",
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
