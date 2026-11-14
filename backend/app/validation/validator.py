"""Deterministic safety & consistency validator.

This is the only gate between a candidate allocation and a committed one.
No natural-language statement and no LLM output can bypass it. Its coverage
is the system's safety ceiling, so every check returns a structured
violation code:

  NON_NUMERIC, NON_FINITE_OR_NEGATIVE  malformed values (checked before any arithmetic)
  DUPLICATE_PROPOSAL, STALE_PROPOSAL   idempotency / optimistic concurrency
  AGENT_SET_MISMATCH                   every active and reserved agent exactly once
  OVER_CAPACITY                        total <= verified grid supply + battery offer
  ABOVE_MAX, BELOW_MIN_SAFE            per-agent nameplate limit and (avoidable) safe minimum
  SUPPLY_WITHHELD_IN_DEGRADATION       no idle supply while minimums are unmet
  RAMP_LIMIT                           load restoration per agent vs the previous committed allocation
  FEEDER_CAP                           per-feeder thermal capacity from the digital twin
  BATTERY_LIMIT, BATTERY_SOC           discharge within the offer and within usable stored energy
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
    previous: dict[str, float] | None = None                 # last committed allocation (ramp reference)
    ramp_up: dict[str, float] = field(default_factory=dict)  # max MW increase per interval
    feeders: dict[str, tuple[list[str], float]] = field(default_factory=dict)  # feeder -> (members, MW)
    battery_usable_mwh: float | None = None
    dt_hours: float = 0.25

    @property
    def total_supply(self) -> float:
        return self.grid_supply + self.battery_offer

    def upper_cap(self, aid: str) -> float:
        """Highest allocation this agent may receive in this interval (nameplate and ramp)."""
        cap = self.max_allowed.get(aid, float("inf"))
        if self.previous is not None and aid in self.previous and aid in self.ramp_up and aid not in self.reserved:
            cap = min(cap, self.ramp_ceiling(aid))
        return cap

    def ramp_ceiling(self, aid: str) -> float:
        """Ramp limits never block restoring an agent to its safe minimum (critical load comes first)."""
        floor = min(self.min_safe.get(aid, 0.0), self.demand.get(aid, 0.0))
        return max((self.previous or {}).get(aid, 0.0) + self.ramp_up.get(aid, float("inf")), floor)


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


def _is_number(v: object) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool)


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

    def bail() -> ValidationResult:
        return ValidationResult(False, False, violations, checks, 0.0, c.total_supply, {}, 0.0)

    if not isinstance(allocation, dict):
        check("well_formed", False, "allocation must be a mapping of agent id -> MW", "NON_NUMERIC")
        return bail()
    full = dict(allocation)
    for aid, mw in c.reserved.items():
        full.setdefault(aid, mw)
    expected = set(c.active_agents) | set(c.reserved)

    # Malformed numbers are rejected before any arithmetic touches them.
    non_numeric = sorted(str(k) for k, v in full.items() if not _is_number(v))
    check("values_numeric", not non_numeric, f"non-numeric allocations: {non_numeric or 'none'}", "NON_NUMERIC")
    if non_numeric:
        return bail()
    bad = sorted(k for k, v in full.items() if not math.isfinite(v) or v < 0)
    check("values_finite_non_negative", not bad, f"non-finite or negative allocations: {bad or 'none'}",
          "NON_FINITE_OR_NEGATIVE")
    if bad:
        return bail()

    check("proposal_unique", proposal_id not in committed_ids,
          f"proposal {proposal_id} {'already committed' if proposal_id in committed_ids else 'is new'}",
          "DUPLICATE_PROPOSAL")
    check("version_current", base_version == c.version,
          f"proposal base version {base_version}, current version {c.version}", "STALE_PROPOSAL")
    missing = expected - set(full)
    unknown = set(full) - expected
    check("agents_complete", not missing and not unknown,
          f"missing={sorted(missing)} unknown={sorted(unknown)}", "AGENT_SET_MISMATCH")

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
        if c.previous is not None and aid in c.previous and aid in c.ramp_up and aid not in c.reserved:
            ceiling = c.ramp_ceiling(aid)
            check("ramp_limit", mw <= ceiling + TOL,
                  f"{aid}: {mw:.2f} MW vs ramp ceiling {ceiling:.2f} MW (previous {c.previous[aid]:.2f} "
                  f"+ {c.ramp_up[aid]:.2f} MW/interval, never below the safe minimum)", "RAMP_LIMIT", aid)
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
        # In degradation mode shortages are unavoidable but supply must not be wasted
        # (up to what nameplate and ramp limits allow the agents to absorb).
        absorbable = sum(c.reserved[a] if a in c.reserved else min(c.upper_cap(a), c.demand.get(a, float("inf")))
                         for a in expected)
        target = min(c.total_supply, absorbable)
        check("degradation_uses_supply", total >= target - 0.05,
              f"degradation mode: allocated {total:.2f} of {target:.2f} MW usable while minimums unmet",
              "SUPPLY_WITHHELD_IN_DEGRADATION")

    for fid, (members, cap) in sorted(c.feeders.items()):
        load = sum(full.get(a, 0.0) for a in members)
        check("feeder_capacity", load <= cap + TOL, f"{fid}: {load:.2f} MW vs capacity {cap:.2f} MW",
              "FEEDER_CAP")

    battery_needed = max(0.0, total - c.grid_supply)
    check("battery_limit", battery_needed <= c.battery_offer + TOL,
          f"battery discharge required {battery_needed:.2f} MW, offered {c.battery_offer:.2f} MW",
          "BATTERY_LIMIT")
    if c.battery_usable_mwh is not None:
        energy = battery_needed * c.dt_hours
        check("battery_soc", energy <= c.battery_usable_mwh + TOL,
              f"discharge needs {energy:.2f} MWh this interval, usable above reserve {c.battery_usable_mwh:.2f} MWh",
              "BATTERY_SOC")

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
