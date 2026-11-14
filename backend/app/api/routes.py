"""REST API. Every mutating endpoint goes through the run's lock and is audited.

Routers are grouped by the role they require (F2), and the role check is a
router-level dependency, so a new route is protected by default:

  read     viewer+     GET routes
  control  commander+  operational actions
  admin    admin       event injection, run deletion
  test     admin       reset / step / fake-event injection; only registered when ENABLE_TEST_ROUTES

Each router is mounted at ``/api`` (the default run) and at
``/api/runs/{run_id}`` (F8). Run management lives at ``/api/runs``.
"""
from __future__ import annotations

import asyncio

from fastapi import APIRouter, Depends, Path, Query, Request
from fastapi.responses import Response

from app.agents.base import AGENT_META
from app.evaluation.runner import METRIC_DEFINITIONS, VARIANTS, run_evaluation
from app.observability import render
from app.schemas import api as S
from app.simulation.engine import EngineError
from app.simulation.events import EVENT_CATALOG, SCENARIOS
from app.simulation.runtime import RunManager, SimulationRuntime
from app.trust.injector import FAKE_KINDS

VERSION = "0.2.0"


def rt(request: Request) -> SimulationRuntime:
    runs: RunManager = request.app.state.runs
    return runs.get(request.path_params.get("run_id"))


def run_id_param(run_id: str = Path(..., min_length=3, max_length=40, pattern=r"^[A-Za-z0-9_\-]+$")) -> str:
    return run_id


R = Depends(rt)

read = APIRouter()
control = APIRouter()
admin = APIRouter()
test = APIRouter()
runs_read = APIRouter(prefix="/api/runs", tags=["runs"])
runs_control = APIRouter(prefix="/api/runs", tags=["runs"])
runs_admin = APIRouter(prefix="/api/runs", tags=["runs"])


# ======================================================================= read (viewer)
@read.get("/health", response_model=S.HealthResponse, tags=["system"])
async def health(r: SimulationRuntime = R):
    return S.HealthResponse(status="ok", version=VERSION, database=r.repo.healthy(), llm=r.llm.status(),
                            simulation_status=r.engine.status, session_id=r.engine.session_id, run_id=r.run_id)


@read.get("/meta", tags=["system"])
async def meta(request: Request):
    return {"agents": AGENT_META, "events": EVENT_CATALOG, "fake_events": FAKE_KINDS,
            "scenarios": {k: {"description": v["description"], "script": v["script"]} for k, v in SCENARIOS.items()},
            "allocation_modes": list(VARIANTS), "test_routes": request.app.state.settings.test_routes_enabled,
            "auth": {"viewer_public": request.app.state.tokens.public_read,
                     "roles": {"viewer": "GET + WebSocket", "commander": "operational control",
                               "admin": "reset, step, event injection"}}}


@read.get("/simulation/state", tags=["simulation"])
async def state(r: SimulationRuntime = R):
    return await r.call(r.engine.snapshot)


@read.get("/simulation/metrics", tags=["simulation"])
async def metrics(last: int = Query(96, ge=1, le=5000), r: SimulationRuntime = R):
    return await r.call(lambda: {"summary": r.engine.metrics.summary(), "series": r.engine.metrics.series(last),
                                 "negotiation_outcomes": r.engine.metrics.outcome_rates()})


@read.get("/events/history", tags=["events"])
async def event_history(r: SimulationRuntime = R):
    return await r.call(lambda: r.engine.events_log[-200:])


@read.get("/events/catalog", tags=["events"])
async def event_catalog():
    return {"events": EVENT_CATALOG, "fake_events": FAKE_KINDS}


@read.get("/agents", tags=["agents"])
async def list_agents(r: SimulationRuntime = R):
    return await r.call(r.engine.agents)


@read.get("/agents/{agent_id}", tags=["agents"])
async def get_agent(agent_id: S.AgentId, r: SimulationRuntime = R):
    def run():
        if agent_id not in r.engine.city.consumers and agent_id not in ("battery_agent", "grid_agent"):
            raise EngineError("INVALID_AGENT", f"unknown agent {agent_id}", 422)
        info = r.engine.agent_summary(agent_id)
        info["recent_messages"] = [m for m in r.engine.messages if m["sender"] == agent_id][-25:]
        info["active_kids"] = r.engine.registry.public_keys.active_kids(agent_id)
        return info
    return await r.call(run)


