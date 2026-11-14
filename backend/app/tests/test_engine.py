import pytest

from app.evaluation.runner import run_evaluation
from app.simulation.engine import EngineError, SimulationEngine


def test_steps_advance_time_and_deplete_battery(engine):
    soc0 = engine.city.battery.soc
    for _ in range(4):
        engine.step()
    assert engine.city.tick == 4
    assert engine.city.battery.soc < soc0
    assert engine.metrics.summary()["constraint_violations"] == 0


def test_events_change_state_and_cascade(engine):
    engine.inject_event("hospital_demand_spike", {"additional_mw": 20})
    assert engine.city.consumers["hospital_agent"].effective_demand == 120
    engine.inject_event("water_pump_failure", {"capacity_fraction": 0.3})
    assert any(c["root"] == "water_agent" for c in engine.snapshot()["cascades"])
    engine.inject_event("recovery", {"scope": "full"})
    assert engine.city.grid.available == engine.city.grid.nominal_capacity
    assert engine.agreements.current.method == "uncontested"


def test_deterministic_for_same_seed(settings):
    runs = []
    for _ in range(2):
        e = SimulationEngine(settings, seed=11, scenario="flood_cascade")
        e.start()
        for _ in range(10):
            e.step()
        runs.append(e.metrics.summary()["weighted_damage"])
    assert runs[0] == runs[1]


def test_manual_approval_and_override(engine):
    engine.set_approval_mode("manual")
    engine.set_fairness(0.95)  # current allocation stays feasible -> new proposal waits for approval
    pending = engine.agreements.pending()
    assert pending
    v = engine.agreements.version
    engine.approve_proposal(pending[-1].proposal_id)
    assert engine.agreements.version == v + 1
    res = engine.override(dict(engine.agreements.current.allocation), "commander test override")
    assert res["committed"] and engine.agreements.current.method == "commander_override"


def test_unsafe_current_allocation_is_not_held_for_approval(engine):
    engine.set_approval_mode("manual")
    engine.inject_event("hospital_demand_spike", {"additional_mw": 10})  # raises ICU minimum
    assert engine.agreements.current.allocation["hospital_agent"] >= engine.city.consumers["hospital_agent"].effective_min


def test_override_cannot_break_safety(engine):
    with pytest.raises(EngineError):
        engine.override({"hospital_agent": 130, "water_agent": 90, "telecom_agent": 60, "emergency_agent": 80},
                        "exceeds supply")


def test_evaluation_runs_all_modes(settings):
    res = run_evaluation(settings, "flood_cascade", 3, 12, 0.5)
    assert set(res["results"]) == {"negotiation", "centralized", "fixed_priority", "fcfs"}
    for r in res["results"].values():
        assert r["ticks"] == 12
    assert res["results"]["negotiation"]["constraint_violations"] == 0
    assert res["results"]["negotiation"]["mean_negotiation_latency_ms"] is not None
