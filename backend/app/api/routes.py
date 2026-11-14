"""REST API. Every mutating endpoint goes through the runtime lock and is audited."""
from __future__ import annotations

import asyncio
import hmac

from fastapi import APIRouter, Depends, Query, Request

from app.agents.base import AGENT_META
from app.evaluation.runner import METRIC_DEFINITIONS, run_evaluation
from app.schemas import api as S
from app.simulation.engine import EngineError
from app.simulation.events import EVENT_CATALOG, SCENARIOS
from app.simulation.runtime import SimulationRuntime
from app.trust.injector import FAKE_KINDS

VERSION = "0.1.0"


def rt(request: Request) -> SimulationRuntime:
    return request.app.state.runtime


R = Depends(rt)

system = APIRouter(tags=["system"])
simulation = APIRouter(prefix="/api/simulation", tags=["simulation"])
events = APIRouter(prefix="/api/events", tags=["events"])
agents = APIRouter(prefix="/api/agents", tags=["agents"])
negotiation = APIRouter(prefix="/api/negotiation", tags=["negotiation"])
allocations = APIRouter(prefix="/api/allocations", tags=["allocations"])
trust = APIRouter(prefix="/api/trust", tags=["trust"])
audit = APIRouter(prefix="/api/audit", tags=["audit"])
commander = APIRouter(prefix="/api/commander", tags=["commander"])
evaluation = APIRouter(prefix="/api/evaluation", tags=["evaluation"])
twin = APIRouter(prefix="/api/twin", tags=["digital twin"])


# ----------------------------------------------------------------- system
@system.get("/api/health", response_model=S.HealthResponse)
async def health(r: SimulationRuntime = R):
    return S.HealthResponse(status="ok", version=VERSION, database=r.repo.healthy(), llm=r.llm.status(),
                            simulation_status=r.engine.status, session_id=r.engine.session_id)


@system.get("/api/meta")
async def meta():
    return {"agents": AGENT_META, "events": EVENT_CATALOG, "fake_events": FAKE_KINDS,
            "scenarios": {k: {"description": v["description"], "script": v["script"]} for k, v in SCENARIOS.items()},
            "allocation_modes": ["negotiation", "centralized", "fixed_priority", "fcfs"]}


# ------------------------------------------------------------- simulation
@simulation.post("/start")
async def start(r: SimulationRuntime = R):
    return await r.start()


@simulation.post("/pause")
async def pause(r: SimulationRuntime = R):
    return await r.call(r.engine.pause)


@simulation.post("/resume")
async def resume(r: SimulationRuntime = R):
    return await r.resume()


@simulation.post("/reset")
async def reset(body: S.ResetRequest | None = None, r: SimulationRuntime = R):
    body = body or S.ResetRequest()
    return await r.reset(body.seed, body.scenario)


@simulation.post("/step")
async def step(body: S.StepRequest | None = None, r: SimulationRuntime = R):
    body = body or S.StepRequest()

    def run():
        if r.engine.status == "running":
            raise EngineError("RUNNING", "pause the simulation before advancing manually", 409)
        r.engine.audit("commander", "commander", "advance_time", {"ticks": body.ticks})
        for _ in range(body.ticks):
            r.engine.step()
        return r.engine.snapshot()
    return await r.call(run)


@simulation.get("/state")
async def state(r: SimulationRuntime = R):
    return await r.call(r.engine.snapshot)


@simulation.put("/fairness")
async def fairness(body: S.FairnessRequest, r: SimulationRuntime = R):
    return await r.call(r.engine.set_fairness, body.value)


@simulation.put("/settings")
async def settings(body: S.SettingsRequest, r: SimulationRuntime = R):
    out = {}
    if body.approval_mode is not None:
        out.update(await r.call(r.engine.set_approval_mode, body.approval_mode))
    if body.tick_interval_s is not None:
        await r.set_tick_interval(body.tick_interval_s)
        out["tick_interval_s"] = body.tick_interval_s
    return out


@simulation.get("/metrics")
async def metrics(last: int = Query(96, ge=1, le=5000), r: SimulationRuntime = R):
    return await r.call(lambda: {"summary": r.engine.metrics.summary(), "series": r.engine.metrics.series(last)})


# ----------------------------------------------------------------- events
@events.post("/inject")
async def inject(body: S.EventInjectRequest, r: SimulationRuntime = R):
    return await r.call(r.engine.inject_event, body.event_type.value, body.params)


@events.post("/inject-fake")
async def inject_fake(body: S.FakeInjectRequest | None = None, r: SimulationRuntime = R):
    body = body or S.FakeInjectRequest()
    return await r.call(r.engine.inject_fake, body.kind, body.params)


