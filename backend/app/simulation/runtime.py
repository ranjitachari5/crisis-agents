"""Async runtime: owns the live engine, the tick loop and LLM side-tasks.

All engine mutations happen under one asyncio lock, so REST calls, the tick
loop and WebSocket events never interleave mid-negotiation.
"""
from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, Callable

from app.config import Settings
from app.llm.service import LLMService
from app.negotiation.agreements import AllocationProposal
from app.schemas.messages import MessageType
from app.simulation.engine import SimulationEngine
from app.websocket.manager import ConnectionManager

log = logging.getLogger(__name__)


class SimulationRuntime:
    def __init__(self, settings: Settings, repo, ws: ConnectionManager, llm: LLMService):
        self.settings = settings
        self.repo = repo
        self.ws = ws
        self.llm = llm
        self.lock = asyncio.Lock()
        self.tick_interval = settings.tick_interval_s
        self._loop_task: asyncio.Task | None = None
        self._side_tasks: set[asyncio.Task] = set()
        self._last_summary = 0.0
        self.engine = self._new_engine(settings.random_seed, "grid_shortage")

    def _new_engine(self, seed: int, scenario: str) -> SimulationEngine:
        e = SimulationEngine(self.settings, seed=seed, scenario=scenario, emit=self.ws.publish, repo=self.repo)
        e.commit_hooks.append(self._on_commit)
        return e

    # ------------------------------------------------------------- loop
    def ensure_loop(self) -> None:
        if self._loop_task is None or self._loop_task.done():
            self._loop_task = asyncio.create_task(self._loop())

    async def _loop(self) -> None:
        while True:
            await asyncio.sleep(self.tick_interval)
            try:
                async with self.lock:
                    if self.engine.status == "running":
                        self.engine.step()
            except Exception:
                log.exception("tick failed")

    async def shutdown(self) -> None:
        for t in [self._loop_task, *self._side_tasks]:
            if t:
                t.cancel()

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
        facts = {"version": agreement["version"], "method": agreement["method"],
                 "allocation": agreement["allocation"], "degradation_mode": agreement["degradation_mode"],
                 "battery_discharge_mw": agreement["battery_discharge"], "fairness": engine.fairness,
                 "demands": (neg or {}).get("demands") or dict(engine.telemetry.consumer_meters),
                 "trigger_note": "; ".join(proposal.notes) or None,
                 "rounds": (neg or {}).get("rounds", proposal.rounds), "objective": proposal.objective}
        self._spawn(self._post_summary(engine, facts, proposal.proposal_id, proposal.negotiation_id))

    async def _post_summary(self, engine: SimulationEngine, facts: dict, proposal_id: str, nid: str | None):
        res = await self.llm.summarize_agreement(facts)
        async with self.lock:
            if engine is not self.engine:
                return
            engine.system_msg("analyst", MessageType.EXPLANATION, res["text"], proposal_id=proposal_id,
                              negotiation_id=nid, resource=None,
                              data={"source": res["source"], "advisory_only": True})

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
                                  data={"source": res["source"], "question": question, "advisory_only": True})
        return {**res, "facts": facts}
