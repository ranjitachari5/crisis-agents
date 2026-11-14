"""Ground-truth city state for the discrete-time simulation.

Agents never read this directly: they observe it through telemetry
(see ``simulation/telemetry.py``), which can be noisy or faulty.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone

CONSUMER_IDS = ("hospital_agent", "water_agent", "telecom_agent", "emergency_agent")
SUPPLIER_IDS = ("grid_agent", "battery_agent")
AGENT_IDS = CONSUMER_IDS + SUPPLIER_IDS

SIM_START = datetime(2026, 7, 14, 6, 0, tzinfo=timezone.utc)


@dataclass
class ConsumerProfile:
    """Static configuration of a consuming utility (illustrative values)."""
    agent_id: str
    name: str
    base_demand: float      # MW
    min_safe: float         # MW: hard minimum for critical services
    max_allowed: float      # MW: physical connection / nameplate limit
    damage_weight: float    # harm per MW of unmet flexible demand per hour
    critical_weight: float  # harm per MW below the safe minimum per hour
    concession_rate: float  # fraction of flexible demand released per round
    peer_grant_fraction: float  # how generously it answers peer requests
    dependencies: dict[str, float] = field(default_factory=dict)  # upstream -> coupling


CONSUMER_PROFILES: dict[str, ConsumerProfile] = {
    "hospital_agent": ConsumerProfile(
        "hospital_agent", "Hospital Agent", 100, 85, 130, 10, 100, 0.34, 0.5,
        {"water_agent": 0.35, "telecom_agent": 0.15}),
    "water_agent": ConsumerProfile(
        "water_agent", "Water Agent", 70, 55, 90, 6, 60, 0.30, 1.0, {}),
    "telecom_agent": ConsumerProfile(
        "telecom_agent", "Telecom Agent", 50, 30, 60, 7, 70, 0.50, 1.0, {}),
    "emergency_agent": ConsumerProfile(
        "emergency_agent", "Emergency Services Agent", 60, 35, 80, 8, 80, 0.30, 0.5,
        {"water_agent": 0.30, "telecom_agent": 0.35}),
}


@dataclass
class ConsumerState:
    agent_id: str
    base_demand: float
    demand: float
    min_safe: float
    max_allowed: float
    extra_min: float = 0.0             # added critical load (e.g. ICU surge)
    health: float = 1.0                # physical asset health 0..1
    operational_capacity: float = 1.0  # usable fraction of the asset (failures)
    connected: bool = True
    isolated: bool = False
    active_operations: bool = False    # emergency agent: rescue under way
    allocation: float = 0.0
    service_level: float = 1.0         # effective service after cascades
    ticks_below_min: int = 0
    ticks_conceding: int = 0           # consecutive ticks served below demand

    @property
    def effective_demand(self) -> float:
        return round(min(self.demand * self.operational_capacity, self.max_allowed), 3)

    @property
    def effective_min(self) -> float:
        return round(min(self.min_safe + self.extra_min, self.effective_demand), 3)


@dataclass
class GridState:
    nominal_capacity: float = 320.0
    available: float = 200.0
    health: float = 1.0
    sensor_faults: dict[int, float] = field(default_factory=dict)  # sensor idx -> forced reading
    supply_override: float | None = None  # commander-confirmed value


@dataclass
class BatteryState:
    capacity_mwh: float = 120.0
    soc: float = 0.8
    reserve_fraction: float = 0.2
    max_discharge_mw: float = 30.0
    max_charge_mw: float = 20.0
    discharge_mw: float = 0.0   # positive = discharging, negative = charging
    health: float = 1.0
    connected: bool = True

    @property
    def usable_energy_mwh(self) -> float:
        return max(0.0, (self.soc - self.reserve_fraction) * self.capacity_mwh)


@dataclass
class Hazards:
    flood_severity: int = 0          # 0 none .. 3 severe
    seismic_g: float = 0.0
    active_alerts: list[dict] = field(default_factory=list)


@dataclass
class CityState:
    tick: int = 0
    sim_time: datetime = SIM_START
    scenario: str = "grid_shortage"
    consumers: dict[str, ConsumerState] = field(default_factory=dict)
    grid: GridState = field(default_factory=GridState)
    battery: BatteryState = field(default_factory=BatteryState)
    hazards: Hazards = field(default_factory=Hazards)

    def to_dict(self) -> dict:
        d = asdict(self)
        d["sim_time"] = self.sim_time.isoformat()
        for cid, c in self.consumers.items():
            d["consumers"][cid]["effective_demand"] = c.effective_demand
            d["consumers"][cid]["effective_min"] = c.effective_min
        d["battery"]["usable_energy_mwh"] = round(self.battery.usable_energy_mwh, 3)
        return d


def initial_city(scenario: str = "grid_shortage") -> CityState:
    consumers = {
        cid: ConsumerState(cid, p.base_demand, p.base_demand, p.min_safe, p.max_allowed)
        for cid, p in CONSUMER_PROFILES.items()
    }
    grid = GridState()
    if scenario == "normal":
        grid.available = grid.nominal_capacity
    return CityState(scenario=scenario, consumers=consumers, grid=grid)
