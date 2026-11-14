"""Service levels, dependency graph and cascading-failure propagation.

effective_service_i = power_service_i * asset_service_i
                      * prod_{d in deps(i)} (1 - k_id * (1 - effective_service_d))
Derived city services (ICU, hospital water, firefighting, dispatch) are
computed from the utility service levels, so a water pump failure visibly
propagates to hospital water availability and firefighting capacity.
"""
from __future__ import annotations

from typing import Any

from app.models.state import CONSUMER_PROFILES, CityState

ORDER = ("water_agent", "telecom_agent", "hospital_agent", "emergency_agent")  # topological

DERIVED_SERVICES: dict[str, dict[str, Any]] = {
    "svc_icu": {"label": "ICU life support", "inputs": {"hospital_agent": 1.0}},
    "svc_hospital_water": {"label": "Hospital water availability", "inputs": {"water_agent": 1.0}},
    "svc_firefighting": {"label": "Firefighting capacity", "inputs": {"water_agent": 0.5, "emergency_agent": 0.5}},
    "svc_dispatch": {"label": "Emergency dispatch comms", "inputs": {"telecom_agent": 0.6, "emergency_agent": 0.4}},
}


def power_service(alloc: float, demand: float, min_safe: float) -> float:
    if demand <= 1e-6:
        return 1.0
    s = min(1.0, alloc / demand)
    if alloc < min_safe - 1e-3 and min_safe > 0:
        s *= max(0.0, alloc / min_safe)  # below minimum, service collapses quickly
    return s


def compute_service_levels(city: CityState) -> dict[str, dict]:
    levels: dict[str, dict] = {}
    for aid in ORDER:
        c = city.consumers[aid]
        ps = power_service(c.allocation, c.effective_demand, c.effective_min)
        if not c.connected:
            ps = min(ps, 1.0)
        asset = c.health * c.operational_capacity
        eff = ps * asset
        cascade_from = []
        for up, k in CONSUMER_PROFILES[aid].dependencies.items():
            up_eff = levels[up]["effective"]
            factor = 1 - k * (1 - up_eff)
            if factor < 0.999:
                cascade_from.append({"from": up, "loss": round(1 - factor, 4)})
            eff *= factor
        levels[aid] = {
            "power_service": round(ps, 4),
            "asset_service": round(asset, 4),
            "effective": round(max(0.0, eff), 4),
            "cascade_from": cascade_from,
        }
        c.service_level = levels[aid]["effective"]
    return levels


def derived_services(levels: dict[str, dict], city: CityState) -> dict[str, dict]:
    out = {}
    for sid, spec in DERIVED_SERVICES.items():
        if sid == "svc_icu":
            h = city.consumers["hospital_agent"]
            val = 1.0 if h.allocation >= h.effective_min - 1e-3 else max(0.0, h.allocation / max(h.effective_min, 1e-6))
            val *= h.health
        else:
            val = sum(levels[a]["effective"] * w for a, w in spec["inputs"].items())
        out[sid] = {"label": spec["label"], "level": round(val, 4), "inputs": list(spec["inputs"])}
    return out


def cascade_chains(levels: dict[str, dict], derived: dict[str, dict], city: CityState) -> list[dict]:
    """Human-readable cascades rooted at degraded utilities."""
    chains = []
    names = {"water_agent": "Water pumping", "telecom_agent": "Telecom network",
             "hospital_agent": "Hospital", "emergency_agent": "Emergency services"}
    for root in ORDER:
        if levels[root]["effective"] >= 0.95:
            continue
        c = city.consumers[root]
        cause = ("asset failure" if c.operational_capacity < 1 or c.health < 0.9
                 else "power shortfall" if c.allocation < c.effective_demand - 0.5 else "dependency loss")
        path = [f"{names[root]} degraded to {levels[root]['effective']*100:.0f}% ({cause})"]
        for down in ORDER:
            for edge in levels[down]["cascade_from"]:
                if edge["from"] == root and edge["loss"] > 0.01:
                    path.append(f"{names[down]} service −{edge['loss']*100:.0f}%")
        for sid, d in derived.items():
            if root in d["inputs"] and d["level"] < 0.95:
                path.append(f"{d['label']} at {d['level']*100:.0f}%")
        if len(path) > 1:
            chains.append({"root": root, "cause": cause, "path": path})
    return chains


def build_graph(city: CityState, battery_flow: float, grid_flow: float) -> dict:
    levels = compute_service_levels(city)
    derived = derived_services(levels, city)

    def status(level: float) -> str:
        return "ok" if level >= 0.95 else "degraded" if level >= 0.6 else "critical"

    nodes = [
        {"id": "grid_agent", "type": "supply", "label": "Power Grid",
         "data": {"available_mw": city.grid.available, "nominal_mw": city.grid.nominal_capacity,
                  "health": city.grid.health,
                  "status": status(city.grid.available / city.grid.nominal_capacity)}},
        {"id": "battery_agent", "type": "storage", "label": "Battery Storage",
         "data": {"soc": round(city.battery.soc, 4), "discharge_mw": round(city.battery.discharge_mw, 3),
                  "status": "ok" if city.battery.soc > city.battery.reserve_fraction + 0.05 else "critical"}},
        {"id": "power_bus", "type": "bus", "label": "City Power Bus",
         "data": {"grid_flow_mw": round(grid_flow, 3), "battery_flow_mw": round(battery_flow, 3)}},
    ]
    edges = [
        {"id": "e-grid-bus", "source": "grid_agent", "target": "power_bus", "kind": "power",
         "data": {"mw": round(grid_flow, 3)}},
        {"id": "e-bat-bus", "source": "battery_agent", "target": "power_bus", "kind": "power",
         "data": {"mw": round(max(0.0, battery_flow), 3)}},
    ]
    for aid in ORDER:
        c = city.consumers[aid]
        lv = levels[aid]
        nodes.append({"id": aid, "type": "utility", "label": CONSUMER_PROFILES[aid].name,
                      "data": {"allocation_mw": c.allocation, "demand_mw": c.effective_demand,
                               "min_safe_mw": c.effective_min, "health": round(c.health, 4),
                               "operational_capacity": c.operational_capacity,
                               "connected": c.connected and not c.isolated, **lv,
                               "status": status(lv["effective"])}})
        edges.append({"id": f"e-bus-{aid}", "source": "power_bus", "target": aid, "kind": "power",
                      "data": {"mw": c.allocation}})
        for up, k in CONSUMER_PROFILES[aid].dependencies.items():
            edges.append({"id": f"e-{up}-{aid}", "source": up, "target": aid, "kind": "dependency",
                          "data": {"coupling": k, "active_cascade": any(e["from"] == up for e in lv["cascade_from"])}})
    for sid, d in derived.items():
        nodes.append({"id": sid, "type": "service", "label": d["label"],
                      "data": {"level": d["level"], "status": status(d["level"])}})
        for src in d["inputs"]:
            edges.append({"id": f"e-{src}-{sid}", "source": src, "target": sid, "kind": "service", "data": {}})
    return {"nodes": nodes, "edges": edges, "cascades": cascade_chains(levels, derived, city),
            "service_levels": levels, "derived_services": derived}
