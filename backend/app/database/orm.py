"""Persistent tables. JSON columns keep the schema portable to PostgreSQL (JSONB).

Schema changes go through Alembic migrations (``backend/migrations``); keep
this module and the latest migration in sync (a test checks for drift).
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import JSON, DateTime, Float, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.database.db import Base


def _now() -> datetime:
    return datetime.now(timezone.utc)


class RunSession(Base):
    __tablename__ = "run_sessions"
    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    scenario: Mapped[str] = mapped_column(String(64))
    seed: Mapped[int] = mapped_column(Integer)
    version: Mapped[int] = mapped_column(Integer, default=0, server_default="0")  # agreement version (CAS)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class MessageRecord(Base):
    __tablename__ = "messages"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    session_id: Mapped[str] = mapped_column(String(40), index=True)
    seq: Mapped[int] = mapped_column(Integer, index=True)
    message_id: Mapped[str] = mapped_column(String(64), index=True)
    negotiation_id: Mapped[str | None] = mapped_column(String(64), index=True, nullable=True)
    tick: Mapped[int] = mapped_column(Integer)
    sender: Mapped[str] = mapped_column(String(64))
    message_type: Mapped[str] = mapped_column(String(32))
    status: Mapped[str] = mapped_column(String(16))
    payload: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class SeenMessage(Base):
    """Durable replay protection (F4): a (sender, message_id) pair is accepted at most once, ever."""
    __tablename__ = "seen_messages"
    __table_args__ = (UniqueConstraint("agent_id", "message_id", name="uq_seen_agent_message"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    agent_id: Mapped[str] = mapped_column(String(64))
    message_id: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class AuditRecord(Base):
    """Hash-chained audit log (F12): hash = sha256(prev_hash + body)."""
    __tablename__ = "audit_logs"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    session_id: Mapped[str] = mapped_column(String(40), index=True)
    tick: Mapped[int] = mapped_column(Integer)
    category: Mapped[str] = mapped_column(String(32), index=True)
    actor: Mapped[str] = mapped_column(String(64))
    action: Mapped[str] = mapped_column(String(128))
    details: Mapped[dict] = mapped_column(JSON)
    body: Mapped[str] = mapped_column(Text, default="")
    prev_hash: Mapped[str] = mapped_column(String(64), default="")
    hash: Mapped[str] = mapped_column(String(64), default="", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class AgreementRecord(Base):
    __tablename__ = "agreements"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    session_id: Mapped[str] = mapped_column(String(40), index=True)
    version: Mapped[int] = mapped_column(Integer)
    proposal_id: Mapped[str] = mapped_column(String(64), unique=True)   # idempotency enforced by the DB (F7)
    method: Mapped[str] = mapped_column(String(40))
    outcome: Mapped[str] = mapped_column(String(24), default="", server_default="")
    committed_by: Mapped[str] = mapped_column(String(64))
    payload: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class TrustIncidentRecord(Base):
    __tablename__ = "trust_incidents"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    session_id: Mapped[str] = mapped_column(String(40), index=True)
    incident_id: Mapped[str] = mapped_column(String(64), index=True)
    kind: Mapped[str] = mapped_column(String(48))
    decision: Mapped[str] = mapped_column(String(16))
    payload: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class EvaluationRecord(Base):
    __tablename__ = "evaluation_runs"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[str] = mapped_column(String(40), index=True)
    scenario: Mapped[str] = mapped_column(String(64))
    seed: Mapped[int] = mapped_column(Integer)
    ticks: Mapped[int] = mapped_column(Integer)
    duration_s: Mapped[float] = mapped_column(Float)
    config_hash: Mapped[str] = mapped_column(String(64), default="", server_default="", index=True)
    results: Mapped[dict] = mapped_column(JSON)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
