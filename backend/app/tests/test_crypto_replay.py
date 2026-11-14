"""F3/F4: Ed25519 signatures, key revocation/rotation, durable replay protection, sequence numbers,
plus a mutation fuzz of the trust engine (F17)."""
import random
from datetime import timedelta

import pytest

from app.database.repository import Repository
from app.schemas.messages import AgentMessage, MessageType
from app.trust.engine import TrustDecision, TrustEngine


def bid(engine, agent="water_agent", qty=None):
    ag = engine.registry.consumers[agent]
    q = qty if qty is not None else engine.telemetry.consumer_meters[agent]
    return ag.message(engine.ctx(), MessageType.BID, "bid", quantity=q)


def verdict(engine, msg):
    return engine.trust.verify(msg, engine.trust_ctx())


def test_trust_engine_holds_only_public_keys(engine):
    assert not hasattr(engine.trust, "keyring")
    for kid_map in engine.registry.public_keys._keys.values():
        for pk in kid_map.values():
            assert not hasattr(pk, "sign")


@pytest.mark.parametrize("field,value", [
    ("quantity", 1.0), ("reason", "tampered"), ("text", "tampered"), ("receiver", "grid_agent"),
    ("tick", 999), ("agent_seq", 10**6), ("data", {"x": 1}), ("message_type", MessageType.OFFER),
])
def test_tampering_any_signed_field_rejects(engine, field, value):
    msg = bid(engine)
    setattr(msg, field, value)
    res = verdict(engine, msg)
    assert res.decision == TrustDecision.REJECTED
    assert not next(e for e in res.evidence if e.check == "source_authentication").passed


def test_swapping_sender_rejects(engine):
    msg = bid(engine)
    msg.sender = "hospital_agent"
    assert verdict(engine, msg).decision == TrustDecision.REJECTED


def test_revoked_key_rejects_and_rotation_restores(engine):
    old = bid(engine)
    engine.isolate("water_agent", "test")
    assert engine.registry.public_keys.active_kids("water_agent") == []
    engine.isolate("water_agent", "restored", isolate=False)
    res = verdict(engine, old)  # signed with the revoked key
    assert res.decision == TrustDecision.REJECTED
    assert "revoked" in next(e for e in res.evidence if e.check == "source_authentication").detail
    assert verdict(engine, bid(engine)).decision == TrustDecision.ACCEPTED


def test_sequence_regression_rejected(engine):
    first, second = bid(engine), bid(engine)
    assert verdict(engine, second).accepted
    res = verdict(engine, first)  # older sequence number, never seen id
    assert res.decision == TrustDecision.REJECTED
    assert not next(e for e in res.evidence if e.check == "sequence_monotonic").passed


def test_stale_wallclock_timestamp_rejected(engine):
    msg = bid(engine)
    msg.timestamp = msg.timestamp - timedelta(hours=1)
    msg.signature = engine.registry.consumers["water_agent"]._key.sign(msg.signing_payload())
    res = verdict(engine, msg)
    assert res.decision == TrustDecision.REJECTED
    assert not next(e for e in res.evidence if e.check == "wallclock_freshness").passed


def test_replay_rejected_after_restart(engine, tmp_path):
    repo = Repository(f"sqlite:///{(tmp_path / 'replay.db').as_posix()}")
    msg = bid(engine)
    t1 = TrustEngine(engine.registry.public_keys, replay_store=repo.record_message_id)
    assert t1.verify(msg, engine.trust_ctx()).accepted
    # "restart": a fresh trust engine with an empty in-memory cache, same durable store
    t2 = TrustEngine(engine.registry.public_keys, replay_store=repo.record_message_id)
    res = t2.verify(AgentMessage.model_validate(msg.model_dump()), engine.trust_ctx())
    assert res.decision == TrustDecision.REJECTED
    assert not next(e for e in res.evidence if e.check == "unique_message_id").passed


def test_mutation_fuzz_never_accepts_tampered_messages(engine):
    rng = random.Random(1234)
    base = bid(engine).model_dump()
    fields = [k for k in base if k not in ("seq", "status", "signature", "trust")]
    for _ in range(200):
        d = dict(base)
        op = rng.choice(["swap", "truncate_sig", "huge", "dup", "drop_sig", "flip"])
        if op == "swap":
            a, b = rng.sample(fields, 2)
            d[a], d[b] = d[b], d[a]
        elif op == "truncate_sig":
            d["signature"] = (d["signature"] or "")[: rng.randint(0, 100)]
        elif op == "huge":
            d["text"] = "x" * rng.randint(2001, 50000)
        elif op == "drop_sig":
            d["signature"] = None
        elif op == "flip":
            d["quantity"] = (d["quantity"] or 0) + rng.uniform(0.01, 50)
        if op != "dup" and d == base:
            continue  # the mutation was a no-op (e.g. swapped two equal fields)
        try:
            msg = AgentMessage.model_validate(d)
        except Exception:
            continue  # schema rejects it before it can reach the trust engine
        if op == "dup":
            verdict(engine, AgentMessage.model_validate(base))
        assert not verdict(engine, msg).accepted, op