@read.get("/negotiation/history", tags=["negotiation"])
async def negotiation_history(since_seq: int = Query(0, ge=0), limit: int = Query(300, ge=1, le=2000),
                              negotiation_id: str | None = Query(None, max_length=64), r: SimulationRuntime = R):
    def run():
        msgs = [m for m in r.engine.messages if m["seq"] > since_seq
                and (negotiation_id is None or m.get("negotiation_id") == negotiation_id)]
        if not msgs and since_seq and r.engine.messages and since_seq < r.engine.messages[0]["seq"]:
            msgs = r.repo.messages(r.engine.session_id, since_seq, limit)  # older than memory window
        return {"session_id": r.engine.session_id, "messages": msgs[:limit],
                "negotiations": r.engine.negotiations[-50:], "last_seq": r.engine._seq}
    return await r.call(run)


@read.get("/allocations/current", tags=["allocations"])
async def current_allocation(r: SimulationRuntime = R):
    def run():
        cur = r.engine.agreements.current
        return {"version": r.engine.agreements.version, "agreement": cur.to_dict() if cur else None,
                "pending": [p.to_dict() for p in r.engine.agreements.pending()]}
    return await r.call(run)


@read.get("/allocations/history", tags=["allocations"])
async def allocation_history(r: SimulationRuntime = R):
    return await r.call(lambda: [a.to_dict() for a in r.engine.agreements.history[-100:]])


@read.get("/trust/incidents", tags=["trust"])
async def incidents(r: SimulationRuntime = R):
    return await r.call(lambda: [i.to_dict() for i in reversed(r.engine.trust.incidents)])


@read.get("/trust/incidents/{incident_id}", tags=["trust"])
async def incident(incident_id: str = Path(..., max_length=64), r: SimulationRuntime = R):
    def run():
        inc = r.engine.trust.get_incident(incident_id)
        if inc is None:
            raise EngineError("NOT_FOUND", "incident not found", 404)
        return inc.to_dict()
    return await r.call(run)


@read.get("/trust/reputation", tags=["trust"])
async def reputation(r: SimulationRuntime = R):
    return await r.call(lambda: {"agents": r.engine.trust.reputation, "sensors": r.engine.trust.sensor_reputation})


@read.get("/trust/quarantine", tags=["trust"])
async def quarantine(r: SimulationRuntime = R):
    return await r.call(lambda: r.engine.trust.quarantine[-100:])


@read.get("/audit/logs", tags=["audit"])
async def audit_logs(limit: int = Query(200, ge=1, le=2000), category: str | None = Query(None, max_length=32),
                     all_sessions: bool = False, r: SimulationRuntime = R):
    def run():
        logs = r.repo.audit_logs(None if all_sessions else r.engine.session_id, limit, category)
        if not logs:  # DB unavailable fallback
            logs = [a for a in reversed(r.engine.audit_log) if not category or a["category"] == category][:limit]
        return logs
    return await r.call(run)


@read.get("/audit/verify", tags=["audit"])
async def audit_verify(r: SimulationRuntime = R):
    """Walk the hash-chained audit log; reports the first tampered row (F12)."""
    return await asyncio.to_thread(r.repo.verify_audit_chain)


@read.get("/evaluation/plan", tags=["evaluation"])
async def evaluation_plan():
    return {"modes": {"fcfs": "first-come-first-served (seeded arrival order)",
                      "fixed_priority": "hospital > emergency > telecom > water, full demand",
                      "centralized": "single optimizer with full (metered) information",
                      "hidden_information": "single optimizer that only sees agents' reported demand",
                      "rolling_horizon": "optimizer that budgets battery energy over an 8-tick horizon",
                      "negotiation": "autonomous multi-agent negotiation (this system)",
                      "no_trust": "ablation: negotiation with the trust engine disabled",
                      "fallback_only": "ablation: optimizer decides, no negotiation rounds",
                      "negotiation_only": "ablation: negotiation without the optimizer fallback"},
            "metrics": METRIC_DEFINITIONS,
            "protocol": "Each mode runs the same scenario script, seeds and tick count in a fresh headless "
                        "engine; the validator stays on in every mode. Multi-seed runs report mean, std and a "
                        "95% confidence interval. Values are only shown after a run; no numbers are pre-filled."}


