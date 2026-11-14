"""Creates the agents and their signing keys (the trust keyring)."""
from __future__ import annotations

import os

from app.agents.base import SystemActor
from app.agents.consumers import AGENT_CLASSES, ConsumerAgent
from app.agents.suppliers import BatteryAgent, GridAgent
from app.models.state import CONSUMER_PROFILES

SYSTEM_ACTORS = ("negotiation_protocol", "trust_engine", "simulation", "commander", "analyst")


class AgentRegistry:
    def __init__(self, dt_minutes: int, nominal_capacity: float):
        self.keyring: dict[str, bytes] = {}

        def key(aid: str) -> bytes:
            self.keyring[aid] = os.urandom(32)
            return self.keyring[aid]

        self.consumers: dict[str, ConsumerAgent] = {
            aid: AGENT_CLASSES[aid](profile, key(aid), dt_minutes)
            for aid, profile in CONSUMER_PROFILES.items()
        }
        self.grid = GridAgent(key("grid_agent"), nominal_capacity)
        self.battery = BatteryAgent(key("battery_agent"), dt_minutes / 60)
        self.system = {aid: SystemActor(aid, key(aid)) for aid in SYSTEM_ACTORS}

    def utility_ids(self) -> list[str]:
        return list(self.consumers) + ["battery_agent", "grid_agent"]

    def get(self, agent_id: str):
        if agent_id in self.consumers:
            return self.consumers[agent_id]
        if agent_id == "grid_agent":
            return self.grid
        if agent_id == "battery_agent":
            return self.battery
        return self.system.get(agent_id)
