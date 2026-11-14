"""Consumer utility agents: Hospital, Water, Telecom, Emergency Services.

Each agent owns its policy. Concessions follow a time-dependent schedule
(the acceptable floor drops by ``concession_rate`` of flexible demand per
round) that is modulated by each agent's local situation. Agents never go
below their hard safe minimum, and they decide for themselves how much of a
requested reduction to accept.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from app.agents.base import BaseAgent
from app.models.state import CONSUMER_PROFILES, ConsumerProfile, ConsumerState


@dataclass
class Estimate:
    demand: float
    min_safe: float
    flexible: float
    urgency: float
    notes: list[str] = field(default_factory=list)


@dataclass
class Decision:
    new_bid: float
    released: float
    kind: str        # "concession" | "partial" | "hold"
    text: str
    reason: str
    conditions: dict = field(default_factory=dict)


def dependents_weight(agent_id: str) -> float:
    """Extra harm this utility's shortage causes downstream (dependency graph)."""
    total = 0.0
    for other in CONSUMER_PROFILES.values():
        k = other.dependencies.get(agent_id)
        if k:
            total += 0.5 * k * other.damage_weight
    return total


class ConsumerAgent(BaseAgent):
    def __init__(self, profile: ConsumerProfile, secret: bytes, dt_minutes: int):
        super().__init__(secret)
        self.agent_id = profile.agent_id
        self.profile = profile
        self.dt_minutes = dt_minutes
        self.local: ConsumerState | None = None
        self.estimate_: Estimate | None = None
        self.stubborn = False  # set by tests/fault-injection to simulate a non-cooperative agent

    # ---- perception --------------------------------------------------------
    def observe_local(self, local: ConsumerState) -> None:
        self.local = local

    def situational_multiplier(self) -> float:
        return 1.0

    def estimate(self) -> Estimate:
        assert self.observation is not None and self.local is not None
        # The regulated/verified minimum is exact; the meter is noisy and never read below the minimum.
        min_safe = self.observation.consumer_mins.get(self.agent_id, self.profile.min_safe)
        demand = self.observation.consumer_meters.get(self.agent_id, self.local.effective_demand)
        demand = min(max(demand, min_safe), self.profile.max_allowed)
        urgency = self.profile.damage_weight * self.situational_multiplier() + dependents_weight(self.agent_id)
        self.estimate_ = Estimate(round(demand, 3), round(min_safe, 3), round(demand - min_safe, 3), round(urgency, 3))
        return self.estimate_

    # ---- policy ------------------------------------------------------------
    def effective_rate(self) -> float:
        return 0.05 if self.stubborn else self.profile.concession_rate

    def floor(self, round_no: float) -> float:
        e = self.estimate_
        assert e is not None
        return e.min_safe + e.flexible * max(0.0, 1.0 - self.effective_rate() * round_no)

    def decide_concession(self, round_no: int, requested: float, current_bid: float) -> Decision:
        e = self.estimate_
        assert e is not None
        room = max(0.0, current_bid - self.floor(round_no))
        release = round(min(requested, room), 3)
        new_bid = round(current_bid - release, 3)
        if release <= 1e-3:
            return Decision(current_bid, 0.0, "hold", self.say_hold(current_bid), "at acceptable floor for this round")
        if release + 1e-3 < requested:
            return Decision(new_bid, release, "partial", self.say_partial(release, new_bid, requested),
                            "bounded concession this round")
        return Decision(new_bid, release, "concession", self.say_concede(release, new_bid), "concession within policy")

    def decide_peer_request(self, round_no: int, asked: float, requester: str, current_bid: float) -> Decision:
        """A peer asks this agent directly to release capacity."""
        room = max(0.0, current_bid - self.floor(round_no + 0.5)) * self.profile.peer_grant_fraction
        grant = round(min(asked, room), 3)
        if grant <= 1e-3:
            return Decision(current_bid, 0.0, "hold", self.say_peer_reject(requester, current_bid),
                            "no further safe flexibility")
        new_bid = round(current_bid - grant, 3)
        kind = "concession" if grant + 1e-3 >= asked else "partial"
        return Decision(new_bid, grant, kind, self.say_peer_grant(requester, grant, new_bid, kind == "partial"),
                        "peer concession", self.conditions())

    def conditions(self) -> dict:
        return {}

    # ---- phrasing (presentation only; protocol uses the structured fields) --
    def say_request(self, e: Estimate) -> str:
        return f"Requesting {e.demand:.0f} MW. Minimum safe level is {e.min_safe:.0f} MW."

    def say_concede(self, release: float, bid: float) -> str:
        return f"Releasing {release:.1f} MW. New position: {bid:.1f} MW."

    def say_partial(self, release: float, bid: float, requested: float) -> str:
        return f"Can release {release:.1f} of the {requested:.1f} MW asked this round. Holding {bid:.1f} MW."

    def say_hold(self, bid: float) -> str:
        return f"Cannot reduce further this round. Holding {bid:.1f} MW."

    def say_peer_grant(self, requester: str, grant: float, bid: float, partial: bool) -> str:
        pre = "Counteroffer:" if partial else "Accepted:"
        return f"{pre} releasing {grant:.1f} MW for @{requester}. Now at {bid:.1f} MW."

    def say_peer_reject(self, requester: str, bid: float) -> str:
        return f"@{requester} request declined — {bid:.1f} MW is our minimum workable level right now."

    def say_shortfall(self, alloc: float, min_safe: float) -> str:
        return f"EMERGENCY: allocation {alloc:.1f} MW is {min_safe - alloc:.1f} MW below our safe minimum."


