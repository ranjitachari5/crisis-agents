import dataclasses

import pytest

from app.config import get_settings
from app.simulation.engine import SimulationEngine


@pytest.fixture
def settings(tmp_path):
    return dataclasses.replace(get_settings(), database_url=f"sqlite:///{(tmp_path / 't.db').as_posix()}",
                               llm_enabled=False, chat_message_delay_ms=0, tick_interval_s=60,
                               commander_auth_token="test-token")


@pytest.fixture
def engine(settings):
    e = SimulationEngine(settings, seed=7)
    e.start()
    return e
