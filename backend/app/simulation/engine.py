"""Discrete-time simulation engine: owns city state and orchestrates agents,
trust verification, negotiation, validation and versioned commits."""
from __future__ import annotations

import logging
import time
from datetime import timedelta
from typing import Any, Callable

import numpy as np

from app.agents.base import AGENT_META, MessageContext
from app.agents.registry import AgentRegistry
from app.config import Settings
from app.evaluation.metrics import MetricsTracker
from app.models.state import CONSUMER_IDS, CONSUMER_PROFILES, CityState, ConsumerProfile, ConsumerState, feeders, initial_city
from app.schemas import api as S
from app.negotiation.agreements import (CLOSED_STATES, Agreement, AgreementStore, AllocationProposal, CommitError,
                                        ProposalStatus)
from app.observability import (COMMITS, NEG_MESSAGES, NEG_ROUNDS, NEG_SECONDS, NEG_TOTAL, PROPOSALS_EXPIRED,
                               SOLVER_RUNS, SOLVER_SECONDS, TRUST_DECISIONS)
from app.negotiation.protocol import NegotiationInput, NegotiationProtocol
from app.optimization import baselines
from app.optimization.allocator import AllocationProblem, solve
from app.optimization.weights import critical_weights, damage_weights
from app.schemas.messages import AgentMessage, MessageStatus, MessageType, new_id, utcnow
from app.simulation.cascade import build_graph, compute_service_levels, derived_services, cascade_chains
from app.simulation.events import SCENARIOS, EventType, apply_event
from app.simulation.telemetry import GRID_SENSOR_IDS, TelemetryService
from app.trust.engine import TrustContext, TrustDecision, TrustEngine, TrustIncident
from app.trust.injector import build_fake_message
from app.validation.validator import AllocationConstraints, ValidationResult, validate_allocation

log = logging.getLogger(__name__)

ALLOCATION_MODES = ("negotiation", "centralized", "fixed_priority", "fcfs", "rolling_horizon",
                    "hidden_information")
FEATURE_DEFAULTS = {"trust_engine": True, "fallback_only": False, "negotiation_only": False}
RNG_STREAMS = ("telemetry", "agents", "injector", "negotiation", "fcfs")
ROLLING_HORIZON_TICKS = 8
STATUS_MAP = {
    TrustDecision.ACCEPTED: MessageStatus.VERIFIED,
    TrustDecision.QUARANTINED: MessageStatus.QUARANTINED,
    TrustDecision.ESCALATED: MessageStatus.QUARANTINED,
    TrustDecision.REJECTED: MessageStatus.REJECTED,
}


class EngineError(Exception):
    def __init__(self, code: str, message: str, status: int = 400, details: Any = None):
        super().__init__(message)
        self.code, self.message, self.status, self.details = code, message, status, details


