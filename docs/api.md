# API

Interactive docs: `http://127.0.0.1:8000/docs`. Errors use one envelope:
`{"error": {"code": "STALE_PROPOSAL", "message": "...", "details": ...}}` (400/403/404/409/422/500).

## Simulation
| Method | Path | Body |
|---|---|---|
| POST | `/api/simulation/start` | – (runs the first negotiation immediately) |
| POST | `/api/simulation/pause` · `/resume` | – |
| POST | `/api/simulation/reset` | `{"scenario": "grid_shortage"\|"flood_cascade"\|"normal", "seed": 42}` |
| POST | `/api/simulation/step` | `{"ticks": 1..96}` (only while paused/idle) |
| GET | `/api/simulation/state` | full snapshot |
| PUT | `/api/simulation/fairness` | `{"value": 0..1}` → triggers renegotiation |
| PUT | `/api/simulation/settings` | `{"approval_mode": "auto"\|"manual", "tick_interval_s": 0.5..60}` |
| GET | `/api/simulation/metrics?last=96` | measured metrics + series |

## Events
| POST | `/api/events/inject` | `{"event_type": "power_reduction"\|"flood_warning"\|"hospital_demand_spike"\|"water_pump_failure"\|"telecom_outage"\|"battery_depletion"\|"agent_disconnect"\|"agent_reconnect"\|"recovery", "params": {...}}` |
|---|---|---|
| POST | `/api/events/inject-fake` | `{"kind": "false_capacity_drop"\|"fake_disaster_alert"\|"inflated_bid"\|"replay_message"\|"false_recovery"\|"contradictory_sensors", "params": {...}}` |
| GET | `/api/events/history` · `/api/events/catalog` | |

## Agents, negotiation, allocations
| GET | `/api/agents` · `/api/agents/{agent_id}` | |
|---|---|---|
| POST | `/api/negotiation/start` | `{"reason": "..."}` |
| POST | `/api/negotiation/pause` · `/resume` | |
| GET | `/api/negotiation/history?since_seq=0&limit=300&negotiation_id=` | messages + negotiation summaries |
| GET | `/api/allocations/current` · `/api/allocations/history` | |
| POST | `/api/allocations/validate` | `{"allocation": {...}}` or `{"proposal_id": "..."}` |
| POST | `/api/allocations/commit` | `{"proposal_id": "..."}` (commander approval) |
| POST | `/api/allocations/reject` | `{"proposal_id": "...", "reason": "..."}` |

## Trust, audit, commander
| GET | `/api/trust/incidents` · `/api/trust/incidents/{id}` · `/api/trust/reputation` · `/api/trust/quarantine` | |
|---|---|---|
| POST | `/api/trust/incidents/{id}/resolve` | `{"action": "confirm_claim"\|"dismiss", "note": "", "confirmed_supply_mw": 200}` |
| GET | `/api/audit/logs?limit=200&category=&all_sessions=false` | |
| POST | `/api/commander/explain` | `{"question": "..."}` → Groq or deterministic |
| POST | `/api/commander/agents/{id}/isolate` · `/restore` | `{"reason": "..."}` |
| POST | `/api/commander/override` | `{"allocation": {...}, "reason": "...", "authorization": "<COMMANDER_AUTH_TOKEN>"}` |
| POST | `/api/commander/alerts/{id}/acknowledge` | |

## Evaluation & twin
| GET | `/api/evaluation/plan` · `/api/evaluation/results` | |
|---|---|---|
| POST | `/api/evaluation/run` | `{"scenario": "flood_cascade", "seed": 42, "ticks": 32, "fairness": 0.5, "modes": [...]}` |
| GET | `/api/twin/graph` | React-Flow-ready nodes/edges + cascades |
| GET | `/api/health` · `/api/meta` | |

## WebSocket `/ws/simulation`
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
 "sim_time": "ISO-8601", "status": "accepted", "signature": "hmac-sha256-hex",
 "trust": {"decision": "accepted", "score": 1.0}}
```
