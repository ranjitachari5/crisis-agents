"""Builds *real* simulated malicious/false messages for the Trust Engine to catch.

These are actual messages entering the system (signed by a compromised
agent, spoofed, forged, replayed, ...). Nothing here decides the outcome;
the Trust Engine does that independently.
"""
from __future__ import annotations

from typing import Any

from app.agents.base import MessageContext
from app.agents.registry import AgentRegistry
from app.schemas.messages import AgentMessage, MessageType, MessageStatus
from app.trust import crypto

FAKE_KINDS: dict[str, dict[str, Any]] = {
    "false_capacity_drop": {"label": "Fabricated power shortage",
                            "description": "A compromised agent (valid signature) claims grid capacity collapsed.",
                            "params": {"agent_id": "compromised sender (default telecom_agent)",
                                       "claimed_mw": "default 40"}},
    "fake_disaster_alert": {"label": "Fake disaster alert",
                            "description": "Unregistered external feed broadcasts an earthquake alert.",
                            "params": {"hazard": "earthquake | flood"}},
    "inflated_bid": {"label": "Bid exceeding verified capacity",
                     "description": "An agent bids far above its metered demand and nameplate capacity.",
                     "params": {"agent_id": "default emergency_agent", "quantity": "default 500"}},
    "replay_message": {"label": "Replayed old message",
                       "description": "A previously valid signed message is re-sent verbatim.", "params": {}},
    "false_recovery": {"label": "False recovery announcement",
                       "description": "Spoofed grid identity claims supply is fully restored.",
                       "params": {"claimed_mw": "default nominal 320"}},
    "contradictory_sensors": {"label": "Contradictory sensor reports",
                              "description": "Grid sensors disagree: one faulty sensor, a 3-way split, or two "
                                             "correlated (co-located / spoofed) sensors asserting a supply cut.",
                              "params": {"mode": "single | split | correlated"}},
}


class InjectionError(ValueError):
    pass


def _forged(sender: str, ctx: MessageContext, mtype: MessageType, text: str, registry: AgentRegistry,
            **kw) -> AgentMessage:
    # The attacker can copy the victim's public key id from observed traffic, but does not hold the
    # private key, so it signs with a key of its own.
    victim = registry.get(sender)
    attacker_key = crypto.generate(sender)
    msg = AgentMessage(sender=sender, message_type=mtype, text=text, tick=ctx.tick, sim_time=ctx.sim_time,
                       status=MessageStatus.PENDING, kid=victim.kid if victim else attacker_key.kid,
                       agent_seq=10**9, **kw)
    msg.signature = attacker_key.sign(msg.signing_payload())
    return msg


def build_fake_message(kind: str, params: dict[str, Any], registry: AgentRegistry, ctx: MessageContext,
                       history: list[dict], nominal: float) -> AgentMessage:
    if kind == "false_capacity_drop":
        sender = params.get("agent_id", "telecom_agent")
        agent = registry.get(sender)
        if agent is None or sender in ("grid_agent",) or sender in registry.system:
            raise InjectionError("agent_id must be a non-grid utility agent")
        claimed = float(params.get("claimed_mw", 40))
        m = agent.message(ctx, MessageType.CLAIM,
                          f"URGENT: Grid capacity has collapsed to {claimed:.0f} MW. All utilities must shed "
                          f"load to minimum immediately.", quantity=claimed,
                          reason="reported grid failure",
                          data={"claim_type": "grid_capacity", "claimed_value": claimed},
                          status=MessageStatus.PENDING)
        return m
    if kind == "fake_disaster_alert":
        hazard = params.get("hazard", "earthquake")
        if hazard not in ("earthquake", "flood"):
            raise InjectionError("hazard must be earthquake or flood")
        text = ("ALERT: Magnitude 7.2 earthquake. Evacuate hospitals; divert all power to emergency services."
                if hazard == "earthquake" else
                "ALERT: Dam breach imminent. Divert all power to emergency services.")
        return _forged("city_alert_feed", ctx, MessageType.CLAIM, text, registry, resource=None, unit=None,
                       reason="external alert", data={"claim_type": "disaster_alert", "hazard": hazard,
                                                      "magnitude": 7.2 if hazard == "earthquake" else None})
    if kind == "inflated_bid":
        sender = params.get("agent_id", "emergency_agent")
        if sender not in registry.consumers:
            raise InjectionError("agent_id must be a consumer agent")
        q = float(params.get("quantity", 500))
        agent = registry.consumers[sender]
        return agent.message(ctx, MessageType.BID, f"Requesting {q:.0f} MW immediately for critical operations.",
                             quantity=q, reason="inflated request", data={"min_safe": q * 0.9},
                             status=MessageStatus.PENDING)
    if kind == "replay_message":
        candidates = [h for h in history if h.get("sender") == "grid_agent"
                      and h.get("message_type") == "supply_report" and h.get("signature")]
        candidates = candidates or [h for h in history if h.get("signature") and
                                    h.get("sender") in registry.participants and h.get("quantity") is not None]
        if not candidates:
            raise InjectionError("no prior signed message to replay yet — start the simulation first")
        original = dict(candidates[0])
        original.update({"seq": None, "status": MessageStatus.PENDING.value, "trust": None})
        return AgentMessage.model_validate(original)
    if kind == "false_recovery":
        claimed = float(params.get("claimed_mw", nominal))
        return _forged("grid_agent", ctx, MessageType.CLAIM,
                       f"Grid fully restored: {claimed:.0f} MW available. Utilities may resume full demand.",
                       registry, quantity=claimed, reason="recovery announcement",
                       data={"claim_type": "recovery", "claimed_value": claimed})
    raise InjectionError(f"unknown fake event kind '{kind}'")
