"""F8 run scoping, F9 optimizer optimality, F10 outcome metrics, F11 approval timeout, F15 determinism,
F16 evaluation statistics."""
import random
import threading
import time

import numpy as np
from fastapi.testclient import TestClient

from app.evaluation.runner import run_evaluation
from app.main import create_app
from app.negotiation.agreements import ProposalStatus
from app.optimization.allocator import AllocationProblem, evaluate_objective, solve
from app.simulation.engine import SimulationEngine

AUTH = {"Authorization": "Bearer test-token"}
IDS = ["hospital_agent", "water_agent", "telecom_agent", "emergency_agent"]


def history(e):
    return [(a.version, a.method, a.outcome, sorted(a.allocation.items())) for a in e.agreements.history]


def run(settings, seed, ticks=12, scenario="flood_cascade"):
    e = SimulationEngine(settings, seed=seed, scenario=scenario)
    e.start()
    for _ in range(ticks):
        e.step()
    return e


# ------------------------------------------------------------------ F15
def test_same_seed_gives_identical_allocation_history(settings):
    assert history(run(settings, 5)) == history(run(settings, 5))


def test_rng_streams_are_independent(settings):
    e = SimulationEngine(settings, seed=5)
    a = e.rngs["telemetry"].random()
    e2 = SimulationEngine(settings, seed=5)
    e2.rngs["fcfs"].random(100)  # consuming one stream must not shift another
    assert e2.rngs["telemetry"].random() == a


