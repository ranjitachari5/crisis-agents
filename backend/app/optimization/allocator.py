"""Constrained allocation optimizer.

Minimise   alpha * predicted_damage + beta * fairness_penalty + gamma * unmet_critical
subject to sum(a) <= supply, a_i <= min(demand_i, max_i), and — whenever the
supply can cover them — a_i >= min_safe_i (hard constraint, never relaxed by
the fairness slider). If the minimums cannot all be met, the problem switches
to explicit *degradation mode*: lower bounds drop to 0 and the gamma term
(weighted critical shortfall) is minimised instead, with shortages reported.

All terms are normalised so the weights are comparable:
  predicted_damage = sum w_i * (D_i - a_i) / sum w_i D_i
  fairness_penalty = sum p_i (r_i - r_bar)^2,  r_i = a_i / D_i, p_i = D_i / sum D
  unmet_critical   = sum c_i * max(0, M_i - a_i) / sum c_i M_i
The solver is SciPy SLSQP (deterministic). A greedy fractional-knapsack
fallback guarantees a valid answer if the solver ever fails.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field

import numpy as np
from scipy.optimize import minimize

log = logging.getLogger(__name__)

ALPHA = 1.0
GAMMA = 50.0
BETA_MAX = 1.5
EPS = 1e-6


def beta_from_fairness(fairness: float) -> float:
    """Map the commander's slider (0 = priority, 1 = equity) to beta."""
    return BETA_MAX * min(1.0, max(0.0, fairness))


@dataclass
class AllocationProblem:
    agent_ids: list[str]
    demand: dict[str, float]
    min_safe: dict[str, float]
    max_allowed: dict[str, float]
    damage_weight: dict[str, float]
    critical_weight: dict[str, float]
    supply: float
    fairness: float = 0.5
    lower_bounds: dict[str, float] | None = None
    alpha: float = ALPHA
    gamma: float = GAMMA


@dataclass
class AllocationSolution:
    allocation: dict[str, float]
    degradation: bool
    objective: dict[str, float]
    shortages: dict[str, float] = field(default_factory=dict)
    solver: str = "slsqp"


def _arrays(p: AllocationProblem):
    ids = p.agent_ids
    D = np.array([max(p.demand[i], 0.0) for i in ids], float)
    X = np.array([p.max_allowed[i] for i in ids], float)
    ub = np.minimum(D, X)
    M = np.minimum(np.array([p.min_safe[i] for i in ids], float), ub)
    w = np.array([p.damage_weight[i] for i in ids], float)
    c = np.array([p.critical_weight[i] for i in ids], float)
    return ids, D, M, ub, w, c


def evaluate_objective(p: AllocationProblem, allocation: dict[str, float]) -> dict[str, float]:
    ids, D, M, ub, w, c = _arrays(p)
    a = np.array([allocation.get(i, 0.0) for i in ids], float)
    beta = beta_from_fairness(p.fairness)
    damage_raw = float(np.sum(w * np.maximum(0.0, D - a)))
    crit_raw = float(np.sum(c * np.maximum(0.0, M - a)))
    Dsum = max(D.sum(), EPS)
    r = np.where(D > EPS, a / np.maximum(D, EPS), 1.0)
    pw = D / Dsum
    rbar = float(np.sum(pw * r))
    fairness_pen = float(np.sum(pw * (r - rbar) ** 2))
    damage_n = damage_raw / max(float(np.sum(w * D)), EPS)
    crit_n = crit_raw / max(float(np.sum(c * M)), EPS)
    return {
        "predicted_damage": round(damage_raw, 4),
        "unmet_critical": round(crit_raw, 4),
        "fairness_penalty": round(fairness_pen, 6),
        "predicted_damage_norm": round(damage_n, 6),
        "unmet_critical_norm": round(crit_n, 6),
        "alpha": p.alpha, "beta": round(beta, 4), "gamma": p.gamma,
        "total": round(p.alpha * damage_n + beta * fairness_pen + p.gamma * crit_n, 6),
    }


def _repair(a: np.ndarray, lb: np.ndarray, ub: np.ndarray, supply: float) -> np.ndarray:
    a = np.clip(np.round(a, 3), lb, ub)
    excess = float(a.sum()) - supply
    if excess > EPS:
        room = a - lb
        if room.sum() > EPS:
            a = a - room * min(1.0, excess / room.sum())
        a = np.clip(np.floor(a * 1000) / 1000, lb, ub)
        # final guard against rounding residue
        excess = float(a.sum()) - supply
        if excess > EPS:
            k = int(np.argmax(a - lb))
            a[k] = max(lb[k], a[k] - excess)
    return a


