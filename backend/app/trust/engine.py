"""Crisis Trust Engine.

Deterministic verification of every message before it can influence the
negotiation: Ed25519 authentication, schema, freshness/replay/sequence,
telemetry comparison, independent cross-type corroboration and
consistency/authority checks. Unverified claims are quarantined and can never
directly change a committed allocation.
"""
from __future__ import annotations

from collections import OrderedDict
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Callable

from pydantic import ValidationError

from app.schemas.messages import AgentMessage, MessageType, new_id, utcnow
from app.simulation.telemetry import GRID_SENSOR_IDS, SENSOR_TYPES, TelemetrySnapshot
from app.trust import crypto
from app.trust.consensus import ConsensusResult, sensor_consensus, tolerance
from app.trust.crypto import PublicKeyRegistry

CONSUMERS = {"hospital_agent", "water_agent", "telecom_agent", "emergency_agent"}
# Who is authoritative for which kind of claim.
AUTHORITY = {
    "grid_capacity": {"grid_agent"},
    "recovery": {"grid_agent", "simulation", "commander"},
    "disaster_alert": {"simulation", "commander"},
}
HIGH_IMPACT_FRACTION = 0.2
MIN_CORROBORATING_TYPES = 2
SEEN_CACHE_MAX = 20_000
HARD_FAIL = {"source_authentication", "schema_validation", "unique_message_id", "timestamp_freshness",
             "wallclock_freshness", "sequence_monotonic", "sender_not_isolated"}

# (agent_id, message_id) -> True if newly recorded, False if already seen (durable store, F4)
ReplayStore = Callable[[str, str], bool]


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
    consensus: ConsensusResult | None = None   # the engine's current grid assessment, if available


