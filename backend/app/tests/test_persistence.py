"""F7 atomic/idempotent commit, F12 hash-chained audit log and migration drift."""
import threading

from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import create_engine, func, select, text

from app.database.db import Base, run_migrations
from app.database.orm import AgreementRecord, RunSession
from app.database.repository import Repository


def repo(tmp_path, name="p.db"):
    return Repository(f"sqlite:///{(tmp_path / name).as_posix()}")


def test_50_concurrent_identical_commits_yield_one_row_and_one_bump(tmp_path):
    r = repo(tmp_path)
    r.new_session("run-1", "grid_shortage", 1)
    agreement = {"version": 1, "proposal_id": "prop-same", "method": "negotiation", "committed_by": "t",
                 "outcome": "converged"}
    results, barrier = [], threading.Barrier(50)

    def worker():
        barrier.wait()
        results.append(r.commit_agreement("run-1", 0, agreement))

    threads = [threading.Thread(target=worker) for _ in range(50)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    with r.Session() as s:
        assert s.scalar(select(func.count()).select_from(AgreementRecord)) == 1
        assert s.scalar(select(RunSession.version).where(RunSession.id == "run-1")) == 1
    assert results.count("committed") == 1
    assert set(results) <= {"committed", "duplicate", "stale"}


def test_stale_base_version_rejected_by_database(tmp_path):
    r = repo(tmp_path)
    r.new_session("run-1", "grid_shortage", 1)
    base = {"method": "m", "committed_by": "t"}
    assert r.commit_agreement("run-1", 0, {**base, "version": 1, "proposal_id": "a"}) == "committed"
    assert r.commit_agreement("run-1", 0, {**base, "version": 1, "proposal_id": "b"}) == "stale"
    assert r.commit_agreement("run-1", 1, {**base, "version": 2, "proposal_id": "a"}) == "duplicate"


def test_engine_commits_are_persisted_with_outcome(settings, tmp_path):
    from app.simulation.engine import SimulationEngine
    r = repo(tmp_path, "e.db")
    e = SimulationEngine(settings, seed=7, repo=r)
    e.start()
    e.step()
    with r.Session() as s:
        rows = list(s.scalars(select(AgreementRecord)))
        assert rows and all(row.outcome for row in rows)
        assert s.scalar(select(RunSession.version).where(RunSession.id == e.session_id)) == e.agreements.version


def test_audit_chain_detects_edits_and_deletions(tmp_path):
    r = repo(tmp_path)
    for i in range(6):
        r.save_audit("run-1", {"id": f"a{i}", "tick": i, "category": "c", "actor": "x", "action": f"act{i}",
                               "details": {"i": i}, "created_at": "t"})
    assert r.verify_audit_chain() == {**r.verify_audit_chain(), "ok": True, "checked": 6}
    with r.engine.begin() as conn:  # an insider edits a column by hand
        conn.execute(text("UPDATE audit_logs SET action='forged' WHERE id=4"))
    res = r.verify_audit_chain()
    assert not res["ok"] and res["first_broken_id"] == 4
    with r.engine.begin() as conn:
        conn.execute(text("UPDATE audit_logs SET action='act3' WHERE id=4"))
        conn.execute(text("DELETE FROM audit_logs WHERE id=2"))
    res = r.verify_audit_chain()
    assert not res["ok"] and res["first_broken_id"] == 3


def test_alembic_migrations_match_orm(tmp_path):
    url = f"sqlite:///{(tmp_path / 'm.db').as_posix()}"
    run_migrations(url)
    engine = create_engine(url)
    with engine.connect() as conn:
        diff = compare_metadata(MigrationContext.configure(conn), Base.metadata)
    # unique constraints/indexes on SQLite reflect without names; only column/table drift matters here
    drift = [d for d in diff if d[0] in ("add_table", "remove_table", "add_column", "remove_column")]
    assert not drift, drift


def test_sqlite_runs_in_wal_mode(tmp_path):
    r = repo(tmp_path)
    with r.engine.connect() as conn:
        assert conn.exec_driver_sql("PRAGMA journal_mode").scalar().lower() == "wal"
