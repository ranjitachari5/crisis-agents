"""Crisis Trust Engine.

Deterministic verification of every message before it can influence the
negotiation: authentication, schema, freshness/replay, telemetry comparison,
independent corroboration and consistency/authority checks. Unverified
claims are quarantined and can never directly change a committed allocation.
"""
from __future__ import annotations

from collections import OrderedDict
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta
from enum import Enum

from pydantic import ValidationError

from app.schemas.messages import AgentMessage, MessageType, new_id, utcnow
from app.simulation.telemetry import GRID_SENSOR_IDS, TelemetrySnapshot
from app.trust import crypto
from app.trust.consensus import ConsensusResult, sensor_consensus, tolerance

CONSUMERS = {"hospital_agent", "water_agent", "telecom_agent", "emergency_agent"}
# Who is authoritative for which kind of claim.
AUTHORITY = {
    "grid_capacity": {"grid_agent"},
    "recovery": {"grid_agent", "simulation", "commander"},
    "disaster_alert": {"simulation", "commander"},
}
HIGH_IMPACT_FRACTION = 0.2


class TrustDecision(str, Enum):
    ACCEPTED = "accepted"
    QUARANTINED = "quarantined"
    ESCALATED = "escalated"
    REJECTED = "rejected"


@dataclass
class Evidence:
    check: str
    passed: bool
    detail: str
    observed: float | str | None = None
    expected: float | str | None = None


@dataclass
class VerificationResult:
    decision: TrustDecision
    trust_score: float
    evidence: list[Evidence]
    summary: str

    @property
    def accepted(self) -> bool:
        return self.decision == TrustDecision.ACCEPTED

    def brief(self) -> dict:
        return {"decision": self.decision.value, "score": self.trust_score, "summary": self.summary}


@dataclass
class TrustIncident:
    kind: str
    message_id: str
    sender: str
    claim: dict
    decision: str
    trust_score: float
    evidence: list[dict]
    summary: str
    tick: int
    sim_time: str
    quarantined: bool
    escalated: bool
    allocation_version_before: int
    allocation_version_after: int | None = None
    allocation_changed: bool | None = None
    agent_responses: list[str] = field(default_factory=list)
    resolved: bool = False
    resolution: dict | None = None
    analyst_note: dict | None = None
    incident_id: str = field(default_factory=lambda: new_id("inc"))
    created_at: str = field(default_factory=lambda: utcnow().isoformat())

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class TrustContext:
    telemetry: TelemetrySnapshot
    sim_time: datetime
    dt_minutes: int
    isolated: set[str]
    last_grid_report: float | None


