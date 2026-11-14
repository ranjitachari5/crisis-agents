"""Persistence repository.

Most writes are best-effort: failures are logged, never allowed to break the
simulation. Two operations are authoritative and enforced by the database:

* ``commit_agreement`` - compare-and-swap on the run version plus a UNIQUE
  ``proposal_id`` in one transaction (F7).
* ``record_message_id`` - UNIQUE (agent_id, message_id) replay protection
  that survives restarts (F4).

The audit log is hash-chained (F12) and can be verified with
``verify_audit_chain``.
"""
from __future__ import annotations

import hashlib
import json
import logging
import threading
from typing import Any

from sqlalchemy import desc, select, update
from sqlalchemy.exc import IntegrityError

from app.database.db import make_session_factory
from app.database.orm import (AgreementRecord, AuditRecord, EvaluationRecord, MessageRecord, RunSession,
                              SeenMessage, TrustIncidentRecord)

log = logging.getLogger(__name__)
GENESIS_HASH = "0" * 64
AUDIT_FIELDS = ("id", "session_id", "tick", "category", "actor", "action", "details", "created_at")


class StaleVersion(Exception):
    pass


def audit_body(session_id: str, entry: dict[str, Any]) -> str:
    doc = {"id": entry.get("id"), "session_id": session_id, "tick": entry["tick"], "category": entry["category"],
           "actor": entry["actor"], "action": entry["action"], "details": entry.get("details", {}),
           "created_at": entry.get("created_at")}
    return json.dumps(doc, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)


def chain_hash(prev_hash: str, body: str) -> str:
    return hashlib.sha256((prev_hash + body).encode()).hexdigest()