@events.get("/history")
async def event_history(r: SimulationRuntime = R):
    return await r.call(lambda: r.engine.events_log[-200:])


@events.get("/catalog")
async def event_catalog():
    return {"events": EVENT_CATALOG, "fake_events": FAKE_KINDS}


# ----------------------------------------------------------------- agents
@agents.get("")
async def list_agents(r: SimulationRuntime = R):
    return await r.call(r.engine.agents)


@agents.get("/{agent_id}")
async def get_agent(agent_id: S.AgentId, r: SimulationRuntime = R):
    def run():
        info = r.engine.agent_summary(agent_id)
        info["recent_messages"] = [m for m in r.engine.messages if m["sender"] == agent_id][-25:]
        return info
    return await r.call(run)


# ------------------------------------------------------------ negotiation
@negotiation.post("/start")
async def start_negotiation(body: S.NegotiationStartRequest | None = None, r: SimulationRuntime = R):
    body = body or S.NegotiationStartRequest()

    def run():
        if r.engine.negotiation_paused:
            raise EngineError("NEGOTIATION_PAUSED", "negotiation is paused by the commander", 409)
        r.engine.audit("commander", "commander", "start_negotiation", {"reason": body.reason})
        return r.engine.run_negotiation(body.reason) or {"started": False, "reason": "supply unverifiable or "
                                                                                     "non-negotiation mode"}
    return await r.call(run)


@negotiation.post("/pause")
async def pause_negotiation(r: SimulationRuntime = R):
    return await r.call(r.engine.set_negotiation_paused, True)


@negotiation.post("/resume")
async def resume_negotiation(r: SimulationRuntime = R):
    return await r.call(r.engine.set_negotiation_paused, False)


@negotiation.get("/history")
async def negotiation_history(since_seq: int = Query(0, ge=0), limit: int = Query(300, ge=1, le=2000),
                              negotiation_id: str | None = None, r: SimulationRuntime = R):
    def run():
        msgs = [m for m in r.engine.messages if m["seq"] > since_seq
                and (negotiation_id is None or m.get("negotiation_id") == negotiation_id)]
        if not msgs and since_seq and r.engine.messages and since_seq < r.engine.messages[0]["seq"]:
            msgs = r.repo.messages(r.engine.session_id, since_seq, limit)  # older than memory window
        return {"session_id": r.engine.session_id, "messages": msgs[:limit],
                "negotiations": r.engine.negotiations[-50:], "last_seq": r.engine._seq}
    return await r.call(run)


# ------------------------------------------------------------ allocations
@allocations.get("/current")
async def current_allocation(r: SimulationRuntime = R):
    def run():
        cur = r.engine.agreements.current
        return {"version": r.engine.agreements.version, "agreement": cur.to_dict() if cur else None,
                "pending": [p.to_dict() for p in r.engine.agreements.pending()]}
    return await r.call(run)


@allocations.get("/history")
async def allocation_history(r: SimulationRuntime = R):
    return await r.call(lambda: [a.to_dict() for a in r.engine.agreements.history[-100:]])


@allocations.post("/validate")
async def validate(body: S.ValidateRequest, r: SimulationRuntime = R):
    def run():
        e = r.engine
        if body.proposal_id:
            p = e.find_proposal(body.proposal_id)
            v = e.validate(p.allocation, p.base_version, p.proposal_id, p.battery_offer)
        else:
            reserved, _ = e.reserved()
            alloc = {**body.allocation, **{k: v for k, v in reserved.items() if k not in body.allocation}}
            v = e.validate(alloc, e.agreements.version, "__adhoc__", e.battery_capability())
        e.audit("commander", "commander", "validate_allocation",
                {"proposal_id": body.proposal_id, "valid": v.valid})
        return v.to_dict()
    return await r.call(run)


@allocations.post("/commit")
async def commit(body: S.CommitRequest, r: SimulationRuntime = R):
    return await r.call(r.engine.approve_proposal, body.proposal_id)


@allocations.post("/reject")
async def reject(body: S.RejectRequest, r: SimulationRuntime = R):
    return await r.call(r.engine.reject_proposal, body.proposal_id, body.reason)


# ----------------------------------------------------------------- trust
@trust.get("/incidents")
async def incidents(r: SimulationRuntime = R):
    return await r.call(lambda: [i.to_dict() for i in reversed(r.engine.trust.incidents)])


