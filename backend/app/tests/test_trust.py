import pytest

from app.schemas.messages import MessageType


@pytest.mark.parametrize("kind,expected", [
    ("false_capacity_drop", "quarantined"),
    ("fake_disaster_alert", "rejected"),
    ("inflated_bid", "quarantined"),
    ("replay_message", "rejected"),
    ("false_recovery", "rejected"),
])
def test_fake_events_caught_and_allocation_unchanged(engine, kind, expected):
    before = dict(engine.agreements.current.allocation)
    inc = engine.inject_fake(kind, {})
    assert inc["decision"] == expected
    assert inc["quarantined"] and inc["allocation_changed"] is False
    assert engine.agreements.current.allocation == before
    assert inc["evidence"] and inc["agent_responses"]
    assert any(a["category"] == "trust" for a in engine.audit_log)


def test_single_faulty_sensor_excluded(engine):
    inc = engine.inject_fake("contradictory_sensors", {"mode": "single"})
    assert inc["decision"] == "accepted" and not engine.frozen
    assert engine.grid_assessment.verified_supply > 190


def test_split_sensors_escalate_and_freeze_until_commander(engine):
    v = engine.agreements.version
    inc = engine.inject_fake("contradictory_sensors", {"mode": "split"})
    assert inc["decision"] == "escalated" and engine.frozen
    engine.step()
    assert engine.agreements.version == v  # no allocation change while supply is unverified
    res = engine.resolve_incident(inc["incident_id"], "dismiss", "sensors recalibrated", None)
    assert res["resolved"] and not engine.frozen


def test_compromised_agent_loses_reputation(engine):
    engine.inject_fake("false_capacity_drop", {"agent_id": "telecom_agent"})
    assert engine.trust.reputation["telecom_agent"] < 1.0


def test_replay_does_not_penalise_original_sender(engine):
    engine.inject_fake("replay_message", {})
    assert engine.trust.reputation["grid_agent"] >= 0.99


def test_isolated_agent_messages_rejected(engine):
    engine.isolate("emergency_agent", "test")
    msg = engine.registry.consumers["emergency_agent"].message(engine.ctx(), MessageType.BID, "bid", quantity=60)
    assert engine.submit(msg) is False
