# Architecture

```
 Commander (REST)        WebSocket clients
        │                       ▲
        ▼                       │ ordered, paced events (seq-numbered, replayable)
  FastAPI routes (role-based bearer auth) ──► RunManager ──► SimulationRuntime per run
                                                   (own asyncio lock, tick loop, WS hub, LLM side-tasks)
                              │
                              ▼
                       SimulationEngine
   ┌──────────────┬───────────┼──────────────┬──────────────┬──────────────┐
 Telemetry     Agents     Negotiation     Validator     AgreementStore   TrustEngine
 (noisy,       (6, own    Protocol        (deterministic (versioned,     (auth, schema,
  sensors)      policy)   (mediator)       hard rules)    idempotent)     replay, telemetry,
                                                                          corroboration)
                              │
                     Repository (SQLAlchemy) ── SQLite / PostgreSQL
```

## Separation of concerns

| Layer | Decides | Never does |
|---|---|---|
| Agents (`app/agents`) | their own bids, concessions, peer grants, battery offers | read ground truth (only telemetry + own asset) |
| Negotiation protocol | round boundaries, relays deficit & fairness norm | set allocations (except deterministic fallback after `max_rounds`) |
| Optimizer | mediator reference / fallback / degradation allocation | commit anything |
| Validator | whether a proposal is safe & current | get bypassed — every commit path calls it |
| Agreement store | version, idempotency, stale rejection | accept an invalid proposal |
| Trust engine | accept / quarantine / escalate / reject messages | use an LLM, or hold a private key |
| LLM (Groq) | wording of explanations | allocate, validate, judge trust, or see free text from messages |

## Message lifecycle

1. An agent builds an `AgentMessage` (Pydantic, `extra="forbid"`) and signs the canonical JSON payload
   (sorted keys, fixed separators; every field except `seq`, `status`, `signature`, `trust`, including `kid`,
   `agent_seq` and `timestamp`) with its own **Ed25519** private key. The trust engine holds only public keys
   (two active key ids per agent during rotation); isolating an agent revokes its keys.
2. `engine.submit()` runs the Trust Engine: signature, isolation, schema, unique `(sender, message_id)`
   (in-memory TTL cache in front of a UNIQUE database table, so replays stay rejected after a restart),
   per-agent monotonic sequence number, sim-time and wall-clock freshness, telemetry comparison (meters, battery
   capability, robust grid sensor consensus, hazard sensors), corroboration from at least two different source
   types (SCADA, PMU, grid agent), source authority.
3. Status becomes `verified`, `quarantined` or `rejected`. Only verified messages change positions.
4. Every message is persisted, given a sequence number and broadcast.

## Negotiation (per reassessment)

1. Trigger: event, supply change > 2 MW, demand change > 3 MW, connectivity, battery capability, water
   2-hour limit, fairness change, periodic, or commander request.
2. Grid agent publishes verified supply: implausible readings are dropped, the median/MAD estimator (weighted
   by per-sensor reputation, threshold clamped to the measurement tolerance) rejects outliers, and the lowest kept
   value minus a 0.5% reserve margin is used. A large step that only a majority supports while the dissenter
   still reads the previous value (a correlated fault) is escalated to the commander instead of accepted.
3. Disconnected/isolated agents get their verified safe minimum reserved (fallback policy).
4. Consumer agents bid demand, minimum, flexibility and urgency.
5. Highest-urgency agent asks the Battery agent for discharge; the battery offers full capability only when
   minimums are at risk or the deficit persists (otherwise 50% to conserve reserve).
6. If minimums exceed supply → **degradation mode**: optimizer minimises weighted critical harm; agents issue
   emergency warnings; shortages are reported, never hidden.
7. Otherwise up to `MAX_NEGOTIATION_ROUNDS` (default 5):
   * mediator announces deficit and requested releases from the fairness norm
     (`(1-f)·priority share + f·equity share`);
   * each agent concedes according to its own time-dependent floor
     `min + flexible·max(0, 1 − rate·round)` (hospital never below ICU minimum; emergency slows concessions
     during active rescue; water attaches a 2-hour limit and stiffens once it is exceeded);
   * the most urgent agent sends a direct peer request to the agent with the most public slack, which grants,
     partially counters, or rejects by its own policy.
8. Converged → positions (+ surplus redistributed by the optimizer). Not converged → deterministic fallback.
   Load increases are capped by per-agent ramp limits (never below the safe minimum); the rest follows next tick.
9. Validator → commit (auto, or commander approval in manual mode) → version increments → state & chat update.
   Proposals awaiting approval are `superseded` by newer ones and `expired` after `APPROVAL_TIMEOUT_S`
   (policy `keep_last` or `commit`), so an absent commander never stalls allocation.
10. Every negotiation records its outcome (`uncontested | converged | fallback | degraded`), rounds, messages and
    solver metadata; these feed `/metrics` and the evaluation harness.

## Objective

```
minimise  α·predicted_damage + β·fairness_penalty + γ·unmet_critical
β = 1.5 · fairness_slider        α = 1, γ = 50
```
Hard constraints (`Σa ≤ supply`, `min ≤ a ≤ min(demand, max)`) are bounds, never penalties, so the slider cannot
remove them. The problem is convex (linear damage and shortfall terms plus a convex quadratic fairness term), so
an SLSQP KKT point is a global optimum; solves run through SLSQP → LP (HiGHS) → greedy with an iteration cap
and a wall-clock budget, warm-started from the previous allocation, and record solver, status, iterations and
time. If even the fallback fails validation, the last valid allocation stays in force. Weights include dependency impact (a water shortfall harms hospital and firefighting).
"Sum over time" is handled receding-horizon: optimise each reassessment; evaluation sums harm over all ticks.

## Consistency guarantees

* Unique proposal IDs; proposals carry `base_version`; commits require `base_version == current`.
* The database is the arbiter: a commit is one transaction that compare-and-swaps the run version and inserts
  the agreement under a UNIQUE `proposal_id` (50 concurrent identical commits → one row, one version bump; tested).
* Re-committing a committed proposal is a no-op (idempotent); pending proposals go `stale` on any new commit.
* Natural-language "I agree" messages carry no authority — only validated proposals commit (tested).
* All mutations of a run are serialised by that run's asyncio lock; runs are independent.
* State is in-process: run a single worker (`main.py` enforces it).
* The validator also enforces ramp limits, feeder capacity, battery energy, and rejects malformed numbers.

## Persistence

SQLAlchemy 2.0 with JSON columns. `DATABASE_URL=postgresql+psycopg://...` switches to PostgreSQL with no code
changes (install a driver; a connection pool is used). Tables: `run_sessions` (with CAS `version`), `messages`,
`seen_messages` (replay store), `audit_logs` (hash-chained: `hash = sha256(prev_hash + body)`, verify with
`GET /api/audit/verify`), `agreements` (UNIQUE `proposal_id`, `outcome`), `trust_incidents`, `evaluation_runs`
(with `config_hash`). Schema is managed by Alembic (`backend/migrations`); `create_all` is used only in dev.
SQLite runs in WAL mode with a busy timeout and `BEGIN IMMEDIATE` transactions.
