"""Harm weights shared by the optimizer, agents and metrics."""
from __future__ import annotations

from app.agents.consumers import dependents_weight
from app.models.state import CONSUMER_PROFILES, CityState


def situational_multiplier(city: CityState, agent_id: str) -> float:
    c = city.consumers[agent_id]
    if agent_id == "hospital_agent" and c.extra_min > 0:
        return 1.3
    if agent_id == "emergency_agent" and c.active_operations:
        return 1.5
    return 1.0


def damage_weights(city: CityState) -> dict[str, float]:
    return {
        aid: round(p.damage_weight * situational_multiplier(city, aid) + dependents_weight(aid), 3)
        for aid, p in CONSUMER_PROFILES.items()
    }


def critical_weights() -> dict[str, float]:
    """Harm per MW below minimum, including downstream harm through dependencies."""
    out = {}
    for aid, p in CONSUMER_PROFILES.items():
        downstream = sum(0.5 * o.dependencies.get(aid, 0.0) * o.critical_weight for o in CONSUMER_PROFILES.values())
        out[aid] = round(p.critical_weight + downstream, 3)
    return out