def _greedy(p: AllocationProblem, lb: np.ndarray, ub: np.ndarray, degradation: bool) -> np.ndarray:
    """Fractional knapsack on marginal harm per MW; exact for the linear terms."""
    ids, D, M, _, w, c = _arrays(p)
    a = lb.copy()
    remaining = p.supply - a.sum()
    wd = max(float(np.sum(w * D)), EPS)
    cm = max(float(np.sum(c * M)), EPS)
    # Phase 1: critical minimums (only matters in degradation mode)
    if degradation:
        for k in np.argsort(-(c / cm)):
            give = min(max(0.0, M[k] - a[k]), remaining)
            a[k] += give
            remaining -= give
    for k in np.argsort(-(w / wd)):
        give = min(ub[k] - a[k], remaining)
        if give > 0:
            a[k] += give
            remaining -= give
    return a


def solve(p: AllocationProblem) -> AllocationSolution:
    ids, D, M, ub, w, c = _arrays(p)
    n = len(ids)
    supply = max(0.0, float(p.supply))
    if n == 0:
        return AllocationSolution({}, False, evaluate_objective(p, {}), {}, "trivial")

    if ub.sum() <= supply + EPS:
        alloc = {i: round(float(v), 3) for i, v in zip(ids, ub)}
        return AllocationSolution(alloc, False, evaluate_objective(p, alloc), {}, "no_deficit")

    degradation = M.sum() > supply + EPS
    lb = np.zeros(n) if degradation else M.copy()
    if p.lower_bounds and not degradation:
        override = np.array([min(max(p.lower_bounds.get(i, 0.0), lb[k]), ub[k]) for k, i in enumerate(ids)])
        if override.sum() <= supply + EPS:
            lb = override

    beta = beta_from_fairness(p.fairness)
    Dsum = max(D.sum(), EPS)
    wd = max(float(np.sum(w * D)), EPS)
    cm = max(float(np.sum(c * M)), EPS)
    scale = 1000.0

    def obj(x):
        a, s = x[:n], x[n:]
        r = a / np.maximum(D, EPS)
        rbar = a.sum() / Dsum
        fair = np.sum((D / Dsum) * (r - rbar) ** 2)
        return scale * (p.alpha * np.sum(w * (D - a)) / wd + beta * fair + p.gamma * np.sum(c * s) / cm)

    def grad(x):
        a = x[:n]
        r = a / np.maximum(D, EPS)
        rbar = a.sum() / Dsum
        ga = -p.alpha * w / wd + beta * 2 * (r - rbar) / Dsum
        gs = p.gamma * c / cm
        return scale * np.concatenate([ga, gs])

    # initial guess: proportional fill of the room above lower bounds
    room = ub - lb
    frac = min(1.0, (supply - lb.sum()) / room.sum()) if room.sum() > EPS else 0.0
    a0 = lb + room * max(frac, 0.0)
    s0 = np.maximum(0.0, M - a0) if degradation else np.zeros(n)
    bounds = [(lb[k], ub[k]) for k in range(n)] + [((0.0, M[k]) if degradation else (0.0, 0.0)) for k in range(n)]
    cons = [
        {"type": "ineq", "fun": lambda x: supply - x[:n].sum(), "jac": lambda x: np.concatenate([-np.ones(n), np.zeros(n)])},
        {"type": "ineq", "fun": lambda x: x[:n] + x[n:] - M, "jac": lambda x: np.hstack([np.eye(n), np.eye(n)])},
    ]
    solver = "slsqp"
    if beta <= EPS or degradation:
        # Objective is linear here (critical shortfall dominates in degradation):
        # the greedy fractional knapsack is the exact optimum.
        a = _repair(_greedy(p, lb, ub, degradation), lb, ub, supply)
        alloc = {i: round(float(v), 3) for i, v in zip(ids, a)}
        shortages = {i: round(float(M[k] - a[k]), 3) for k, i in enumerate(ids) if M[k] - a[k] > 1e-3}
        return AllocationSolution(alloc, bool(degradation), evaluate_objective(p, alloc), shortages, "greedy_exact")
    try:
        res = minimize(obj, np.concatenate([a0, s0]), jac=grad, method="SLSQP", bounds=bounds,
                       constraints=cons, options={"maxiter": 500, "ftol": 1e-10})
        if not res.success or not np.all(np.isfinite(res.x)):
            raise RuntimeError(res.message)
        a = res.x[:n]
    except Exception as exc:  # deterministic fallback
        log.warning("SLSQP failed (%s); using greedy allocation", exc)
        a = _greedy(p, lb, ub, degradation)
        solver = "greedy_fallback"

    a = _repair(a, lb, ub, supply)
    alloc = {i: round(float(v), 3) for i, v in zip(ids, a)}
    shortages = {i: round(float(M[k] - a[k]), 3) for k, i in enumerate(ids) if M[k] - a[k] > 1e-3}
    return AllocationSolution(alloc, bool(degradation), evaluate_objective(p, alloc), shortages, solver)
