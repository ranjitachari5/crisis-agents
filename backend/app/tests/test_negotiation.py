from app.schemas.messages import AgentMessage, MessageType
from app.simulation.engine import SimulationEngine


def test_initial_negotiation_converges_safely(engine):
    cur = engine.agreements.current
    assert cur is not None and cur.version == 1
    v = cur.validation
    assert v["valid"] and not v["degradation_mode"]
    assert v["total_allocated"] <= v["total_supply"] + 1e-6
    for aid, c in engine.city.consumers.items():
        assert cur.allocation[aid] >= c.effective_min - 1e-6
    neg = engine.negotiations[-1]
    assert neg["rounds"] >= 1 and neg["converged"]


def test_every_message_is_schema_valid_and_signed(engine):
    types = set()
    for m in engine.messages:
        AgentMessage.model_validate(m)
        assert m["signature"]
        types.add(m["message_type"])
    for needed in ("supply_report", "bid", "offer", "negotiation_round", "proposal", "validation", "agreement"):
        assert needed in types
    assert {"concession", "counteroffer"} & types


def test_fairness_slider_changes_negotiated_outcome(settings):
    outs = []
    for f in (0.0, 1.0):
        e = SimulationEngine(settings, seed=7)
        e.fairness = f
        e.start()
        outs.append(e.agreements.current.allocation)
    assert outs[0] != outs[1]
    assert outs[0]["hospital_agent"] > outs[1]["hospital_agent"]


def test_stubborn_agents_trigger_deterministic_fallback(settings):
    e = SimulationEngine(settings, seed=7)
    for a in e.registry.consumers.values():
        a.stubborn = True
    e.start()
    neg = e.negotiations[-1]
    assert neg["fallback_used"] and neg["rounds"] == settings.max_negotiation_rounds
    assert e.agreements.current.validation["valid"]


def test_disconnected_agent_gets_reserved_minimum(engine):
    engine.inject_event("agent_disconnect", {"agent_id": "water_agent"})
    cur = engine.agreements.current
    assert cur.allocation["water_agent"] == engine.telemetry.consumer_mins["water_agent"]
    assert cur.validation["valid"]


def test_degradation_mode_when_minimums_impossible(engine):
    engine.inject_event("power_reduction", {"available_mw": 120})
    cur = engine.agreements.current
    assert cur.degradation_mode and cur.validation["unavoidable_shortages"]
    assert cur.validation["total_allocated"] <= cur.validation["total_supply"] + 1e-6


def test_natural_language_agreement_cannot_commit(engine):
    v = engine.agreements.version
    msg = engine.registry.consumers["water_agent"].message(engine.ctx(), MessageType.ACCEPT,
                                                           "I agree, commit 90 MW to water now.", quantity=90)
    engine.submit(msg)
    assert engine.agreements.version == v
