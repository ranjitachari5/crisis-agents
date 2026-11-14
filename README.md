# CRISIS AGENTS

**Autonomous Multi-Agent Negotiation for Crisis Resource Allocation**

Team: Ranjith Kumar · Suraj M N · Shubhod Loni

Six independent utility agents (Hospital, Water, Telecom, Emergency Services, Battery, Grid) negotiate scarce
electricity during a disaster through signed, schema-validated messages. A deterministic validator is the only gate
to a committed, versioned allocation; a Crisis Trust Engine quarantines fake or malicious claims; Groq LLMs are used
**only** for explanations (with a deterministic fallback when no key is set).

> Status: **backend complete** (simulation, agents, negotiation, optimizer, validator, trust engine, persistence,
> REST + WebSocket API, evaluation, 42 tests passing). The React dashboard (`frontend/`) is the next milestone.

## Quick start (backend)

Requirements: Python 3.11+ (tested on 3.13).

```bash
cd backend
python -m venv .venv
# Windows: .venv\Scripts\activate     macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
cp ../.env.example .env                # then set GROQ_API_KEY and COMMANDER_AUTH_TOKEN
python main.py                         # http://127.0.0.1:8000  (Swagger UI at /docs)
```

Run tests:

```bash
cd backend
python -m pytest -q
```

Without `GROQ_API_KEY` everything still works; explanations come from deterministic templates.

## Two-minute demo (curl)

```bash
curl -X POST localhost:8000/api/simulation/start                       # first negotiation runs immediately
curl localhost:8000/api/negotiation/history                             # the live group chat (structured)
curl -X POST localhost:8000/api/events/inject -H "Content-Type: application/json" \
     -d '{"event_type":"flood_warning","params":{"severity":2}}'         # agents renegotiate
curl -X PUT localhost:8000/api/simulation/fairness -H "Content-Type: application/json" -d '{"value":0.9}'
curl -X POST localhost:8000/api/events/inject-fake -H "Content-Type: application/json" \
     -d '{"kind":"false_capacity_drop"}'                                 # quarantined, allocation unchanged
curl -X POST localhost:8000/api/commander/explain                        # Groq explanation (advisory)
curl -X POST localhost:8000/api/evaluation/run                           # measured baseline comparison
```

Live stream: connect a WebSocket to `ws://localhost:8000/ws/simulation`.

## Repository layout

```
backend/
  main.py                 entry point
  app/
    agents/               6 agent classes + policies, signing keys
    negotiation/          bounded protocol, versioned agreement store
    optimization/         SLSQP/greedy objective, baselines, harm weights
    validation/           deterministic safety validator
    trust/                trust engine, consensus, HMAC, fake-event injector
    simulation/           city state engine, telemetry, events, cascades, async runtime
    evaluation/           metrics + baseline runner
    llm/                  Groq explanations with deterministic fallback
    api/  websocket/      REST routes, WS hub
    database/             SQLAlchemy models + repository (SQLite → PostgreSQL via DATABASE_URL)
    schemas/  models/     Pydantic message/API schemas, domain state
    tests/                42 tests
docs/  architecture.md · api.md · simulation.md
```

See [docs/architecture.md](docs/architecture.md) for the design and safety argument.
