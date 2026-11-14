# Architecture

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
| Trust engine | accept / quarantine / escalate / reject messages | use an LLM |
| LLM (Groq) | wording of explanations | allocate, validate, or judge trust |

## Message lifecycle

1. An agent builds an `AgentMessage` (Pydantic, `extra="forbid"`) and signs the canonical payload with
   HMAC-SHA256 using its own key.
2. `engine.submit()` runs the Trust Engine: signature, isolation, schema, unique ID, sim-time freshness,
   telemetry comparison (meters, battery capability, grid sensor consensus, hazard sensors), independent
   corroboration, source authority.
3. Status becomes `verified`, `quarantined` or `rejected`. Only verified messages change positions.
4. Every message is persisted, given a sequence number and broadcast.

## Negotiation (per reassessment)

1. Trigger: event, supply change > 2 MW, demand change > 3 MW, connectivity, battery capability, water
   2-hour limit, fairness change, periodic, or commander request.
2. Grid agent publishes verified supply (2-of-3 sensor consensus, lowest agreeing value, minus 0.5% reserve margin).
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
9. Validator → commit (auto, or commander approval in manual mode) → version increments → state & chat update.

## Objective

```
minimise  α·predicted_damage + β·fairness_penalty + γ·unmet_critical
β = 1.5 · fairness_slider        α = 1, γ = 50
```
Hard constraints (`Σa ≤ supply`, `min ≤ a ≤ min(demand, max)`) are bounds, never penalties, so the slider cannot
remove them. Weights include dependency impact (a water shortfall harms hospital and firefighting).
"Sum over time" is handled receding-horizon: optimise each reassessment; evaluation sums harm over all ticks.

## Consistency guarantees

* Unique proposal IDs; proposals carry `base_version`; commits require `base_version == current`.
* Re-committing a committed proposal is a no-op (idempotent); pending proposals go `stale` on any new commit.
* Natural-language "I agree" messages carry no authority — only validated proposals commit (tested).
* All engine mutations are serialised by one asyncio lock.

## Persistence

SQLAlchemy 2.0 with JSON columns. `DATABASE_URL=postgresql+psycopg://...` switches to PostgreSQL with no code
changes (install a driver). Tables: `run_sessions, messages, audit_logs, agreements, trust_incidents, evaluation_runs`.
