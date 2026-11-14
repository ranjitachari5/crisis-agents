"""Versioned, idempotent agreement store (optimistic concurrency).

A proposal is built against ``base_version``. Commit succeeds only if the
proposal validated, its base version is still current, and its id has not
been committed before. Re-committing the same proposal id is a no-op that
returns the existing agreement (idempotency).
"""
from __future__ import annotations

import threading
from dataclasses import asdict, dataclass, field
from datetime import datetime
from enum import Enum

from app.schemas.messages import new_id, utcnow
from app.validation.validator import ValidationResult


class ProposalStatus(str, Enum):
    PENDING = "pending"
    VALIDATED = "validated"
    REJECTED = "rejected"
    COMMITTED = "committed"
    STALE = "stale"


@dataclass
class AllocationProposal:
    allocation: dict[str, float]
    base_version: int
    method: str                       # negotiation | fallback | degradation | commander_override | ...
    supply_total: float
    grid_supply: float
    battery_offer: float
    negotiation_id: str | None = None
    proposal_id: str = field(default_factory=lambda: new_id("prop"))
    objective: dict = field(default_factory=dict)
    rounds: int = 0
    converged: bool = True
    status: ProposalStatus = ProposalStatus.PENDING
    validation: dict | None = None
    created_at: datetime = field(default_factory=utcnow)
    tick: int = 0
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        d = asdict(self)
        d["status"] = self.status.value
        d["created_at"] = self.created_at.isoformat()
        return d


@dataclass
class Agreement:
    version: int
    proposal_id: str
    allocation: dict[str, float]
    method: str
    committed_by: str
    tick: int
    degradation_mode: bool
    battery_discharge: float
    supply_total: float
    negotiation_id: str | None
    committed_at: datetime = field(default_factory=utcnow)
    validation: dict | None = None

    def to_dict(self) -> dict:
        d = asdict(self)
        d["committed_at"] = self.committed_at.isoformat()
        return d


class CommitError(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


class AgreementStore:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.version = 0
        self.current: Agreement | None = None
        self.history: list[Agreement] = []
        self.committed_ids: set[str] = set()
        self.proposals: dict[str, AllocationProposal] = {}

    def register(self, proposal: AllocationProposal) -> None:
        self.proposals[proposal.proposal_id] = proposal

    def pending(self) -> list[AllocationProposal]:
        return [p for p in self.proposals.values()
                if p.status in (ProposalStatus.PENDING, ProposalStatus.VALIDATED)]

    def mark_stale_pending(self) -> list[str]:
        stale = []
        for p in self.pending():
            if p.base_version != self.version:
                p.status = ProposalStatus.STALE
                stale.append(p.proposal_id)
        return stale

    def commit(self, proposal: AllocationProposal, validation: ValidationResult,
               committed_by: str, tick: int) -> tuple[Agreement, bool]:
        """Returns (agreement, newly_committed)."""
        with self._lock:
            if proposal.proposal_id in self.committed_ids:
                existing = next((a for a in self.history if a.proposal_id == proposal.proposal_id), None)
                if existing is None:
                    raise CommitError("DUPLICATE_PROPOSAL", "proposal already committed")
                return existing, False
            if not validation.valid:
                raise CommitError("VALIDATION_FAILED", "proposal failed safety validation")
            if proposal.base_version != self.version:
                proposal.status = ProposalStatus.STALE
                raise CommitError("STALE_PROPOSAL",
                                  f"proposal built on v{proposal.base_version}, current is v{self.version}")
            self.version += 1
            agreement = Agreement(
                version=self.version,
                proposal_id=proposal.proposal_id,
                allocation=dict(proposal.allocation),
                method=proposal.method,
                committed_by=committed_by,
                tick=tick,
                degradation_mode=validation.degradation_mode,
                battery_discharge=validation.battery_discharge,
                supply_total=validation.total_supply,
                negotiation_id=proposal.negotiation_id,
                validation=validation.to_dict(),
            )
            self.current = agreement
            self.history.append(agreement)
            self.committed_ids.add(proposal.proposal_id)
            proposal.status = ProposalStatus.COMMITTED
            self.history = self.history[-500:]
            return agreement, True
