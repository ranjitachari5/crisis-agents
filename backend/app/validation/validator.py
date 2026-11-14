"""Deterministic safety & consistency validator.

This is the only gate between a candidate allocation and a committed one.
No natural-language statement and no LLM output can bypass it.
"""
from __future__ import annotations

import math
from dataclasses import asdict, dataclass, field

TOL = 0.01  # MW (10 kW): absorbs 3-decimal rounding of several allocations


@dataclass
class AllocationConstraints:
    version: int
    grid_supply: float                 # verified grid supply (after reserve margin)
    battery_offer: float               # discharge the battery agent has committed to
    min_safe: dict[str, float]
    max_allowed: dict[str, float]
    demand: dict[str, float]
    active_agents: list[str]
    reserved: dict[str, float] = field(default_factory=dict)  # disconnected/isolated fallback

    @property
    def total_supply(self) -> float:
        return self.grid_supply + self.battery_offer


@dataclass
class Violation:
    code: str
    detail: str
    agent_id: str | None = None


@dataclass
class ValidationResult:
    valid: bool
    degradation_mode: bool
    violations: list[Violation]
    checks: list[dict]
    total_allocated: float
    total_supply: float
    unavoidable_shortages: dict[str, float]
    battery_discharge: float

    def to_dict(self) -> dict:
        d = asdict(self)
        d["violations"] = [asdict(v) for v in self.violations]
        return d


def validate_allocation(
    allocation: dict[str, float],
    c: AllocationConstraints,
    base_version: int,
    proposal_id: str,
    committed_ids: set[str],
) -> ValidationResult:
    violations: list[Violation] = []
    checks: list[dict] = []

    def check(name: str, ok: bool, detail: str, code: str, agent: str | None = None):
        checks.append({"check": name, "passed": ok, "detail": detail, "agent_id": agent})
        if not ok:
            violations.append(Violation(code, detail, agent))

    full = dict(allocation)
    for aid, mw in c.reserved.items():
        full.setdefault(aid, mw)
    expected = set(c.active_agents) | set(c.reserved)

    check("proposal_unique", proposal_id not in committed_ids,
          f"proposal {proposal_id} {'already committed' if proposal_id in committed_ids else 'is new'}",
          "DUPLICATE_PROPOSAL")
    check("version_current", base_version == c.version,
          f"proposal base version {base_version}, current version {c.version}", "STALE_PROPOSAL")
    missing = expected - set(full)
    unknown = set(full) - expected
    check("agents_complete", not missing and not unknown,
          f"missing={sorted(missing)} unknown={sorted(unknown)}", "AGENT_SET_MISMATCH")

    finite = all(isinstance(v, (int, float)) and math.isfinite(v) and v >= 0 for v in full.values())
    check("values_finite_non_negative", finite, "all allocations finite and >= 0", "INVALID_VALUE")
    if not finite:
        return ValidationResult(False, False, violations, checks, 0.0, c.total_supply, {}, 0.0)

    total = sum(full.values())
    check("capacity", total <= c.total_supply + TOL,
          f"total {total:.2f} MW vs verified supply {c.total_supply:.2f} MW "
          f"(grid {c.grid_supply:.2f} + battery {c.battery_offer:.2f})", "OVER_CAPACITY")

    mins = {a: min(c.min_safe.get(a, 0.0), c.demand.get(a, 0.0)) for a in expected}
    degradation = sum(mins.values()) > c.total_supply + TOL
    shortages: dict[str, float] = {}
    for aid in sorted(expected & set(full)):
        mw = full[aid]
        cap = c.max_allowed.get(aid, float("inf"))
        check("max_allowed", mw <= cap + TOL, f"{aid}: {mw:.2f} <= max {cap:.2f}", "ABOVE_MAX", aid)
        if mw < mins[aid] - TOL:
            shortages[aid] = round(mins[aid] - mw, 3)
            if not degradation:
                check("min_safe", False, f"{aid}: {mw:.2f} below safe minimum {mins[aid]:.2f}",
                      "BELOW_MIN_SAFE", aid)
    if not degradation:
        checks.append({"check": "min_safe", "passed": not shortages,
                       "detail": "all safe minimums satisfied" if not shortages else "minimums violated",
                       "agent_id": None})
    else:
        # In degradation mode shortages are unavoidable but supply must not be wasted.
        check("degradation_uses_supply", total >= c.total_supply - 0.05,
              f"degradation mode: allocated {total:.2f} of {c.total_supply:.2f} MW while minimums unmet",
              "SUPPLY_WITHHELD_IN_DEGRADATION")

    battery_needed = max(0.0, total - c.grid_supply)
    check("battery_limit", battery_needed <= c.battery_offer + TOL,
          f"battery discharge required {battery_needed:.2f} MW, offered {c.battery_offer:.2f} MW",
          "BATTERY_LIMIT")

    return ValidationResult(
        valid=not violations,
        degradation_mode=degradation,
        violations=violations,
        checks=checks,
        total_allocated=round(total, 3),
        total_supply=round(c.total_supply, 3),
        unavoidable_shortages=shortages if degradation else {},
        battery_discharge=round(battery_needed, 3),
    )