class SimulationEngine:
    def __init__(self, settings: Settings, *, seed: int | None = None, scenario: str = "grid_shortage",
                 emit: Callable[[str, dict], None] | None = None, repo=None,
                 allocation_mode: str = "negotiation", max_history: int = 3000,
                 features: dict[str, bool] | None = None):
        if scenario not in SCENARIOS:
            raise EngineError("UNKNOWN_SCENARIO", f"unknown scenario '{scenario}'")
        if allocation_mode not in ALLOCATION_MODES:
            raise EngineError("UNKNOWN_MODE", f"unknown allocation mode '{allocation_mode}'")
        self.settings = settings
        self.seed = settings.random_seed if seed is None else seed
        self.scenario = scenario
        self.script = {t: (e, p) for t, e, p in SCENARIOS[scenario]["script"]}
        self.allocation_mode = allocation_mode
        unknown = set(features or {}) - set(FEATURE_DEFAULTS)
        if unknown:
            raise EngineError("UNKNOWN_FEATURE", f"unknown feature flags {sorted(unknown)}")
        self.features = {**FEATURE_DEFAULTS, **(features or {})}
        # One independent generator per component (F15): call order in one component never shifts another.
        streams = np.random.SeedSequence(self.seed).spawn(len(RNG_STREAMS))
        self.rngs = {name: np.random.default_rng(ss) for name, ss in zip(RNG_STREAMS, streams)}
        self.rng = self.rngs["telemetry"]
        self.order_rng = self.rngs["fcfs"]
        self.dt_minutes = settings.sim_minutes_per_tick
        self.dt_hours = self.dt_minutes / 60
        self.city: CityState = initial_city(SCENARIOS[scenario]["initial"])
        self.city.scenario = scenario
        self.registry = AgentRegistry(self.dt_minutes, self.city.grid.nominal_capacity)
        self.telemetry_service = TelemetryService(self.rng, self.dt_hours)
        self.trust = TrustEngine(self.registry.public_keys,
                                 replay_store=repo.record_message_id if repo else None,
                                 max_age_s=settings.message_max_age_s, clock_skew_s=settings.message_clock_skew_s)
        self.agreements = AgreementStore()
        self.protocol = NegotiationProtocol(self.submit, self.publish, self.registry.system["negotiation_protocol"])
        self.metrics = MetricsTracker(self.dt_hours)
        self._emit = emit
        self.repo = repo
        self.max_history = max_history
        self.session_id = new_id("run")
        if repo:
            repo.new_session(self.session_id, scenario, self.seed)

        self.status = "idle"
        self.fairness = 0.5
        self.approval_mode = "auto"
        self.approval_timeout_s = settings.approval_timeout_s
        self.approval_timeout_policy = settings.approval_timeout_policy
        self.negotiation_paused = False
        self.frozen = False
        self.messages: list[dict] = []
        self._msg_by_id: dict[str, dict] = {}
        self._seq = 0
        self.audit_log: list[dict] = []
        self.alerts: list[dict] = []
        self.events_log: list[dict] = []
        self.negotiations: list[dict] = []
        self.commit_hooks: list[Callable[[dict, AllocationProposal], None]] = []
        self._basis: dict | None = None
        self._force_reason: str | None = None
        self._sensor_status = "consensus"
        self._last_shed = 0.0
        self.baseline_allocation: dict[str, float] = {}
        self.refresh_telemetry()

    # ------------------------------------------------------------------ infra
    def emit(self, event: str, payload: dict) -> None:
        if self._emit:
            try:
                self._emit(event, payload)
            except Exception:  # pragma: no cover
                log.exception("emit failed")

    @property
    def headless(self) -> bool:
        return self._emit is None and self.repo is None

    @property
    def observed(self) -> bool:
        """Report to the process-wide Prometheus registry (live runs only, not evaluation engines)."""
        return not self.headless

    def ctx(self, negotiation_id: str | None = None) -> MessageContext:
        return MessageContext(self.city.tick, self.city.sim_time, negotiation_id)

    def publish(self, msg: AgentMessage) -> AgentMessage:
        self._seq += 1
        msg.seq = self._seq
        d = msg.model_dump(mode="json")
        self.messages.append(d)
        if len(self.messages) > self.max_history:
            self.messages = self.messages[-self.max_history:]
        self._msg_by_id[msg.message_id] = d
        if self.repo:
            self.repo.save_message(self.session_id, d)
        self.emit("message", d)
        return msg

    def set_status(self, message_id: str, status: MessageStatus) -> None:
        d = self._msg_by_id.get(message_id)
        if d is None or d["status"] == status.value:
            return
        d["status"] = status.value
        if self.repo:
            self.repo.update_message_status(self.session_id, message_id, status.value)
        self.emit("message_status", {"message_id": message_id, "seq": d["seq"], "status": status.value})

    def system_msg(self, actor: str, mtype: MessageType, text: str, **kw) -> AgentMessage:
        return self.publish(self.registry.system[actor].message(self.ctx(kw.pop("negotiation_id", None)),
                                                                 mtype, text, **kw))

    def audit(self, category: str, actor: str, action: str, details: dict | None = None) -> dict:
        entry = {"id": new_id("aud"), "tick": self.city.tick, "sim_time": self.city.sim_time.isoformat(),
                 "category": category, "actor": actor, "action": action, "details": details or {},
                 "created_at": utcnow().isoformat()}
        self.audit_log.append(entry)
        self.audit_log = self.audit_log[-5000:]
        if self.repo:
            self.repo.save_audit(self.session_id, entry)
        self.emit("audit", entry)
        return entry

    def alert(self, severity: str, title: str, detail: str, source: str) -> dict:
        a = {"id": new_id("alt"), "severity": severity, "title": title, "detail": detail, "source": source,
             "tick": self.city.tick, "sim_time": self.city.sim_time.isoformat(), "active": True}
        self.alerts.append(a)
        self.alerts = self.alerts[-200:]
        self.emit("alert", a)
        return a

    def acknowledge_alert(self, alert_id: str, actor: str = "commander") -> dict:
        a = next((x for x in self.alerts if x["id"] == alert_id), None)
        if a is None:
            raise EngineError("NOT_FOUND", "alert not found", 404)
        a["active"] = False
        self.audit("commander", actor, "acknowledge_alert", {"alert_id": alert_id})
        return a

    # ------------------------------------------------------------- telemetry
    def refresh_telemetry(self) -> None:
        self.telemetry = self.telemetry_service.read(self.city)
        for aid, agent in self.registry.consumers.items():
            agent.observe(self.telemetry)
            agent.observe_local(self.city.consumers[aid])
        self.registry.grid.observe(self.telemetry)
        self.registry.battery.observe(self.telemetry)
        self.grid_assessment = self.registry.grid.assess(self.city.grid.supply_override,
                                                         self.trust.sensor_weights())

    def trust_ctx(self) -> TrustContext:
        isolated = {aid for aid, c in self.city.consumers.items() if c.isolated}
        return TrustContext(self.telemetry, self.city.sim_time, self.dt_minutes, isolated,
                            self.registry.grid.last_reported, self.grid_assessment.consensus)

    def submit(self, msg: AgentMessage, kind: str | None = None) -> bool:
        if not self.features["trust_engine"]:  # evaluation ablation: everything is accepted unverified
            msg.trust = {"decision": "accepted", "score": None, "summary": "trust engine disabled (ablation)"}
            msg.status = MessageStatus.DELIVERED
            self.publish(msg)
            return True
        res = self.trust.verify(msg, self.trust_ctx())
        if self.observed:
            TRUST_DECISIONS.labels(decision=res.decision.value).inc()
        msg.trust = res.brief()
        msg.status = STATUS_MAP[res.decision]
        self.publish(msg)
        if not res.accepted:
            self._open_incident(kind or f"suspicious_{msg.message_type.value}", msg, res)
        return res.accepted

    def _open_incident(self, kind: str, msg: AgentMessage, res) -> TrustIncident:
        inc = self.trust.open_incident(kind, msg, res, self.city.tick, self.agreements.version)
        failed = [e.detail for e in res.evidence if not e.passed]
        ta = self.system_msg(
            "trust_engine", MessageType.TRUST_ALERT,
            f"{res.decision.value.upper()} — {msg.message_type.value} from @{msg.sender}: "
            f"{'; '.join(failed[:3]) or 'see evidence'}. "
            + ("Escalated to the human commander." if res.decision == TrustDecision.ESCALATED else
               "Quarantined: it cannot change the committed allocation."),
            in_reply_to=msg.message_id, mentions=[msg.sender] if msg.sender in self.registry.participants else [],
            data={"incident_id": inc.incident_id, "decision": res.decision.value, "trust_score": res.trust_score},
            resource=None)
        inc.agent_responses.append(ta.message_id)
        self.audit("trust", "trust_engine", f"incident_{res.decision.value}",
                   {"incident_id": inc.incident_id, "kind": kind, "sender": msg.sender, "summary": res.summary})
        if res.decision == TrustDecision.ESCALATED:
            self.alert("critical", "Trust escalation", f"Ambiguous high-impact claim from {msg.sender} "
                       f"requires a commander decision ({inc.incident_id}).", "trust_engine")
        rep = self.trust.reputation.get(msg.sender)
        if rep is not None and rep < 0.5 and msg.sender in self.city.consumers \
                and not self.city.consumers[msg.sender].isolated:
            self.alert("warning", "Low agent reputation",
                       f"{msg.sender} reputation {rep:.2f}. Consider isolating the agent.", "trust_engine")
        self._save_incident(inc)
        return inc

    def _save_incident(self, inc: TrustIncident) -> None:
        if self.repo:
            self.repo.save_incident(self.session_id, inc.to_dict())
        self.emit("trust_incident", inc.to_dict())

    def check_sensors(self) -> None:
        """Detect contradictory sensor reports every tick (independent of any claim)."""
        cons = self.grid_assessment.consensus
        status = "override" if self.grid_assessment.override else cons.status
        if status == self._sensor_status:
            return
        prev, self._sensor_status = self._sensor_status, status
        readings = dict(zip(GRID_SENSOR_IDS, self.telemetry.grid_sensors))
        if status == "majority":
            bad = [GRID_SENSOR_IDS[i] for i in cons.outliers]
            inc = TrustIncident(
                kind="contradictory_sensors", message_id="telemetry", sender="sensor_network",
                claim={"readings": readings}, decision=TrustDecision.ACCEPTED.value, trust_score=0.67,
                evidence=[{"check": "sensor_consensus", "passed": True,
                           "detail": f"robust consensus of {len(cons.agreeing)} sensors at {cons.median:.1f} MW",
                           "observed": cons.median,
                           "expected": None},
                          {"check": "outlier_detection", "passed": False,
                           "detail": f"{', '.join(bad)} disagrees with majority; excluded", "observed": None,
                           "expected": None}],
                summary=f"Faulty sensor(s) {bad} excluded as outliers (median/MAD); supply verification "
                        f"unaffected.",
                tick=self.city.tick, sim_time=self.city.sim_time.isoformat(), quarantined=True, escalated=False,
                allocation_version_before=self.agreements.version,
                allocation_version_after=self.agreements.version, allocation_changed=False)
            self.trust.incidents.append(inc)
            m = self.system_msg("trust_engine", MessageType.TRUST_ALERT,
                                f"Contradictory sensor reports: {readings}. {inc.summary}",
                                data={"incident_id": inc.incident_id}, resource=None)
            inc.agent_responses.append(m.message_id)
            self.audit("trust", "trust_engine", "sensor_outlier_excluded", {"incident_id": inc.incident_id,
                                                                             "readings": readings})
            self._save_incident(inc)
        elif status == "ambiguous":
            self.frozen = True
            inc = TrustIncident(
                kind="contradictory_sensors", message_id="telemetry", sender="sensor_network",
                claim={"readings": readings}, decision=TrustDecision.ESCALATED.value, trust_score=0.0,
                evidence=[{"check": "sensor_consensus", "passed": False,
                           "detail": (f"{cons.reason}: a majority asserts a large supply change while the "
                                      f"dissenting sensor still reads the last accepted value (possible correlated "
                                      f"fault)" if cons.reason == "UNCORROBORATED_STEP" else
                                      f"{cons.reason}: no robust consensus (spread {cons.spread:.1f} MW)"),
                           "observed": cons.spread, "expected": None}],
                summary="Grid sensors cannot be reconciled. Allocation frozen at last verified "
                        "agreement; commander decision required.",
                tick=self.city.tick, sim_time=self.city.sim_time.isoformat(), quarantined=True, escalated=True,
                allocation_version_before=self.agreements.version)
            self.trust.incidents.append(inc)
            m = self.system_msg("trust_engine", MessageType.TRUST_ALERT,
                                f"ESCALATED — contradictory grid sensors {readings}. {inc.summary}",
                                data={"incident_id": inc.incident_id}, resource=None)
            inc.agent_responses.append(m.message_id)
            g = self.registry.grid.message(self.ctx(), MessageType.EMERGENCY_WARNING,
                                           self.registry.grid.describe(self.grid_assessment), resource=None)
            self.submit(g)
            self.alert("critical", "Sensor contradiction", inc.summary, "trust_engine")
            self.audit("trust", "trust_engine", "sensor_ambiguity_escalated", {"incident_id": inc.incident_id,
                                                                                "readings": readings})
            self._save_incident(inc)
        elif status in ("consensus", "override") and prev == "ambiguous":
            self.frozen = False
            self._force_reason = "sensor consensus restored"

    # ---------------------------------------------------------- constraints
    def active_ids(self) -> list[str]:
        return [aid for aid, c in self.city.consumers.items() if c.connected and not c.isolated]

    def reserved(self) -> tuple[dict[str, float], dict[str, str]]:
        res, why = {}, {}
        for aid, c in self.city.consumers.items():
            if not c.connected or c.isolated:
                res[aid] = self.telemetry.consumer_mins[aid]
                why[aid] = "isolated by the commander" if c.isolated else "disconnected"
        return res, why

    def battery_capability(self) -> float:
        return self.telemetry.battery_max_discharge_mw if self.city.battery.connected else 0.0

    def ramp_limits(self) -> dict[str, float]:
        return {a: p.ramp_up_mw_per_min * self.dt_minutes for a, p in CONSUMER_PROFILES.items()}

    def previous_allocation(self) -> dict[str, float] | None:
        cur = self.agreements.current
        return dict(cur.allocation) if cur else None

    def upper_caps(self) -> dict[str, float] | None:
        """Per-agent ceiling for the next commit: nameplate limit and ramp limit vs the committed allocation."""
        prev = self.previous_allocation()
        if prev is None:
            return None
        ramp = self.ramp_limits()
        tel = self.telemetry
        # never below the safe minimum: restoring critical load is not ramp-limited
        return {a: min(tel.consumer_max[a], max(prev[a] + ramp[a], min(tel.consumer_mins[a], tel.consumer_meters[a])))
                for a in self.active_ids() if a in prev}

    def constraints(self, battery_offer: float) -> AllocationConstraints:
        reserved, _ = self.reserved()
        tel = self.telemetry
        return AllocationConstraints(
            version=self.agreements.version,
            grid_supply=self.grid_assessment.verified_supply or 0.0,
            battery_offer=min(battery_offer, self.battery_capability()),
            min_safe=dict(tel.consumer_mins), max_allowed=dict(tel.consumer_max),
            demand=dict(tel.consumer_meters), active_agents=self.active_ids(), reserved=reserved,
            previous=self.previous_allocation(), ramp_up=self.ramp_limits(), feeders=feeders(),
            battery_usable_mwh=tel.battery_usable_mwh if self.city.battery.connected else 0.0,
            dt_hours=self.dt_hours)

    def validate(self, allocation: dict[str, float], base_version: int, proposal_id: str,
                 battery_offer: float) -> ValidationResult:
        return validate_allocation(allocation, self.constraints(battery_offer), base_version, proposal_id,
                                   self.agreements.committed_ids)

    def central_problem(self, supply: float, reported: bool = False, respect_ramp: bool = True) -> AllocationProblem:
        """``reported=True``: the planner only sees what agents report (hidden-information baseline)."""
        tel = self.telemetry
        ids = self.active_ids()
        w, c = damage_weights(self.city), critical_weights()
        caps = (self.upper_caps() or {}) if respect_ramp else {}
        if reported:
            est = {i: self.registry.consumers[i].estimate() for i in ids}
            demand = {i: est[i].demand for i in ids}
            mins = {i: min(est[i].min_safe, est[i].demand) for i in ids}
        else:
            demand = {i: tel.consumer_meters[i] for i in ids}
            mins = {i: min(tel.consumer_mins[i], tel.consumer_meters[i]) for i in ids}
        return AllocationProblem(ids, demand, mins,
                                 {i: min(tel.consumer_max[i], caps.get(i, float("inf"))) for i in ids},
                                 {i: w[i] for i in ids}, {i: c[i] for i in ids}, supply, self.fairness,
                                 warm_start=self.previous_allocation())

    # ---------------------------------------------------------- negotiation
    def renegotiation_reason(self) -> str | None:
        if self._force_reason:
            return self._force_reason
        if self.agreements.current is None:
            return "initial allocation"
        b = self._basis
        verified = self.grid_assessment.verified_supply
        if b is None or verified is None:
            return None
        if abs(verified - b["supply"]) > 2.0:
            return f"verified supply changed {b['supply']:.0f} → {verified:.0f} MW"
        for aid, c in self.city.consumers.items():
            if abs(c.effective_demand - b["demands"].get(aid, 0.0)) > 3.0:
                return f"{aid} demand changed {b['demands'].get(aid, 0):.0f} → {c.effective_demand:.0f} MW"
        if set(self.active_ids()) != b["active"]:
            return "agent connectivity changed"
        if b.get("ramp_limited"):
            return "ramp-limited load restoration continuing (" + ", ".join(b["ramp_limited"]) + ")"
        cap = self.battery_capability()
        alloc_total = sum(self.agreements.current.allocation.values())
        required = max(0.0, alloc_total - verified)
        if required > cap + 0.05:
            return f"battery can no longer sustain {required:.1f} MW discharge (capability {cap:.1f} MW)"
        if cap - b["battery_cap"] > 5.0 and alloc_total < sum(b["demands"].values()) - 0.5:
            return f"battery capability recovered to {cap:.1f} MW"
        w = self.city.consumers["water_agent"]
        if w.ticks_conceding * self.dt_minutes == 120:
            return "water agent two-hour reduced-pumping limit reached"
        if self.city.tick - b["tick"] >= 8 and alloc_total < sum(b["demands"].values()) - 0.5:
            return "periodic reassessment (2 h)"
        return None

    def run_negotiation(self, trigger: str) -> dict | None:
        self._force_reason = None
        if self.allocation_mode != "negotiation":
            self.baseline_allocate()
            return None
        if self.frozen or self.grid_assessment.verified_supply is None:
            self.system_msg("negotiation_protocol", MessageType.SYSTEM,
                            f"Reassessment requested ({trigger}) but supply cannot be verified. Holding committed "
                            f"allocation v{self.agreements.version} pending commander decision.", resource=None)
            return None
        active = [self.registry.consumers[a] for a in self.active_ids()]
        reserved, why = self.reserved()
        inp = NegotiationInput(
            tick=self.city.tick, sim_time=self.city.sim_time, version=self.agreements.version,
            fairness=self.fairness, active=active, reserved=reserved, reserved_reason=why,
            grid_assessment=self.grid_assessment, grid=self.registry.grid,
            battery=self.registry.battery if self.city.battery.connected else None,
            trigger=trigger, max_rounds=self.settings.max_negotiation_rounds,
            upper_caps=self.upper_caps(), warm_start=self.previous_allocation(),
            fallback_only=self.features["fallback_only"], negotiation_only=self.features["negotiation_only"])
        seq0 = self._seq
        result = self.protocol.run(inp)
        n_messages = self._seq - seq0
        self.metrics.record_negotiation(result.latency_ms, result.rounds, result.outcome, n_messages,
                                        (result.solver or {}).get("solver"))
        if self.observed:
            NEG_TOTAL.labels(outcome=result.outcome).inc()
            NEG_ROUNDS.observe(result.rounds)
            NEG_MESSAGES.observe(n_messages)
            NEG_SECONDS.observe(result.latency_ms / 1000)
            if result.solver:
                SOLVER_RUNS.labels(solver=result.solver["solver"], status=result.solver["status"]).inc()
                SOLVER_SECONDS.observe(result.solver["solve_ms"] / 1000)
        self.agreements.register(result.proposal)
        self._basis = {"supply": self.grid_assessment.verified_supply, "tick": self.city.tick,
                       "demands": {a: c.effective_demand for a, c in self.city.consumers.items()},
                       "active": set(self.active_ids()), "battery_cap": self.battery_capability(),
                       "ramp_limited": result.ramp_limited}
        summary = result.summary()
        summary["messages"] = n_messages
        self.audit("negotiation", "negotiation_protocol", "negotiation_completed",
                   {k: summary[k] for k in ("negotiation_id", "proposal_id", "method", "rounds", "converged",
                                            "fallback_used", "degradation", "latency_ms", "outcome", "messages")})
        outcome = self.process_proposal(result.proposal, "negotiation_protocol", result.position_messages)
        summary["outcome"] = outcome
        self.negotiations.append(summary)
        self.negotiations = self.negotiations[-200:]
        self.emit("negotiation", summary)
        return summary

    def process_proposal(self, proposal: AllocationProposal, committed_by: str,
                         position_messages: dict[str, str] | None = None, allow_pending: bool = True) -> dict:
        v = self.validate(proposal.allocation, proposal.base_version, proposal.proposal_id, proposal.battery_offer)
        proposal.validation = v.to_dict()
        nid = proposal.negotiation_id
        if v.valid:
            txt = (f"Validation passed for {proposal.proposal_id}: total {v.total_allocated:.1f} MW ≤ verified "
                   f"supply {v.total_supply:.1f} MW; " +
                   ("DEGRADATION MODE — unavoidable shortages: " +
                    ", ".join(f"{k} −{s:.1f} MW" for k, s in v.unavoidable_shortages.items())
                    if v.degradation_mode else "all safe minimums satisfied; version current."))
        else:
            txt = (f"Validation FAILED for {proposal.proposal_id}: "
                   + "; ".join(f"{x.code}: {x.detail}" for x in v.violations[:4]))
        self.system_msg("negotiation_protocol", MessageType.VALIDATION, txt, negotiation_id=nid,
                        proposal_id=proposal.proposal_id, quantity=v.total_allocated,
                        data={"valid": v.valid, "violations": [x.code for x in v.violations],
                              "degradation_mode": v.degradation_mode})
        if not v.valid:
            proposal.status = ProposalStatus.REJECTED
            self.audit("agreement", "validator", "proposal_rejected",
                       {"proposal_id": proposal.proposal_id, "violations": v.to_dict()["violations"]})
            if committed_by == "negotiation_protocol" and not self.features["negotiation_only"]:
                return self._safety_fallback(f"validation failed for {proposal.proposal_id}")
            if committed_by == "negotiation_protocol":
                self._retain_last_valid(f"validation failed for {proposal.proposal_id} (no fallback: ablation)")
            return {"committed": False, "validation": v.to_dict()}
        proposal.status = ProposalStatus.VALIDATED
        current_ok = self._current_feasible()
        if allow_pending and self.approval_mode == "manual" and committed_by == "negotiation_protocol" and current_ok:
            proposal.awaiting_since = time.monotonic()
            for pid in self.agreements.supersede_awaiting(proposal):
                self.audit("agreement", "agreement_store", "proposal_superseded",
                           {"proposal_id": pid, "superseded_by": proposal.proposal_id})
            self.system_msg("negotiation_protocol", MessageType.SYSTEM,
                            f"Proposal {proposal.proposal_id} validated. Awaiting commander approval "
                            f"(manual approval mode). Current allocation v{self.agreements.version} stays in force"
                            + (f"; expires in {self.approval_timeout_s:.0f} s "
                               f"(policy: {self.approval_timeout_policy})." if self.approval_timeout_s > 0 else "."),
                            negotiation_id=nid, proposal_id=proposal.proposal_id, resource=None)
            self.alert("info", "Proposal awaiting approval", proposal.proposal_id, "negotiation_protocol")
            return {"committed": False, "pending_approval": True, "validation": v.to_dict()}
        return self.commit(proposal, v, committed_by, position_messages)

    def _current_feasible(self) -> bool:
        cur = self.agreements.current
        if cur is None:
            return False
        v = validate_allocation(cur.allocation, self.constraints(self.battery_capability()), self.agreements.version,
                                "__feasibility__", set())
        return v.valid

    def commit(self, proposal: AllocationProposal, v: ValidationResult, committed_by: str,
               position_messages: dict[str, str] | None = None) -> dict:
        persist = None
        if self.repo:
            def persist(ag: Agreement, base: int) -> str:
                return self.repo.commit_agreement(self.session_id, base, {**ag.to_dict(), "committed_by": committed_by})
        if not proposal.outcome:
            proposal.outcome = "override" if proposal.method == "commander_override" else proposal.method
        try:
            agreement, new = self.agreements.commit(proposal, v, committed_by, self.city.tick, persist)
        except CommitError as exc:
            self.audit("agreement", committed_by, "commit_rejected", {"proposal_id": proposal.proposal_id,
                                                                       "code": exc.code, "reason": str(exc)})
            raise EngineError(exc.code, str(exc), 409)
        if not new:
            return {"committed": False, "duplicate": True, "version": agreement.version}
        for aid, c in self.city.consumers.items():
            c.allocation = agreement.allocation.get(aid, 0.0)
        for pid in self.agreements.mark_stale_pending():
            self.audit("agreement", "agreement_store", "proposal_stale", {"proposal_id": pid})
        alloc_txt = ", ".join(f"{k.split('_')[0]} {x:.1f}" for k, x in agreement.allocation.items())
        self.system_msg("negotiation_protocol", MessageType.AGREEMENT,
                        f"Allocation v{agreement.version} verified and committed ({agreement.method}, by "
                        f"{committed_by}): {alloc_txt} MW. Battery discharge {agreement.battery_discharge:.1f} MW.",
                        negotiation_id=proposal.negotiation_id, proposal_id=proposal.proposal_id,
                        quantity=sum(agreement.allocation.values()), status=MessageStatus.COMMITTED,
                        data={"version": agreement.version, "allocation": agreement.allocation,
                              "degradation_mode": agreement.degradation_mode, "method": agreement.method,
                              "shortages": v.unavoidable_shortages})
        for mid in (position_messages or {}).values():
            self.set_status(mid, MessageStatus.ACCEPTED)
        d = agreement.to_dict()
        self.audit("agreement", committed_by, f"committed_v{agreement.version}",
                   {"proposal_id": proposal.proposal_id, "method": agreement.method, "outcome": agreement.outcome,
                    "allocation": agreement.allocation, "degradation_mode": agreement.degradation_mode})
        if self.observed:
            COMMITS.labels(outcome=agreement.outcome or "unknown").inc()
        self.metrics.record_commit(agreement.outcome)
        if agreement.degradation_mode:
            self.alert("critical", "Emergency degradation mode",
                       "Unavoidable shortages: " + ", ".join(f"{k} −{s:.1f} MW"
                                                             for k, s in v.unavoidable_shortages.items()),
                       "validator")
        self.emit("agreement", d)
        for hook in self.commit_hooks:
            try:
                hook(d, proposal)
            except Exception:  # pragma: no cover
                log.exception("commit hook failed")
        self.update_services()
        return {"committed": True, "version": agreement.version, "agreement": d}

    def _safety_fallback(self, reason: str, method: str = "safety_fallback") -> dict:
        """Deterministic emergency policy: constrained optimizer, validated, committed."""
        cap = self.battery_capability()
        reserved, _ = self.reserved()
        verified = self.grid_assessment.verified_supply or 0.0
        sol = solve(self.central_problem(max(0.0, verified + cap - sum(reserved.values()))))
        alloc = {**sol.allocation, **reserved}
        prop = AllocationProposal(allocation=alloc, base_version=self.agreements.version, method=method,
                                  supply_total=verified + cap, grid_supply=verified, battery_offer=cap,
                                  objective=sol.objective, tick=self.city.tick, notes=[reason], outcome="fallback",
                                  solver=sol.info.to_dict() if sol.info else None)
        self.agreements.register(prop)
        self.system_msg("negotiation_protocol", MessageType.EMERGENCY_WARNING,
                        f"Deterministic emergency policy engaged: {reason}.", proposal_id=prop.proposal_id,
                        resource=None)
        out = self.process_proposal(prop, "emergency_policy", allow_pending=False)
        if not out.get("committed"):
            self._retain_last_valid(f"emergency policy proposal {prop.proposal_id} also failed validation")
        return out

    def _retain_last_valid(self, reason: str) -> None:
        """Last link of the fallback chain: keep the last committed (validated) allocation in force."""
        self.audit("agreement", "emergency_policy", "last_valid_retained",
                   {"reason": reason, "version": self.agreements.version})
        self.system_msg("negotiation_protocol", MessageType.EMERGENCY_WARNING,
                        f"{reason}. Keeping last valid allocation v{self.agreements.version} in force.",
                        resource=None)

    def baseline_allocate(self) -> None:
        cap = self.battery_capability()
        reserved, _ = self.reserved()
        supply = max(0.0, (self.grid_assessment.verified_supply or 0.0) + cap - sum(reserved.values()))
        p = self.central_problem(supply, reported=self.allocation_mode == "hidden_information",
                                 respect_ramp=False)
        if self.allocation_mode in ("centralized", "hidden_information"):
            alloc = baselines.centralized_optimization(p)
        elif self.allocation_mode == "rolling_horizon":
            # Spread usable battery energy over the planning horizon instead of draining it now.
            budget = min(cap, self.telemetry.battery_usable_mwh / (ROLLING_HORIZON_TICKS * self.dt_hours)) \
                if self.city.battery.connected else 0.0
            p.supply = max(0.0, (self.grid_assessment.verified_supply or 0.0) + budget - sum(reserved.values()))
            alloc = baselines.centralized_optimization(p)
        elif self.allocation_mode == "fixed_priority":
            alloc = baselines.fixed_priority(p)
        else:
            order = list(self.order_rng.permutation(p.agent_ids))
            alloc = baselines.first_come_first_served(p, order)
        alloc = {**alloc, **reserved}
        self.baseline_allocation = alloc
        for aid, c in self.city.consumers.items():
            c.allocation = alloc.get(aid, 0.0)

    # ------------------------------------------------------------- physics
    def current_allocation(self) -> dict[str, float]:
        if self.allocation_mode != "negotiation":
            return dict(self.baseline_allocation)
        return dict(self.agreements.current.allocation) if self.agreements.current else {}

    def count_violations(self, alloc: dict[str, float]) -> int:
        if not alloc:
            return 0
        v = validate_allocation(alloc, self.constraints(self.battery_capability()), self.agreements.version,
                                "__metrics__", set())
        safety = {"OVER_CAPACITY", "BELOW_MIN_SAFE", "ABOVE_MAX", "BATTERY_LIMIT", "BATTERY_SOC", "FEEDER_CAP",
                  "NON_NUMERIC", "NON_FINITE_OR_NEGATIVE"}
        return sum(1 for x in v.violations if x.code in safety)

    def advance_physics(self) -> None:
        """Apply the allocation in force over the elapsed interval and record measured metrics."""
        alloc = self.current_allocation()
        violations = self.count_violations(alloc)  # against what was verified when it was applied
        b, g = self.city.battery, self.city.grid
        total = sum(alloc.values())
        need = total - g.available
        shed = 0.0
        if need > 0:
            max_dis = min(b.max_discharge_mw, b.usable_energy_mwh / self.dt_hours) if b.connected else 0.0
            dis = min(need, max_dis)
            shed = need - dis
        else:
            dis = -min(-need, b.max_charge_mw, (1 - b.soc) * b.capacity_mwh / self.dt_hours) if b.connected else 0.0
        b.soc = float(np.clip(b.soc - dis * self.dt_hours / b.capacity_mwh, 0.0, 1.0))
        b.discharge_mw = round(dis, 3)
        applied = dict(alloc)
        if shed > 1e-3 and total > 0:
            factor = (total - shed) / total
            applied = {k: x * factor for k, x in alloc.items()}
            self.alert("critical", "Physical load shedding",
                       f"Allocation exceeded real supply by {shed:.1f} MW; automatic under-frequency "
                       f"load shedding applied.", "grid")
        self._last_shed = shed
        for aid, c in self.city.consumers.items():
            c.allocation = round(applied.get(aid, 0.0), 3)
            if c.allocation < c.effective_min - 0.01:
                c.ticks_below_min += 1
                c.health = round(max(0.2, c.health - 0.02), 4)
            else:
                c.ticks_below_min = 0
                c.health = round(min(1.0, c.health + 0.01), 4)
            c.ticks_conceding = c.ticks_conceding + 1 if c.allocation < c.effective_demand - 0.5 else 0
        demand = {a: c.effective_demand for a, c in self.city.consumers.items()}
        mins = {a: c.effective_min for a, c in self.city.consumers.items()}
        supply = (self.grid_assessment.verified_supply or 0.0) + self.battery_capability()
        degradation = sum(mins.values()) > supply + 1e-3
        self.metrics.record(self.city.tick, {a: c.allocation for a, c in self.city.consumers.items()},
                            demand, mins, damage_weights(self.city), critical_weights(), supply, violations,
                            shed, degradation)
        for aid, c in self.city.consumers.items():
            c.allocation = round(alloc.get(aid, 0.0), 3)  # agreed allocation stays in force

    def update_services(self) -> dict:
        levels = compute_service_levels(self.city)
        return levels

    # --------------------------------------------------------------- control
    def start(self) -> dict:
        if self.status == "running":
            raise EngineError("ALREADY_RUNNING", "simulation already running", 409)
        first = self.status == "idle"
        self.status = "running"
        self.audit("simulation", "commander", "start" if first else "resume", {"scenario": self.scenario})
        if first:
            self.system_msg("simulation", MessageType.SYSTEM,
                            f"Simulation started: scenario '{self.scenario}' — {SCENARIOS[self.scenario]['description']}",
                            resource=None)
            self.run_negotiation("initial allocation")
        self.emit("state", self.snapshot())
        return {"status": self.status}

    def pause(self) -> dict:
        if self.status != "running":
            raise EngineError("NOT_RUNNING", "simulation is not running", 409)
        self.status = "paused"
        self.audit("simulation", "commander", "pause")
        self.emit("state", self.snapshot())
        return {"status": self.status}

    def resume(self) -> dict:
        if self.status != "paused":
            raise EngineError("NOT_PAUSED", "simulation is not paused", 409)
        return self.start()

    def step(self) -> dict:
        if self.status == "idle" and self.allocation_mode == "negotiation" and self.agreements.current is None:
            self.status = "paused"
            self.run_negotiation("initial allocation")
        self.advance_physics()
        self.city.tick += 1
        self.city.sim_time = self.city.sim_time + timedelta(minutes=self.dt_minutes)
        if self.city.tick in self.script:
            etype, params = self.script[self.city.tick]
            self.inject_event(etype, dict(params), actor="scenario", renegotiate=False)
        self.refresh_telemetry()
        self.trust.update_sensor_reputation(self.grid_assessment.consensus)
        self.check_sensors()
        if self.allocation_mode == "negotiation":
            reason = self.renegotiation_reason()
            if reason:
                if not self.negotiation_paused:
                    self.run_negotiation(reason)
                elif not self._current_feasible() and not self.frozen:
                    self._safety_fallback(f"{reason}; negotiation paused and current allocation infeasible")
                    self._force_reason = None
        else:
            self.baseline_allocate()
        self.update_services()
        if self._emit:
            self.emit("state", self.snapshot())
        return {"tick": self.city.tick, "sim_time": self.city.sim_time.isoformat()}

    # --------------------------------------------------------------- events
    def inject_event(self, event_type: str, params: dict[str, Any], actor: str = "commander",
                     renegotiate: bool = True) -> dict:
        try:
            etype = EventType(event_type)
        except ValueError:
            raise EngineError("UNKNOWN_EVENT", f"unknown event type '{event_type}'", 422)
        from app.simulation.events import EventError
        try:
            ev = apply_event(self.city, etype, params)
        except EventError as exc:
            raise EngineError("INVALID_EVENT_PARAMS", str(exc), 422)
        ev.update({"id": new_id("evt"), "tick": self.city.tick, "actor": actor,
                   "sim_time": self.city.sim_time.isoformat()})
        self.events_log.append(ev)
        m = self.registry.system["simulation"].message(
            self.ctx(), MessageType.EVENT, ev["description"], resource=None,
            data={"event_type": etype.value, "params": params, "actor": actor})
        self.submit(m)
        self.audit("event", actor, etype.value, ev)
        self.alert(ev["severity"], etype.value.replace("_", " ").title(), ev["description"], actor)
        self.refresh_telemetry()
        self.check_sensors()
        negotiation = None
        if renegotiate:
            reason = f"{etype.value.replace('_', ' ')} event"
            if self.allocation_mode == "negotiation" and not self.negotiation_paused:
                negotiation = self.run_negotiation(reason)
            elif self.allocation_mode != "negotiation":
                self.baseline_allocate()
            else:
                self._force_reason = reason
        else:
            self._force_reason = f"{etype.value.replace('_', ' ')} event"
        self.update_services()
        self.emit("state", self.snapshot())
        return {"event": ev, "negotiation": negotiation}

    def inject_fake(self, kind: str, params: dict[str, Any], actor: str = "commander") -> dict:
        from app.trust.injector import InjectionError
        before = self.agreements.version
        self.audit("trust", actor, f"inject_fake_{kind}", {"params": params})
        if kind == "contradictory_sensors":
            mode = params.get("mode", "single")
            avail = self.city.grid.available
            if mode == "single":
                self.city.grid.sensor_faults = {2: round(avail * 0.2, 1)}
            elif mode == "split":
                self.city.grid.sensor_faults = {1: round(avail * 0.6, 1), 2: round(avail * 0.2, 1)}
            elif mode == "correlated":
                # Two co-located/spoofed sensors agree on a fabricated supply cut.
                self.city.grid.sensor_faults = {0: round(avail * 0.3, 1), 1: round(avail * 0.3, 1)}
            else:
                raise EngineError("INVALID_PARAMS", "mode must be 'single', 'split' or 'correlated'", 422)
            self.refresh_telemetry()
            self.check_sensors()
            inc = next((i for i in reversed(self.trust.incidents) if i.kind == "contradictory_sensors"), None)
            if inc is None:
                raise EngineError("NO_EFFECT", "sensor state unchanged (fault already active?)", 409)
            self.emit("state", self.snapshot())
            return inc.to_dict()
        try:
            msg = build_fake_message(kind, params, self.registry, self.ctx(), self.messages,
                                     self.city.grid.nominal_capacity)
        except InjectionError as exc:
            raise EngineError("INVALID_INJECTION", str(exc), 422)
        accepted = self.submit(msg, kind)
        if accepted:  # pragma: no cover - would indicate a trust engine gap
            self.alert("warning", "Injected message accepted", f"{kind} passed verification", "trust_engine")
            return {"accepted": True, "message_id": msg.message_id}
        inc = self.trust.incidents[-1]
        verified = self.grid_assessment.verified_supply
        ctx = self.ctx()
        responses = []
        if kind in ("false_capacity_drop", "false_recovery", "fake_disaster_alert"):
            sensors = ", ".join(f"{v:.1f}" for v in self.telemetry.grid_sensors)
            responses.append(self.registry.grid.message(
                ctx, MessageType.REJECT,
                f"Disputing claim {msg.message_id}: my sensors read [{sensors}] MW. Verified supply remains "
                f"{verified:.1f} MW.", quantity=verified, in_reply_to=msg.message_id, reason="telemetry contradiction"))
        if kind == "inflated_bid":
            aid = msg.sender
            responses.append(self.registry.system["negotiation_protocol"].message(
                ctx, MessageType.SYSTEM,
                f"Bid from @{aid} excluded. Telemetry meter shows {self.telemetry.consumer_meters[aid]:.1f} MW; "
                f"verified max is {self.telemetry.consumer_max[aid]:.0f} MW.", mentions=[aid], resource=None))
        responses.append(self.registry.consumers["hospital_agent"].message(
            ctx, MessageType.SYSTEM,
            f"Acknowledged trust decision on {msg.message_id}. ICU continues on committed allocation "
            f"v{self.agreements.version}.", in_reply_to=msg.message_id, resource=None))
        for r in responses:
            self.submit(r)
            inc.agent_responses.append(r.message_id)
        inc.allocation_version_after = self.agreements.version
        inc.allocation_changed = self.agreements.version != before
        self._save_incident(inc)
        self.emit("state", self.snapshot())
        return inc.to_dict()

    # ----------------------------------------------------------- commander
    def set_fairness(self, value: float, actor: str = "commander") -> dict:
        old, self.fairness = self.fairness, round(float(value), 3)
        self.audit("commander", actor, "set_fairness", {"from": old, "to": self.fairness})
        self.system_msg("commander", MessageType.COMMANDER_ACTION,
                        f"Fairness–priority balance set to {self.fairness:.2f} (was {old:.2f}).", resource=None,
                        data={"fairness": self.fairness})
        result = None
        if abs(old - self.fairness) > 1e-6 and self.status != "idle":
            if self.allocation_mode == "negotiation" and not self.negotiation_paused:
                result = self.run_negotiation(f"fairness policy changed to {self.fairness:.2f}")
            else:
                self._force_reason = "fairness policy changed"
        return {"fairness": self.fairness, "negotiation": result}

    def set_approval_mode(self, mode: str, actor: str = "commander", timeout_s: float | None = None,
                          policy: str | None = None) -> dict:
        if mode not in ("auto", "manual"):
            raise EngineError("INVALID_MODE", "approval mode must be auto or manual", 422)
        if policy is not None and policy not in ("keep_last", "commit"):
            raise EngineError("INVALID_POLICY", "approval timeout policy must be keep_last or commit", 422)
        self.approval_mode = mode
        if timeout_s is not None:
            self.approval_timeout_s = float(timeout_s)
        if policy is not None:
            self.approval_timeout_policy = policy
        self.audit("commander", actor, "set_approval_mode",
                   {"mode": mode, "timeout_s": self.approval_timeout_s, "policy": self.approval_timeout_policy})
        return {"approval_mode": mode, "approval_timeout_s": self.approval_timeout_s,
                "approval_timeout_policy": self.approval_timeout_policy}

    def expire_pending(self, now: float | None = None) -> list[dict]:
        """Approval timeout (F11): an unattended proposal never stalls allocation indefinitely."""
        if self.approval_timeout_s <= 0:
            return []
        now = time.monotonic() if now is None else now
        out = []
        for p in self.agreements.awaiting_approval():
            if now - (p.awaiting_since or now) < self.approval_timeout_s:
                continue
            policy = self.approval_timeout_policy
            p.awaiting_since = None
            committed = False
            if policy == "commit":
                v = self.validate(p.allocation, p.base_version, p.proposal_id, p.battery_offer)
                if v.valid:
                    p.status = ProposalStatus.APPROVED
                    self.audit("agreement", "approval_timeout", "proposal_auto_committed",
                               {"proposal_id": p.proposal_id, "policy": policy, "timeout_s": self.approval_timeout_s})
                    self.commit(p, v, "approval_timeout")
                    committed = True
            if not committed:
                p.status = ProposalStatus.EXPIRED
                self.audit("agreement", "approval_timeout", "proposal_expired",
                           {"proposal_id": p.proposal_id, "policy": policy, "timeout_s": self.approval_timeout_s,
                            "kept_version": self.agreements.version})
                self.system_msg("negotiation_protocol", MessageType.SYSTEM,
                                f"Proposal {p.proposal_id} expired after {self.approval_timeout_s:.0f} s without "
                                f"commander approval (policy {policy}). Allocation v{self.agreements.version} "
                                f"stays in force.", proposal_id=p.proposal_id, resource=None)
            if self.observed:
                PROPOSALS_EXPIRED.labels(policy=policy).inc()
            out.append({"proposal_id": p.proposal_id, "status": p.status.value, "policy": policy})
        if out:
            self.emit("state", self.snapshot())
        return out

    def set_negotiation_paused(self, paused: bool, actor: str = "commander") -> dict:
        self.negotiation_paused = paused
        self.audit("commander", actor, "pause_negotiation" if paused else "resume_negotiation")
        self.system_msg("commander", MessageType.COMMANDER_ACTION,
                        "Negotiation paused by commander. Committed allocation stays in force; the deterministic "
                        "safety policy still applies if it becomes infeasible." if paused else
                        "Negotiation resumed by commander.", resource=None)
        if not paused and self._force_reason and self.status != "idle":
            self.run_negotiation(self._force_reason)
        return {"negotiation_paused": paused}

    def isolate(self, agent_id: str, reason: str, actor: str = "commander", isolate: bool = True) -> dict:
        if agent_id not in self.city.consumers:
            raise EngineError("INVALID_AGENT", "only consumer utility agents can be isolated", 422)
        self.city.consumers[agent_id].isolated = isolate
        # Isolation revokes the agent's signing keys; restoring it issues a fresh key pair.
        kids = self.registry.revoke(agent_id) if isolate else [self.registry.rotate_key(agent_id)]
        self.audit("commander", actor, "isolate_agent" if isolate else "restore_agent",
                   {"agent_id": agent_id, "reason": reason, "revoked_kids" if isolate else "new_kid": kids})
        self.system_msg("commander", MessageType.COMMANDER_ACTION,
                        (f"@{agent_id} isolated: {reason}. Its messages will be rejected; it receives its verified "
                         f"safe minimum under the fallback policy." if isolate else
                         f"@{agent_id} restored to the negotiation group."), mentions=[agent_id], resource=None)
        self.refresh_telemetry()
        res = None
        if self.status != "idle" and not self.negotiation_paused:
            res = self.run_negotiation(f"{agent_id} {'isolated' if isolate else 'restored'} by commander")
        return {"agent_id": agent_id, "isolated": isolate, "negotiation": res}

    def find_proposal(self, proposal_id: str) -> AllocationProposal:
        p = self.agreements.proposals.get(proposal_id)
        if p is None:
            raise EngineError("NOT_FOUND", f"proposal {proposal_id} not found", 404)
        return p

    def approve_proposal(self, proposal_id: str, actor: str = "commander") -> dict:
        p = self.find_proposal(proposal_id)
        if proposal_id in self.agreements.committed_ids:
            return {"committed": False, "duplicate": True, "version": self.agreements.version}
        if p.status in CLOSED_STATES:
            raise EngineError("PROPOSAL_CLOSED", f"proposal is {p.status.value}", 409)
        self.audit("commander", actor, "approve_proposal", {"proposal_id": proposal_id})
        v = self.validate(p.allocation, p.base_version, p.proposal_id, p.battery_offer)
        if not v.valid:
            raise EngineError("VALIDATION_FAILED", "proposal failed validation", 409, v.to_dict())
        p.status = ProposalStatus.APPROVED
        return self.commit(p, v, actor)

    def reject_proposal(self, proposal_id: str, reason: str, actor: str = "commander") -> dict:
        p = self.find_proposal(proposal_id)
        if p.status == ProposalStatus.COMMITTED:
            raise EngineError("ALREADY_COMMITTED", "committed proposals cannot be rejected; use override", 409)
        p.status = ProposalStatus.REJECTED
        p.awaiting_since = None
        self.audit("commander", actor, "reject_proposal", {"proposal_id": proposal_id, "reason": reason})
        self.system_msg("commander", MessageType.COMMANDER_ACTION,
                        f"Proposal {proposal_id} rejected by commander: {reason}", proposal_id=proposal_id,
                        resource=None)
        return {"proposal_id": proposal_id, "status": p.status.value}

    def override(self, allocation: dict[str, float], reason: str, actor: str = "commander") -> dict:
        cap = self.battery_capability()
        prop = AllocationProposal(allocation=dict(allocation), base_version=self.agreements.version,
                                  method="commander_override", outcome="override", supply_total=(self.grid_assessment.verified_supply or 0) + cap,
                                  grid_supply=self.grid_assessment.verified_supply or 0.0, battery_offer=cap,
                                  tick=self.city.tick, notes=[reason])
        self.agreements.register(prop)
        self.audit("commander", actor, "override_requested", {"allocation": allocation, "reason": reason,
                                                               "proposal_id": prop.proposal_id})
        v = self.validate(prop.allocation, prop.base_version, prop.proposal_id, cap)
        if not v.valid:
            prop.status = ProposalStatus.REJECTED
            self.audit("commander", "validator", "override_rejected", {"proposal_id": prop.proposal_id,
                                                                        "violations": v.to_dict()["violations"]})
            raise EngineError("VALIDATION_FAILED", "override violates hard safety constraints", 409, v.to_dict())
        self.system_msg("commander", MessageType.COMMANDER_ACTION,
                        f"Authorized override {prop.proposal_id}: {reason}", proposal_id=prop.proposal_id,
                        data={"allocation": allocation}, resource=None)
        return self.commit(prop, v, actor)

    def resolve_incident(self, incident_id: str, action: str, note: str, confirmed_supply_mw: float | None,
                         actor: str = "commander") -> dict:
        inc = self.trust.get_incident(incident_id)
        if inc is None:
            raise EngineError("NOT_FOUND", "incident not found", 404)
        if not inc.escalated or inc.resolved:
            raise EngineError("NOT_ESCALATED", "only open escalated incidents need a commander decision", 409)
        if action == "confirm_claim":
            if confirmed_supply_mw is None or not 0 <= confirmed_supply_mw <= self.city.grid.nominal_capacity:
                raise EngineError("INVALID_PARAMS", "confirmed_supply_mw required (0..nominal)", 422)
            self.city.grid.supply_override = float(confirmed_supply_mw)
        elif action == "dismiss":
            self.city.grid.sensor_faults.clear()
        else:
            raise EngineError("INVALID_PARAMS", "action must be confirm_claim or dismiss", 422)
        inc.resolved = True
        inc.resolution = {"action": action, "note": note, "confirmed_supply_mw": confirmed_supply_mw,
                          "by": actor, "tick": self.city.tick}
        self.audit("commander", actor, f"resolve_incident_{action}", {"incident_id": incident_id, "note": note,
                                                                      "confirmed_supply_mw": confirmed_supply_mw})
        self.system_msg("commander", MessageType.COMMANDER_ACTION,
                        f"Incident {incident_id} resolved: {action.replace('_', ' ')}"
                        + (f" — supply confirmed at {confirmed_supply_mw:.0f} MW" if confirmed_supply_mw else "")
                        + (f". {note}" if note else "."), resource=None)
        self.refresh_telemetry()
        self.frozen = False
        self.check_sensors()
        self.frozen = False
        before = self.agreements.version
        if self.status != "idle" and not self.negotiation_paused:
            self.run_negotiation(f"commander resolved incident {incident_id}")
        inc.allocation_version_after = self.agreements.version
        inc.allocation_changed = self.agreements.version != before
        self._save_incident(inc)
        return inc.to_dict()

    # -------------------------------------------------------------- views
    def agent_summary(self, aid: str) -> dict:
        meta = AGENT_META.get(aid, {"display_name": aid, "role": "Utility Agent", "icon": "Cpu", "color": "#38bdf8"})
        rep = self.trust.reputation.get(aid)
        if aid in self.city.consumers:
            c = self.city.consumers[aid]
            ag = self.registry.consumers[aid]
            status = "isolated" if c.isolated else "online" if c.connected else "disconnected"
            return {"agent_id": aid, **meta, "kind": "consumer", "status": status,
                    "demand_mw": c.effective_demand, "min_safe_mw": c.effective_min, "max_allowed_mw": c.max_allowed,
                    "allocation_mw": c.allocation, "service_level": c.service_level, "health": c.health,
                    "operational_capacity": c.operational_capacity, "active_operations": c.active_operations,
                    "ticks_below_min": c.ticks_below_min, "ticks_conceding": c.ticks_conceding,
                    "urgency": damage_weights(self.city)[aid], "reputation": rep,
                    "policy": {"concession_rate": ag.effective_rate(),
                               "peer_grant_fraction": ag.profile.peer_grant_fraction,
                               "critical_weight": ag.profile.critical_weight,
                               "dependencies": ag.profile.dependencies}}
        if aid == "battery_agent":
            b = self.city.battery
            return {"agent_id": aid, **meta, "kind": "storage", "status": "online" if b.connected else "disconnected",
                    "soc": round(b.soc, 4), "reserve_fraction": b.reserve_fraction, "capacity_mwh": b.capacity_mwh,
                    "usable_energy_mwh": round(b.usable_energy_mwh, 3), "capability_mw": self.battery_capability(),
                    "discharge_mw": b.discharge_mw, "max_discharge_mw": b.max_discharge_mw, "reputation": rep}
        ga = self.grid_assessment
        return {"agent_id": aid, **meta, "kind": "supply", "status": "online",
                "nominal_mw": self.city.grid.nominal_capacity,
                "verified_supply_mw": ga.verified_supply, "sensor_status": ga.consensus.status,
                "sensors": dict(zip(GRID_SENSOR_IDS, self.telemetry.grid_sensors)),
                "reserve_margin_mw": ga.margin, "override_mw": self.city.grid.supply_override, "reputation": rep}

    def add_custom_consumer(self, req: S.CreateAgentRequest) -> dict:
        aid = req.agent_id
        if aid in self.city.consumers or aid in ("grid_agent", "battery_agent"):
            raise EngineError("AGENT_EXISTS", f"Agent '{aid}' already exists", 409)

        profile = ConsumerProfile(
            agent_id=aid,
            name=req.name,
            base_demand=req.base_demand,
            min_safe=req.min_safe,
            max_allowed=req.max_allowed,
            damage_weight=req.damage_weight,
            critical_weight=req.critical_weight,
            concession_rate=req.concession_rate,
            peer_grant_fraction=req.peer_grant_fraction,
            dependencies=dict(req.dependencies),
            ramp_up_mw_per_min=2.0,
            feeder=req.feeder,
        )
        CONSUMER_PROFILES[aid] = profile

        # Register in agent registry (generates Ed25519 key, registers in public_keys)
        agent = self.registry.add_consumer(profile)

        # Create consumer state in city
        c_state = ConsumerState(
            agent_id=aid,
            base_demand=req.base_demand,
            demand=req.base_demand,
            min_safe=req.min_safe,
            max_allowed=req.max_allowed,
            health=1.0,
            operational_capacity=1.0,
            connected=True,
            isolated=False,
            allocation=0.0,
        )
        self.city.consumers[aid] = c_state

        # Register metadata for UI
        AGENT_META[aid] = {
            "display_name": req.name,
            "role": req.role,
            "icon": req.icon,
            "color": req.color,
        }

        # Refresh telemetry and feed to agent
        self.refresh_telemetry()
        agent.observe(self.telemetry)
        agent.observe_local(c_state)

        # Audit log entry
        self.audit("commander", "commander", "create_custom_agent", {
            "agent_id": aid,
            "name": req.name,
            "feeder": req.feeder,
            "base_demand": req.base_demand,
            "min_safe": req.min_safe,
        })

        # Run negotiation immediately if requested so the agent begins participating
        if req.start_negotiation:
            self.run_negotiation(f"New utility '{req.name}' joined the municipal grid")

        snap = self.snapshot()
        self.emit("state", snap)

        return {
            "agent": self.agent_summary(aid),
            "negotiation_started": req.start_negotiation,
            "state": snap,
        }

    def agents(self) -> list[dict]:
        return [self.agent_summary(a) for a in list(self.city.consumers) + ["battery_agent", "grid_agent"]]

    def graph(self) -> dict:
        b = self.city.battery
        alloc_total = sum(c.allocation for c in self.city.consumers.values())
        battery_flow = max(0.0, alloc_total - (self.grid_assessment.verified_supply or 0.0))
        return build_graph(self.city, battery_flow, alloc_total - battery_flow) | {
            "battery_soc": round(b.soc, 4)}

    def snapshot(self) -> dict:
        levels = compute_service_levels(self.city)
        derived = derived_services(levels, self.city)
        cur = self.agreements.current
        ga = self.grid_assessment
        demand = sum(c.effective_demand for c in self.city.consumers.values())
        mins = sum(c.effective_min for c in self.city.consumers.values())
        cap = self.battery_capability()
        available = (ga.verified_supply or 0.0) + cap
        health = round(float(np.mean([v["effective"] for v in levels.values()])), 4)
        return {
            "session_id": self.session_id, "status": self.status, "scenario": self.scenario, "seed": self.seed,
            "scenario_description": SCENARIOS[self.scenario]["description"],
            "tick": self.city.tick, "sim_time": self.city.sim_time.isoformat(),
            "minutes_per_tick": self.dt_minutes, "allocation_mode": self.allocation_mode,
            "fairness": self.fairness, "approval_mode": self.approval_mode,
            "approval_timeout_s": self.approval_timeout_s, "approval_timeout_policy": self.approval_timeout_policy,
            "features": self.features,
            "negotiation_paused": self.negotiation_paused, "frozen": self.frozen,
            "supply": {"grid_actual_mw": self.city.grid.available, "grid_verified_mw": ga.verified_supply,
                       "grid_nominal_mw": self.city.grid.nominal_capacity, "battery_capability_mw": cap,
                       "total_available_mw": round(available, 3), "sensor_status": ga.consensus.status},
            "demand_total_mw": round(demand, 3), "min_safe_total_mw": round(mins, 3),
            "deficit_mw": round(max(0.0, demand - available), 3),
            "degradation_mode": mins > available + 1e-3,
            "agents": self.agents(),
            "allocation": cur.to_dict() if cur else None,
            "allocation_version": self.agreements.version,
            "pending_proposals": [p.to_dict() for p in self.agreements.pending()],
            "last_negotiation": self.negotiations[-1] if self.negotiations else None,
            "negotiation_count": len(self.negotiations),
            "alerts": [a for a in self.alerts if a["active"]][-20:],
            "infrastructure_health": health,
            "service_levels": levels, "derived_services": derived,
            "cascades": cascade_chains(levels, derived, self.city),
            "metrics": self.metrics.summary(),
            "trust": {"incidents": len(self.trust.incidents),
                      "open_escalations": sum(1 for i in self.trust.incidents if i.escalated and not i.resolved),
                      "quarantined": len(self.trust.quarantine), "reputation": self.trust.reputation},
            "last_seq": self._seq,
        }

    def explanation_facts(self) -> dict:
        cur = self.agreements.current
        last = self.negotiations[-1] if self.negotiations else None
        return {
            "tick": self.city.tick, "sim_time": self.city.sim_time.isoformat(), "fairness": self.fairness,
            "verified_supply_mw": self.grid_assessment.verified_supply,
            "battery_capability_mw": self.battery_capability(),
            "battery_discharge_mw": self.city.battery.discharge_mw,
            "battery_soc": round(self.city.battery.soc, 2),
            "battery_usable_mwh": round(self.city.battery.usable_energy_mwh, 1),
            "agents": {a["agent_id"]: {k: a.get(k) for k in ("status", "demand_mw", "min_safe_mw", "allocation_mw",
                                                             "urgency", "service_level")}
                       for a in self.agents() if a["kind"] == "consumer"},
            "agreement": ({"version": cur.version, "method": cur.method, "allocation": cur.allocation,
                           "degradation_mode": cur.degradation_mode,
                           "battery_discharge_mw": cur.battery_discharge} if cur else None),
            "last_negotiation": ({k: last[k] for k in ("method", "rounds", "converged", "fallback_used",
                                                       "degradation", "final_positions", "demands")}
                                 if last else None),
            "objective": (self.agreements.proposals[cur.proposal_id].objective
                          if cur and cur.proposal_id in self.agreements.proposals else None),
            "cascades": cascade_chains(compute_service_levels(self.city),
                                       derived_services(compute_service_levels(self.city), self.city), self.city),
            # structured fields only: no free text from messages reaches the LLM prompt (F14)
            "open_trust_incidents": [{"kind": i.kind, "decision": i.decision,
                                      "sender": i.sender if i.sender in self.registry.participants else "unregistered"}
                                     for i in self.trust.incidents if not i.resolved][-5:],
        }