# ------------------------------------------------------------------ F8
def test_concurrent_runs_match_solo_runs(settings):
    solo = {s: history(run(settings, s)) for s in (3, 4)}
    out = {}
    threads = [threading.Thread(target=lambda s=s: out.__setitem__(s, history(run(settings, s)))) for s in (3, 4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert out == solo


def test_run_scoped_api(settings):
    with TestClient(create_app(settings), headers=AUTH) as c:
        rid = c.post("/api/runs", json={"seed": 9, "scenario": "flood_cascade"}).json()["run_id"]
        assert c.post(f"/api/runs/{rid}/simulation/start").status_code == 200
        assert c.get(f"/api/runs/{rid}/simulation/state").json()["status"] == "running"
        assert c.get("/api/simulation/state").json()["status"] == "idle"  # default run untouched
        assert {r["run_id"] for r in c.get("/api/runs").json()} == {"default", rid}
        assert c.get("/api/runs/nope-123/simulation/state").status_code == 404
        assert c.delete(f"/api/runs/{rid}").json()["deleted"]
        assert c.get(f"/api/runs/{rid}/simulation/state").status_code == 404
        assert c.delete("/api/runs/default").status_code == 409


def test_run_limit(settings):
    import dataclasses
    with TestClient(create_app(dataclasses.replace(settings, max_runs=2)), headers=AUTH) as c:
        assert c.post("/api/runs", json={}).status_code == 200
        assert c.post("/api/runs", json={}).status_code == 429


# ------------------------------------------------------------------ F9
def random_problem(rng, fairness):
    demand = {i: rng.uniform(30, 120) for i in IDS}
    mins = {i: demand[i] * rng.uniform(0.3, 0.8) for i in IDS}
    return AllocationProblem(IDS, demand, mins, {i: demand[i] * 1.2 for i in IDS},
                             {i: rng.uniform(5, 12) for i in IDS}, {i: rng.uniform(60, 110) for i in IDS},
                             rng.uniform(sum(mins.values()) * 1.01, sum(demand.values()) * 0.98), fairness)


def test_slsqp_is_globally_optimal_vs_lp_on_random_instances():
    rng = random.Random(7)
    fallbacks, gaps = 0, []
    for _ in range(300):
        p = random_problem(rng, rng.uniform(0.05, 1.0))
        s, lp = solve(p), solve(p, method="lp")
        fallbacks += s.info.status == "fallback"
        # the LP point is feasible for the full problem, so SLSQP (convex QP) can never be worse
        gaps.append(evaluate_objective(p, s.allocation)["total"] - evaluate_objective(p, lp.allocation)["total"])
    assert max(gaps) <= 1e-4 and fallbacks / 300 < 0.02


def test_linear_case_greedy_matches_lp():
    rng = random.Random(3)
    for _ in range(200):
        p = random_problem(rng, 0.0)
        g, lp = solve(p), solve(p, method="lp")
        assert abs(evaluate_objective(p, g.allocation)["total"] - evaluate_objective(p, lp.allocation)["total"]) < 1e-4


def test_timeout_falls_through_chain_and_records_reason():
    p = random_problem(random.Random(1), 0.7)
    p.time_budget_s = 0.0
    s = solve(p)
    assert s.info.solver in ("lp", "greedy_fallback") and "SolverTimeout" in s.info.fallback_reason
    assert sum(s.allocation.values()) <= p.supply + 1e-6


# ------------------------------------------------------------------ F10
def test_outcome_metrics_recorded(settings):
    e = run(settings, 2, ticks=24)
    rates = e.metrics.outcome_rates()
    assert rates["negotiations"] == len(e.negotiations) and sum(rates["outcomes"].values()) == rates["negotiations"]
    assert all(a.outcome for a in e.agreements.history)
    summary = e.metrics.summary()
    assert "convergence_rate" in summary and "fallback_rate" in summary


def test_prometheus_endpoint(settings):
    with TestClient(create_app(settings), headers=AUTH) as c:
        c.post("/api/simulation/start")
        body = c.get("/metrics").text
        assert 'crisis_negotiations_total{outcome=' in body and "crisis_negotiation_rounds_bucket" in body


# ------------------------------------------------------------------ F11
def test_unattended_proposal_expires_and_policy_is_audited(engine):
    engine.set_approval_mode("manual", timeout_s=2, policy="keep_last")
    engine.set_fairness(0.95)
    p = engine.agreements.awaiting_approval()[-1]
    v = engine.agreements.version
    assert engine.expire_pending(time.monotonic() + 1) == []
    out = engine.expire_pending(time.monotonic() + 3)
    assert out and p.status == ProposalStatus.EXPIRED and engine.agreements.version == v
    entry = next(a for a in reversed(engine.audit_log) if a["action"] == "proposal_expired")
    assert entry["details"]["policy"] == "keep_last"


def test_expiry_commit_policy_and_supersession(engine):
    engine.set_approval_mode("manual", timeout_s=2, policy="commit")
    engine.set_fairness(0.95)
    first = engine.agreements.awaiting_approval()[-1]
    engine.set_fairness(0.2)
    second = engine.agreements.awaiting_approval()[-1]
    assert first.status == ProposalStatus.SUPERSEDED and second is not first
    v = engine.agreements.version
    engine.expire_pending(time.monotonic() + 3)
    assert second.status == ProposalStatus.COMMITTED and engine.agreements.version == v + 1


# ------------------------------------------------------------------ F16
def test_multi_seed_evaluation_with_ablations(settings):
    res = run_evaluation(settings, "flood_cascade", [1, 2, 3], 10, 0.5,
                         ["negotiation", "no_trust", "fallback_only", "centralized"], adversarial=True)
    assert len(res["config_hash"]) == 64
    for mode, r in res["results"].items():
        st = r["stats"]["weighted_damage"]
        assert st["n"] == 3 and st["ci95"][0] <= st["mean"] <= st["ci95"][1]
        assert r["constraint_violations"] >= 0
    assert res["results"]["fallback_only"]["fallback_rate"] is not None
    again = run_evaluation(settings, "flood_cascade", [1, 2, 3], 10, 0.5,
                           ["negotiation", "no_trust", "fallback_only", "centralized"], adversarial=True)
    assert again["config_hash"] == res["config_hash"]
    assert np.isclose(again["results"]["negotiation"]["stats"]["weighted_damage"]["mean"],
                      res["results"]["negotiation"]["stats"]["weighted_damage"]["mean"])
