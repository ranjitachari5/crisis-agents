"""Per-tick performance metrics (measured, never invented)."""
from __future__ import annotations

from collections import Counter
from dataclasses import asdict, dataclass, field

import numpy as np


@dataclass
class TickMetrics:
    tick: int
    weighted_damage: float          # sum(w * unmet + c * below-min) * hours
    unmet_mwh: float
    critical_met: int
    critical_total: int
    fairness_penalty: float
    constraint_violations: int
    shed_mw: float                  # physical load shedding (allocation exceeded real supply)
    degradation: bool
    supply_mw: float
    demand_mw: float
    allocated_mw: float


@dataclass
class MetricsTracker:
    dt_hours: float
    ticks: list[TickMetrics] = field(default_factory=list)
    negotiation_latency_ms: list[float] = field(default_factory=list)
    negotiation_rounds: list[int] = field(default_factory=list)
    negotiation_messages: list[int] = field(default_factory=list)
    outcomes: Counter = field(default_factory=Counter)        # uncontested | converged | fallback | degraded | ...
    commit_outcomes: Counter = field(default_factory=Counter)
    solvers: Counter = field(default_factory=Counter)

    def record(self, tick: int, allocation: dict[str, float], demand: dict[str, float],
               mins: dict[str, float], w: dict[str, float], c: dict[str, float], supply: float,
               violations: int, shed: float, degradation: bool) -> TickMetrics:
        ids = list(demand)
        unmet = {i: max(0.0, demand[i] - allocation.get(i, 0.0)) for i in ids}
        below = {i: max(0.0, mins[i] - allocation.get(i, 0.0)) for i in ids}
        dmg = sum(w[i] * unmet[i] + c[i] * below[i] for i in ids) * self.dt_hours
        D = np.array([demand[i] for i in ids])
        r = np.array([allocation.get(i, 0.0) / demand[i] if demand[i] > 1e-6 else 1.0 for i in ids])
        p = D / max(D.sum(), 1e-6)
        rbar = float((p * r).sum())
        fair = float((p * (r - rbar) ** 2).sum())
        tm = TickMetrics(tick, round(dmg, 4), round(sum(unmet.values()) * self.dt_hours, 4),
                         sum(1 for i in ids if below[i] <= 1e-3), len(ids), round(fair, 6), violations,
                         round(shed, 3), degradation, round(supply, 3), round(sum(demand.values()), 3),
                         round(sum(allocation.get(i, 0.0) for i in ids), 3))
        self.ticks.append(tm)
        self.ticks = self.ticks[-5000:]
        return tm

    def record_negotiation(self, latency_ms: float, rounds: int, outcome: str = "converged", messages: int = 0,
                           solver: str | None = None) -> None:
        self.negotiation_latency_ms.append(latency_ms)
        self.negotiation_rounds.append(rounds)
        self.negotiation_messages.append(messages)
        self.outcomes[outcome] += 1
        if solver:
            self.solvers[solver] += 1

    def record_commit(self, outcome: str) -> None:
        self.commit_outcomes[outcome or "unknown"] += 1

    def outcome_rates(self) -> dict:
        """Share of negotiations decided by the agents vs the deterministic fallback (F10)."""
        n = sum(self.outcomes.values())
        contested = n - self.outcomes.get("uncontested", 0)
        rate = (lambda k: round(self.outcomes.get(k, 0) / contested, 4) if contested else None)
        return {"negotiations": n, "contested": contested, "outcomes": dict(self.outcomes),
                "convergence_rate": rate("converged"), "fallback_rate": rate("fallback"),
                "degraded_rate": rate("degraded"), "unconverged_rate": rate("unconverged"),
                "commit_outcomes": dict(self.commit_outcomes), "solvers": dict(self.solvers)}

    def recovery_episodes(self) -> list[int]:
        """Lengths (in ticks) of contiguous periods where any critical minimum was unmet."""
        eps, run = [], 0
        for t in self.ticks:
            if t.critical_met < t.critical_total:
                run += 1
            elif run:
                eps.append(run)
                run = 0
        if run:
            eps.append(run)
        return eps

    def summary(self) -> dict:
        n = len(self.ticks)
        if n == 0:
            return {"ticks": 0}
        crit_met = sum(t.critical_met for t in self.ticks)
        crit_total = sum(t.critical_total for t in self.ticks)
        eps = self.recovery_episodes()
        minutes = self.dt_hours * 60
        return {
            "ticks": n,
            "weighted_damage": round(sum(t.weighted_damage for t in self.ticks), 3),
            "critical_service_uptime_pct": round(100 * crit_met / max(crit_total, 1), 2),
            "unmet_demand_mwh": round(sum(t.unmet_mwh for t in self.ticks), 3),
            "mean_fairness_penalty": round(float(np.mean([t.fairness_penalty for t in self.ticks])), 6),
            "constraint_violations": int(sum(t.constraint_violations for t in self.ticks)),
            "physical_load_shed_mwh": round(sum(t.shed_mw for t in self.ticks) * self.dt_hours, 3),
            "degradation_ticks": sum(1 for t in self.ticks if t.degradation),
            "negotiations": len(self.negotiation_latency_ms),
            "mean_negotiation_latency_ms": (round(float(np.mean(self.negotiation_latency_ms)), 3)
                                            if self.negotiation_latency_ms else None),
            "mean_negotiation_rounds": (round(float(np.mean(self.negotiation_rounds)), 3)
                                        if self.negotiation_rounds else None),
            "mean_negotiation_messages": (round(float(np.mean(self.negotiation_messages)), 2)
                                          if self.negotiation_messages else None),
            "shortfall_episodes": len(eps),
            "mean_recovery_time_min": round(float(np.mean(eps)) * minutes, 1) if eps else 0.0,
            **{k: v for k, v in self.outcome_rates().items() if k.endswith("_rate")},
        }

    def series(self, last: int = 96) -> list[dict]:
        return [asdict(t) for t in self.ticks[-last:]]