class Repository:
    def __init__(self, url: str, auto_create: bool = True):
        self.url = url
        self.engine, self.Session = make_session_factory(url, auto_create)
        self._audit_lock = threading.Lock()

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
        self._write(RunSession(id=session_id, scenario=scenario, seed=seed, version=0))

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

    def record_message_id(self, agent_id: str, message_id: str) -> bool:
        """True if newly recorded; False if this (agent, message id) was seen before (replay)."""
        try:
            with self.Session.begin() as s:
                s.add(SeenMessage(agent_id=agent_id, message_id=message_id))
            return True
        except IntegrityError:
            return False
        except Exception:  # pragma: no cover - the in-memory cache still protects this process
            log.exception("replay store unavailable")
            return True

    def save_audit(self, session_id: str, entry: dict[str, Any]) -> str | None:
        """Append to the hash chain. Returns the row hash (None if the write failed)."""
        body = audit_body(session_id, entry)
        try:
            with self._audit_lock, self.Session.begin() as s:
                prev = s.scalar(select(AuditRecord.hash).order_by(desc(AuditRecord.id)).limit(1)) or GENESIS_HASH
                h = chain_hash(prev, body)
                s.add(AuditRecord(session_id=session_id, tick=entry["tick"], category=entry["category"],
                                  actor=entry["actor"], action=entry["action"], details=entry.get("details", {}),
                                  body=body, prev_hash=prev, hash=h))
            return h
        except Exception:  # pragma: no cover
            log.exception("audit write failed")
            return None

    def commit_agreement(self, session_id: str, base_version: int, agreement: dict[str, Any]) -> str:
        """Atomic, idempotent commit: "committed" | "duplicate" | "stale" | "unavailable"."""
        try:
            with self.Session.begin() as s:
                if s.scalar(select(AgreementRecord.id).where(
                        AgreementRecord.proposal_id == agreement["proposal_id"])) is not None:
                    return "duplicate"
                bumped = s.execute(update(RunSession)
                                   .where(RunSession.id == session_id, RunSession.version == base_version)
                                   .values(version=base_version + 1)).rowcount
                if bumped != 1:
                    exists = s.scalar(select(RunSession.id).where(RunSession.id == session_id))
                    raise StaleVersion("stale" if exists else "unavailable")
                s.add(AgreementRecord(session_id=session_id, version=agreement["version"],
                                      proposal_id=agreement["proposal_id"], method=agreement["method"],
                                      outcome=agreement.get("outcome", ""),
                                      committed_by=agreement["committed_by"], payload=agreement))
            return "committed"
        except StaleVersion as exc:
            if str(exc) == "unavailable":
                log.error("run session %s missing from the database; committing in memory only", session_id)
            return str(exc)
        except IntegrityError:
            return "duplicate"
        except Exception:
            log.exception("agreement commit could not be persisted; committing in memory only")
            return "unavailable"

    def save_agreement(self, session_id: str, agreement: dict[str, Any]) -> None:
        """Non-authoritative write (kept for callers that do not use CAS)."""
        self._write(AgreementRecord(session_id=session_id, version=agreement["version"],
                                    proposal_id=agreement["proposal_id"], method=agreement["method"],
                                    outcome=agreement.get("outcome", ""),
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
                        results: dict[str, Any], config_hash: str = "") -> None:
        self._write(EvaluationRecord(run_id=run_id, scenario=scenario, seed=seed, ticks=ticks,
                                     duration_s=duration_s, results=results, config_hash=config_hash))

    # reads ----------------------------------------------------------------
    def audit_logs(self, session_id: str | None, limit: int, category: str | None = None) -> list[dict]:
        with self.Session() as s:
            q = select(AuditRecord).order_by(desc(AuditRecord.id)).limit(limit)
            if session_id:
                q = q.where(AuditRecord.session_id == session_id)
            if category:
                q = q.where(AuditRecord.category == category)
            return [{"id": r.id, "session_id": r.session_id, "tick": r.tick, "category": r.category,
                     "actor": r.actor, "action": r.action, "details": r.details, "hash": r.hash,
                     "prev_hash": r.prev_hash, "created_at": r.created_at.isoformat()} for r in s.scalars(q)]

    def verify_audit_chain(self, batch: int = 1000) -> dict[str, Any]:
        """Walk the whole chain. Reports the first row whose linkage, hash or columns do not match."""
        prev = GENESIS_HASH
        checked = 0
        last_id = 0
        with self.Session() as s:
            while True:
                rows = list(s.scalars(select(AuditRecord).where(AuditRecord.id > last_id)
                                      .order_by(AuditRecord.id).limit(batch)))
                if not rows:
                    break
                for r in rows:
                    reason = None
                    if r.prev_hash != prev:
                        reason = "prev_hash does not match the previous row (row deleted or reordered)"
                    elif chain_hash(r.prev_hash, r.body or "") != r.hash:
                        reason = "hash does not match body (body edited)"
                    else:
                        try:
                            doc = json.loads(r.body)
                        except (TypeError, ValueError):
                            doc = {}
                        cols = {"session_id": r.session_id, "tick": r.tick, "category": r.category,
                                "actor": r.actor, "action": r.action, "details": r.details}
                        if any(json.dumps(doc.get(k), sort_keys=True, default=str) !=
                               json.dumps(v, sort_keys=True, default=str) for k, v in cols.items()):
                            reason = "row columns differ from the hashed body (columns edited)"
                    if reason:
                        return {"ok": False, "checked": checked, "first_broken_id": r.id, "reason": reason}
                    prev = r.hash
                    checked += 1
                    last_id = r.id
        return {"ok": True, "checked": checked, "first_broken_id": None, "reason": None, "head": prev}

    def messages(self, session_id: str, since_seq: int, limit: int) -> list[dict]:
        with self.Session() as s:
            q = (select(MessageRecord).where(MessageRecord.session_id == session_id, MessageRecord.seq > since_seq)
                 .order_by(MessageRecord.seq).limit(limit))
            return [{**r.payload, "status": r.status} for r in s.scalars(q)]

    def evaluations(self, limit: int = 20) -> list[dict]:
        with self.Session() as s:
            q = select(EvaluationRecord).order_by(desc(EvaluationRecord.id)).limit(limit)
            return [{"run_id": r.run_id, "scenario": r.scenario, "seed": r.seed, "ticks": r.ticks,
                     "duration_s": r.duration_s, "config_hash": r.config_hash, "results": r.results,
                     "created_at": r.created_at.isoformat()}
                    for r in s.scalars(q)]
