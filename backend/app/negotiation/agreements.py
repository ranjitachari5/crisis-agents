"""Versioned, idempotent agreement store (optimistic concurrency).

A proposal is built against ``base_version``. Commit succeeds only if the
proposal validated, its base version is still current, and its id has not
been committed before. Re-committing the same proposal id is a no-op that
returns the existing agreement (idempotency).

The in-memory checks are mirrored by the database (F7): ``persist`` runs a
single compare-and-swap transaction on the run version with a UNIQUE
constraint on ``proposal_id``, before memory is mutated, so idempotency and
version monotonicity hold even across retries or several writers.

Proposal state machine (F11)::

    PENDING -> VALIDATED -> COMMITTED
                         -> APPROVED -> COMMITTED       (commander approval)
                         -> REJECTED                    (validator or commander)
                         -> EXPIRED                     (approval timeout)
                         -> SUPERSEDED                  (a newer proposal is awaiting approval)
                         -> STALE                       (another agreement was committed first)
"""
from __future__ import annotations

import threading
from dataclasses import asdict, dataclass, field
from datetime import datetime
from enum import Enum
from typing import Callable

from app.schemas.messages import new_id, utcnow
from app.validation.validator import ValidationResult


class ProposalStatus(str, Enum):
    PENDING = "pending"
    VALIDATED = "validated"
    APPROVED = "approved"
    REJECTED = "rejected"
    EXPIRED = "expired"
    SUPERSEDED = "superseded"
    COMMITTED = "committed"
    STALE = "stale"


OPEN_STATES = (ProposalStatus.PENDING, ProposalStatus.VALIDATED)
CLOSED_STATES = (ProposalStatus.REJECTED, ProposalStatus.EXPIRED, ProposalStatus.SUPERSEDED, ProposalStatus.STALE)


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
    outcome: str = ""                 # uncontested | converged | fallback | degraded | override
    solver: dict | None = None        # optimizer metadata (F9)
    awaiting_since: float | None = None  # monotonic time it started waiting for approval (F11)

    def to_dict(self) -> dict:
        d = asdict(self)
        d["status"] = self.status.value
        d["created_at"] = self.created_at.isoformat()
        d.pop("awaiting_since", None)
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
    outcome: str = ""

    def to_dict(self) -> dict:
        d = asdict(self)
        d["committed_at"] = self.committed_at.isoformat()
        return d


class CommitError(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


# persist(agreement, base_version) -> "committed" | "duplicate" | "stale" | "unavailable"
Persist = Callable[[Agreement, int], str]


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
        if len(self.proposals) > 2000:  # bound memory: drop the oldest closed proposals
            for pid in [k for k, p in self.proposals.items() if p.status not in OPEN_STATES][:500]:
                del self.proposals[pid]

    def pending(self) -> list[AllocationProposal]:
        return [p for p in self.proposals.values() if p.status in OPEN_STATES]

    def awaiting_approval(self) -> list[AllocationProposal]:
        return [p for p in self.pending() if p.awaiting_since is not None]

    def mark_stale_pending(self) -> list[str]:
        stale = []
        for p in self.pending():
            if p.base_version != self.version:
                p.status = ProposalStatus.STALE
                stale.append(p.proposal_id)
        return stale

    def supersede_awaiting(self, newer: AllocationProposal) -> list[str]:
        """A newer proposal is awaiting approval: older ones can no longer be applied."""
        out = []
        for p in self.awaiting_approval():
            if p.proposal_id != newer.proposal_id:
                p.status = ProposalStatus.SUPERSEDED
                out.append(p.proposal_id)
        return out

    def commit(self, proposal: AllocationProposal, validation: ValidationResult,
               committed_by: str, tick: int, persist: Persist | None = None) -> tuple[Agreement, bool]:
        """Returns (agreement, newly_committed)."""
        with self._lock:
            if proposal.proposal_id in self.committed_ids:
                existing = next((a for a in self.history if a.proposal_id == proposal.proposal_id), None)
                if existing is None:
                    raise CommitError("DUPLICATE_PROPOSAL", "proposal already committed")
                return existing, False
            if proposal.status in CLOSED_STATES:
                raise CommitError("PROPOSAL_CLOSED", f"proposal is {proposal.status.value}")
            if not validation.valid:
                raise CommitError("VALIDATION_FAILED", "proposal failed safety validation")
            if proposal.base_version != self.version:
                proposal.status = ProposalStatus.STALE
                raise CommitError("STALE_PROPOSAL",
                                  f"proposal built on v{proposal.base_version}, current is v{self.version}")
            agreement = Agreement(
                version=self.version + 1,
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
                outcome=proposal.outcome,
            )
            if persist is not None:
                # The database is the arbiter: CAS on the run version + UNIQUE(proposal_id).
                result = persist(agreement, self.version)
                if result == "duplicate":
                    raise CommitError("DUPLICATE_PROPOSAL", "proposal already committed (database)")
                if result == "stale":
                    proposal.status = ProposalStatus.STALE
                    raise CommitError("STALE_PROPOSAL", "run version changed in the database")
            self.version = agreement.version
            self.current = agreement
            self.history.append(agreement)
            self.committed_ids.add(proposal.proposal_id)
            proposal.status = ProposalStatus.COMMITTED
            proposal.awaiting_since = None
            self.history = self.history[-500:]
            return agreement, True
