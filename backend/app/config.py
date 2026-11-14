"""Application settings loaded from environment variables (.env supported)."""
from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv

BACKEND_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BACKEND_DIR / ".env")
load_dotenv(BACKEND_DIR.parent / ".env")

DEFAULT_TOKEN = "change-me"
MIN_TOKEN_LEN = 24
APPROVAL_POLICIES = ("keep_last", "commit")


def _bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _float(name: str, default: float) -> float:
    raw = os.getenv(name)
    return float(raw) if raw not in (None, "") else default


def _int(name: str, default: int) -> int:
    raw = os.getenv(name)
    return int(raw) if raw not in (None, "") else default


def weak_token(token: str) -> bool:
    return token in {"", DEFAULT_TOKEN} or len(token) < MIN_TOKEN_LEN


@dataclass(frozen=True)
class Settings:
    groq_api_key: str | None = field(repr=False)
    groq_model: str
    llm_enabled: bool
    llm_timeout_s: float
    llm_agreement_summaries: bool
    database_url: str
    tick_interval_s: float
    sim_minutes_per_tick: int
    chat_message_delay_ms: int
    max_negotiation_rounds: int
    random_seed: int
    commander_auth_token: str = field(repr=False)
    cors_origins: tuple[str, ...]
    log_level: str
    # --- security (F1/F2) ---------------------------------------------------
    env: str = "dev"
    admin_auth_token: str = field(default="", repr=False)    # empty in dev: commander token acts as admin
    viewer_auth_token: str = field(default="", repr=False)   # empty: read-only routes are public
    enable_test_routes: bool | None = None                   # None: enabled only in dev
    auth_max_failures_per_min: int = 10
    max_request_bytes: int = 64 * 1024
    # --- trust (F4) ---------------------------------------------------------
    message_max_age_s: float = 300.0
    message_clock_skew_s: float = 30.0
    # --- runs (F8) ----------------------------------------------------------
    max_runs: int = 8
    run_ttl_s: float = 3600.0
    # --- approval workflow (F11) -------------------------------------------
    approval_timeout_s: float = 120.0
    approval_timeout_policy: str = "keep_last"
    # --- websocket (F13) ----------------------------------------------------
    ws_client_queue: int = 256
    ws_max_inbound_bytes: int = 4096
    ws_max_inbound_per_s: float = 20.0
    ws_auth_timeout_s: float = 5.0
    # --- persistence (F12) --------------------------------------------------
    db_auto_create: bool | None = None                       # None: create_all in dev, Alembic otherwise

    def __post_init__(self) -> None:
        if self.env != "dev":
            if weak_token(self.commander_auth_token):
                raise ValueError("COMMANDER_AUTH_TOKEN is weak (default, empty or < 24 chars); refusing to start")
            if weak_token(self.admin_auth_token):
                raise ValueError("ADMIN_AUTH_TOKEN is weak (default, empty or < 24 chars); refusing to start")
            if self.admin_auth_token == self.commander_auth_token:
                raise ValueError("ADMIN_AUTH_TOKEN must differ from COMMANDER_AUTH_TOKEN outside dev")
            if self.viewer_auth_token and weak_token(self.viewer_auth_token):
                raise ValueError("VIEWER_AUTH_TOKEN is weak (< 24 chars); refusing to start")
        if self.approval_timeout_policy not in APPROVAL_POLICIES:
            raise ValueError(f"APPROVAL_TIMEOUT_POLICY must be one of {APPROVAL_POLICIES}")
        if self.max_runs < 1:
            raise ValueError("MAX_RUNS must be >= 1")

    @property
    def llm_configured(self) -> bool:
        return bool(self.llm_enabled and self.groq_api_key)

    @property
    def test_routes_enabled(self) -> bool:
        return self.env == "dev" if self.enable_test_routes is None else self.enable_test_routes

    @property
    def auto_create_schema(self) -> bool:
        return self.env == "dev" if self.db_auto_create is None else self.db_auto_create


def _opt_bool(name: str) -> bool | None:
    raw = os.getenv(name)
    return None if raw is None or raw.strip() == "" else _bool(name, False)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    default_db = f"sqlite:///{(BACKEND_DIR / 'crisis_agents.db').as_posix()}"
    origins = os.getenv("CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173")
    return Settings(
        groq_api_key=os.getenv("GROQ_API_KEY") or None,
        groq_model=os.getenv("GROQ_MODEL", "openai/gpt-oss-120b"),
        llm_enabled=_bool("LLM_ENABLED", True),
        llm_timeout_s=_float("LLM_TIMEOUT_S", 12.0),
        llm_agreement_summaries=_bool("LLM_AGREEMENT_SUMMARIES", True),
        database_url=os.getenv("DATABASE_URL", default_db),
        tick_interval_s=_float("TICK_INTERVAL_S", 5.0),
        sim_minutes_per_tick=_int("SIM_MINUTES_PER_TICK", 15),
        chat_message_delay_ms=_int("CHAT_MESSAGE_DELAY_MS", 250),
        max_negotiation_rounds=_int("MAX_NEGOTIATION_ROUNDS", 5),
        random_seed=_int("RANDOM_SEED", 42),
        commander_auth_token=os.getenv("COMMANDER_AUTH_TOKEN", DEFAULT_TOKEN),
        cors_origins=tuple(o.strip() for o in origins.split(",") if o.strip()),
        log_level=os.getenv("LOG_LEVEL", "INFO").upper(),
        env=os.getenv("ENV", "dev").strip().lower(),
        admin_auth_token=os.getenv("ADMIN_AUTH_TOKEN", ""),
        viewer_auth_token=os.getenv("VIEWER_AUTH_TOKEN", ""),
        enable_test_routes=_opt_bool("ENABLE_TEST_ROUTES"),
        auth_max_failures_per_min=_int("AUTH_MAX_FAILURES_PER_MIN", 10),
        max_request_bytes=_int("MAX_REQUEST_BYTES", 64 * 1024),
        message_max_age_s=_float("MESSAGE_MAX_AGE_S", 300.0),
        message_clock_skew_s=_float("MESSAGE_CLOCK_SKEW_S", 30.0),
        max_runs=_int("MAX_RUNS", 8),
        run_ttl_s=_float("RUN_TTL_S", 3600.0),
        approval_timeout_s=_float("APPROVAL_TIMEOUT_S", 120.0),
        approval_timeout_policy=os.getenv("APPROVAL_TIMEOUT_POLICY", "keep_last").strip().lower(),
        ws_client_queue=_int("WS_CLIENT_QUEUE", 256),
        ws_max_inbound_bytes=_int("WS_MAX_INBOUND_BYTES", 4096),
        ws_max_inbound_per_s=_float("WS_MAX_INBOUND_PER_S", 20.0),
        ws_auth_timeout_s=_float("WS_AUTH_TIMEOUT_S", 5.0),
        db_auto_create=_opt_bool("DB_AUTO_CREATE"),
    )


def configure_logging(level: str) -> None:
    logging.basicConfig(
        level=getattr(logging, level, logging.INFO),
        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
    )
