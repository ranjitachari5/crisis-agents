"""Async runtime: owns live engines, tick loops and LLM side-tasks.

``SimulationRuntime`` is one simulation run: an engine, its own asyncio lock,
tick loop and WebSocket hub. All mutations of that engine happen under its
lock, so REST calls, the tick loop and WebSocket events never interleave
mid-negotiation.

``RunManager`` (F8) scopes everything by run id so clients no longer share a
single global simulation: ``/api/runs/{run_id}/...``. The un-prefixed
``/api/...`` routes address the ``default`` run. Idle runs expire after
``RUN_TTL_S``. State lives in this process, so the server must run with a
single worker (enforced in ``main.py``).
"""
from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, Callable

from app.config import Settings
from app.llm.service import LLMService
from app.negotiation.agreements import AllocationProposal
from app.schemas.messages import MessageType, new_id
from app.simulation.engine import EngineError, SimulationEngine
from app.websocket.manager import ConnectionManager

log = logging.getLogger(__name__)
DEFAULT_RUN = "default"
HOUSEKEEPING_INTERVAL_S = 0.5


class SimulationRuntime:
    def __init__(self, settings: Settings, repo, ws: ConnectionManager, llm: LLMService, run_id: str = DEFAULT_RUN,
                 seed: int | None = None, scenario: str = "grid_shortage"):
        self.settings = settings
        self.repo = repo
        self.ws = ws
        self.llm = llm
        self.run_id = run_id
        self.lock = asyncio.Lock()
        self.tick_interval = settings.tick_interval_s
        self.last_access = time.monotonic()
        self.created_at = time.time()
        self._loop_task: asyncio.Task | None = None
        self._side_tasks: set[asyncio.Task] = set()
        self._last_summary = 0.0
        self.engine = self._new_engine(settings.random_seed if seed is None else seed, scenario)

    def _new_engine(self, seed: int, scenario: str) -> SimulationEngine:
        e = SimulationEngine(self.settings, seed=seed, scenario=scenario, emit=self.ws.publish, repo=self.repo)
        e.commit_hooks.append(self._on_commit)
        return e

    def touch(self) -> None:
        self.last_access = time.monotonic()

    def info(self) -> dict:
        e = self.engine
        return {"run_id": self.run_id, "session_id": e.session_id, "scenario": e.scenario, "seed": e.seed,
                "status": e.status, "tick": e.city.tick, "clients": len(self.ws.clients),
                "idle_s": round(time.monotonic() - self.last_access, 1)}

    # ------------------------------------------------------------- loop
    def ensure_loop(self) -> None:
        if self._loop_task is None or self._loop_task.done():
            self._loop_task = asyncio.create_task(self._loop())

    async def _loop(self) -> None:
        # Wall-clock pacing lives here; the engine itself only advances in logical ticks (F15).
        while True:
            await asyncio.sleep(self.tick_interval)
            try:
                async with self.lock:
                    if self.engine.status == "running":
                        self.engine.step()
            except Exception:
                log.exception("tick failed (run %s)", self.run_id)

    async def housekeeping(self) -> None:
        """Approval timeouts are wall-clock based, so they are checked here, not in the engine (F11)."""
        async with self.lock:
            try:
                self.engine.expire_pending(time.monotonic())
            except Exception:
                log.exception("approval expiry failed (run %s)", self.run_id)

    async def shutdown(self) -> None:
        for t in [self._loop_task, *self._side_tasks]:
            if t:
                t.cancel()
        await self.ws.stop()

    async def call(self, fn: Callable[..., Any], *args, **kwargs) -> Any:
        async with self.lock:
            return fn(*args, **kwargs)

    # ---------------------------------------------------------- control
    async def start(self) -> dict:
        async with self.lock:
            res = self.engine.start()
        self.ensure_loop()
        return res

    async def resume(self) -> dict:
        async with self.lock:
            res = self.engine.resume()
        self.ensure_loop()
        return res

    async def reset(self, seed: int | None, scenario: str) -> dict:
        async with self.lock:
            old = self.engine
            self.engine = self._new_engine(self.settings.random_seed if seed is None else seed, scenario)
            self.engine.fairness = old.fairness
            self.engine.audit("simulation", "commander", "reset",
                              {"previous_session": old.session_id, "scenario": scenario, "seed": self.engine.seed})
            snap = self.engine.snapshot()
        self.ws.publish("reset", {"session_id": snap["session_id"]})
        self.ws.publish("state", snap)
        return snap

    async def set_tick_interval(self, seconds: float) -> None:
        self.tick_interval = seconds
        async with self.lock:
            self.engine.audit("commander", "commander", "set_tick_interval", {"seconds": seconds})

    # ------------------------------------------------------------ LLM
    def _spawn(self, coro) -> None:
        try:
            t = asyncio.get_running_loop().create_task(coro)
        except RuntimeError:  # no loop (e.g. sync tests)
            coro.close()
            return
        self._side_tasks.add(t)
        t.add_done_callback(self._side_tasks.discard)

    def _on_commit(self, agreement: dict, proposal: AllocationProposal) -> None:
        if not (self.settings.llm_agreement_summaries and self.llm.available):
            return
        now = time.monotonic()
        if now - self._last_summary < 15:  # rate-limit the API
            return
        self._last_summary = now
        engine = self.engine
        neg = next((n for n in reversed(engine.negotiations) if n["proposal_id"] == proposal.proposal_id), None)
        # Structured fields only (numbers, enums, agent ids): no free text reaches the prompt (F14).
        facts = {"version": agreement["version"], "method": agreement["method"], "outcome": agreement["outcome"],
                 "allocation": agreement["allocation"], "degradation_mode": agreement["degradation_mode"],
                 "battery_discharge_mw": agreement["battery_discharge"], "fairness": engine.fairness,
                 "demands": (neg or {}).get("demands") or dict(engine.telemetry.consumer_meters),
                 "rounds": (neg or {}).get("rounds", proposal.rounds), "objective": proposal.objective}
        self._spawn(self._post_summary(engine, facts, proposal.proposal_id, proposal.negotiation_id))

    async def _post_summary(self, engine: SimulationEngine, facts: dict, proposal_id: str, nid: str | None):
        res = await self.llm.summarize_agreement(facts)
        async with self.lock:
            if engine is not self.engine:
                return
            engine.system_msg("analyst", MessageType.EXPLANATION, res["text"], proposal_id=proposal_id,
                              negotiation_id=nid, resource=None,
                              data={"source": res["source"], "advisory_only": True, "generated": res["generated"]})

    async def explain(self, question: str | None) -> dict:
        async with self.lock:
            facts = self.engine.explanation_facts()
            engine = self.engine
        res = await self.llm.explain(facts, question)
        async with self.lock:
            if engine is self.engine:
                engine.audit("commander", "commander", "request_explanation",
                             {"question": question, "source": res["source"]})
                engine.system_msg("analyst", MessageType.EXPLANATION, res["text"], resource=None,
                                  data={"source": res["source"], "question": question, "advisory_only": True,
                                        "generated": res["generated"]})
        return {**res, "facts": facts}


