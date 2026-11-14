"""SQLAlchemy engine/session setup.

SQLite (dev): WAL journal, a busy timeout and ``BEGIN IMMEDIATE`` transactions
so concurrent writers queue instead of failing with "database is locked".
PostgreSQL (shared deployments): set DATABASE_URL; a connection pool is used.

Schema management: ``auto_create=True`` (dev/tests) uses ``create_all``;
otherwise the schema is brought to the latest Alembic revision.
"""
from __future__ import annotations

import logging
from pathlib import Path

from sqlalchemy import create_engine, event, inspect
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

log = logging.getLogger(__name__)
BACKEND_DIR = Path(__file__).resolve().parents[2]


class Base(DeclarativeBase):
    pass


def _configure_sqlite(engine: Engine) -> None:
    @event.listens_for(engine, "connect")
    def _on_connect(dbapi_conn, _record):  # pragma: no cover - exercised implicitly
        dbapi_conn.isolation_level = None  # let SQLAlchemy emit BEGIN itself (below)
        cur = dbapi_conn.cursor()
        cur.execute("PRAGMA journal_mode=WAL")
        cur.execute("PRAGMA busy_timeout=30000")
        cur.execute("PRAGMA synchronous=NORMAL")
        cur.close()

    @event.listens_for(engine, "begin")
    def _on_begin(conn):  # pragma: no cover - exercised implicitly
        conn.exec_driver_sql("BEGIN IMMEDIATE")


def run_migrations(url: str) -> None:
    from alembic import command
    from alembic.config import Config

    cfg = Config(str(BACKEND_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND_DIR / "migrations"))
    cfg.set_main_option("sqlalchemy.url", url)
    command.upgrade(cfg, "head")


def _check_schema(engine: Engine) -> None:
    """Warn loudly if an existing database predates the current schema."""
    from app.database import orm  # noqa: F401

    insp = inspect(engine)
    for table in Base.metadata.sorted_tables:
        if not insp.has_table(table.name):
            continue
        have = {c["name"] for c in insp.get_columns(table.name)}
        missing = [c.name for c in table.columns if c.name not in have]
        if missing:
            log.error("table %s is missing columns %s: this database predates the current schema. "
                      "Run `alembic upgrade head` (or delete the dev SQLite file).", table.name, missing)


def make_session_factory(url: str, auto_create: bool = True):
    kwargs: dict = {"pool_pre_ping": True}
    if url.startswith("sqlite"):
        kwargs["connect_args"] = {"check_same_thread": False, "timeout": 30}
    else:
        kwargs.update(pool_size=10, max_overflow=20)
    engine = create_engine(url, **kwargs)
    if url.startswith("sqlite"):
        _configure_sqlite(engine)
    from app.database import orm  # noqa: F401  (register tables)
    if auto_create:
        Base.metadata.create_all(engine)
    else:
        run_migrations(url)
    _check_schema(engine)
    return engine, sessionmaker(bind=engine, expire_on_commit=False)
