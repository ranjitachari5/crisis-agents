"""Bounded multi-round negotiation protocol.

The protocol is a *mediator*: it relays the deficit, the commander's
fairness norm and round boundaries. It has no authority to set allocations;
agents decide their own concessions and answer peer requests with their own
policies. Only if agents fail to converge within ``max_rounds`` does a
deterministic emergency fallback (the constrained optimizer) apply.

Every step emits a signed, schema-validated ``AgentMessage`` that is passed
through the Trust Engine (``submit``) before it can affect positions.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Callable

from app.agents.base import MessageContext, SystemActor
from app.agents.consumers import ConsumerAgent, Estimate
from app.agents.suppliers import BatteryAgent, GridAgent, GridAssessment
from app.models.state import CONSUMER_PROFILES
from app.negotiation.agreements import AllocationProposal
from app.optimization.allocator import AllocationProblem, evaluate_objective, solve
from app.optimization.weights import critical_weights
from app.schemas.messages import AgentMessage, MessageType, new_id
from app.simulation.telemetry import GRID_SENSOR_IDS

TOL = 0.05


@dataclass
class NegotiationInput:
    tick: int
    sim_time: datetime
    version: int
    fairness: float
    active: list[ConsumerAgent]
    reserved: dict[str, float]
    reserved_reason: dict[str, str]
    grid_assessment: GridAssessment
    grid: GridAgent
    battery: BatteryAgent | None
    trigger: str
    max_rounds: int


@dataclass
class NegotiationResult:
    negotiation_id: str
    proposal: AllocationProposal
    rounds: int
    converged: bool
    fallback_used: bool
    degradation: bool
    latency_ms: float
    demands: dict[str, float]
    final_positions: dict[str, float]
    position_messages: dict[str, str] = field(default_factory=dict)
    timeline: list[dict] = field(default_factory=list)

    def summary(self) -> dict:
        return {
            "negotiation_id": self.negotiation_id,
            "proposal_id": self.proposal.proposal_id,
            "method": self.proposal.method,
            "rounds": self.rounds,
            "converged": self.converged,
            "fallback_used": self.fallback_used,
            "degradation": self.degradation,
            "latency_ms": round(self.latency_ms, 2),
            "demands": self.demands,
            "final_positions": self.final_positions,
            "allocation": self.proposal.allocation,
            "supply_total": self.proposal.supply_total,
            "battery_offer": self.proposal.battery_offer,
            "timeline": self.timeline,
        }


def fairness_label(f: float) -> str:
    return "priority-focused" if f < 0.34 else "balanced" if f < 0.67 else "equity-focused"


class NegotiationProtocol:
    def __init__(self, submit: Callable[[AgentMessage], bool], post: Callable[[AgentMessage], AgentMessage],
                 mediator: SystemActor):
        self.submit = submit      # agent message -> trust-verified + published; returns accepted
        self.post = post          # system message -> published
        self.mediator = mediator

    # -- helpers -----------------------------------------------------------
    @staticmethod
    def problem(est: dict[str, Estimate], supply: float, fairness: float,
                lower_bounds: dict[str, float] | None = None) -> AllocationProblem:
        ids = list(est)
        crit = critical_weights()
        return AllocationProblem(
            agent_ids=ids,
            demand={i: est[i].demand for i in ids},
            min_safe={i: est[i].min_safe for i in ids},
            max_allowed={i: CONSUMER_PROFILES[i].max_allowed for i in ids},
            damage_weight={i: est[i].urgency for i in ids},
            critical_weight={i: crit[i] for i in ids},
            supply=supply,
            fairness=fairness,
            lower_bounds=lower_bounds,
        )

    @staticmethod
    def concession_shares(gap: float, est: dict[str, Estimate], bids: dict[str, float],
                          fairness: float) -> dict[str, float]:
        """The fairness norm announced by the mediator: how the deficit should be split.

        priority end: shares ~ 1/urgency^2 (low-urgency utilities give more)
        equity end:   shares ~ demand (equal percentage cuts)
        """
        slack = {i: bids[i] - est[i].min_safe for i in bids if bids[i] - est[i].min_safe > TOL}
        if not slack:
            return {}
        pw = {i: 1.0 / max(est[i].urgency, 0.1) ** 2 for i in slack}
        ew = {i: est[i].demand for i in slack}
        ps, es = sum(pw.values()), sum(ew.values())
        return {i: round(gap * ((1 - fairness) * pw[i] / ps + fairness * ew[i] / es), 3) for i in slack}

    # -- main --------------------------------------------------------------
    def run(self, inp: NegotiationInput) -> NegotiationResult:
        t0 = time.perf_counter()
        nid = new_id("neg")
        ctx = MessageContext(inp.tick, inp.sim_time, nid, 0)
        P = self.mediator
        timeline: list[dict] = []
        positions_msg: dict[str, str] = {}

        self.post(P.message(ctx, MessageType.SYSTEM,
                            f"Reassessment triggered: {inp.trigger}. Opening negotiation #{nid[-6:]}.",
                            data={"trigger": inp.trigger, "fairness": inp.fairness}, resource=None))

        # Step 2: supply from the grid agent (verified telemetry)
        ga = inp.grid_assessment
        gm = inp.grid.message(
            ctx, MessageType.SUPPLY_REPORT, inp.grid.describe(ga), quantity=ga.verified_supply,
            reason="sensor consensus minus reserve margin",
            data={"raw_value": ga.raw_value, "margin": ga.margin, "nominal": ga.nominal,
                  "consensus": ga.consensus.status,
                  "sensors": dict(zip(GRID_SENSOR_IDS, inp.grid.observation.grid_sensors))})
        self.submit(gm)
        inp.grid.last_reported = ga.verified_supply
        verified = ga.verified_supply or 0.0

        reserved_total = sum(inp.reserved.values())
        for aid, mw in inp.reserved.items():
            self.post(P.message(ctx, MessageType.SYSTEM,
                                f"@{aid} is {inp.reserved_reason.get(aid, 'unavailable')}. Fallback policy: "
                                f"reserving its verified safe minimum of {mw:.1f} MW outside negotiation.",
                                quantity=mw, mentions=[aid], data={"fallback": "reserved_minimum"}))
        grid_supply = max(0.0, verified - reserved_total)

        # Steps 3-4: each agent estimates its needs and bids
        est: dict[str, Estimate] = {}
        for ag in inp.active:
            e = ag.estimate()
            m = ag.message(ctx, MessageType.BID, ag.say_request(e), quantity=e.demand,
                           reason=f"minimum safe level {e.min_safe:.1f} MW",
                           data={"min_safe": e.min_safe, "flexible": e.flexible, "urgency": e.urgency})
            if not self.submit(m):
                tel = ag.observation
                meter = tel.consumer_meters[ag.agent_id]
                mn = tel.consumer_mins[ag.agent_id]
                meter = max(meter, mn)
                e = Estimate(meter, mn, round(meter - mn, 3), e.urgency)
                ag.estimate_ = e
                self.post(P.message(ctx, MessageType.SYSTEM,
                                    f"Bid from @{ag.agent_id} quarantined. Using telemetry-verified demand "
                                    f"{meter:.1f} MW instead.", mentions=[ag.agent_id], quantity=meter))
            est[ag.agent_id] = e
            positions_msg[ag.agent_id] = m.message_id
        ids = list(est)
        demand = {i: est[i].demand for i in ids}
        mins = {i: est[i].min_safe for i in ids}
        bids = dict(demand)
        total_d, total_m = sum(demand.values()), sum(mins.values())
        timeline.append({"step": "bids", "bids": dict(bids), "grid_supply": grid_supply})

        battery_offer = 0.0
        cap = inp.battery.capability() if inp.battery else 0.0
        rounds = 0
        converged = True
        fallback = False
        degradation = False
        method = "uncontested"
        requester = max(inp.active, key=lambda a: est[a.agent_id].urgency) if inp.active else None

        def ask_battery(amount: float, critical: bool, round_no: int, reason: str):
            nonlocal battery_offer
            if not inp.battery or requester is None:
                return
            rq = requester.message(ctx, MessageType.PEER_REQUEST,
                                   f"@battery_agent requesting {amount:.1f} MW temporary discharge — {reason}.",
                                   receiver="battery_agent", mentions=["battery_agent"], quantity=amount,
                                   reason=reason)
            self.submit(rq)
            offer, text, why = inp.battery.decide_offer(amount, critical, round_no)
            om = inp.battery.message(ctx, MessageType.OFFER if offer > 0 else MessageType.REJECT, text,
                                     quantity=offer, reason=why, in_reply_to=rq.message_id,
                                     mentions=[requester.agent_id],
                                     data={"soc": inp.battery.observation.battery_soc, "capability_mw": cap})
            if self.submit(om) and offer > battery_offer:
                battery_offer = offer

        deficit_grid = total_d - grid_supply
        if deficit_grid <= TOL:
            self.post(P.message(ctx, MessageType.SYSTEM,
                                f"Verified supply {grid_supply:.1f} MW covers all requests ({total_d:.1f} MW). "
                                f"No negotiation required.", quantity=total_d))
            candidate = dict(demand)
        else:
            self.post(P.message(ctx, MessageType.SYSTEM,
                                f"Resource deficit detected: requests {total_d:.1f} MW vs grid {grid_supply:.1f} MW "
                                f"(deficit {deficit_grid:.1f} MW). Safe minimums total {total_m:.1f} MW.",
                                quantity=deficit_grid, data={"deficit": deficit_grid, "total_min": total_m}))
            critical_need = total_m > grid_supply + TOL
            ask_battery(min(deficit_grid, max(cap, 0.0)) if cap > 0 else deficit_grid, critical_need, 0,
                        "safe minimums at risk" if critical_need else "covering flexible deficit")
            supply = grid_supply + battery_offer
            if total_d <= supply + TOL:
                method = "negotiation"
                candidate = dict(demand)
                self.post(P.message(ctx, MessageType.SYSTEM,
                                    f"Battery transfer of {battery_offer:.1f} MW closes the deficit.",
                                    quantity=battery_offer))
            elif total_m > supply + TOL:
                if battery_offer < cap - TOL:
                    ask_battery(cap, True, 2, "minimums cannot be met without full discharge")
                    supply = grid_supply + battery_offer
            if total_d > supply + TOL and total_m > supply + TOL:
                # Emergency degradation: minimums cannot all be met. Minimise weighted harm.
                degradation, converged, method = True, False, "degradation"
                self.post(P.message(ctx, MessageType.EMERGENCY_WARNING,
                                    f"EMERGENCY DEGRADATION MODE: safe minimums total {total_m:.1f} MW but only "
                                    f"{supply:.1f} MW is verified. Minimising weighted harm; unavoidable "
                                    f"shortages will be reported.", quantity=supply,
                                    data={"total_min": total_m, "supply": supply}))
                sol = solve(self.problem(est, supply, inp.fairness))
                candidate = sol.allocation
                for ag in inp.active:
                    a = candidate[ag.agent_id]
                    if a < est[ag.agent_id].min_safe - 1e-3:
                        self.submit(ag.message(ctx, MessageType.EMERGENCY_WARNING,
                                               ag.say_shortfall(a, est[ag.agent_id].min_safe), quantity=a,
                                               reason="unavoidable shortfall",
                                               data={"shortfall": round(est[ag.agent_id].min_safe - a, 3)}))
            elif total_d > supply + TOL:
                # Steps 5-6: bounded rounds of offers, counteroffers and concessions
                method = "negotiation"
                converged = False
                gap = total_d - supply
                for r in range(1, inp.max_rounds + 1):
                    rounds = r
                    ctx.round_id = r
                    gap = sum(bids.values()) - supply
                    shares = self.concession_shares(gap, est, bids, inp.fairness)
                    share_txt = ", ".join(f"{i.split('_')[0]} {v:.1f}" for i, v in shares.items())
                    rm = self.post(P.message(
                        ctx, MessageType.NEGOTIATION_ROUND,
                        f"Round {r}/{inp.max_rounds}: deficit {gap:.1f} MW. Fairness norm "
                        f"{fairness_label(inp.fairness)} (f={inp.fairness:.2f}). Requested releases (MW): {share_txt}.",
                        quantity=gap, data={"deficit": gap, "requested_shares": shares, "fairness": inp.fairness}))
                    for ag in sorted(inp.active, key=lambda a: est[a.agent_id].urgency):
                        aid = ag.agent_id
                        if aid not in shares:
                            continue
                        d = ag.decide_concession(r, shares[aid], bids[aid])
                        mtype = {"concession": MessageType.CONCESSION, "partial": MessageType.COUNTEROFFER,
                                 "hold": MessageType.REJECT}[d.kind]
                        m = ag.message(ctx, mtype, d.text, quantity=d.new_bid, reason=d.reason,
                                       in_reply_to=rm.message_id,
                                       data={"released": d.released, "requested": shares[aid],
                                             "position": d.new_bid, "conditions": d.conditions})
                        if self.submit(m):
                            bids[aid] = d.new_bid
                            positions_msg[aid] = m.message_id
                    gap = sum(bids.values()) - supply
                    if gap <= TOL:
                        converged = True
                        break
                    # direct agent-to-agent exchange
                    peers = [i for i in ids if i != requester.agent_id and bids[i] - mins[i] > TOL]
                    if peers:
                        peer_id = max(peers, key=lambda i: bids[i] - mins[i])
                        peer = next(a for a in inp.active if a.agent_id == peer_id)
                        ask = round(min(gap, bids[peer_id] - mins[peer_id]), 3)
                        pr = requester.message(ctx, MessageType.PEER_REQUEST,
                                               f"@{peer_id} deficit is still {gap:.1f} MW. Can you release "
                                               f"{ask:.1f} MW? Our critical load cannot absorb further cuts.",
                                               receiver=peer_id, mentions=[peer_id], quantity=ask,
                                               reason="peer reallocation request")
                        self.submit(pr)
                        d = peer.decide_peer_request(r, ask, requester.agent_id, bids[peer_id])
                        mtype = {"concession": MessageType.ACCEPT, "partial": MessageType.COUNTEROFFER,
                                 "hold": MessageType.REJECT}[d.kind]
                        m = peer.message(ctx, mtype, d.text, quantity=d.new_bid, reason=d.reason,
                                         in_reply_to=pr.message_id, mentions=[requester.agent_id],
                                         receiver=requester.agent_id,
                                         data={"released": d.released, "requested": ask, "position": d.new_bid,
                                               "conditions": d.conditions})
                        if self.submit(m):
                            bids[peer_id] = d.new_bid
                            positions_msg[peer_id] = m.message_id
                    if battery_offer < cap - TOL and r >= 1:
                        ask_battery(cap, total_m > grid_supply, r + 1, f"deficit persists after round {r}")
                        supply = grid_supply + battery_offer
                    timeline.append({"step": f"round_{r}", "bids": dict(bids), "supply": supply})
                    if sum(bids.values()) - supply <= TOL:
                        converged = True
                        break
                if converged:
                    surplus = supply - sum(bids.values())
                    candidate = (solve(self.problem(est, supply, inp.fairness, lower_bounds=bids)).allocation
                                 if surplus > TOL else dict(bids))
                    self.post(P.message(ctx, MessageType.SYSTEM,
                                        f"Agents converged in round {rounds}. Positions sum to "
                                        f"{sum(bids.values()):.1f} MW of {supply:.1f} MW"
                                        + (f"; redistributing {surplus:.1f} MW surplus." if surplus > TOL else "."),
                                        data={"positions": bids}))
                else:
                    fallback, method = True, "fallback"
                    gap = sum(bids.values()) - supply
                    self.post(P.message(ctx, MessageType.EMERGENCY_WARNING,
                                        f"No agreement after {inp.max_rounds} rounds (gap {gap:.1f} MW). Applying "
                                        f"deterministic emergency fallback policy (constrained optimizer, "
                                        f"f={inp.fairness:.2f}).", quantity=gap, data={"positions": bids}))
                    candidate = solve(self.problem(est, supply, inp.fairness)).allocation
            else:
                candidate = dict(demand)

        supply_total = grid_supply + battery_offer
        allocation = {**{i: round(v, 3) for i, v in candidate.items()}, **inp.reserved}
        objective = (evaluate_objective(self.problem(est, supply_total, inp.fairness),
                                        {i: allocation[i] for i in est}) if est else {})
        proposal = AllocationProposal(
            allocation=allocation, base_version=inp.version, method=method,
            supply_total=round(verified + battery_offer, 3), grid_supply=verified,
            battery_offer=round(battery_offer, 3), negotiation_id=nid, objective=objective,
            rounds=rounds, converged=converged, tick=inp.tick,
        )
        alloc_txt = ", ".join(f"{i.split('_')[0]} {v:.1f}" for i, v in allocation.items())
        self.post(P.message(ctx, MessageType.PROPOSAL,
                            f"Candidate allocation {proposal.proposal_id} ({method}): {alloc_txt} MW. "
                            f"Running safety and capacity validation.",
                            quantity=sum(allocation.values()), data={"allocation": allocation, "method": method,
                                                                    "proposal_id": proposal.proposal_id}))
        latency = (time.perf_counter() - t0) * 1000
        return NegotiationResult(nid, proposal, rounds, converged, fallback, degradation, latency,
                                 demand, dict(bids), positions_msg, timeline)
