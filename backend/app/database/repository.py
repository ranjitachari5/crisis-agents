"""Persistence repository. Failures are logged, never allowed to break the simulation."""
from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import desc, select, update

from app.database.db import make_session_factory
from app.database.orm import (AgreementRecord, AuditRecord, EvaluationRecord, MessageRecord, RunSession,
                              TrustIncidentRecord)

log = logging.getLogger(__name__)


class Repository:
    def __init__(self, url: str):
        self.url = url
        self.engine, self.Session = make_session_factory(url)

    def _write(self, obj) -> None:
        try:
            with self.Session.begin() as s:
                s.add(obj)
        except Exception:  # pragma: no cover - logged, not fatal
            log.exception("database write failed")

    def healthy(self) -> bool:
        try:
            with self.Session() as s:
                s.execute(select(1))
            return True
        except Exception:
            return False

    # writes ---------------------------------------------------------------
    def new_session(self, session_id: str, scenario: str, seed: int) -> None:
        self._write(RunSession(id=session_id, scenario=scenario, seed=seed))

    def save_message(self, session_id: str, msg: dict[str, Any]) -> None:
        self._write(MessageRecord(session_id=session_id, seq=msg["seq"], message_id=msg["message_id"],
                                  negotiation_id=msg.get("negotiation_id"), tick=msg["tick"],
                                  sender=msg["sender"], message_type=msg["message_type"],
                                  status=msg["status"], payload=msg))

    def update_message_status(self, session_id: str, message_id: str, status: str) -> None:
        try:
            with self.Session.begin() as s:
                s.execute(update(MessageRecord)
                          .where(MessageRecord.session_id == session_id, MessageRecord.message_id == message_id)
                          .values(status=status))
        except Exception:  # pragma: no cover
            log.exception("status update failed")

    def save_audit(self, session_id: str, entry: dict[str, Any]) -> None:
        self._write(AuditRecord(session_id=session_id, tick=entry["tick"], category=entry["category"],
                                actor=entry["actor"], action=entry["action"], details=entry.get("details", {})))

    def save_agreement(self, session_id: str, agreement: dict[str, Any]) -> None:
        self._write(AgreementRecord(session_id=session_id, version=agreement["version"],
                                    proposal_id=agreement["proposal_id"], method=agreement["method"],
                                    committed_by=agreement["committed_by"], payload=agreement))

    def save_incident(self, session_id: str, incident: dict[str, Any]) -> None:
        try:
            with self.Session.begin() as s:
                existing = s.scalar(select(TrustIncidentRecord).where(
                    TrustIncidentRecord.session_id == session_id,
                    TrustIncidentRecord.incident_id == incident["incident_id"]))
                if existing:
                    existing.payload = incident
                    existing.decision = incident["decision"]
                else:
                    s.add(TrustIncidentRecord(session_id=session_id, incident_id=incident["incident_id"],
                                              kind=incident["kind"], decision=incident["decision"],
                                              payload=incident))
        except Exception:  # pragma: no cover
            log.exception("incident write failed")

    def save_evaluation(self, run_id: str, scenario: str, seed: int, ticks: int, duration_s: float,
                        results: dict[str, Any]) -> None:
        self._write(EvaluationRecord(run_id=run_id, scenario=scenario, seed=seed, ticks=ticks,
                                     duration_s=duration_s, results=results))

    # reads ----------------------------------------------------------------
    def audit_logs(self, session_id: str | None, limit: int, category: str | None = None) -> list[dict]:
        with self.Session() as s:
            q = select(AuditRecord).order_by(desc(AuditRecord.id)).limit(limit)
            if session_id:
                q = q.where(AuditRecord.session_id == session_id)
            if category:
                q = q.where(AuditRecord.category == category)
            return [{"id": r.id, "session_id": r.session_id, "tick": r.tick, "category": r.category,
                     "actor": r.actor, "action": r.action, "details": r.details,
                     "created_at": r.created_at.isoformat()} for r in s.scalars(q)]

    def messages(self, session_id: str, since_seq: int, limit: int) -> list[dict]:
        with self.Session() as s:
            q = (select(MessageRecord).where(MessageRecord.session_id == session_id, MessageRecord.seq > since_seq)
                 .order_by(MessageRecord.seq).limit(limit))
            return [{**r.payload, "status": r.status} for r in s.scalars(q)]

    def evaluations(self, limit: int = 20) -> list[dict]:
        with self.Session() as s:
            q = select(EvaluationRecord).order_by(desc(EvaluationRecord.id)).limit(limit)
            return [{"run_id": r.run_id, "scenario": r.scenario, "seed": r.seed, "ticks": r.ticks,
                     "duration_s": r.duration_s, "results": r.results, "created_at": r.created_at.isoformat()}
                    for r in s.scalars(q)]
