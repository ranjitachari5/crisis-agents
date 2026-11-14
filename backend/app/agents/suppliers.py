"""Supply-side agents: Grid (telemetry publisher) and Battery (storage)."""
from __future__ import annotations

from dataclasses import dataclass

from app.agents.base import BaseAgent
from app.simulation.telemetry import GRID_SENSOR_IDS
from app.trust.consensus import ConsensusResult, sensor_consensus


@dataclass
class GridAssessment:
    consensus: ConsensusResult
    verified_supply: float | None   # after reserve margin; None if ambiguous
    raw_value: float | None
    margin: float
    nominal: float
    override: bool = False

    @property
    def ok(self) -> bool:
        return self.verified_supply is not None


class GridAgent(BaseAgent):
    """Publishes verified supply. Has NO authority to allocate power."""
    agent_id = "grid_agent"
    RESERVE_MARGIN_FRAC = 0.005

    def __init__(self, secret: bytes, nominal_capacity: float):
        super().__init__(secret)
        self.nominal = nominal_capacity
        self.last_reported: float | None = None

    def assess(self, override: float | None = None) -> GridAssessment:
        assert self.observation is not None
        cons = sensor_consensus(self.observation.grid_sensors)
        if override is not None:
            margin = max(0.5, override * self.RESERVE_MARGIN_FRAC)
            return GridAssessment(cons, round(override - margin, 3), override, margin, self.nominal, True)
        if cons.value is None:
            return GridAssessment(cons, None, None, 0.0, self.nominal)
        margin = max(0.5, cons.value * self.RESERVE_MARGIN_FRAC)
        return GridAssessment(cons, round(max(0.0, cons.value - margin), 3), cons.value, margin, self.nominal)

    def describe(self, a: GridAssessment) -> str:
        if not a.ok:
            readings = ", ".join(f"{s}={v:.1f}" for s, v in zip(GRID_SENSOR_IDS, self.observation.grid_sensors))
            return f"Sensor disagreement — cannot verify supply ({readings}). Escalating to commander."
        drop = (1 - a.raw_value / self.nominal) * 100 if self.nominal else 0
        parts = []
        if drop > 1:
            parts.append(f"Power supply is {drop:.0f}% below nominal {self.nominal:.0f} MW.")
        else:
            parts.append(f"Power supply at nominal ({a.raw_value:.0f} MW).")
        parts.append(f"Verified available capacity: {a.verified_supply:.1f} MW "
                     f"(after {a.margin:.1f} MW reserve margin).")
        if a.consensus.outliers:
            bad = ", ".join(GRID_SENSOR_IDS[i] for i in a.consensus.outliers)
            parts.append(f"Excluded inconsistent sensor(s): {bad}.")
        if a.override:
            parts.append("Value confirmed by commander override.")
        return " ".join(parts)


class BatteryAgent(BaseAgent):
    agent_id = "battery_agent"

    def __init__(self, secret: bytes, dt_hours: float):
        super().__init__(secret)
        self.dt_hours = dt_hours

    def capability(self) -> float:
        assert self.observation is not None
        return self.observation.battery_max_discharge_mw

    def decide_offer(self, requested: float, critical_need: bool, round_no: int) -> tuple[float, str, str]:
        """Discharge offer policy.

        Full capability is released only when safe minimums are at stake or the
        deficit persists into round 2+. Otherwise the agent offers half to
        preserve reserve for later critical shortfalls.
        """
        o = self.observation
        cap = self.capability()
        if cap <= 1e-3:
            return 0.0, (f"Cannot discharge: state of charge {o.battery_soc*100:.0f}% is at the protected "
                         f"reserve."), "reserve limit"
        conserve = not critical_need and round_no < 2
        offer = round(min(requested, cap * (0.5 if conserve else 1.0)), 3)
        hours = o.battery_usable_mwh / offer if offer > 0 else float("inf")
        if conserve:
            text = (f"Offering {offer:.1f} MW (half of {cap:.1f} MW available). Conserving reserve: "
                    f"no safe minimum is at risk yet. SoC {o.battery_soc*100:.0f}%.")
            reason = "conserving reserve for critical shortfalls"
        else:
            text = (f"Offering {offer:.1f} MW discharge. Sustainable for ~{hours:.1f} h at this rate "
                    f"(SoC {o.battery_soc*100:.0f}%, reserve floor protected).")
            reason = "critical demand at risk" if critical_need else "persistent deficit"
        return offer, text, reason
