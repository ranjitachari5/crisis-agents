"""Structured inter-agent message schema.

Every chat line shown in the UI is one of these objects. Natural-language
``text`` is presentation only; the protocol acts on the structured fields.
"""
from __future__ import annotations

import json
import math
import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


class MessageType(str, Enum):
    SUPPLY_REPORT = "supply_report"
    REQUEST = "request"
    BID = "bid"
    OFFER = "offer"
    COUNTEROFFER = "counteroffer"
    CONCESSION = "concession"
    ACCEPT = "accept"
    REJECT = "reject"
    PEER_REQUEST = "peer_request"
    EMERGENCY_WARNING = "emergency_warning"
    NEGOTIATION_ROUND = "negotiation_round"
    PROPOSAL = "proposal"
    VALIDATION = "validation"
    AGREEMENT = "agreement"
    SYSTEM = "system"
    EVENT = "event"
    CLAIM = "claim"
    TRUST_ALERT = "trust_alert"
    EXPLANATION = "explanation"
    COMMANDER_ACTION = "commander_action"


class MessageStatus(str, Enum):
    PENDING = "pending"
    DELIVERED = "delivered"
    VERIFIED = "verified"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    QUARANTINED = "quarantined"
    COMMITTED = "committed"
    SUPERSEDED = "superseded"


# Every field is covered by the Ed25519 signature except these, which change after
# sending (delivery sequence, status, the signature itself, verification outcome).
UNSIGNED_FIELDS = {"seq", "status", "signature", "trust"}
MAX_DATA_BYTES = 8192


def new_id(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:12]}"


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class AgentMessage(BaseModel):
    model_config = ConfigDict(extra="forbid", use_enum_values=False)

    message_id: str = Field(default_factory=lambda: new_id("msg"), min_length=4, max_length=64)
    seq: int | None = None
    round_id: int = Field(default=0, ge=0, le=1000)
    negotiation_id: str | None = None
    tick: int = Field(default=0, ge=0)
    sender: str = Field(min_length=2, max_length=64, pattern=r"^[a-z0-9_]+$")
    receiver: str = Field(default="negotiation_group", min_length=2, max_length=64)
    message_type: MessageType
    resource: str | None = "electricity"
    quantity: float | None = None
    unit: str | None = "MW"
    reason: str | None = Field(default=None, max_length=500)
    text: str = Field(default="", max_length=2000)
    mentions: list[str] = Field(default_factory=list, max_length=10)
    in_reply_to: str | None = Field(default=None, max_length=64)
    proposal_id: str | None = Field(default=None, max_length=64)
    data: dict[str, Any] = Field(default_factory=dict)
    timestamp: datetime = Field(default_factory=utcnow)
    sim_time: datetime
    kid: str | None = Field(default=None, max_length=80)          # signing key id
    agent_seq: int | None = Field(default=None, ge=0)              # per-agent monotonic counter
    status: MessageStatus = MessageStatus.DELIVERED
    signature: str | None = Field(default=None, max_length=256)
    trust: dict[str, Any] | None = None  # verification outcome (not signed)

    @field_validator("quantity")
    @classmethod
    def _finite_quantity(cls, v: float | None) -> float | None:
        if v is None:
            return v
        if isinstance(v, bool) or not math.isfinite(v) or v < 0 or v > 100_000:
            raise ValueError("quantity must be finite and within [0, 100000]")
        return round(float(v), 3)

    @field_validator("data")
    @classmethod
    def _bounded_data(cls, v: dict[str, Any]) -> dict[str, Any]:
        if len(json.dumps(v, default=str)) > MAX_DATA_BYTES:
            raise ValueError(f"data payload exceeds {MAX_DATA_BYTES} bytes")
        return v

    def signing_payload(self) -> dict[str, Any]:
        return self.model_dump(mode="json", exclude=UNSIGNED_FIELDS)
