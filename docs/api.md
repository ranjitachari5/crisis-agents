# API

Interactive docs: `http://127.0.0.1:8000/docs`. Errors use one envelope:
`{"error": {"code": "STALE_PROPOSAL", "message": "...", "details": ...}}` (400/403/404/409/413/422/429/500).

## Authentication
Send `Authorization: Bearer <token>`. Roles: **viewer** (all GET routes, WebSocket; public when
`VIEWER_AUTH_TOKEN` is unset), **commander** (everything marked *C*), **admin** (everything marked *A*, plus all
commander routes). Missing/wrong/insufficient tokens get `403`; repeated failures get `429`. Routes marked *T*
are admin-only test tooling registered only when `ENABLE_TEST_ROUTES` is on (default: dev only).

## Runs
Every route below exists for the default run at `/api/...` and for any run at `/api/runs/{run_id}/...`.
| Method | Path | Body |
|---|---|---|
| GET | `/api/runs` | list runs |
| POST *C* | `/api/runs` | `{"scenario": "...", "seed": 7}` → `{"run_id", "state"}` |
| DELETE *A* | `/api/runs/{run_id}` | (the `default` run cannot be deleted) |

## Simulation
| Method | Path | Body |
|---|---|---|
| POST *C* | `/api/simulation/start` | – (runs the first negotiation immediately) |
| POST *C* | `/api/simulation/pause` · `/resume` | – |
| POST *T* | `/api/simulation/reset` | `{"scenario": "grid_shortage"\|"flood_cascade"\|"normal", "seed": 42}` |
| POST *T* | `/api/simulation/step` | `{"ticks": 1..96}` (only while paused/idle) |
| GET | `/api/simulation/state` | full snapshot |
| PUT *C* | `/api/simulation/fairness` | `{"value": 0..1}` → triggers renegotiation |
| PUT *C* | `/api/simulation/settings` | `{"approval_mode": "auto"\|"manual", "approval_timeout_s": 0..3600, "approval_timeout_policy": "keep_last"\|"commit", "tick_interval_s": 0.5..60}` |
| GET | `/api/simulation/metrics?last=96` | measured metrics + series + negotiation outcome rates |

## Events
| POST *A* | `/api/events/inject` | `{"event_type": "power_reduction"\|"flood_warning"\|"hospital_demand_spike"\|"water_pump_failure"\|"telecom_outage"\|"battery_depletion"\|"agent_disconnect"\|"agent_reconnect"\|"recovery", "params": {...}}` |
|---|---|---|
| POST *T* | `/api/events/inject-fake` | `{"kind": "false_capacity_drop"\|"fake_disaster_alert"\|"inflated_bid"\|"replay_message"\|"false_recovery"\|"contradictory_sensors", "params": {...}}` (sensors: `{"mode": "single"\|"split"\|"correlated"}`) |
| GET | `/api/events/history` · `/api/events/catalog` | |

## Agents, negotiation, allocations
| GET | `/api/agents` · `/api/agents/{agent_id}` | |
|---|---|---|
| POST *C* | `/api/negotiation/start` | `{"reason": "..."}` |
| POST *C* | `/api/negotiation/pause` · `/resume` | |
| GET | `/api/negotiation/history?since_seq=0&limit=300&negotiation_id=` | messages + negotiation summaries |
| GET | `/api/allocations/current` · `/api/allocations/history` | |
| POST *C* | `/api/allocations/validate` | `{"allocation": {...}}` or `{"proposal_id": "..."}` |
| POST *C* | `/api/allocations/commit` | `{"proposal_id": "..."}` (commander approval; `409` if expired/superseded/stale) |
| POST *C* | `/api/allocations/reject` | `{"proposal_id": "...", "reason": "..."}` |

## Trust, audit, commander
| GET | `/api/trust/incidents` · `/api/trust/incidents/{id}` · `/api/trust/reputation` · `/api/trust/quarantine` | |
|---|---|---|
| POST *C* | `/api/trust/incidents/{id}/resolve` | `{"action": "confirm_claim"\|"dismiss", "note": "", "confirmed_supply_mw": 200}` |
| GET | `/api/audit/logs?limit=200&category=&all_sessions=false` | rows include `hash` / `prev_hash` |
| GET | `/api/audit/verify` | `{"ok", "checked", "first_broken_id", "reason"}` |
| POST *C* | `/api/commander/explain` | `{"question": "..."}` → Groq (labelled `generated`) or deterministic, always with `deterministic_summary` |
| POST *C* | `/api/commander/agents/{id}/isolate` · `/restore` | `{"reason": "..."}` (isolation revokes the agent's keys; restore issues new ones) |
| POST *C* | `/api/commander/override` | `{"allocation": {...}, "reason": "..."}` |
| POST *C* | `/api/commander/alerts/{id}/acknowledge` | |

## Evaluation & twin
| GET | `/api/evaluation/plan` · `/api/evaluation/results` | |
|---|---|---|
| POST *C* | `/api/evaluation/run` | `{"scenario": "flood_cascade", "seed": 42, "seeds": [1,2,3], "ticks": 32, "fairness": 0.5, "modes": [...], "adversarial": false}`; modes: `negotiation, no_trust, fallback_only, negotiation_only, centralized, hidden_information, rolling_horizon, fixed_priority, fcfs` |
| GET | `/api/twin/graph` | React-Flow-ready nodes/edges + cascades |
| GET | `/api/health` · `/api/meta` | |
| GET | `/metrics` | Prometheus text format |
| GET | `/healthz` | public liveness probe |

## WebSocket `/ws/simulation` · `/ws/runs/{run_id}`
If `VIEWER_AUTH_TOKEN` is set, the first frame must be `{"type": "auth", "token": "..."}` (closed with 1008
otherwise). Inbound frames are limited in size (1009) and rate (1008); slow consumers are dropped (1008).
On connect: `{"type": "snapshot", "data": {"state", "messages", "incidents"}, "event_seq": N}`.
Then envelopes `{"event_seq", "type", "data", "server_time"}` with type `message | message_status | state |
agreement | negotiation | trust_incident | audit | alert | reset`. Chat messages are paced
(`CHAT_MESSAGE_DELAY_MS`) for readability. After reconnect send `{"type": "sync", "since": <last event_seq>}`;
the server replays missed events or sends a fresh snapshot. `{"type": "ping"}` → `pong`.

## Message schema
```json
{"message_id": "msg-…", "seq": 12, "round_id": 1, "negotiation_id": "neg-…", "tick": 0,
 "sender": "hospital_agent", "receiver": "negotiation_group", "message_type": "counteroffer",
 "resource": "electricity", "quantity": 94.7, "unit": "MW", "reason": "bounded concession this round",
 "text": "Only 5.0 MW of administrative load can be deferred…", "mentions": [], "in_reply_to": "msg-…",
 "proposal_id": null, "data": {"released": 5.0, "requested": 14.1}, "timestamp": "ISO-8601",
 "sim_time": "ISO-8601", "kid": "hospital_agent#1a2b3c4d", "agent_seq": 7,
 "status": "accepted", "signature": "ed25519-hex",
 "trust": {"decision": "accepted", "score": 1.0}}
```
