"""Creates the agents and their Ed25519 signing keys.

Each agent receives only its own private key. The registry also builds the
``PublicKeyRegistry`` that is handed to the trust engine; the trust engine
never sees private keys.
"""
from __future__ import annotations

from app.agents.base import SystemActor
from app.agents.consumers import AGENT_CLASSES, ConsumerAgent
from app.agents.suppliers import BatteryAgent, GridAgent
from app.models.state import CONSUMER_PROFILES
from app.trust import crypto
from app.trust.crypto import PublicKeyRegistry, SigningKey

SYSTEM_ACTORS = ("negotiation_protocol", "trust_engine", "simulation", "commander", "analyst")


class AgentRegistry:
    def __init__(self, dt_minutes: int, nominal_capacity: float):
        self.public_keys = PublicKeyRegistry()

        def key(aid: str) -> SigningKey:
            k = crypto.generate(aid)
            self.public_keys.register(aid, k.kid, k.public_key())
            return k

        self.consumers: dict[str, ConsumerAgent] = {
            aid: AGENT_CLASSES[aid](profile, key(aid), dt_minutes)
            for aid, profile in CONSUMER_PROFILES.items()
        }
        self.grid = GridAgent(key("grid_agent"), nominal_capacity)
        self.battery = BatteryAgent(key("battery_agent"), dt_minutes / 60)
        self.system = {aid: SystemActor(aid, key(aid)) for aid in SYSTEM_ACTORS}
        self._participants = frozenset(self.public_keys.participants())

    @property
    def participants(self) -> frozenset[str]:
        """Registered message senders (independent of key revocation)."""
        return self._participants

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

    def revoke(self, agent_id: str) -> list[str]:
        """Revoke every active key of an agent (used when the commander isolates it)."""
        return self.public_keys.revoke_agent(agent_id)

    def rotate_key(self, agent_id: str) -> str:
        """Issue a fresh key pair; the previous key stays valid for one rotation (grace window)."""
        agent = self.get(agent_id)
        if agent is None:
            raise KeyError(agent_id)
        k = crypto.generate(agent_id)
        self.public_keys.register(agent_id, k.kid, k.public_key())
        agent.rotate_key(k)
        return k.kid