class HospitalAgent(ConsumerAgent):
    def situational_multiplier(self) -> float:
        return 1.3 if self.local and self.local.extra_min > 0 else 1.0

    def say_request(self, e: Estimate) -> str:
        return f"Requesting {e.demand:.0f} MW. ICU operations require a minimum of {e.min_safe:.0f} MW."

    def say_concede(self, release: float, bid: float) -> str:
        return (f"We cannot reduce ICU power. We can defer {release:.1f} MW of non-critical "
                f"consumption — holding {bid:.1f} MW.")

    def say_partial(self, release: float, bid: float, requested: float) -> str:
        return (f"Only {release:.1f} MW of administrative load can be deferred this round "
                f"(asked {requested:.1f}). Holding {bid:.1f} MW to protect ICU and theatres.")

    def say_hold(self, bid: float) -> str:
        return f"ICU and emergency wards cannot be reduced further. Holding {bid:.1f} MW."

    def say_shortfall(self, alloc: float, min_safe: float) -> str:
        return (f"CRITICAL: {alloc:.1f} MW is {min_safe - alloc:.1f} MW below ICU minimum. "
                f"Switching non-ICU wards to backup generators and deferring elective procedures.")


class WaterAgent(ConsumerAgent):
    DURATION_LIMIT_MIN = 120

    def limit_reached(self) -> bool:
        return bool(self.local and self.local.ticks_conceding * self.dt_minutes >= self.DURATION_LIMIT_MIN)

    def effective_rate(self) -> float:
        base = super().effective_rate()
        return base * 0.5 if self.limit_reached() else base

    def floor(self, round_no: float) -> float:
        f = super().floor(round_no)
        if self.limit_reached():
            e = self.estimate_
            f = max(f, e.min_safe + 0.5 * e.flexible)
        return f

    def conditions(self) -> dict:
        return {"duration_limit_minutes": self.DURATION_LIMIT_MIN}

    def say_request(self, e: Estimate) -> str:
        return f"Requesting {e.demand:.0f} MW. We can temporarily operate at {e.min_safe:.0f} MW."

    def say_concede(self, release: float, bid: float) -> str:
        if self.limit_reached():
            return (f"Two-hour reduced-pumping limit already reached. Releasing only {release:.1f} MW; "
                    f"holding {bid:.1f} MW to restore reservoir pressure.")
        return f"Reducing non-essential pumping by {release:.1f} MW to {bid:.1f} MW, subject to a two-hour limit."

    def say_hold(self, bid: float) -> str:
        if self.limit_reached():
            return f"Two-hour reduced-pumping limit reached — reservoir pressure must recover. Holding {bid:.1f} MW."
        return f"Essential pumping only. Holding {bid:.1f} MW."

    def say_peer_grant(self, requester: str, grant: float, bid: float, partial: bool) -> str:
        pre = "Partial counteroffer:" if partial else "Counteroffer accepted,"
        return f"{pre} releasing {grant:.1f} MW for @{requester}, subject to a two-hour limit. Now at {bid:.1f} MW."

    def say_shortfall(self, alloc: float, min_safe: float) -> str:
        return (f"WARNING: {alloc:.1f} MW is below essential pumping ({min_safe:.0f} MW). "
                f"Water pressure to hospitals and hydrants will drop.")


class TelecomAgent(ConsumerAgent):
    def say_request(self, e: Estimate) -> str:
        flex = e.flexible * self.profile.concession_rate
        return f"Requesting {e.demand:.0f} MW. We can release {flex:.0f} MW of flexible network capacity."

    def say_concede(self, release: float, bid: float) -> str:
        return f"Releasing {release:.1f} MW of flexible network capacity. Emergency channels protected at {bid:.1f} MW."

    def say_hold(self, bid: float) -> str:
        return f"Remaining load carries emergency communication cores. Holding {bid:.1f} MW."

    def say_shortfall(self, alloc: float, min_safe: float) -> str:
        return (f"WARNING: {alloc:.1f} MW is below core network minimum ({min_safe:.0f} MW). "
                f"Shedding consumer traffic; emergency dispatch channels at risk.")


class EmergencyAgent(ConsumerAgent):
    def situational_multiplier(self) -> float:
        return 1.5 if self.local and self.local.active_operations else 1.0

    def effective_rate(self) -> float:
        base = super().effective_rate()
        return min(base, 0.15) if self.local and self.local.active_operations else base

    def say_request(self, e: Estimate) -> str:
        state = "active" if self.local and self.local.active_operations else "on standby"
        return f"Requesting {e.demand:.0f} MW. Rescue operations are {state}. Minimum {e.min_safe:.0f} MW."

    def say_concede(self, release: float, bid: float) -> str:
        return f"Deferring {release:.1f} MW of non-urgent station load; {bid:.1f} MW keeps response units online."

    def say_partial(self, release: float, bid: float, requested: float) -> str:
        if self.local and self.local.active_operations:
            return (f"Rescue operations are active — can only release {release:.1f} MW this round "
                    f"(asked {requested:.1f}). Holding {bid:.1f} MW.")
        return super().say_partial(release, bid, requested)

    def say_shortfall(self, alloc: float, min_safe: float) -> str:
        return (f"CRITICAL: {alloc:.1f} MW is below response minimum ({min_safe:.0f} MW). "
                f"Prioritising life-safety dispatch; non-urgent stations going dark.")


AGENT_CLASSES = {
    "hospital_agent": HospitalAgent,
    "water_agent": WaterAgent,
    "telecom_agent": TelecomAgent,
    "emergency_agent": EmergencyAgent,
}
