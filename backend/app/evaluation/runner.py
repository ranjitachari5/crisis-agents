"""Baseline comparison and ablations (F16).

Every variant runs the same scenario script, seeds and tick count in a fresh
headless engine. Results are measured, never hard-coded, and reported per
seed plus mean, standard deviation and a 95 % confidence interval
(Student t). The validator stays on in every variant.

Variants
  negotiation            the full system
  no_trust               ablation: trust engine off (messages accepted unverified)
  fallback_only          ablation: skip negotiation rounds, optimizer decides directly
  negotiation_only       ablation: no optimizer fallback when agents fail to converge
  centralized            single optimizer with full (metered) information
  hidden_information     single optimizer that only sees agents' *reported* demand
  rolling_horizon        optimizer that budgets battery energy over an 8-tick horizon
  fixed_priority, fcfs   static baselines

``adversarial=True`` makes one consumer over-report its demand by 50 %, which
is what the trust engine (and full information) is meant to withstand.
"""
from __future__ import annotations

import hashlib
import json
import math
import time

import numpy as np
from scipy import stats

from app.config import Settings
from app.schemas.messages import new_id
from app.simulation.engine import SimulationEngine

VERSION = "0.2.0"
VARIANTS: dict[str, tuple[str, dict[str, bool]]] = {
    "negotiation": ("negotiation", {}),
    "no_trust": ("negotiation", {"trust_engine": False}),
    "fallback_only": ("negotiation", {"fallback_only": True}),
    "negotiation_only": ("negotiation", {"negotiation_only": True}),
    "centralized": ("centralized", {}),
    "hidden_information": ("hidden_information", {}),
    "rolling_horizon": ("rolling_horizon", {}),
    "fixed_priority": ("fixed_priority", {}),
    "fcfs": ("fcfs", {}),
}
DEFAULT_MODES = ["fcfs", "fixed_priority", "centralized", "negotiation"]
ADVERSARIAL_AGENT = "telecom_agent"
ADVERSARIAL_INFLATION = 1.5
MAX_TICK_STEPS = 20_000   # seeds x variants x ticks budget per request

METRIC_DEFINITIONS = {
    "weighted_damage": "Σ over ticks of (damage_weight·unmet MW + critical_weight·MW below minimum)·hours",
    "critical_service_uptime_pct": "% of agent-ticks where allocation ≥ safe minimum",
    "unmet_demand_mwh": "Σ unmet demand × hours",
    "mean_fairness_penalty": "mean demand-weighted variance of satisfaction ratios",
    "constraint_violations": "validator violations of applied allocations (capacity, avoidable minimums, max)",
    "physical_load_shed_mwh": "energy shed because allocation exceeded real supply",
    "mean_negotiation_latency_ms": "wall-clock time to compute one negotiation (negotiation variants only)",
    "mean_recovery_time_min": "mean length of periods with any critical minimum unmet",
    "convergence_rate": "share of contested negotiations where agents converged without fallback",
    "fallback_rate": "share of contested negotiations decided by the deterministic optimizer fallback",
    "degraded_rate": "share of contested negotiations in emergency degradation mode",
}


def config_hash(config: dict) -> str:
    return hashlib.sha256(json.dumps(config, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def aggregate(values: list[float]) -> dict:
    vals = [float(v) for v in values if v is not None and not (isinstance(v, float) and math.isnan(v))]
    if not vals:
        return {"mean": None, "std": None, "ci95": None, "n": 0}
    n = len(vals)
    mean = float(np.mean(vals))
    std = float(np.std(vals, ddof=1)) if n > 1 else 0.0
    half = float(stats.t.ppf(0.975, n - 1) * std / math.sqrt(n)) if n > 1 else None
    return {"mean": round(mean, 4), "std": round(std, 4),
            "ci95": [round(mean - half, 4), round(mean + half, 4)] if half is not None else None, "n": n}


def run_variant(settings: Settings, variant: str, scenario: str, seed: int, ticks: int, fairness: float,
                adversarial: bool = False) -> dict:
    mode, features = VARIANTS[variant]
    e = SimulationEngine(settings, seed=seed, scenario=scenario, allocation_mode=mode, features=features)
    e.fairness = fairness
    if adversarial:
        e.registry.consumers[ADVERSARIAL_AGENT].inflation = ADVERSARIAL_INFLATION
    t0 = time.perf_counter()
    e.start()
    for _ in range(ticks):
        e.step()
    return {**e.metrics.summary(), "wall_time_s": round(time.perf_counter() - t0, 3),
            "messages_exchanged": len(e.messages) if mode == "negotiation" else 0,
            "outcomes": dict(e.metrics.outcomes)}


def run_evaluation(settings: Settings, scenario: str, seed: int | list[int], ticks: int, fairness: float,
                   modes: list[str] | None = None, adversarial: bool = False) -> dict:
    seeds = [seed] if isinstance(seed, int) else list(seed)
    modes = list(modes or DEFAULT_MODES)
    unknown = [m for m in modes if m not in VARIANTS]
    if unknown:
        raise ValueError(f"unknown evaluation variants {unknown}")
    if len(seeds) * len(modes) * ticks > MAX_TICK_STEPS:
        raise ValueError(f"evaluation too large: seeds x variants x ticks must be <= {MAX_TICK_STEPS}")
    config = {"version": VERSION, "scenario": scenario, "seeds": seeds, "ticks": ticks, "fairness": fairness,
              "modes": modes, "adversarial": adversarial, "minutes_per_tick": settings.sim_minutes_per_tick,
              "max_negotiation_rounds": settings.max_negotiation_rounds}
    t0 = time.perf_counter()
    results: dict[str, dict] = {}
    for mode in modes:
        per_seed = {s: run_variant(settings, mode, scenario, s, ticks, fairness, adversarial) for s in seeds}
        numeric = sorted({k for r in per_seed.values() for k, v in r.items()
                          if isinstance(v, (int, float)) and not isinstance(v, bool)})
        stats_ = {k: aggregate([r.get(k) for r in per_seed.values()]) for k in numeric}
        first = per_seed[seeds[0]]
        # Single-seed requests keep the flat shape (backwards compatible); multi-seed adds statistics.
        results[mode] = {**first, "per_seed": per_seed, "stats": stats_} if len(seeds) > 1 else first
    return {"run_id": new_id("eval"), "scenario": scenario, "seed": seeds[0], "seeds": seeds, "ticks": ticks,
            "fairness": fairness, "adversarial": adversarial, "minutes_per_tick": settings.sim_minutes_per_tick,
            "modes": modes, "results": results, "metric_definitions": METRIC_DEFINITIONS,
            "config": config, "config_hash": config_hash(config),
            "duration_s": round(time.perf_counter() - t0, 3)}