@trust.get("/incidents/{incident_id}")
async def incident(incident_id: str, r: SimulationRuntime = R):
    def run():
        inc = r.engine.trust.get_incident(incident_id)
        if inc is None:
            raise EngineError("NOT_FOUND", "incident not found", 404)
        return inc.to_dict()
    return await r.call(run)


@trust.post("/incidents/{incident_id}/resolve")
async def resolve(incident_id: str, body: S.ResolveIncidentRequest, r: SimulationRuntime = R):
    return await r.call(r.engine.resolve_incident, incident_id, body.action, body.note, body.confirmed_supply_mw)


@trust.get("/reputation")
async def reputation(r: SimulationRuntime = R):
    return await r.call(lambda: r.engine.trust.reputation)


@trust.get("/quarantine")
async def quarantine(r: SimulationRuntime = R):
    return await r.call(lambda: r.engine.trust.quarantine[-100:])


# ----------------------------------------------------------------- audit
@audit.get("/logs")
async def audit_logs(limit: int = Query(200, ge=1, le=2000), category: str | None = None,
                     all_sessions: bool = False, r: SimulationRuntime = R):
    def run():
        logs = r.repo.audit_logs(None if all_sessions else r.engine.session_id, limit, category)
        if not logs:  # DB unavailable fallback
            logs = [a for a in reversed(r.engine.audit_log) if not category or a["category"] == category][:limit]
        return logs
    return await r.call(run)


# -------------------------------------------------------------- commander
@commander.post("/explain")
async def explain(body: S.ExplainRequest | None = None, r: SimulationRuntime = R):
    body = body or S.ExplainRequest()
    return await r.explain(body.question)


@commander.post("/agents/{agent_id}/isolate")
async def isolate(agent_id: S.ConsumerId, body: S.IsolateRequest | None = None, r: SimulationRuntime = R):
    body = body or S.IsolateRequest()
    return await r.call(r.engine.isolate, agent_id, body.reason, "commander", True)


@commander.post("/agents/{agent_id}/restore")
async def restore(agent_id: S.ConsumerId, r: SimulationRuntime = R):
    return await r.call(r.engine.isolate, agent_id, "commander restored agent", "commander", False)


@commander.post("/override")
async def override(body: S.OverrideRequest, r: SimulationRuntime = R):
    if not hmac.compare_digest(body.authorization, r.settings.commander_auth_token):
        await r.call(r.engine.audit, "commander", "unknown", "override_denied", {"reason": "bad authorization"})
        raise EngineError("UNAUTHORIZED", "invalid commander authorization", 403)

    def run():
        reserved, _ = r.engine.reserved()
        alloc = {**{k: v for k, v in reserved.items()}, **body.allocation}
        return r.engine.override(alloc, body.reason)
    return await r.call(run)


@commander.post("/alerts/{alert_id}/acknowledge")
async def ack_alert(alert_id: str, r: SimulationRuntime = R):
    return await r.call(r.engine.acknowledge_alert, alert_id)


# ------------------------------------------------------------- evaluation
@evaluation.get("/plan")
async def evaluation_plan():
    return {"modes": {"fcfs": "first-come-first-served (seeded arrival order)",
                      "fixed_priority": "hospital > emergency > telecom > water, full demand",
                      "centralized": "single optimizer with full information",
                      "negotiation": "autonomous multi-agent negotiation (this system)"},
            "metrics": METRIC_DEFINITIONS,
            "protocol": "Each mode runs the same scenario script, seed and tick count in a fresh headless "
                        "engine. Values are only shown after a run; no numbers are pre-filled."}


@evaluation.post("/run")
async def evaluation_run(body: S.EvaluationRequest | None = None, r: SimulationRuntime = R):
    body = body or S.EvaluationRequest()
    res = await asyncio.to_thread(run_evaluation, r.settings, body.scenario, body.seed, body.ticks,
                                  body.fairness, list(body.modes))
    r.repo.save_evaluation(res["run_id"], body.scenario, body.seed, body.ticks, res["duration_s"], res)
    await r.call(r.engine.audit, "evaluation", "commander", "evaluation_run",
                 {"run_id": res["run_id"], "scenario": body.scenario, "seed": body.seed, "ticks": body.ticks})
    return res


@evaluation.get("/results")
async def evaluation_results(limit: int = Query(10, ge=1, le=100), r: SimulationRuntime = R):
    return r.repo.evaluations(limit)


# ------------------------------------------------------------ digital twin
@twin.get("/graph")
async def graph(r: SimulationRuntime = R):
    return await r.call(r.engine.graph)


ROUTERS = [system, simulation, events, agents, negotiation, allocations, trust, audit, commander, evaluation, twin]
