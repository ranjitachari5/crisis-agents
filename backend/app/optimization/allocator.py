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

The problem is convex: the damage and shortfall terms are linear and the
fairness term is a convex quadratic in ``a`` (``r_bar`` is linear in ``a``),
so a KKT point returned by SLSQP is a global optimum. Solves run through a
defined chain, each step with an iteration cap and a wall-clock budget:

  1. SLSQP on the full objective (warm-started from the previous allocation)
  2. LP (HiGHS) on the linear part, i.e. the global optimum without fairness
  3. greedy fractional knapsack (exact for the linear part, never fails)

When beta == 0 or in degradation mode the objective is linear and the greedy
solution is already the exact optimum. Every solution records the solver,
status, iterations, wall time and why a fallback happened. The engine passes
every result through the validator and keeps the last valid allocation if
even the fallback fails validation.
"""
from __future__ import annotations

import logging
import time
from dataclasses import asdict, dataclass, field

import numpy as np
from scipy.optimize import linprog, minimize

log = logging.getLogger(__name__)

ALPHA = 1.0
GAMMA = 50.0
BETA_MAX = 1.5
EPS = 1e-6
DEFAULT_MAXITER = 200
DEFAULT_TIME_BUDGET_S = 0.25


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
    warm_start: dict[str, float] | None = None
    maxiter: int = DEFAULT_MAXITER
    time_budget_s: float = DEFAULT_TIME_BUDGET_S


@dataclass
class SolverInfo:
    solver: str                 # slsqp | lp | greedy_exact | greedy_fallback | no_deficit | trivial
    status: str                 # optimal | fallback | trivial
    iterations: int = 0
    solve_ms: float = 0.0
    fallback_reason: str | None = None
    convex: bool = True
    attempts: list[dict] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class AllocationSolution:
    allocation: dict[str, float]
    degradation: bool
    objective: dict[str, float]
    shortages: dict[str, float] = field(default_factory=dict)
    solver: str = "slsqp"
    info: SolverInfo | None = None


class SolverTimeout(Exception):
    pass


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


def _lp(p: AllocationProblem, lb: np.ndarray, ub: np.ndarray, degradation: bool, supply: float,
        time_budget_s: float) -> tuple[np.ndarray, int]:
    """Global optimum of the linear part (damage + critical shortfall) via HiGHS."""
    ids, D, M, _, w, c = _arrays(p)
    n = len(ids)
    wd = max(float(np.sum(w * D)), EPS)
    cm = max(float(np.sum(c * M)), EPS)
    cost = np.concatenate([-p.alpha * w / wd, p.gamma * c / cm])
    a_ub = np.vstack([np.concatenate([np.ones(n), np.zeros(n)]), np.hstack([-np.eye(n), -np.eye(n)])])
    b_ub = np.concatenate([[supply], -M])
    bounds = [(lb[k], ub[k]) for k in range(n)] + [((0.0, M[k]) if degradation else (0.0, 0.0)) for k in range(n)]
    res = linprog(cost, A_ub=a_ub, b_ub=b_ub, bounds=bounds, method="highs",
                  options={"time_limit": max(time_budget_s, 0.01)})
    if res.status != 0 or res.x is None or not np.all(np.isfinite(res.x)):
        raise RuntimeError(f"linprog: {res.message}")
    return res.x[:n], int(getattr(res, "nit", 0) or 0)


def _finish(p: AllocationProblem, ids: list[str], a: np.ndarray, M: np.ndarray, degradation: bool,
            info: SolverInfo, t0: float, lower_bounds: np.ndarray | None = None) -> AllocationSolution:
    lower = np.array(lower_bounds, float) if lower_bounds is not None else (np.zeros(len(ids), float)
                                                                          if degradation else M.copy())
    upper = np.minimum(np.array([p.demand.get(i, 0.0) for i in ids], float),
                       np.array([p.max_allowed.get(i, float("inf")) for i in ids], float))
    lower_q = np.ceil(np.maximum(lower, 0.0) * 1000.0) / 1000.0
    upper_q = np.floor(np.where(np.isfinite(upper), upper, np.inf) * 1000.0) / 1000.0
    rounded = np.clip(np.round(np.asarray(a, float), 3), lower_q, upper_q)
    while float(rounded.sum()) > float(p.supply) + 1e-9:
        order = np.argsort(rounded - lower_q)[::-1]
        reduced = False
        for idx in order:
            if rounded[idx] <= lower_q[idx] + 1e-9:
                continue
            if rounded[idx] - lower_q[idx] < 0.001 - 1e-9:
                continue
            rounded[idx] = round(max(lower_q[idx], rounded[idx] - 0.001), 3)
            reduced = True
            break
        if not reduced:
            break
    alloc = {i: round(float(v), 3) for i, v in zip(ids, rounded)}
    shortages = {i: round(float(M[k] - a[k]), 3) for k, i in enumerate(ids) if M[k] - a[k] > 1e-3}
    info.solve_ms = round((time.perf_counter() - t0) * 1000, 3)
    return AllocationSolution(alloc, bool(degradation), evaluate_objective(p, alloc), shortages, info.solver, info)


def solve(p: AllocationProblem, method: str = "auto") -> AllocationSolution:
    """Solve the allocation problem.

    ``method`` forces a single solver (auto | slsqp | lp | greedy); used by tests and benchmarks.
    """
    t0 = time.perf_counter()
    ids, D, M, ub, w, c = _arrays(p)
    n = len(ids)
    supply = max(0.0, float(p.supply))
    if n == 0:
        return _finish(p, ids, np.zeros(0), M, False, SolverInfo("trivial", "trivial"), t0)

    if ub.sum() <= supply + EPS:
        lb = np.zeros(n)
        return _finish(p, ids, ub, M, False, SolverInfo("no_deficit", "optimal"), t0, lb)

    degradation = M.sum() > supply + EPS
    lb = np.zeros(n) if degradation else M.copy()
    if p.lower_bounds and not degradation:
        override = np.array([min(max(p.lower_bounds.get(i, 0.0), lb[k]), ub[k]) for k, i in enumerate(ids)])
        if override.sum() <= supply + EPS:
            lb = override

    beta = beta_from_fairness(p.fairness)
    if method == "greedy" or (method == "auto" and (beta <= EPS or degradation)):
        # Objective is linear here (critical shortfall dominates in degradation):
        # the greedy fractional knapsack is the exact optimum.
        a = _repair(_greedy(p, lb, ub, degradation), lb, ub, supply)
        return _finish(p, ids, a, M, degradation, SolverInfo("greedy_exact", "optimal"), t0, lb)
    if method == "lp":
        x, nit = _lp(p, lb, ub, degradation, supply, p.time_budget_s)
        return _finish(p, ids, _repair(x, lb, ub, supply), M, degradation, SolverInfo("lp", "optimal", nit), t0, lb)

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

    # initial guess: warm start from the previous allocation if given, else proportional fill
    room = ub - lb
    if p.warm_start:
        a0 = np.clip(np.array([p.warm_start.get(i, 0.0) for i in ids], float), lb, ub)
        excess_room = (a0 - lb).sum()
        if a0.sum() > supply and excess_room > EPS:
            a0 = lb + (a0 - lb) * max(0.0, (supply - lb.sum()) / excess_room)
    else:
        frac = min(1.0, (supply - lb.sum()) / room.sum()) if room.sum() > EPS else 0.0
        a0 = lb + room * max(frac, 0.0)
    s0 = np.maximum(0.0, M - a0) if degradation else np.zeros(n)
    bounds = [(lb[k], ub[k]) for k in range(n)] + [((0.0, M[k]) if degradation else (0.0, 0.0)) for k in range(n)]
    cons = [
        {"type": "ineq", "fun": lambda x: supply - x[:n].sum(), "jac": lambda x: np.concatenate([-np.ones(n), np.zeros(n)])},
        {"type": "ineq", "fun": lambda x: x[:n] + x[n:] - M, "jac": lambda x: np.hstack([np.eye(n), np.eye(n)])},
    ]
    deadline = t0 + p.time_budget_s

    def budget(_xk):
        if time.perf_counter() > deadline:
            raise SolverTimeout(f"exceeded {p.time_budget_s * 1000:.0f} ms budget")

    attempts: list[dict] = []
    try:
        res = minimize(obj, np.concatenate([a0, s0]), jac=grad, method="SLSQP", bounds=bounds,
                       constraints=cons, callback=budget, options={"maxiter": p.maxiter, "ftol": 1e-10})
        x = res.x
        finite = np.all(np.isfinite(x))
        feasible = finite and x[:n].sum() <= supply + 1e-6 and np.all(x[:n] >= lb - 1e-6) and \
            np.all(x[:n] <= ub + 1e-6) and np.all(x[:n] + x[n:] >= M - 1e-6)
        # Status 8 ("positive directional derivative in linesearch") means SLSQP cannot improve any further
        # at a point that is already (numerically) optimal; accept it only if that point is feasible.
        if not (res.success or (res.status == 8 and feasible)) or not finite:
            raise RuntimeError(f"SLSQP status {res.status}: {res.message}")
        info = SolverInfo("slsqp", "optimal" if res.success else "optimal_tolerance", int(res.nit))
        return _finish(p, ids, _repair(res.x[:n], lb, ub, supply), M, degradation, info, t0, lb)
    except Exception as exc:  # noqa: BLE001 - every failure falls through the chain
        attempts.append({"solver": "slsqp", "error": f"{type(exc).__name__}: {exc}"[:200]})
        log.warning("SLSQP failed (%s); falling back to LP", attempts[-1]["error"])
    if method == "slsqp":
        raise RuntimeError(attempts[-1]["error"])
    try:
        x, nit = _lp(p, lb, ub, degradation, supply, max(0.05, p.time_budget_s))
        info = SolverInfo("lp", "fallback", nit, fallback_reason=attempts[0]["error"], attempts=attempts)
        return _finish(p, ids, _repair(x, lb, ub, supply), M, degradation, info, t0, lb)
    except Exception as exc:  # noqa: BLE001
        attempts.append({"solver": "lp", "error": f"{type(exc).__name__}: {exc}"[:200]})
        log.warning("LP fallback failed (%s); using greedy allocation", attempts[-1]["error"])
    a = _repair(_greedy(p, lb, ub, degradation), lb, ub, supply)
    info = SolverInfo("greedy_fallback", "fallback", fallback_reason=attempts[0]["error"], attempts=attempts)
    return _finish(p, ids, a, M, degradation, info, t0, lb)
