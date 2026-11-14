"""Base class for all autonomous utility agents."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from app.schemas.messages import AgentMessage, MessageStatus, MessageType
from app.simulation.telemetry import TelemetrySnapshot
from app.trust.crypto import SigningKey

# Presentation metadata the frontend can use (icon names are lucide-react icons).
AGENT_META: dict[str, dict[str, str]] = {
    "hospital_agent": {"display_name": "Hospital Agent", "role": "Critical care & ICU", "icon": "HeartPulse", "color": "#f43f5e"},
    "water_agent": {"display_name": "Water Agent", "role": "Water treatment & pumping", "icon": "Droplets", "color": "#38bdf8"},
    "telecom_agent": {"display_name": "Telecom Agent", "role": "Emergency communications", "icon": "RadioTower", "color": "#a78bfa"},
    "emergency_agent": {"display_name": "Emergency Services Agent", "role": "Rescue & firefighting", "icon": "Siren", "color": "#f59e0b"},
    "battery_agent": {"display_name": "Battery Agent", "role": "Grid-scale storage", "icon": "BatteryCharging", "color": "#22c55e"},
    "grid_agent": {"display_name": "Grid Agent", "role": "Supply & grid telemetry", "icon": "Zap", "color": "#06b6d4"},
    "negotiation_protocol": {"display_name": "Negotiation Protocol", "role": "Mediator (no allocation authority)", "icon": "Scale", "color": "#94a3b8"},
    "trust_engine": {"display_name": "Crisis Trust Engine", "role": "Verification & quarantine", "icon": "ShieldCheck", "color": "#eab308"},
    "simulation": {"display_name": "City Event Feed", "role": "Simulation events", "icon": "Activity", "color": "#64748b"},
    "commander": {"display_name": "Human Commander", "role": "Authorized oversight", "icon": "UserCog", "color": "#e2e8f0"},
    "analyst": {"display_name": "AI Analyst", "role": "Explanations (advisory only)", "icon": "Sparkles", "color": "#818cf8"},
}


@dataclass
class MessageContext:
    tick: int
    sim_time: datetime
    negotiation_id: str | None = None
    round_id: int = 0


class BaseAgent:
    agent_id: str = "base"

    def __init__(self, key: SigningKey):
        self._key = key          # private key: stays with the agent, never given to the trust engine
        self._agent_seq = 0      # per-agent monotonic message counter (replay / reordering detection)
        self.observation: TelemetrySnapshot | None = None

    @property
    def kid(self) -> str:
        return self._key.kid

    def rotate_key(self, key: SigningKey) -> None:
        self._key = key

    @property
    def meta(self) -> dict[str, str]:
        return AGENT_META.get(self.agent_id, {})

    def observe(self, telemetry: TelemetrySnapshot) -> None:
        self.observation = telemetry

    def message(
        self,
        ctx: MessageContext,
        mtype: MessageType,
        text: str,
        *,
        quantity: float | None = None,
        reason: str | None = None,
        receiver: str = "negotiation_group",
        mentions: list[str] | None = None,
        in_reply_to: str | None = None,
        proposal_id: str | None = None,
        data: dict[str, Any] | None = None,
        status: MessageStatus = MessageStatus.DELIVERED,
        resource: str | None = "electricity",
        unit: str | None = "MW",
    ) -> AgentMessage:
        msg = AgentMessage(
            round_id=ctx.round_id,
            negotiation_id=ctx.negotiation_id,
            tick=ctx.tick,
            sender=self.agent_id,
            receiver=receiver,
            message_type=mtype,
            resource=resource,
            quantity=None if quantity is None else round(max(0.0, quantity), 3),
            unit=unit if quantity is not None else None,
            reason=reason,
            text=text,
            mentions=mentions or [],
            in_reply_to=in_reply_to,
            proposal_id=proposal_id,
            data=data or {},
            sim_time=ctx.sim_time,
            status=status,
            kid=self._key.kid,
            agent_seq=self._next_seq(),
        )
        msg.signature = self._key.sign(msg.signing_payload())
        return msg

    def _next_seq(self) -> int:
        self._agent_seq += 1
        return self._agent_seq


class SystemActor(BaseAgent):
    """Non-utility participants (protocol mediator, trust engine, event feed, commander)."""

    def __init__(self, agent_id: str, key: SigningKey):
        super().__init__(key)
        self.agent_id = agent_id
