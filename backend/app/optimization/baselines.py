"""Baseline allocation policies used for evaluation (no negotiation, no min-protection)."""
from __future__ import annotations

from app.optimization.allocator import AllocationProblem, solve

FIXED_PRIORITY_ORDER = ("hospital_agent", "emergency_agent", "telecom_agent", "water_agent")


def _fill_in_order(p: AllocationProblem, order: list[str]) -> dict[str, float]:
    remaining = max(0.0, p.supply)
    alloc = {i: 0.0 for i in p.agent_ids}
    for i in order:
        if i not in alloc:
            continue
        give = min(min(p.demand[i], p.max_allowed[i]), remaining)
        alloc[i] = round(give, 3)
        remaining -= give
    return alloc


def first_come_first_served(p: AllocationProblem, arrival_order: list[str]) -> dict[str, float]:
    """Requests are granted in arrival order until supply runs out."""
    return _fill_in_order(p, arrival_order)


def fixed_priority(p: AllocationProblem) -> dict[str, float]:
    """Static ranking: hospital > emergency > telecom > water, full demand each."""
    order = [i for i in FIXED_PRIORITY_ORDER if i in p.agent_ids]
    order += [i for i in p.agent_ids if i not in order]
    return _fill_in_order(p, order)


def centralized_optimization(p: AllocationProblem) -> dict[str, float]:
    """A single central optimizer with full information (no agent autonomy)."""
    return solve(p).allocation
