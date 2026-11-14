"""Validated request/response schemas for the REST API."""
from __future__ import annotations

import math
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.simulation.events import EventType

ScenarioName = Literal["grid_shortage", "flood_cascade", "normal"]
ConsumerId = Literal["hospital_agent", "water_agent", "telecom_agent", "emergency_agent"]
AgentId = Literal["hospital_agent", "water_agent", "telecom_agent", "emergency_agent", "battery_agent", "grid_agent"]
FakeKind = Literal["false_capacity_drop", "fake_disaster_alert", "inflated_bid", "replay_message",
                   "false_recovery", "contradictory_sensors"]
Mode = Literal["negotiation", "centralized", "fixed_priority", "fcfs"]


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ResetRequest(Strict):
    scenario: ScenarioName = "grid_shortage"
    seed: int | None = Field(default=None, ge=0, le=2**31 - 1)


class StepRequest(Strict):
    ticks: int = Field(default=1, ge=1, le=96)


class FairnessRequest(Strict):
    value: float = Field(ge=0.0, le=1.0, description="0 = priority-based, 0.5 = balanced, 1 = equity-focused")


class SettingsRequest(Strict):
    approval_mode: Literal["auto", "manual"] | None = None
    tick_interval_s: float | None = Field(default=None, ge=0.5, le=60)


class EventInjectRequest(Strict):
    event_type: EventType
    params: dict[str, Any] = Field(default_factory=dict)


class FakeInjectRequest(Strict):
    kind: FakeKind = "false_capacity_drop"
    params: dict[str, Any] = Field(default_factory=dict)


def _check_alloc(v: dict[str, float] | None) -> dict[str, float] | None:
    if v is None:
        return v
    for k, x in v.items():
        if not isinstance(x, (int, float)) or not math.isfinite(x) or x < 0 or x > 10_000:
            raise ValueError(f"allocation for {k} must be a finite number in [0, 10000]")
    return v


class ValidateRequest(Strict):
    allocation: dict[ConsumerId, float] | None = None
    proposal_id: str | None = None

    @field_validator("allocation")
    @classmethod
    def _alloc(cls, v):
        return _check_alloc(v)

    @model_validator(mode="after")
    def _one(self):
        if (self.allocation is None) == (self.proposal_id is None):
            raise ValueError("provide exactly one of 'allocation' or 'proposal_id'")
        return self


class CommitRequest(Strict):
    proposal_id: str = Field(min_length=4, max_length=64)


class RejectRequest(Strict):
    proposal_id: str = Field(min_length=4, max_length=64)
    reason: str = Field(min_length=3, max_length=300)


class NegotiationStartRequest(Strict):
    reason: str = Field(default="commander requested reassessment", max_length=200)


class OverrideRequest(Strict):
    allocation: dict[ConsumerId, float]
    reason: str = Field(min_length=5, max_length=300)
    authorization: str = Field(min_length=1, max_length=200, description="COMMANDER_AUTH_TOKEN")

    @field_validator("allocation")
    @classmethod
    def _alloc(cls, v):
        return _check_alloc(v)


class IsolateRequest(Strict):
    reason: str = Field(default="suspicious behaviour reported by trust engine", max_length=300)


class ExplainRequest(Strict):
    question: str | None = Field(default=None, max_length=500)


class ResolveIncidentRequest(Strict):
    action: Literal["confirm_claim", "dismiss"]
    note: str = Field(default="", max_length=300)
    confirmed_supply_mw: float | None = Field(default=None, ge=0, le=10_000)


class EvaluationRequest(Strict):
    scenario: ScenarioName = "flood_cascade"
    seed: int = Field(default=42, ge=0, le=2**31 - 1)
    ticks: int = Field(default=32, ge=4, le=200)
    fairness: float = Field(default=0.5, ge=0, le=1)
    modes: list[Mode] = Field(default_factory=lambda: ["fcfs", "fixed_priority", "centralized", "negotiation"])


class HealthResponse(BaseModel):
    status: str
    version: str
    database: bool
    llm: dict
    simulation_status: str
    session_id: str


class ErrorBody(BaseModel):
    code: str
    message: str
    details: Any = None


class ErrorResponse(BaseModel):
    error: ErrorBody
