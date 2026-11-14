"""Real (ground-truth) disaster events. Each mutates the city state."""
from __future__ import annotations

from enum import Enum
from typing import Any

from app.models.state import CONSUMER_IDS, CONSUMER_PROFILES, CityState


class EventType(str, Enum):
    POWER_REDUCTION = "power_reduction"
    FLOOD_WARNING = "flood_warning"
    HOSPITAL_DEMAND_SPIKE = "hospital_demand_spike"
    WATER_PUMP_FAILURE = "water_pump_failure"
    TELECOM_OUTAGE = "telecom_outage"
    BATTERY_DEPLETION = "battery_depletion"
    AGENT_DISCONNECT = "agent_disconnect"
    AGENT_RECONNECT = "agent_reconnect"
    RECOVERY = "recovery"


EVENT_CATALOG: dict[str, dict[str, Any]] = {
    "power_reduction": {"label": "Power shortage", "params": {"percent": "0-95 (% of current supply lost)",
                                                              "available_mw": "optional absolute value"}},
    "flood_warning": {"label": "Flood", "params": {"severity": "1-3"}},
    "hospital_demand_spike": {"label": "Hospital demand spike", "params": {"additional_mw": "1-40"}},
    "water_pump_failure": {"label": "Water pumping failure", "params": {"capacity_fraction": "0.1-0.9"}},
    "telecom_outage": {"label": "Telecom tower outage", "params": {"capacity_fraction": "0.1-0.9"}},
    "battery_depletion": {"label": "Battery depletion", "params": {"soc": "reserve..1 (default reserve+2%)"}},
    "agent_disconnect": {"label": "Disconnect agent", "params": {"agent_id": list(CONSUMER_IDS) + ["battery_agent"]}},
    "agent_reconnect": {"label": "Reconnect agent", "params": {"agent_id": list(CONSUMER_IDS) + ["battery_agent"]}},
    "recovery": {"label": "Restore supply / recovery", "params": {"scope": "full | grid",
                                                                  "available_mw": "optional grid target"}},
}


class EventError(ValueError):
    pass


def _num(params: dict, key: str, default: float, lo: float, hi: float) -> float:
    v = params.get(key, default)
    try:
        v = float(v)
    except (TypeError, ValueError):
        raise EventError(f"'{key}' must be a number")
    if not lo <= v <= hi:
        raise EventError(f"'{key}' must be within [{lo}, {hi}]")
    return v