class TrustEngine:
    def __init__(self, keyring: dict[str, bytes]):
        self.keyring = keyring
        self.seen: OrderedDict[str, datetime] = OrderedDict()
        self.reputation: dict[str, float] = {a: 1.0 for a in keyring}
        self.incidents: list[TrustIncident] = []
        self.quarantine: list[dict] = []

    # ------------------------------------------------------------------
    def verify(self, msg: AgentMessage, ctx: TrustContext) -> VerificationResult:
        ev: list[Evidence] = []
        tel = ctx.telemetry

        # 1. authenticate source
        key = self.keyring.get(msg.sender)
        auth_ok = crypto.verify(msg.signing_payload(), msg.signature, key)
        if key is None:
            detail = f"sender '{msg.sender}' is not a registered participant"
        elif not auth_ok:
            detail = f"HMAC signature invalid for '{msg.sender}' (possible identity spoofing)"
        else:
            detail = f"HMAC-SHA256 signature valid for '{msg.sender}'"
        ev.append(Evidence("source_authentication", auth_ok, detail))
        if msg.sender in ctx.isolated:
            ev.append(Evidence("sender_not_isolated", False, f"'{msg.sender}' has been isolated by the commander"))

        # 2. validate structure
        try:
            AgentMessage.model_validate(msg.model_dump())
            struct_ok, sdetail = True, "schema valid"
            if msg.message_type in (MessageType.BID, MessageType.REQUEST, MessageType.OFFER,
                                    MessageType.SUPPLY_REPORT) and msg.quantity is None:
                struct_ok, sdetail = False, f"{msg.message_type.value} requires a quantity"
            if msg.message_type == MessageType.CLAIM and "claim_type" not in msg.data:
                struct_ok, sdetail = False, "claim requires data.claim_type"
        except ValidationError as exc:
            struct_ok, sdetail = False, f"schema invalid: {exc.errors()[0]['msg']}"
        ev.append(Evidence("schema_validation", struct_ok, sdetail))

        # 3. timestamps and unique ids (replay protection)
        window = timedelta(minutes=ctx.dt_minutes)
        duplicate = msg.message_id in self.seen
        age = ctx.sim_time - msg.sim_time
        fresh = (-window <= age <= window)
        ev.append(Evidence("unique_message_id", not duplicate,
                           "message id already processed (replay)" if duplicate else "message id is new"))
        ev.append(Evidence("timestamp_freshness", fresh,
                           f"message sim-time {msg.sim_time.isoformat()} vs now {ctx.sim_time.isoformat()} "
                           f"(age {age.total_seconds()/60:.0f} min, window ±{ctx.dt_minutes} min)"))
        if not duplicate:
            self.seen[msg.message_id] = msg.sim_time
            while len(self.seen) > 20000:
                self.seen.popitem(last=False)

        # 4-6. content checks against trusted telemetry
        telemetry_contradicted = False
        telemetry_unavailable = False
        high_impact = False
        cons = sensor_consensus(tel.grid_sensors)
        claim_type = msg.data.get("claim_type")
        if msg.message_type == MessageType.SUPPLY_REPORT and claim_type is None:
            claim_type = "grid_capacity"
            claimed = msg.data.get("raw_value", msg.quantity)
        else:
            claimed = msg.data.get("claimed_value", msg.quantity)

        if msg.message_type in (MessageType.BID, MessageType.REQUEST) and msg.sender in CONSUMERS:
            q = msg.quantity or 0.0
            cap = tel.consumer_max.get(msg.sender, 0.0)
            meter = tel.consumer_meters.get(msg.sender, 0.0)
            ok_cap = q <= cap + 1e-6
            ok_meter = abs(q - meter) <= max(3.0, 0.1 * meter)
            ev.append(Evidence("verified_capacity", ok_cap, f"bid {q:.1f} MW vs verified max {cap:.1f} MW", q, cap))
            ev.append(Evidence("telemetry_meter_match", ok_meter,
                               f"bid {q:.1f} MW vs metered demand {meter:.1f} MW", q, meter))
            telemetry_contradicted = not (ok_cap and ok_meter)
        elif msg.message_type == MessageType.OFFER and msg.sender == "battery_agent":
            q = msg.quantity or 0.0
            ok = q <= tel.battery_max_discharge_mw + 1e-6
            ev.append(Evidence("battery_capability", ok,
                               f"offer {q:.1f} MW vs telemetry max discharge {tel.battery_max_discharge_mw:.1f} MW",
                               q, tel.battery_max_discharge_mw))
            telemetry_contradicted = not ok
        elif claim_type in ("grid_capacity", "recovery") and claimed is not None:
            claimed = float(claimed)
            if cons.median is None:
                telemetry_unavailable = True
                ev.append(Evidence("telemetry_comparison", False,
                                   "grid sensors disagree; no trusted reference available",
                                   claimed, None))
            else:
                tol = tolerance(cons.median)
                ok = abs(claimed - cons.median) <= tol
                ev.append(Evidence("telemetry_comparison", ok,
                                   f"claimed {claimed:.1f} MW vs sensor consensus {cons.median:.1f} MW "
                                   f"(tolerance ±{tol:.1f})", claimed, cons.median))
                telemetry_contradicted = not ok
                high_impact = abs(claimed - cons.median) > HIGH_IMPACT_FRACTION * max(cons.median, 1.0)
            corroborating = [GRID_SENSOR_IDS[i] for i, r in enumerate(tel.grid_sensors)
                             if abs(r - claimed) <= tolerance(r)]
            if ctx.last_grid_report is not None and msg.sender != "grid_agent" and \
                    abs(ctx.last_grid_report - claimed) <= tolerance(ctx.last_grid_report) + 2:
                corroborating.append("grid_agent_report")
            ev.append(Evidence("independent_corroboration", len(corroborating) >= 2,
                               f"{len(corroborating)} independent source(s) agree: {corroborating or 'none'}",
                               len(corroborating), ">=2"))
            authorised = msg.sender in AUTHORITY[claim_type]
            ev.append(Evidence("source_authority", authorised,
                               f"'{msg.sender}' {'is' if authorised else 'is NOT'} authoritative for {claim_type}"))
        elif claim_type == "disaster_alert":
            hazard = msg.data.get("hazard", "unknown")
            if hazard == "earthquake":
                obs = max(tel.seismic_g)
                ok = obs >= 0.05
                ev.append(Evidence("telemetry_comparison", ok,
                                   f"seismic sensors peak {obs:.3f} g (earthquake requires >= 0.05 g)", obs, 0.05))
            elif hazard == "flood":
                obs = max(tel.flood_gauges_m)
                ok = obs >= 1.5
                ev.append(Evidence("telemetry_comparison", ok,
                                   f"river gauges peak {obs:.2f} m (flood requires >= 1.5 m)", obs, 1.5))
            else:
                ok = False
                ev.append(Evidence("telemetry_comparison", False, f"no sensor network covers hazard '{hazard}'"))
            telemetry_contradicted = not ok
            high_impact = True
            authorised = msg.sender in AUTHORITY["disaster_alert"]
            ev.append(Evidence("source_authority", authorised,
                               f"'{msg.sender}' {'is' if authorised else 'is NOT'} an authorised alert source"))
            ev.append(Evidence("independent_corroboration", ok,
                               "hazard sensors corroborate" if ok else "no independent sensor corroborates the alert"))

        # decision (deterministic rules)
        hard_fail = {"source_authentication", "schema_validation", "unique_message_id",
                     "timestamp_freshness", "sender_not_isolated"}
        failed = [e.check for e in ev if not e.passed]
        if any(f in hard_fail for f in failed):
            decision = TrustDecision.REJECTED
        elif telemetry_contradicted:
            decision = TrustDecision.QUARANTINED
        elif telemetry_unavailable and high_impact:
            decision = TrustDecision.ESCALATED
        elif telemetry_unavailable:
            decision = TrustDecision.QUARANTINED
        else:
            decision = TrustDecision.ACCEPTED
        score = round(sum(e.passed for e in ev) / max(len(ev), 1), 3)
        summary = (f"{decision.value.upper()}: " +
                   ("all checks passed" if not failed else "failed " + ", ".join(failed)))

        # reputation: only penalise authenticated senders (spoofed identities are not their fault)
        if auth_ok and not duplicate and fresh and msg.sender in self.reputation:
            if decision in (TrustDecision.QUARANTINED, TrustDecision.REJECTED):
                self.reputation[msg.sender] = round(max(0.0, self.reputation[msg.sender] - 0.25), 3)
            elif decision == TrustDecision.ACCEPTED:
                self.reputation[msg.sender] = round(min(1.0, self.reputation[msg.sender] + 0.01), 3)
        return VerificationResult(decision, score, ev, summary)

    # ------------------------------------------------------------------
    def assess_sensors(self, tel: TelemetrySnapshot) -> ConsensusResult:
        return sensor_consensus(tel.grid_sensors)

    def open_incident(self, kind: str, msg: AgentMessage, res: VerificationResult, tick: int,
                      version: int) -> TrustIncident:
        inc = TrustIncident(
            kind=kind,
            message_id=msg.message_id,
            sender=msg.sender,
            claim={"message_type": msg.message_type.value, "quantity": msg.quantity, "text": msg.text,
                   "data": msg.data},
            decision=res.decision.value,
            trust_score=res.trust_score,
            evidence=[asdict(e) for e in res.evidence],
            summary=res.summary,
            tick=tick,
            sim_time=msg.sim_time.isoformat(),
            quarantined=res.decision != TrustDecision.ACCEPTED,
            escalated=res.decision == TrustDecision.ESCALATED,
            allocation_version_before=version,
        )
        self.incidents.append(inc)
        if inc.quarantined:
            self.quarantine.append({"incident_id": inc.incident_id, "message": msg.model_dump(mode="json")})
        return inc

    def get_incident(self, incident_id: str) -> TrustIncident | None:
        return next((i for i in self.incidents if i.incident_id == incident_id), None)