class RunManager:
    """Registry of independent simulation runs, one lock per run."""

    def __init__(self, settings: Settings, repo, llm: LLMService):
        self.settings = settings
        self.repo = repo
        self.llm = llm
        self.runs: dict[str, SimulationRuntime] = {}
        self._task: asyncio.Task | None = None

    def _make(self, run_id: str, seed: int | None, scenario: str) -> SimulationRuntime:
        ws = ConnectionManager(self.settings.chat_message_delay_ms, client_queue=self.settings.ws_client_queue)
        ws.start()
        rt = SimulationRuntime(self.settings, self.repo, ws, self.llm, run_id, seed, scenario)
        self.runs[run_id] = rt
        return rt

    async def start(self) -> None:
        self._make(DEFAULT_RUN, None, "grid_shortage")
        self._task = asyncio.create_task(self._housekeeping())

    def default(self) -> SimulationRuntime:
        return self.runs[DEFAULT_RUN]

    def get(self, run_id: str | None) -> SimulationRuntime:
        rt = self.runs.get(run_id or DEFAULT_RUN)
        if rt is None:
            raise EngineError("RUN_NOT_FOUND", f"run '{run_id}' not found", 404)
        rt.touch()
        return rt

    async def create(self, seed: int | None, scenario: str) -> SimulationRuntime:
        if len(self.runs) >= self.settings.max_runs:
            raise EngineError("TOO_MANY_RUNS", f"at most {self.settings.max_runs} concurrent runs", 429)
        return self._make(new_id("sim"), seed, scenario)

    async def delete(self, run_id: str) -> None:
        if run_id == DEFAULT_RUN:
            raise EngineError("PROTECTED_RUN", "the default run cannot be deleted; reset it instead", 409)
        rt = self.runs.pop(run_id, None)
        if rt is None:
            raise EngineError("RUN_NOT_FOUND", f"run '{run_id}' not found", 404)
        await rt.shutdown()

    def list_runs(self) -> list[dict]:
        return [rt.info() for rt in self.runs.values()]

    async def _housekeeping(self) -> None:
        last_prune = time.monotonic()
        while True:
            await asyncio.sleep(HOUSEKEEPING_INTERVAL_S)
            for rt in list(self.runs.values()):
                await rt.housekeeping()
            if time.monotonic() - last_prune > 30:
                last_prune = time.monotonic()
                await self.prune()

    async def prune(self) -> list[str]:
        """Drop abandoned runs (no API access and no WebSocket clients for RUN_TTL_S)."""
        now = time.monotonic()
        stale = [rid for rid, rt in self.runs.items() if rid != DEFAULT_RUN and not rt.ws.clients
                 and now - rt.last_access > self.settings.run_ttl_s]
        for rid in stale:
            log.info("expiring idle run %s", rid)
            await self.runs.pop(rid).shutdown()
        return stale

    async def shutdown(self) -> None:
        if self._task:
            self._task.cancel()
        for rt in list(self.runs.values()):
            await rt.shutdown()
