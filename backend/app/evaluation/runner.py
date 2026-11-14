"""Baseline comparison: identical scenario, seed and ticks for every mode.

Results are measured from the simulation; nothing is hard-coded.
"""
from __future__ import annotations

import time

from app.config import Settings
from app.schemas.messages import new_id
from app.simulation.engine import ALLOCATION_MODES, SimulationEngine

METRIC_DEFINITIONS = {
    "weighted_damage": "Σ over ticks of (damage_weight·unmet MW + critical_weight·MW below minimum)·hours",
    "critical_service_uptime_pct": "% of agent-ticks where allocation ≥ safe minimum",
    "unmet_demand_mwh": "Σ unmet demand × hours",
    "mean_fairness_penalty": "mean demand-weighted variance of satisfaction ratios",
    "constraint_violations": "validator violations of applied allocations (capacity, avoidable minimums, max)",
    "physical_load_shed_mwh": "energy shed because allocation exceeded real supply",
    "mean_negotiation_latency_ms": "wall-clock time to compute one negotiation (negotiation mode only)",
    "mean_recovery_time_min": "mean length of periods with any critical minimum unmet",
}


def run_evaluation(settings: Settings, scenario: str, seed: int, ticks: int, fairness: float,
                   modes: list[str] | None = None) -> dict:
    modes = modes or list(ALLOCATION_MODES)
    results = {}
    t0 = time.perf_counter()
    for mode in modes:
        e = SimulationEngine(settings, seed=seed, scenario=scenario, allocation_mode=mode)
        e.fairness = fairness
        m0 = time.perf_counter()
        e.start()
        for _ in range(ticks):
            e.step()
        results[mode] = {**e.metrics.summary(), "wall_time_s": round(time.perf_counter() - m0, 3),
                         "messages_exchanged": len(e.messages) if mode == "negotiation" else 0}
    return {"run_id": new_id("eval"), "scenario": scenario, "seed": seed, "ticks": ticks, "fairness": fairness,
            "minutes_per_tick": settings.sim_minutes_per_tick, "modes": modes, "results": results,
            "metric_definitions": METRIC_DEFINITIONS, "duration_s": round(time.perf_counter() - t0, 3)}
