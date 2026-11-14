"""Trusted telemetry: noisy, independently-sourced sensor readings of the city.

The trust engine and the grid agent use these readings, never ground truth.
Sensor faults (simulated hardware failure / tampering) are applied here.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

import numpy as np

from app.models.state import CityState

GRID_SENSOR_IDS = ("scada_substation_a", "scada_substation_b", "pmu_feeder_c")
# Measurement technology per sensor: corroboration must span different types (F5).
SENSOR_TYPES = {"scada_substation_a": "scada", "scada_substation_b": "scada", "pmu_feeder_c": "pmu"}


@dataclass
class TelemetrySnapshot:
    tick: int
    sim_time: datetime
    grid_sensors: list[float]
    battery_soc: float
    battery_usable_mwh: float
    battery_max_discharge_mw: float
    consumer_meters: dict[str, float]
    consumer_mins: dict[str, float]
    consumer_max: dict[str, float]
    flood_gauges_m: list[float]
    seismic_g: list[float]
    connected: dict[str, bool] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "tick": self.tick,
            "sim_time": self.sim_time.isoformat(),
            "grid_sensors": dict(zip(GRID_SENSOR_IDS, self.grid_sensors)),
            "battery_soc": self.battery_soc,
            "battery_usable_mwh": self.battery_usable_mwh,
            "battery_max_discharge_mw": self.battery_max_discharge_mw,
            "consumer_meters": self.consumer_meters,
            "flood_gauges_m": self.flood_gauges_m,
            "seismic_g": self.seismic_g,
        }


class TelemetryService:
    def __init__(self, rng: np.random.Generator, dt_hours: float):
        self.rng = rng
        self.dt_hours = dt_hours

    def read(self, city: CityState) -> TelemetrySnapshot:
        g = city.grid
        sensors = []
        for i in range(len(GRID_SENSOR_IDS)):
            if i in g.sensor_faults:
                sensors.append(round(g.sensor_faults[i], 2))
            else:
                sensors.append(round(float(g.available + self.rng.normal(0, 0.4)), 2))
        b = city.battery
        max_dis = 0.0
        if b.connected:
            max_dis = min(b.max_discharge_mw, b.usable_energy_mwh / self.dt_hours)
        meters = {
            cid: round(max(float(c.effective_demand * (1 + self.rng.normal(0, 0.003))), c.effective_min), 2)
            for cid, c in city.consumers.items()
        }
        flood_base = 0.4 + 1.1 * city.hazards.flood_severity
        return TelemetrySnapshot(
            tick=city.tick,
            sim_time=city.sim_time,
            grid_sensors=sensors,
            battery_soc=round(b.soc, 4),
            battery_usable_mwh=round(b.usable_energy_mwh, 3),
            battery_max_discharge_mw=round(max_dis, 3),
            consumer_meters=meters,
            consumer_mins={cid: c.effective_min for cid, c in city.consumers.items()},
            consumer_max={cid: c.max_allowed for cid, c in city.consumers.items()},
            flood_gauges_m=[round(float(flood_base + self.rng.normal(0, 0.05)), 2) for _ in range(2)],
            seismic_g=[round(float(abs(city.hazards.seismic_g + self.rng.normal(0, 0.003))), 4)
                       for _ in range(2)],
            connected={cid: c.connected and not c.isolated for cid, c in city.consumers.items()},
        )
