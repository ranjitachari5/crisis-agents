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

    @property
    def llm_configured(self) -> bool:
        return bool(self.llm_enabled and self.groq_api_key)


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
        commander_auth_token=os.getenv("COMMANDER_AUTH_TOKEN", "change-me"),
        cors_origins=tuple(o.strip() for o in origins.split(",") if o.strip()),
        log_level=os.getenv("LOG_LEVEL", "INFO").upper(),
    )


def configure_logging(level: str) -> None:
    logging.basicConfig(
        level=getattr(logging, level, logging.INFO),
        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
    )