@read.get("/evaluation/results", tags=["evaluation"])
async def evaluation_results(limit: int = Query(10, ge=1, le=100), r: SimulationRuntime = R):
    return r.repo.evaluations(limit)


@read.get("/twin/graph", tags=["digital twin"])
async def graph(r: SimulationRuntime = R):
    return await r.call(r.engine.graph)


# ================================================================ control (commander)
@control.post("/simulation/start", tags=["simulation"])
async def start(r: SimulationRuntime = R):
    return await r.start()


@control.post("/simulation/pause", tags=["simulation"])
async def pause(r: SimulationRuntime = R):
    return await r.call(r.engine.pause)


@control.post("/simulation/resume", tags=["simulation"])
async def resume(r: SimulationRuntime = R):
    return await r.resume()


@control.put("/simulation/fairness", tags=["simulation"])
async def fairness(body: S.FairnessRequest, r: SimulationRuntime = R):
    return await r.call(r.engine.set_fairness, body.value)


@control.put("/simulation/settings", tags=["simulation"])
async def settings(body: S.SettingsRequest, r: SimulationRuntime = R):
    out: dict = {}
    if body.approval_mode is not None or body.approval_timeout_s is not None or body.approval_timeout_policy:
        out.update(await r.call(r.engine.set_approval_mode, body.approval_mode or r.engine.approval_mode,
                                "commander", body.approval_timeout_s, body.approval_timeout_policy))
    if body.tick_interval_s is not None:
        await r.set_tick_interval(body.tick_interval_s)
        out["tick_interval_s"] = body.tick_interval_s
    return out


@control.post("/negotiation/start", tags=["negotiation"])
async def start_negotiation(body: S.NegotiationStartRequest | None = None, r: SimulationRuntime = R):
    body = body or S.NegotiationStartRequest()

    def run():
        if r.engine.negotiation_paused:
            raise EngineError("NEGOTIATION_PAUSED", "negotiation is paused by the commander", 409)
        r.engine.audit("commander", "commander", "start_negotiation", {"reason": body.reason})
        return r.engine.run_negotiation(body.reason) or {"started": False, "reason": "supply unverifiable or "
                                                                                     "non-negotiation mode"}
    return await r.call(run)


@control.post("/negotiation/pause", tags=["negotiation"])
async def pause_negotiation(r: SimulationRuntime = R):
    return await r.call(r.engine.set_negotiation_paused, True)


@control.post("/negotiation/resume", tags=["negotiation"])
async def resume_negotiation(r: SimulationRuntime = R):
    return await r.call(r.engine.set_negotiation_paused, False)


@control.post("/allocations/validate", tags=["allocations"])
async def validate(body: S.ValidateRequest, r: SimulationRuntime = R):
    def run():
        e = r.engine
        if body.proposal_id:
            p = e.find_proposal(body.proposal_id)
            v = e.validate(p.allocation, p.base_version, p.proposal_id, p.battery_offer)
        else:
            reserved, _ = e.reserved()
            alloc = {**(body.allocation or {}), **{k: x for k, x in reserved.items() if k not in (body.allocation or {})}}
            v = e.validate(alloc, e.agreements.version, "__adhoc__", e.battery_capability())
        e.audit("commander", "commander", "validate_allocation",
                {"proposal_id": body.proposal_id, "valid": v.valid})
        return v.to_dict()
    return await r.call(run)


@control.post("/allocations/commit", tags=["allocations"])
async def commit(body: S.CommitRequest, r: SimulationRuntime = R):
    return await r.call(r.engine.approve_proposal, body.proposal_id)


@control.post("/allocations/reject", tags=["allocations"])
async def reject(body: S.RejectRequest, r: SimulationRuntime = R):
    return await r.call(r.engine.reject_proposal, body.proposal_id, body.reason)


@control.post("/trust/incidents/{incident_id}/resolve", tags=["trust"])
async def resolve(body: S.ResolveIncidentRequest, incident_id: str = Path(..., max_length=64),
                  r: SimulationRuntime = R):
    return await r.call(r.engine.resolve_incident, incident_id, body.action, body.note, body.confirmed_supply_mw)


@control.post("/commander/explain", tags=["commander"])
async def explain(body: S.ExplainRequest | None = None, r: SimulationRuntime = R):
    body = body or S.ExplainRequest()
    return await r.explain(body.question)


