"""Initial schema: runs (with CAS version), messages, replay store, hash-chained audit log,
agreements (unique proposal_id), trust incidents, evaluation runs (with config hash).

Revision ID: 0001
Revises:
Create Date: 2026-11-14
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "run_sessions",
        sa.Column("id", sa.String(40), primary_key=True),
        sa.Column("scenario", sa.String(64), nullable=False),
        sa.Column("seed", sa.Integer(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "messages",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("session_id", sa.String(40), nullable=False),
        sa.Column("seq", sa.Integer(), nullable=False),
        sa.Column("message_id", sa.String(64), nullable=False),
        sa.Column("negotiation_id", sa.String(64), nullable=True),
        sa.Column("tick", sa.Integer(), nullable=False),
        sa.Column("sender", sa.String(64), nullable=False),
        sa.Column("message_type", sa.String(32), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_messages_session_id", "messages", ["session_id"])
    op.create_index("ix_messages_seq", "messages", ["seq"])
    op.create_index("ix_messages_message_id", "messages", ["message_id"])
    op.create_index("ix_messages_negotiation_id", "messages", ["negotiation_id"])
    op.create_table(
        "seen_messages",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("agent_id", sa.String(64), nullable=False),
        sa.Column("message_id", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("agent_id", "message_id", name="uq_seen_agent_message"),
    )
    op.create_table(
        "audit_logs",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("session_id", sa.String(40), nullable=False),
        sa.Column("tick", sa.Integer(), nullable=False),
        sa.Column("category", sa.String(32), nullable=False),
        sa.Column("actor", sa.String(64), nullable=False),
        sa.Column("action", sa.String(128), nullable=False),
        sa.Column("details", sa.JSON(), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("prev_hash", sa.String(64), nullable=False),
        sa.Column("hash", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_audit_logs_session_id", "audit_logs", ["session_id"])
    op.create_index("ix_audit_logs_category", "audit_logs", ["category"])
    op.create_index("ix_audit_logs_hash", "audit_logs", ["hash"])
    op.create_table(
        "agreements",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("session_id", sa.String(40), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("proposal_id", sa.String(64), nullable=False, unique=True),
        sa.Column("method", sa.String(40), nullable=False),
        sa.Column("outcome", sa.String(24), nullable=False, server_default=""),
        sa.Column("committed_by", sa.String(64), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_agreements_session_id", "agreements", ["session_id"])
    op.create_table(
        "trust_incidents",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("session_id", sa.String(40), nullable=False),
        sa.Column("incident_id", sa.String(64), nullable=False),
        sa.Column("kind", sa.String(48), nullable=False),
        sa.Column("decision", sa.String(16), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_trust_incidents_session_id", "trust_incidents", ["session_id"])
    op.create_index("ix_trust_incidents_incident_id", "trust_incidents", ["incident_id"])
    op.create_table(
        "evaluation_runs",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("run_id", sa.String(40), nullable=False),
        sa.Column("scenario", sa.String(64), nullable=False),
        sa.Column("seed", sa.Integer(), nullable=False),
        sa.Column("ticks", sa.Integer(), nullable=False),
        sa.Column("duration_s", sa.Float(), nullable=False),
        sa.Column("config_hash", sa.String(64), nullable=False, server_default=""),
        sa.Column("results", sa.JSON(), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_evaluation_runs_run_id", "evaluation_runs", ["run_id"])
    op.create_index("ix_evaluation_runs_config_hash", "evaluation_runs", ["config_hash"])


def downgrade() -> None:
    for table in ("evaluation_runs", "trust_incidents", "agreements", "audit_logs", "seen_messages", "messages",
                  "run_sessions"):
        op.drop_table(table)
