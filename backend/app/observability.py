"""Prometheus metrics (F10). Exposed as text on ``/metrics``.

A dedicated registry keeps these separate from library defaults. Headless
engines (evaluation runs) do not report here, so live counters only reflect
the interactive simulations.
"""
from __future__ import annotations

from prometheus_client import CollectorRegistry, Counter, Histogram, generate_latest

REGISTRY = CollectorRegistry()

NEG_TOTAL = Counter("crisis_negotiations_total", "Negotiations by outcome", ["outcome"], registry=REGISTRY)
NEG_ROUNDS = Histogram("crisis_negotiation_rounds", "Negotiation rounds used",
                       buckets=[0, 1, 2, 3, 4, 5, 6, 8, 10], registry=REGISTRY)
NEG_MESSAGES = Histogram("crisis_negotiation_messages", "Messages published per negotiation",
                         buckets=[5, 10, 20, 40, 80, 160, 320], registry=REGISTRY)
NEG_SECONDS = Histogram("crisis_negotiation_seconds", "Wall time per negotiation",
                        buckets=[0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0], registry=REGISTRY)
SOLVER_RUNS = Counter("crisis_solver_runs_total", "Optimizer runs by solver and status", ["solver", "status"],
                      registry=REGISTRY)
SOLVER_SECONDS = Histogram("crisis_solver_seconds", "Optimizer wall time",
                           buckets=[0.0005, 0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5], registry=REGISTRY)
COMMITS = Counter("crisis_commits_total", "Committed agreements by outcome", ["outcome"], registry=REGISTRY)
PROPOSALS_EXPIRED = Counter("crisis_proposals_expired_total", "Manual-approval proposals that timed out",
                            ["policy"], registry=REGISTRY)
TRUST_DECISIONS = Counter("crisis_trust_decisions_total", "Trust engine decisions", ["decision"], registry=REGISTRY)
AUTH_DENIED = Counter("crisis_auth_denied_total", "Denied API requests", ["reason"], registry=REGISTRY)
WS_DROPPED = Counter("crisis_ws_clients_dropped_total", "WebSocket clients dropped", ["reason"], registry=REGISTRY)


def render() -> bytes:
    return generate_latest(REGISTRY)
