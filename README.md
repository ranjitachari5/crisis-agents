# CRISIS AGENTS

**Autonomous Multi-Agent Negotiation for Crisis Resource Allocation**

Team: Ranjith Kumar · Suraj M N · Shubhod Loni

During a disaster there isn't enough electricity to go round. CRISIS AGENTS simulates a city where six independent
utility agents (**Hospital, Water, Telecom, Emergency Services, Battery, Grid**) negotiate over the scarce supply
using signed, schema-validated messages. Agents bid, concede, and trade until they reach an agreement. Before any
allocation takes effect it must pass a **deterministic safety validator**. A **Crisis Trust Engine** detects fake,
replayed, or malicious claims and quarantines them. **Groq LLMs are used only for plain-language explanations**,
and the system falls back to deterministic templates when no API key is set.

> **Status:** the backend is complete: simulation, agents, negotiation, optimizer, validator, trust engine,
> persistence, REST and WebSocket API, evaluation, and a pytest suite. The React dashboard (`frontend/`) is the
> next milestone.

---

## Table of contents

1. [Key features](#key-features)
2. [How it works](#how-it-works)
3. [Tech stack](#tech-stack)
4. [Prerequisites](#prerequisites)
5. [Setup](#setup)
6. [Configuration (.env)](#configuration-env)
7. [Running the server](#running-the-server)
8. [Running the tests](#running-the-tests)
9. [Walkthrough demo](#walkthrough-demo)
10. [API overview](#api-overview)
11. [WebSocket live stream](#websocket-live-stream)
12. [Scenarios and events](#scenarios-and-events)
13. [Evaluation and baselines](#evaluation-and-baselines)
14. [Using PostgreSQL](#using-postgresql)
15. [Repository layout](#repository-layout)
16. [Troubleshooting](#troubleshooting)
17. [Further documentation](#further-documentation)

---

## Key features

- **Six autonomous agents.** Each agent has its own policy, private signing key, concession curve, and view of
  the world. Agents see only noisy telemetry and their own asset, never the ground truth.
- **Bounded negotiation protocol.** A negotiation runs for at most `MAX_NEGOTIATION_ROUNDS` rounds (default 5)
  with time-dependent concessions, direct peer-to-peer requests, and battery discharge offers. If the agents
  don't converge, a deterministic fallback takes over.
- **Fairness slider.** `f ∈ [0, 1]` blends priority-weighted allocation with equal-share allocation. Hard safety
  constraints apply at every slider value.
- **Deterministic validator.** Every commit path goes through the validator, with no exceptions. It enforces
  `Σ allocation ≤ supply`, per-agent minimums and maximums, ramp-rate limits, per-feeder capacity, battery
  discharge and state-of-charge limits, rejects NaN/inf/non-numeric values, and returns structured violation codes.
- **Versioned, idempotent agreements.** Every proposal carries a `base_version`. Commits are a single
  compare-and-swap transaction in the database with a UNIQUE `proposal_id`, so stale or duplicate commits are
  rejected even under concurrent retries.
- **Crisis Trust Engine.** Checks each message for a valid **Ed25519** signature (agents hold private keys; the
  engine holds only public keys), correct schema, a unique ID (durable replay protection in the database),
  per-agent sequence numbers and freshness. It cross-checks claims against telemetry using a robust
  median/MAD sensor consensus with plausibility gates, and requires corroboration from different sensor types.
  It never uses an LLM.
- **Degradation mode.** When the minimum needs exceed the supply, the optimizer minimizes weighted critical harm
  and reports the shortfall openly.
- **Cascading failures.** Water and telecom outages degrade hospital and emergency services through a
  dependency graph.
- **Commander controls.** A human commander can approve or reject proposals manually (with an approval
  timeout so an absent human never stalls allocation), isolate agents (which revokes their signing keys),
  resolve trust incidents, and override allocations.
- **Role-based access.** Bearer tokens with `viewer`, `commander` and `admin` roles; test tooling (reset, step,
  fake-event injection) is only registered when `ENABLE_TEST_ROUTES` is on.
- **Isolated runs.** Several independent simulations can run side by side under `/api/runs/{run_id}/...`.
- **Measured evaluation.** Runs the same scenario across seeds with baselines (FCFS, fixed priority,
  centralized, hidden-information, rolling-horizon) and ablations (no trust engine, fallback only, negotiation
  only); reports mean, std and 95% confidence intervals plus convergence and fallback rates.
- **Observability.** Prometheus metrics on `/metrics`: negotiation outcomes (converged / fallback / degraded),
  rounds, messages, solver runs, trust decisions, auth denials. The audit log is hash-chained and verifiable.
- **Live updates.** A WebSocket stream sends ordered events with sequence numbers, paced chat messages, and
  replay after reconnect.

## How it works

```
 Commander (REST)        WebSocket clients
        │                       ▲
        ▼                       │ ordered, paced events (seq-numbered, replayable)
  FastAPI routes ──► SimulationRuntime (asyncio lock, tick loop, LLM side-tasks)
                              │
                              ▼
                       SimulationEngine
   ┌──────────────┬───────────┼──────────────┬──────────────┬──────────────┐
 Telemetry     Agents     Negotiation     Validator     AgreementStore   TrustEngine
                              │
                     Repository (SQLAlchemy) ── SQLite / PostgreSQL
```

On each tick (15 simulated minutes by default):

1. **Physics:** the committed allocation is applied. The battery covers any gap, load is shed if it can't, and
   asset health decays when an agent runs below its minimum.
2. **Clock and events:** the clock advances and any scripted scenario events fire.
3. **Telemetry:** noisy sensor readings are taken (3 grid sensors, meters, battery, flood and seismic sensors).
4. **Reassessment:** if a trigger fires (supply or demand change, event, fairness change, commander request, and
   so on), the agents negotiate, the validator checks the result, and the result is committed.
5. **Cascades and broadcast:** service levels and cascading effects are recomputed and the state is broadcast.

The allocation objective is:

```
minimise  α·predicted_damage + β·fairness_penalty + γ·unmet_critical
α = 1,  β = 1.5 · fairness_slider,  γ = 50
```

The constraints are hard bounds rather than penalty terms, so no weight setting can trade them away.

**Who decides what:**

| Component | Decides | Never does |
|---|---|---|
| Agents | Their own bids, concessions, peer grants, battery offers | Read ground truth |
| Negotiation protocol | Round boundaries, deficit and fairness norm | Set allocations (except the fallback) |
| Optimizer | Reference, fallback, and degradation allocations | Commit anything |
| Validator | Whether a proposal is safe and current | Get bypassed |
| Trust engine | Accept, quarantine, escalate, or reject messages | Use an LLM |
| LLM (Groq) | The wording of explanations | Allocate, validate, or judge trust |

The full design is in [docs/architecture.md](docs/architecture.md).

## Tech stack

| Area | Technology |
|---|---|
| Language | Python 3.11+ (tested on 3.13) |
| Web framework | FastAPI + Uvicorn (REST + WebSocket) |
| Validation | Pydantic v2 (`extra="forbid"` message schemas) |
| Optimization | NumPy, SciPy (SLSQP, with a greedy fallback) |
| Persistence | SQLAlchemy 2.0, SQLite by default, PostgreSQL optional |
| LLM | Groq SDK (explanations only, optional) |
| Testing | pytest, httpx |

## Prerequisites

- **Python 3.11 or newer.** Check with `python --version`.
- **pip** and **venv** (included with standard Python installs).
- **Git**.
- *Optional:* a [Groq API key](https://console.groq.com/keys) for LLM explanations.
- *Optional:* PostgreSQL, if you don't want to use SQLite.

## Setup

### 1. Clone the repository

```bash
git clone <your-repo-url> crisis-agents
cd crisis-agents
```

### 2. Create and activate a virtual environment

Run this inside `backend/`:

```bash
cd backend
python -m venv .venv
```

Activate it:

| OS / shell | Command |
|---|---|
| Windows (PowerShell) | `.venv\Scripts\Activate.ps1` |
| Windows (cmd) | `.venv\Scripts\activate.bat` |
| Windows (Git Bash) | `source .venv/Scripts/activate` |
| macOS / Linux | `source .venv/bin/activate` |

> If PowerShell blocks the activation script, run
> `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` once.

### 3. Install dependencies

```bash
pip install --upgrade pip
pip install -r requirements.txt
```

`requirements.txt` at the repository root points to `backend/requirements.txt`, so you can also run
`pip install -r requirements.txt` from the root.

### 4. Create your `.env`

```bash
# from backend/
cp ../.env.example .env              # macOS / Linux / Git Bash
copy ..\.env.example .env            # Windows cmd
Copy-Item ..\.env.example .env       # Windows PowerShell
```

Then edit `backend/.env`:

- Set `COMMANDER_AUTH_TOKEN` to a secret value. Every control endpoint requires it as
  `Authorization: Bearer <token>`. In dev, without `ADMIN_AUTH_TOKEN`, it also acts as the admin token.
- *(Optional)* Set `GROQ_API_KEY` to enable LLM explanations.

The app reads `backend/.env` first and then `.env` at the repository root. `.env` is listed in `.gitignore`;
**never commit real secrets.**

### 5. Run it

```bash
python main.py
```

Open:

- API base URL: <http://127.0.0.1:8000>
- Swagger UI (interactive docs): <http://127.0.0.1:8000/docs>
- Health check: <http://127.0.0.1:8000/api/health>

## Configuration (.env)

All settings are optional and have sensible defaults (see `backend/app/config.py`).

| Variable | Default | Description |
|---|---|---|
| `GROQ_API_KEY` | *(empty)* | Groq API key. If it's empty, explanations use deterministic templates. |
| `GROQ_MODEL` | `openai/gpt-oss-120b` | Groq model used for explanations. |
| `LLM_ENABLED` | `true` | Master switch for LLM calls. |
| `LLM_TIMEOUT_S` | `12` | Timeout for each LLM request, in seconds. |
| `LLM_AGREEMENT_SUMMARIES` | `true` | Generate an LLM summary after each agreement. |
| `DATABASE_URL` | `sqlite:///backend/crisis_agents.db` | SQLAlchemy URL. See [Using PostgreSQL](#using-postgresql). |
| `TICK_INTERVAL_S` | `5` | Real seconds between ticks while the simulation is running. |
| `SIM_MINUTES_PER_TICK` | `15` | Simulated minutes per tick. |
| `CHAT_MESSAGE_DELAY_MS` | `250` | Delay between chat messages on the WebSocket, for readability. |
| `MAX_NEGOTIATION_ROUNDS` | `5` | Maximum rounds before the deterministic fallback takes over. |
| `RANDOM_SEED` | `42` | Seed for all randomness. The same seed and scenario give the same run. |
| `ENV` | `dev` | `dev` or `prod`. Outside `dev` the server refuses to start with weak tokens. |
| `COMMANDER_AUTH_TOKEN` | `change-me` | Bearer token for the `commander` role. **Change it** (>= 24 chars outside dev). |
| `ADMIN_AUTH_TOKEN` | *(empty)* | Bearer token for the `admin` role (reset, step, event injection). Required and distinct outside dev. |
| `VIEWER_AUTH_TOKEN` | *(empty)* | If set, GET routes and the WebSocket need it; if empty they are public. |
| `ENABLE_TEST_ROUTES` | dev only | Registers `reset`, `step` and `inject-fake`. |
| `AUTH_MAX_FAILURES_PER_MIN` | `10` | Failed authentications per client per minute before `429`. |
| `MAX_REQUEST_BYTES` | `65536` | Request body limit (`413` above it). |
| `MESSAGE_MAX_AGE_S` / `MESSAGE_CLOCK_SKEW_S` | `300` / `30` | Wall-clock freshness window for agent messages. |
| `MAX_RUNS` / `RUN_TTL_S` | `8` / `3600` | Concurrent simulation runs and idle expiry. |
| `APPROVAL_TIMEOUT_S` | `120` | Manual-approval proposals expire after this (0 disables). |
| `APPROVAL_TIMEOUT_POLICY` | `keep_last` | On expiry: `keep_last` (keep current allocation) or `commit` (commit if still valid). |
| `WS_CLIENT_QUEUE` / `WS_MAX_INBOUND_BYTES` / `WS_MAX_INBOUND_PER_S` | `256` / `4096` / `20` | WebSocket backpressure and inbound limits. |
| `DB_AUTO_CREATE` | dev only | `create_all` on startup; otherwise Alembic `upgrade head` runs. |
| `CORS_ORIGINS` | `http://localhost:5173,http://127.0.0.1:5173` | Comma-separated allowed origins (for the Vite dev server). |
| `LOG_LEVEL` | `INFO` | `DEBUG`, `INFO`, `WARNING`, or `ERROR`. |

Server options, set as environment variables and read by `backend/main.py`:

| Variable | Default | Description |
|---|---|---|
| `HOST` | `127.0.0.1` | Bind address. Use `0.0.0.0` to accept connections from other machines on your LAN. |
| `PORT` | `8000` | Port. |
| `RELOAD` | `false` | Set to `true` to auto-reload on code changes. |

## Running the server

From `backend/` with the virtual environment active:

```bash
python main.py                                   # standard
uvicorn main:app --reload                        # development, with auto-reload
uvicorn main:app --host 0.0.0.0 --port 8080      # custom host/port
```

The simulation starts **idle**. Call `POST /api/simulation/start` to begin.

Run with **one worker only**: simulation state lives in the process, so `--workers N` would split it
(`main.py` refuses `WEB_CONCURRENCY > 1`). Schema changes go through Alembic: `alembic upgrade head` from
`backend/` (it also runs automatically on startup when `DB_AUTO_CREATE` is off). A Dockerfile is in `backend/`.

## Running the tests

```bash
cd backend
python -m pytest -q                       # full suite
python -m pytest app/tests/test_trust.py  # a single file
python -m pytest -k validator -v          # filter by name
```

The tests cover the validator, optimizer, negotiation protocol, agreement store, trust engine, simulation
engine and API, plus property-based tests (hypothesis) for validator soundness, optimizer validity and sensor
consensus, a mutation fuzz of the trust engine, 50 concurrent commits, audit-chain tampering, route protection,
WebSocket limits and prompt-injection hygiene. Tests don't need a Groq key.

```bash
ruff check app migrations main.py && mypy app && pytest -q --cov=app --cov-fail-under=80   # what CI runs
python -m scripts.crisis_benchmark --seeds 1 2 3 4 5 --modes negotiation no_trust fallback_only centralized --adversarial
python -m scripts.load_test --clients 50 --seconds 30 --token <COMMANDER_AUTH_TOKEN>   # against a running server
```

## Walkthrough demo

With the server running, try the following in another terminal. On Windows PowerShell, use `curl.exe` instead
of `curl`, or use the Swagger UI at `/docs` (click **Authorize**). Control endpoints need the bearer token;
in dev the commander token also covers the admin-only calls (steps 4, 6 and 10).

```bash
export AUTH="Authorization: Bearer change-me"   # your COMMANDER_AUTH_TOKEN

# 1. Start the simulation. The first negotiation runs immediately.
curl -X POST localhost:8000/api/simulation/start -H "$AUTH"

# 2. Read the agents' structured group chat.
curl localhost:8000/api/negotiation/history

# 3. See the committed allocation.
curl localhost:8000/api/allocations/current

# 4. Inject a real crisis event. The agents renegotiate.
curl -X POST localhost:8000/api/events/inject -H "$AUTH" -H "Content-Type: application/json" \
     -d '{"event_type":"flood_warning","params":{"severity":2}}'

# 5. Shift toward equal shares. This triggers a renegotiation.
curl -X PUT localhost:8000/api/simulation/fairness -H "$AUTH" -H "Content-Type: application/json" \
     -d '{"value":0.9}'

# 6. Inject a fake attack. It is quarantined and the allocation doesn't change.
curl -X POST localhost:8000/api/events/inject-fake -H "$AUTH" -H "Content-Type: application/json" \
     -d '{"kind":"false_capacity_drop"}'
curl localhost:8000/api/trust/incidents

# 7. Ask for an explanation (Groq, or a deterministic template).
curl -X POST localhost:8000/api/commander/explain -H "$AUTH" -H "Content-Type: application/json" \
     -d '{"question":"Why did the hospital get more power than telecom?"}'

# 8. Switch to manual approval. Proposals now wait for the commander.
curl -X PUT localhost:8000/api/simulation/settings -H "$AUTH" -H "Content-Type: application/json" \
     -d '{"approval_mode":"manual","approval_timeout_s":120,"approval_timeout_policy":"keep_last"}'

# 9. Run the baseline comparison.
curl -X POST localhost:8000/api/evaluation/run -H "$AUTH" -H "Content-Type: application/json" \
     -d '{"scenario":"flood_cascade","seeds":[1,2,3],"ticks":32,"fairness":0.5,"modes":["negotiation","no_trust","centralized"]}'

# 10. Reset to a different scenario.
curl -X POST localhost:8000/api/simulation/reset -H "$AUTH" -H "Content-Type: application/json" \
     -d '{"scenario":"flood_cascade","seed":42}'
```

## API overview

The full reference is in [docs/api.md](docs/api.md), and the interactive version is at `/docs`.

Errors share one envelope:

```json
{"error": {"code": "STALE_PROPOSAL", "message": "...", "details": null}}
```

| Group | Endpoints |
|---|---|
| **Auth** | `Authorization: Bearer <token>`; viewer: GET + WebSocket · commander: control · admin: `events/inject`, `runs` delete, and (if enabled) `reset · step · inject-fake` |
| **Runs** | `GET/POST /api/runs`, `DELETE /api/runs/{run_id}`; every route below also exists as `/api/runs/{run_id}/...` |
| **Simulation** | `POST /api/simulation/start · pause · resume · reset · step`, `GET /api/simulation/state`, `PUT /api/simulation/fairness`, `PUT /api/simulation/settings`, `GET /api/simulation/metrics` |
| **Events** | `POST /api/events/inject`, `POST /api/events/inject-fake`, `GET /api/events/history`, `GET /api/events/catalog` |
| **Agents** | `GET /api/agents`, `GET /api/agents/{agent_id}` |
| **Negotiation** | `POST /api/negotiation/start · pause · resume`, `GET /api/negotiation/history` |
| **Allocations** | `GET /api/allocations/current · history`, `POST /api/allocations/validate · commit · reject` |
| **Trust** | `GET /api/trust/incidents`, `GET /api/trust/incidents/{id}`, `POST /api/trust/incidents/{id}/resolve`, `GET /api/trust/reputation`, `GET /api/trust/quarantine` |
| **Audit** | `GET /api/audit/logs`, `GET /api/audit/verify` (hash-chain check) |
| **Commander** | `POST /api/commander/explain`, `POST /api/commander/agents/{id}/isolate · restore`, `POST /api/commander/override`, `POST /api/commander/alerts/{id}/acknowledge` |
| **Evaluation** | `GET /api/evaluation/plan · results`, `POST /api/evaluation/run` |
| **Digital twin** | `GET /api/twin/graph` (nodes and edges ready for React Flow) |
| **Meta** | `GET /api/health`, `GET /api/meta`, `GET /healthz` (public liveness), `GET /metrics` (Prometheus) |

Agent IDs: `hospital_agent`, `water_agent`, `telecom_agent`, `emergency_agent`, `battery_agent`, `grid_agent`.

An override needs the commander token (in the header; it is never read from the body):

```bash
curl -X POST localhost:8000/api/commander/override -H "$AUTH" -H "Content-Type: application/json" -d '{
  "allocation": {"hospital_agent": 95, "water_agent": 55, "telecom_agent": 30, "emergency_agent": 40},
  "reason": "manual safety override"
}'
```

## WebSocket live stream

Connect to `ws://localhost:8000/ws/simulation` (default run) or `ws://localhost:8000/ws/runs/{run_id}`.

- **Authentication:** if `VIEWER_AUTH_TOKEN` is set, the first frame must be `{"type": "auth", "token": "..."}`
  (any role's token); otherwise the socket is closed with code 1008.
- **Limits:** inbound frames are capped in size (1009) and rate (1008). Each client has a bounded outbound queue;
  a client that can't keep up is disconnected (1008) instead of slowing everyone down.
- **When you connect**, the server sends `{"type": "snapshot", "data": {"state", "messages", "incidents"}, "event_seq": N}`.
- **After that**, each update arrives as `{"event_seq", "type", "data", "server_time"}`, where `type` is one of
  `message`, `message_status`, `state`, `agreement`, `negotiation`, `trust_incident`, `audit`, `alert`, or `reset`.
- **After a reconnect**, send `{"type": "sync", "since": <last event_seq>}`. The server replays the events you
  missed, or sends a fresh snapshot.
- **Keepalive:** send `{"type": "ping"}` and the server answers `pong`.

Quick test from a browser console:

```js
const ws = new WebSocket("ws://localhost:8000/ws/simulation");
ws.onmessage = (e) => console.log(JSON.parse(e.data));
```

## Scenarios and events

**Scenarios** (`POST /api/simulation/reset`):

| Scenario | Description |
|---|---|
| `grid_shortage` | 200 MW available out of 320 MW nominal. The battery covers the deficit for about 2.4 hours, then the city enters degradation mode. |
| `flood_cascade` | Scripted: demand surge (t3), flood (t6), pump failure (t9), telecom outage (t12), partial recovery (t18), full recovery (t24). |
| `normal` | 320 MW, no deficit. |

**Real events** (`POST /api/events/inject`): `power_reduction`, `flood_warning`, `hospital_demand_spike`,
`water_pump_failure`, `telecom_outage`, `battery_depletion`, `agent_disconnect`, `agent_reconnect`, `recovery`.

**Fake or attack events** (`POST /api/events/inject-fake`), which the trust engine should catch:
`false_capacity_drop`, `fake_disaster_alert`, `inflated_bid`, `replay_message`, `false_recovery`,
`contradictory_sensors`.

Initial values, the tick order, and the cascade formulas are in [docs/simulation.md](docs/simulation.md).

## Evaluation and baselines

`POST /api/evaluation/run` runs each mode in its own fresh headless engine with the same scenario, seeds and
number of ticks (the validator stays on in every mode). Pass `"seeds": [...]` for mean, std and 95% CI, and
`"adversarial": true` to make one agent over-report its demand by 50%. Every run is stored with a config hash.

Example measured run (`flood_cascade`, seed 42, 32 ticks, f = 0.5):

| Mode | Weighted damage | Critical uptime | Constraint violations | Mean recovery |
|---|---|---|---|---|
| FCFS | 28 120 | 75.0% | 10 | 105 min |
| Fixed priority | 29 233 | 71.9% | 12 | 360 min |
| Centralized | 9 929 | 90.6% | 0 | 180 min |
| **Negotiation** | **10 023** | **91.4%** | **0** | **82.5 min** |

Ablations (5 seeds, adversarial agent, mean weighted damage with 95% CI):

| Variant | Weighted damage | Note |
|---|---|---|
| Negotiation (full) | 10 012 [9 993, 10 031] | |
| No trust engine | 10 162 [10 142, 10 181] | inflated bids are accepted |
| Fallback only | 9 986 [9 967, 10 005] | optimizer decides directly |
| Negotiation only | 10 383 [10 362, 10 404] | no optimizer fallback |
| Centralized (full info) | 9 919 [9 907, 9 931] | upper reference |

Read these honestly: the trust engine measurably helps under adversarial input, the optimizer fallback matters,
and the negotiation layer lands within about 1% of the centralized optimum. It does not beat it. Only about 30%
of contested negotiations converge between agents; most of the rest run in degradation mode
(see `convergence_rate` / `fallback_rate` in `/api/simulation/metrics` and `/metrics`).

## Using PostgreSQL

SQLite works without any setup. To use PostgreSQL:

```bash
pip install "psycopg[binary]"
```

```env
DATABASE_URL=postgresql+psycopg://user:password@localhost:5432/crisis_agents
```

The tables (`run_sessions`, `messages`, `audit_logs`, `agreements`, `trust_incidents`, `evaluation_runs`) are
created automatically on startup.

## Repository layout

```
crisis-agents/
├── .env.example              template for backend/.env
├── requirements.txt          points to backend/requirements.txt
├── docs/
│   ├── architecture.md       design and safety argument
│   ├── api.md                full REST + WebSocket reference
│   └── simulation.md         state, tick order, events, cascades, evaluation
└── backend/
    ├── main.py               entry point (python main.py / uvicorn main:app)
    ├── requirements.txt
    └── app/
        ├── main.py           FastAPI app factory, error handlers, routers
        ├── config.py         settings loaded from environment / .env
        ├── agents/           6 agent classes and policies, signing keyring
        ├── negotiation/      bounded protocol, versioned agreement store
        ├── optimization/     SLSQP/greedy objective, baselines, harm weights
        ├── validation/       deterministic safety validator
        ├── trust/            trust engine, robust consensus, Ed25519 crypto, fake-event injector
        ├── simulation/       engine, telemetry, events, cascades, async runtime
        ├── evaluation/       metrics and baseline runner
        ├── llm/              Groq explanations with deterministic fallback
        ├── api/              REST routes, role-based auth
        ├── websocket/        WebSocket hub and routes
        ├── database/         SQLAlchemy models, repository (CAS commit, audit chain, replay store)
        ├── schemas/          Pydantic message and API schemas
        ├── models/           domain state and agent profiles
        └── tests/            pytest suite
```

## Troubleshooting

| Problem | Fix |
|---|---|
| `ModuleNotFoundError: No module named 'app'` | Run commands from `backend/`, not from the repository root. |
| `No module named pytest` / `fastapi` | Activate the virtual environment and reinstall: `pip install -r requirements.txt`. |
| PowerShell won't run `Activate.ps1` | Run `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`. |
| Port 8000 already in use | Pick another port, e.g. `PORT=8001 python main.py` (PowerShell: `$env:PORT=8001; python main.py`). |
| Explanations look templated | `GROQ_API_KEY` isn't set, or `LLM_ENABLED=false`. This is expected behavior without a key. |
| Control calls return `403 UNAUTHORIZED` | Send `Authorization: Bearer <COMMANDER_AUTH_TOKEN>` (admin-only calls need the admin token outside dev). |
| `429 TOO_MANY_AUTH_FAILURES` | Too many bad tokens from your client in a minute; wait and retry with the right token. |
| Logs say a table "is missing columns" | Your dev database predates the current schema. Delete `backend/crisis_agents.db` or run `alembic upgrade head` on a fresh database. |
| Server exits with "token is weak" | `ENV` is not `dev`: set strong, distinct `COMMANDER_AUTH_TOKEN` and `ADMIN_AUTH_TOKEN`. |
| `/api/simulation/step` returns an error | Stepping works only while the simulation is paused or idle. |
| Frontend gets CORS errors | Add its origin to `CORS_ORIGINS`. |
| You want a clean slate | Stop the server and delete `backend/crisis_agents.db`, or call `POST /api/simulation/reset`. |

## Further documentation

- [docs/architecture.md](docs/architecture.md): components, message lifecycle, negotiation algorithm,
  consistency guarantees
- [docs/api.md](docs/api.md): every endpoint, request body, and the message schema
- [docs/simulation.md](docs/simulation.md): initial state, tick order, scenarios, cascades, evaluation
