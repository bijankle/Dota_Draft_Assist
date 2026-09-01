"""Item recommendation engine.

Identical in shape to hero scoring, entirely different in origin: there is no
statistical source for item effectiveness against a lineup, so this runs on a
HAND-AUTHORED rules table (rules/items.yaml) — asserted, not measured, and
the UI must say so.

Stacking is SUBLINEAR BY DESIGN: when several heroes trigger the same item,
severities are sorted descending and weighted 1.0 / 0.6 / 0.4 (nothing
beyond the third). One Nullifier answers three enemies; a linear sum would
let breadth beat severity and surface the generically applicable over the
specifically urgent. Do not "fix" this.

Display contract (enforced by callers via recommend()): only after the user's
own pick is locked, severity floor applied, at most MAX_SHOWN items. Silence
in many games is correct and must not be tuned away.
"""

from dataclasses import dataclass

import yaml

from ..config import RULES_FILE

STACK_WEIGHTS = (1.0, 0.6, 0.4)
SEVERITY_FLOOR = 2.0   # stacked score below this is not shown
MAX_SHOWN = 5
# A rule not re-verified within this many minor patches is flagged stale.
STALE_AFTER_PATCHES = 2

ROLE_GROUPS = {
    "core": {"carry", "mid", "offlane"},
    "support": {"soft_support", "hard_support"},
}
ALL_ROLES = {"carry", "mid", "offlane", "soft_support", "hard_support"}


@dataclass
class Rule:
    item: str
    trigger: str            # hero NAME (matched against dataset names)
    side: str               # "enemy" or "ally" (saves key off allies)
    severity: int           # 1..3, coarse by design
    reason: str             # human-readable, names the triggering hero
    roles: set[str]         # empty = any role
    verified_patch: str


@dataclass
class Trigger:
    hero: str
    severity: int
    reason: str
    stale: bool


@dataclass
class ItemAdvice:
    item: str
    score: float
    triggers: list[Trigger]   # severity-descending; weights applied in order
    any_stale: bool


def _patch_tuple(p: str) -> tuple[int, int]:
    # "7.39c" -> (7, 39); letter revisions don't count for staleness.
    core = "".join(ch for ch in p if ch.isdigit() or ch == ".")
    parts = core.split(".")
    return int(parts[0]), int(parts[1]) if len(parts) > 1 else 0


def is_stale(rule_patch: str, current_patch: str,
             after: int = STALE_AFTER_PATCHES) -> bool:
    try:
        cur, rul = _patch_tuple(current_patch), _patch_tuple(rule_patch)
    except (ValueError, IndexError):
        return True  # unparseable = unverified
    if cur[0] != rul[0]:
        return True
    return cur[1] - rul[1] >= after


def _expand_roles(raw: list[str] | None) -> set[str]:
    if not raw:
        return set()
    roles: set[str] = set()
    for r in raw:
        r = r.strip().lower()
        roles |= ROLE_GROUPS.get(r, {r})
    unknown = roles - ALL_ROLES
    if unknown:
        raise ValueError(
            f"unknown role(s) {sorted(unknown)} in rules file; valid: "
            f"{sorted(ALL_ROLES)} or groups {sorted(ROLE_GROUPS)}")
    return roles


def load_rules(path=RULES_FILE) -> tuple[list[Rule], dict]:
    """Returns (rules, meta). Raises with a pointed message on malformed
    entries — the file is hand-edited constantly, so errors must name the
    offending rule."""
    doc = yaml.safe_load(path.read_text(encoding="utf-8"))
    meta = doc.get("meta", {})
    rules = []
    for i, r in enumerate(doc.get("rules", [])):
        where = f"rules[{i}] ({r.get('item', '?')} / {r.get('trigger', '?')})"
        for req in ("item", "trigger", "severity", "reason", "verified_patch"):
            if req not in r:
                raise ValueError(f"{where}: missing required field '{req}'")
        if r["severity"] not in (1, 2, 3):
            raise ValueError(f"{where}: severity must be 1, 2 or 3")
        side = r.get("side", "enemy")
        if side not in ("enemy", "ally"):
            raise ValueError(f"{where}: side must be 'enemy' or 'ally'")
        rules.append(Rule(
            item=str(r["item"]),
            trigger=str(r["trigger"]),
            side=side,
            severity=int(r["severity"]),
            reason=str(r["reason"]),
            roles=_expand_roles(r.get("roles")),
            verified_patch=str(r["verified_patch"]),
        ))
    return rules, meta


def stacked_score(severities: list[int]) -> float:
    """Sublinear stacking; see module docstring."""
    ordered = sorted(severities, reverse=True)
    return sum(sev * w for sev, w in zip(ordered, STACK_WEIGHTS))


def recommend(rules: list[Rule], enemy_names: list[str],
              ally_names: list[str], my_role: str | None,
              current_patch: str,
              floor: float = SEVERITY_FLOOR,
              max_shown: int = MAX_SHOWN) -> list[ItemAdvice]:
    """Ranked item advice for a locked-in pick. Empty output is a correct and
    common result, not a failure."""
    enemy_set = {n.lower() for n in enemy_names}
    ally_set = {n.lower() for n in ally_names}

    per_item: dict[str, list[Trigger]] = {}
    for rule in rules:
        if rule.roles and (my_role is None or my_role not in rule.roles):
            continue
        present = enemy_set if rule.side == "enemy" else ally_set
        if rule.trigger.lower() not in present:
            continue
        per_item.setdefault(rule.item, []).append(Trigger(
            hero=rule.trigger,
            severity=rule.severity,
            reason=rule.reason,
            stale=is_stale(rule.verified_patch, current_patch),
        ))

    advice = []
    for item, triggers in per_item.items():
        triggers.sort(key=lambda t: t.severity, reverse=True)
        score = stacked_score([t.severity for t in triggers])
        if score >= floor:
            advice.append(ItemAdvice(
                item=item, score=score, triggers=triggers,
                any_stale=any(t.stale for t in triggers),
            ))
    advice.sort(key=lambda a: a.score, reverse=True)
    return advice[:max_shown]