def apply_event(city: CityState, etype: EventType, params: dict[str, Any]) -> dict[str, Any]:
    """Apply an event to ground truth. Returns a description dict for logs/alerts."""
    g, b, cs = city.grid, city.battery, city.consumers
    severity = "warning"
    if etype == EventType.POWER_REDUCTION:
        before = g.available
        if params.get("available_mw") is not None:
            g.available = _num(params, "available_mw", before, 0, g.nominal_capacity)
        else:
            pct = _num(params, "percent", 30, 0, 95)
            g.available = round(before * (1 - pct / 100), 3)
        g.health = round(g.available / g.nominal_capacity, 3)
        text = f"Grid supply dropped from {before:.0f} MW to {g.available:.0f} MW."
        severity = "critical"
    elif etype == EventType.FLOOD_WARNING:
        sev = int(_num(params, "severity", 2, 1, 3))
        city.hazards.flood_severity = sev
        em = cs["emergency_agent"]
        em.active_operations = True
        em.demand = round(min(em.base_demand * (1 + 0.15 * sev), em.max_allowed), 3)
        w = cs["water_agent"]
        w.demand = round(min(w.base_demand * (1 + 0.05 * sev), w.max_allowed), 3)
        before = g.available
        g.available = round(g.available * (1 - 0.08 * sev), 3)
        text = (f"Flood (severity {sev}): rescue operations active, drainage pumping increased, "
                f"substation flooding cut grid supply {before:.0f} → {g.available:.0f} MW.")
        severity = "critical"
    elif etype == EventType.HOSPITAL_DEMAND_SPIKE:
        add = _num(params, "additional_mw", 20, 1, 40)
        h = cs["hospital_agent"]
        h.demand = round(min(h.demand + add, h.max_allowed), 3)
        h.extra_min = round(min(h.extra_min + add * 0.5, h.max_allowed - h.min_safe), 3)
        text = f"Mass-casualty intake: hospital demand +{add:.0f} MW (ICU minimum +{add*0.5:.0f} MW)."
    elif etype == EventType.WATER_PUMP_FAILURE:
        frac = _num(params, "capacity_fraction", 0.4, 0.1, 0.9)
        w = cs["water_agent"]
        w.operational_capacity = frac
        w.health = round(min(w.health, 0.6), 3)
        text = f"Water pumping station failure: only {frac*100:.0f}% of pumps operational."
        severity = "critical"
    elif etype == EventType.TELECOM_OUTAGE:
        frac = _num(params, "capacity_fraction", 0.5, 0.1, 0.9)
        t = cs["telecom_agent"]
        t.operational_capacity = frac
        t.health = round(min(t.health, 0.7), 3)
        text = f"Telecom tower outage: {frac*100:.0f}% of network capacity remains."
        severity = "critical"
    elif etype == EventType.BATTERY_DEPLETION:
        soc = _num(params, "soc", b.reserve_fraction + 0.02, b.reserve_fraction, 1.0)
        before = b.soc
        b.soc = soc
        text = f"Battery storage depleted: state of charge {before*100:.0f}% → {soc*100:.0f}%."
    elif etype in (EventType.AGENT_DISCONNECT, EventType.AGENT_RECONNECT):
        aid = params.get("agent_id")
        connect = etype == EventType.AGENT_RECONNECT
        if aid in cs:
            cs[aid].connected = connect
        elif aid == "battery_agent":
            b.connected = connect
        else:
            raise EventError("agent_id must be a consumer agent or battery_agent")
        text = f"{aid} {'reconnected' if connect else 'lost connection (heartbeat timeout)'}."
    elif etype == EventType.RECOVERY:
        scope = params.get("scope", "full")
        if scope not in ("full", "grid"):
            raise EventError("scope must be 'full' or 'grid'")
        before = g.available
        g.available = _num(params, "available_mw", g.nominal_capacity, 0, g.nominal_capacity)
        g.health = round(g.available / g.nominal_capacity, 3)
        g.sensor_faults.clear()
        g.supply_override = None
        if scope == "full":
            city.hazards.flood_severity = 0
            city.hazards.seismic_g = 0.0
            for c in cs.values():
                c.demand = c.base_demand
                c.extra_min = 0.0
                c.operational_capacity = 1.0
                c.active_operations = False
                c.health = max(c.health, 0.9)
        text = f"Recovery ({scope}): grid supply restored {before:.0f} → {g.available:.0f} MW."
        severity = "info"
    else:  # pragma: no cover
        raise EventError(f"unknown event {etype}")
    return {"event_type": etype.value, "params": params, "description": text, "severity": severity}


SCENARIOS: dict[str, dict[str, Any]] = {
    "grid_shortage": {
        "description": "Grid at 200 MW (illustrative initial state); battery bridges the gap until depleted.",
        "initial": "grid_shortage",
        "script": [],
    },
    "flood_cascade": {
        "description": "Shortage, hospital surge, flood, pump failure, then staged recovery.",
        "initial": "grid_shortage",
        "script": [
            (3, "hospital_demand_spike", {"additional_mw": 15}),
            (6, "flood_warning", {"severity": 2}),
            (9, "water_pump_failure", {"capacity_fraction": 0.5}),
            (12, "telecom_outage", {"capacity_fraction": 0.6}),
            (18, "recovery", {"scope": "grid", "available_mw": 260}),
            (24, "recovery", {"scope": "full"}),
        ],
    },
    "normal": {"description": "Nominal supply 320 MW, no deficit.", "initial": "normal", "script": []},
}

assert set(CONSUMER_PROFILES) == set(CONSUMER_IDS)