@control.post("/commander/agents", tags=["commander"])
async def create_custom_agent(body: S.CreateAgentRequest, r: SimulationRuntime = R):
    def run():
        return r.engine.add_custom_consumer(body)
    return await r.call(run)


@control.post("/commander/agents/{agent_id}/isolate", tags=["commander"])
async def isolate(agent_id: S.ConsumerId, body: S.IsolateRequest | None = None, r: SimulationRuntime = R):
    body = body or S.IsolateRequest()
    return await r.call(r.engine.isolate, agent_id, body.reason, "commander", True)


@control.post("/commander/agents/{agent_id}/restore", tags=["commander"])
async def restore(agent_id: S.ConsumerId, r: SimulationRuntime = R):
    return await r.call(r.engine.isolate, agent_id, "commander restored agent", "commander", False)


@control.post("/commander/override", tags=["commander"])
async def override(body: S.OverrideRequest, r: SimulationRuntime = R):
    # Authorization is the router-level bearer-token role check (the token is never read from the body).
    def run():
        reserved, _ = r.engine.reserved()
        alloc = {**reserved, **body.allocation}
        return r.engine.override(alloc, body.reason)
    return await r.call(run)


@control.post("/commander/alerts/{alert_id}/acknowledge", tags=["commander"])
async def ack_alert(alert_id: str = Path(..., max_length=64), r: SimulationRuntime = R):
    return await r.call(r.engine.acknowledge_alert, alert_id)


@control.post("/evaluation/run", tags=["evaluation"])
async def evaluation_run(body: S.EvaluationRequest | None = None, r: SimulationRuntime = R):
    body = body or S.EvaluationRequest()
    seeds = body.seeds or [body.seed]
    try:
        res = await asyncio.to_thread(run_evaluation, r.settings, body.scenario, seeds, body.ticks,
                                      body.fairness, list(body.modes), body.adversarial)
    except ValueError as exc:
        raise EngineError("INVALID_EVALUATION", str(exc), 422)
    r.repo.save_evaluation(res["run_id"], body.scenario, seeds[0], body.ticks, res["duration_s"], res,
                           res["config_hash"])
    await r.call(r.engine.audit, "evaluation", "commander", "evaluation_run",
                 {"run_id": res["run_id"], "scenario": body.scenario, "seeds": seeds, "ticks": body.ticks,
                  "config_hash": res["config_hash"]})
    return res


# ===================================================================== admin
@admin.post("/events/inject", tags=["events"])
async def inject(body: S.EventInjectRequest, r: SimulationRuntime = R):
    return await r.call(r.engine.inject_event, body.event_type.value, body.params)


# =============================================================== test (admin, gated)
@test.post("/simulation/reset", tags=["simulation"])
async def reset(body: S.ResetRequest | None = None, r: SimulationRuntime = R):
    body = body or S.ResetRequest()
    return await r.reset(body.seed, body.scenario)


@test.post("/simulation/step", tags=["simulation"])
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


@test.post("/events/inject-fake", tags=["events"])
async def inject_fake(body: S.FakeInjectRequest | None = None, r: SimulationRuntime = R):
    body = body or S.FakeInjectRequest()
    return await r.call(r.engine.inject_fake, body.kind, body.params)


# ===================================================================== runs (F8)
@runs_read.get("")
async def list_runs(request: Request):
    return request.app.state.runs.list_runs()


@runs_control.post("")
async def create_run(request: Request, body: S.CreateRunRequest | None = None):
    body = body or S.CreateRunRequest()
    runtime = await request.app.state.runs.create(body.seed, body.scenario)
    async with runtime.lock:
        runtime.engine.audit("simulation", "commander", "create_run", {"run_id": runtime.run_id})
        snap = runtime.engine.snapshot()
    return {"run_id": runtime.run_id, "state": snap}


@runs_admin.delete("/{run_id}")
async def delete_run(request: Request, run_id: str = Depends(run_id_param)):
    await request.app.state.runs.delete(run_id)
    return {"run_id": run_id, "deleted": True}


# ===================================================================== /metrics
metrics_router = APIRouter(tags=["system"])


@metrics_router.get("/metrics", include_in_schema=False)
async def prometheus_metrics():
    return Response(render(), media_type="text/plain; version=0.0.4; charset=utf-8")