class TrustEngine:
    def __init__(self, public_keys: PublicKeyRegistry, replay_store: ReplayStore | None = None,
                 max_age_s: float = 300.0, clock_skew_s: float = 30.0):
        self.keys = public_keys
        self.replay_store = replay_store
        self.max_age_s = max_age_s
        self.clock_skew_s = clock_skew_s
        self.seen: OrderedDict[tuple[str, str], datetime] = OrderedDict()   # TTL cache in front of the store
        self.last_seq: dict[str, int] = {}
        self.reputation: dict[str, float] = {a: 1.0 for a in public_keys.participants()}
        self.sensor_reputation: dict[str, float] = {s: 1.0 for s in GRID_SENSOR_IDS}
        self.incidents: list[TrustIncident] = []
        self.quarantine: list[dict] = []

    # ------------------------------------------------------------------ replay
    def _prune_seen(self, now: datetime, ttl: timedelta) -> None:
        # Entries older than the freshness window + skew can no longer pass the freshness check.
        while self.seen:
            key, t = next(iter(self.seen.items()))
            if now - t > ttl or len(self.seen) > SEEN_CACHE_MAX:
                self.seen.popitem(last=False)
            else:
                break

    def _is_duplicate(self, msg: AgentMessage) -> bool:
        return (msg.sender, msg.message_id) in self.seen

    def _record(self, msg: AgentMessage) -> bool:
        """Record an authenticated message id. Returns False if the durable store has seen it."""
        self.seen[(msg.sender, msg.message_id)] = msg.sim_time
        if self.replay_store is not None:
            return self.replay_store(msg.sender, msg.message_id)
        return True

    # ------------------------------------------------------------------ verify
    def verify(self, msg: AgentMessage, ctx: TrustContext) -> VerificationResult:
        ev: list[Evidence] = []
        tel = ctx.telemetry

        # 1. authenticate source (Ed25519, public keys only)
        known = msg.sender in self.keys or msg.sender in self.reputation
        public_key = self.keys.public_key(msg.sender, msg.kid) if known else None
        auth_ok = public_key is not None and crypto.verify(msg.signing_payload(), msg.signature, public_key)
        if not known:
            detail = f"sender '{msg.sender}' is not a registered participant"
        elif self.keys.is_revoked(msg.kid):
            detail = f"key {msg.kid} for '{msg.sender}' has been revoked"
        elif public_key is None:
            detail = f"unknown key id {msg.kid!r} for '{msg.sender}'"
        elif not auth_ok:
            detail = f"Ed25519 signature invalid for '{msg.sender}' (tampering or identity spoofing)"
        else:
            detail = f"Ed25519 signature valid for '{msg.sender}' (kid {msg.kid})"
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

        # 3. freshness (sim time and wall clock), unique ids, per-agent sequence (replay protection)
        window = timedelta(minutes=ctx.dt_minutes)
        self._prune_seen(ctx.sim_time, window * 2)
        duplicate = self._is_duplicate(msg)
        age = ctx.sim_time - msg.sim_time
        fresh = -window <= age <= window
        wall_age = (utcnow() - msg.timestamp).total_seconds()
        wall_fresh = -self.clock_skew_s <= wall_age <= self.max_age_s
        seq_ok, seq_detail = True, "sequence not tracked"
        if auth_ok:
            last = self.last_seq.get(msg.sender, 0)
            if msg.agent_seq is None:
                seq_ok, seq_detail = False, "authenticated message carries no agent sequence number"
            elif msg.agent_seq <= last:
                seq_ok, seq_detail = False, f"sequence {msg.agent_seq} <= last seen {last} (replay or reordering)"
            else:
                gap = msg.agent_seq - last - 1
                seq_detail = f"sequence {msg.agent_seq} > {last}" + (f" ({gap} message(s) not seen)" if gap else "")
            if not duplicate and fresh and wall_fresh and seq_ok:
                if not self._record(msg):
                    duplicate = True  # durable store has it: replay across a restart
        ev.append(Evidence("unique_message_id", not duplicate,
                           "message id already processed (replay)" if duplicate else "message id is new"))
        ev.append(Evidence("timestamp_freshness", fresh,
                           f"message sim-time {msg.sim_time.isoformat()} vs now {ctx.sim_time.isoformat()} "
                           f"(age {age.total_seconds()/60:.0f} min, window ±{ctx.dt_minutes} min)"))
        ev.append(Evidence("wallclock_freshness", wall_fresh,
                           f"sent {wall_age:.1f} s ago (allowed -{self.clock_skew_s:.0f} s .. {self.max_age_s:.0f} s)"))
        if auth_ok:
            ev.append(Evidence("sequence_monotonic", seq_ok, seq_detail))
            if seq_ok and not duplicate:
                self.last_seq[msg.sender] = msg.agent_seq or 0

        # 4-6. content checks against trusted telemetry
        telemetry_contradicted = False
        telemetry_unavailable = False
        high_impact = False
        uncorroborated_claim = False
        cons = ctx.consensus or sensor_consensus(tel.grid_sensors, self.sensor_weights())
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
            try:
                claimed = float(claimed)
            except (TypeError, ValueError):
                claimed = float("nan")
            if claimed != claimed or cons.median is None:  # NaN claim or no trusted reference
                telemetry_unavailable = True
                ev.append(Evidence("telemetry_comparison", False,
                                   "no trusted reference available "
                                   f"({cons.reason.lower().replace('_', ' ') if cons.median is None else 'invalid claim'})",
                                   None if claimed != claimed else claimed, None))
            else:
                tol = tolerance(cons.median)
                ok = abs(claimed - cons.median) <= tol
                ev.append(Evidence("telemetry_comparison", ok,
                                   f"claimed {claimed:.1f} MW vs sensor consensus {cons.median:.1f} MW "
                                   f"(tolerance ±{tol:.1f})", claimed, cons.median))
                telemetry_contradicted = not ok
                high_impact = abs(claimed - cons.median) > HIGH_IMPACT_FRACTION * max(cons.median, 1.0)
            # Corroboration must come from independent source *types* (SCADA, PMU, grid agent report),
            # so two co-located sensors of the same type cannot carry a supply cut or a recovery alone.
            sources = [GRID_SENSOR_IDS[i] for i, r in enumerate(tel.grid_sensors)
                       if claimed == claimed and abs(r - claimed) <= tolerance(r)]
            types = {SENSOR_TYPES[s] for s in sources}
            if ctx.last_grid_report is not None and msg.sender != "grid_agent" and claimed == claimed and \
                    abs(ctx.last_grid_report - claimed) <= tolerance(ctx.last_grid_report) + 2:
                sources.append("grid_agent_report")
                types.add("grid_agent")
            corroborated = len(types) >= MIN_CORROBORATING_TYPES
            ev.append(Evidence("independent_corroboration", corroborated,
                               f"{len(types)} independent source type(s) agree: "
                               f"{sorted(types) or 'none'} via {sources or 'none'}", len(types),
                               f">={MIN_CORROBORATING_TYPES}"))
            # Routine grid supply reports restate the consensus; explicit claims must be corroborated.
            uncorroborated_claim = msg.message_type == MessageType.CLAIM and not corroborated
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
        failed = [e.check for e in ev if not e.passed]
        if any(f in HARD_FAIL for f in failed):
            decision = TrustDecision.REJECTED
        elif telemetry_contradicted:
            decision = TrustDecision.QUARANTINED
        elif telemetry_unavailable and high_impact:
            decision = TrustDecision.ESCALATED
        elif telemetry_unavailable or uncorroborated_claim:
            decision = TrustDecision.QUARANTINED
        else:
            decision = TrustDecision.ACCEPTED
        score = round(sum(e.passed for e in ev) / max(len(ev), 1), 3)
        summary = (f"{decision.value.upper()}: " +
                   ("all checks passed" if not failed else "failed " + ", ".join(failed)))

        # reputation: only penalise authenticated, fresh, in-sequence senders (spoofs are not their fault)
        if auth_ok and not duplicate and fresh and wall_fresh and seq_ok and msg.sender in self.reputation:
            if decision in (TrustDecision.QUARANTINED, TrustDecision.REJECTED):
                self.reputation[msg.sender] = round(max(0.0, self.reputation[msg.sender] - 0.25), 3)
            elif decision == TrustDecision.ACCEPTED:
                self.reputation[msg.sender] = round(min(1.0, self.reputation[msg.sender] + 0.01), 3)
        return VerificationResult(decision, score, ev, summary)

    # ------------------------------------------------------------------ sensors
    def sensor_weights(self) -> list[float]:
        return [self.sensor_reputation[s] for s in GRID_SENSOR_IDS]

    def update_sensor_reputation(self, cons: ConsensusResult) -> None:
        """Decay sensors that are repeatedly outvoted; slowly restore the ones that agree."""
        if cons.status == "ambiguous":
            return
        for i, sid in enumerate(GRID_SENSOR_IDS):
            r = self.sensor_reputation[sid]
            self.sensor_reputation[sid] = round(min(1.0, r + 0.02) if i in cons.agreeing else max(0.1, r - 0.1), 3)

    def assess_sensors(self, tel: TelemetrySnapshot) -> ConsensusResult:
        return sensor_consensus(tel.grid_sensors, self.sensor_weights())

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
            self.quarantine = self.quarantine[-1000:]
        self.incidents = self.incidents[-2000:]
        return inc

    def get_incident(self, incident_id: str) -> TrustIncident | None:
        return next((i for i in self.incidents if i.incident_id == incident_id), None)
