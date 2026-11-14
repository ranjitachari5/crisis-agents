# FRONTEND SPEC: CRISIS AGENTS Commander Dashboard

## Role

You are a senior frontend engineer and UI/UX designer working in React and Tailwind. The FastAPI + WebSocket backend is finished. Build the **single-page commander dashboard** for CRISIS AGENTS, where utility agents (hospital, water, telecom, emergency, battery, grid) negotiate scarce electricity during a disaster.

It must look like a product a small team of careful developers built over several weeks. It must not look generated.

## How to work (Antigravity)

- Work in **Planning mode**. Before writing code, produce an **Implementation Plan** artifact, and **stop for my approval**.
- Keep the **Task List** artifact up to date, one item per build step below.
- After each UI step, start the dev server and use the **browser agent** to open the page. Take a screenshot and check it against this spec: palette, spacing, highlight behavior. Attach the screenshots to the step.
- Run `npm run build` and `npm run lint` after every step. Do not continue while either fails.
- At the end, produce a **Walkthrough** artifact: what works, what is missing, and how to run it.
- Report honestly. If something in this spec doesn't exist in the backend, tell me, and show an empty state in the UI.

## Step 0: Verify against the backend

Open `backend/` and confirm the schemas, routes and WebSocket handler match the API summary below. Build TypeScript types from the real Pydantic schemas. Never invent fields. If the code and this document disagree, the code wins, and you tell me about it.

## Stack

React, Vite, TypeScript (strict), Tailwind CSS (config-file tokens), Framer Motion, Recharts, Lucide React, React Flow, Zustand.

## Design

**Mood:** a quiet, serious operations console. Minimal, flat, dense but not crowded.

| Token | Value | Use |
|---|---|---|
| `bg` | `#0B0B0C` | page |
| `surface` | `#111113` | panels |
| `surface-2` | `#17171A` | raised elements, inputs |
| `border` | `#26262B` | 1px dividers |
| `text` | `#F4F4F5` | primary |
| `muted` | `#8B8B94` | secondary |
| `accent` | `#E5484D` | the one red thing in an area |
| `accent-dim` | `rgba(229,72,77,0.15)` | request tint |
| `ok` | `#4ADE80` | verified / healthy only |

- Define these as Tailwind theme tokens. No hex values inside components.
- Red is the only accent. Use it for the active agent, the current round, the primary action and critical alerts. If everything is red, nothing is.
- No gradients, glassmorphism, glow, purple or blue. Status is text plus a small dot, never a large colored block.
- Font: `ui-sans-serif, system-ui, sans-serif`. Use `tabular-nums` on all numbers. Sizes 12 / 13 / 14 / 16 / 20 / 28 only. Weights 400 / 500 / 600 only. Section labels may be 11px uppercase with letter-spacing.
- 4px spacing grid. Radius 6px on panels, 4px on controls. 1px borders instead of shadows. Panel padding 16 or 24px. Lucide icons at 16px, stroke 1.5. No emoji.

## What makes it feel human-built

- No hero banners, floating blobs, fake 3D, sparkle icons or "AI-powered" badges.
- Copy is plain and specific: "Grid supply dropped to 80 MW". No exclamation marks.
- Panels have uneven, realistic sizes. Not every card is the same.
- Every panel has real loading, empty and error states. An empty state is one muted line.
- Formats are consistent: `120 MW`, `3 / 6 agents`, `14:32:07`.
- Components are small and named by job (`AgentCard`, `MessageBubble`). No giant files, commented-out code or lorem ipsum.

## Motion (functional only)

- 150-250ms, ease-out. No bounce or spring overshoot, and nothing loops.
- Chat message: fade in + 4px slide up.
- Requesting agent card: border animates to red and a faint tint holds ~3s, then fades.
- Network edge: stroke turns red, one dot travels the edge (~800ms), then it fades to grey after ~2s.
- Number change: short cross-fade, no counting up.
- Allocation bars: 300ms width transition.
- Respect `prefers-reduced-motion`: drop the dot and slides, keep color changes.
- The page is calm at rest. Nothing animates unless something happened.

## Layout

One page, no router. Fixed top bar, slim left sidebar with smooth-scroll anchors and scroll-spy, scrolling main column. On narrow screens the sidebar becomes a top drawer.

**Top bar:** "CRISIS AGENTS" wordmark (plain, semibold), simulation status (Idle / Running / Paused) from `status`, scenario from `scenario`, sim time from `sim_time`, WebSocket state (Connected / Reconnecting), and a **local** label "Commander" (it is not in the API).

**Sections and sidebar anchors, in order:** Overview, Live Negotiation, City Digital Twin, Agent Network, Crisis Trust Engine, Resource Allocation, Simulation Lab, Audit Logs.

### 1. Overview
- Metric tiles: total available supply, total demand, deficit (red when > 0), active agents (x / 6), active alerts, negotiation round, infrastructure health %.
- Active alerts list with an Acknowledge button (`POST /api/commander/alerts/{id}/acknowledge`).
- **Commander controls:** Start, Pause, Resume, Reset, Advance (`step`), and the fairness slider.
- **Fairness slider:** value 0..1, stops at 0 / 0.5 / 1 (Priority / Balanced / Equity). Show the current value and a one-line policy description. Debounce on release, then call `PUT /api/simulation/fairness { value }`. Take the new allocation from the next `state` or `agreement` event; never compute it locally. Add the note: "Safety minimums are not affected by this setting."

### 2. Agent Grid + Live Negotiation (side by side on desktop)

**Agent grid:** 6 cards showing name, icon, status (`online | isolated | disconnected`), demand, minimum, allocated, and a thin allocation bar.
- Isolated or disconnected agents are dimmed with a label.
- Clicking a card opens a right drawer with `GET /api/agents/{id}` and its `recent_messages`.
- The drawer has Isolate / Restore (`POST /api/commander/agents/{id}/isolate` and `/restore`). These exist **for the four consumer agents only**. For `battery_agent` and `grid_agent`, show the action disabled with one muted line: "Not isolable".

**Live negotiation chat**, titled **CITY EMERGENCY: LIVE NEGOTIATION**:
- Agents are told apart by icon and name, not by color. System, protocol and agreement messages use a centered, muted, full-width style.
- Each message shows the sender, text built from the structured fields (including `reason`), a quantity + unit chip, a type tag, round, timestamp, and status.
- Mentions of other agents render as plain highlighted text.
- Auto-scroll to the newest message. If the user has scrolled up, stop and show a "New messages" button.
- Filters: All / Requests / Offers / Agreements / System.
- `aria-live="polite"` on the message list.
- Below the chat: pending proposals (Reject = `POST /api/allocations/reject`; Request explanation = `POST /api/commander/explain { question }` naming the proposal id, with a pending state until the `explanation` message arrives), and verified agreements with version numbers.
- Negotiation controls: Start / Pause / Resume (`/api/negotiation/*`).

### 3. Agent Network (React Flow)
- Six agent nodes plus a hub node with id `negotiation_group`.
- Base edges: every agent to the hub (grey), plus agent-to-agent edges derived from the twin `dependency` and `power` edges. Read the twin node ids and map them to agent ids in `lib/agents.ts`.
- Edge id is the sorted pair, `[a,b].sort().join("|")`, so direction never creates duplicates.
- Locked layout, no drag, no minimap. Dimmed nodes and dashed edges for isolated or disconnected agents.

### 4. City Digital Twin
- Use `GET /api/twin/graph`. Nodes are grid, battery, power_bus, the four utilities, and derived services (ICU, hospital water, firefighting, dispatch). Edges have `kind` of `power | dependency | service` and `data.mw`.
- Power edges are solid, with stroke width scaled from `data.mw` and clamped to 1-6px. Dependency edges are dashed. Service edges are thin and grey.
- Node health comes from the node `status`. Read the real enum from the schema and map it to normal, degraded and failed, with failed in red. Tell me the final mapping.
- `cascades[].path` is a `string[]`. Show it as text joined with " -> ", and mark the nodes along the path as degraded one after another (~150ms apart).

### 5. Crisis Trust Engine
- An outlined red **Inject Fake Crisis** button (`POST /api/events/inject-fake`).
- Incident list (`GET /api/trust/incidents`) and an `IncidentDetail` panel with: claim, an `evidence[]` table (check, passed, observed, expected, detail), decision, quarantined, escalated, `agent_responses`, a clear line **"Allocation changed: Yes / No"**, and resolved.
- Escalated and unresolved incidents show Approve (`confirm_claim`) and Reject (`dismiss`) via `POST /api/trust/incidents/{id}/resolve`.
- Two small lists: agent reputation (`GET /api/trust/reputation`) and quarantine (`GET /api/trust/quarantine`).
- Quarantined messages also appear in the chat, muted, with a "Quarantined" tag.

### 6. Resource Allocation
- Recharts bar chart per agent: minimum, allocated and demand. White, grey and red only, with red marking unmet demand.
- Supply vs. demand line chart, built from `state` events received **since page load**, with that caption. Do not backfill it with generated points.
- Show `allocation_version`, `degradation_mode` and the reported shortages.
- **Override** is a deliberately heavy action. The dialog takes a reason and a token (`type="password"`, kept in memory only, never in localStorage). Flow: Validate (`POST /api/allocations/validate`), show the result, then enable "Commit override" (`POST /api/commander/override` with `authorization`). A wrong token returns the API error; show it inline.

### 7. Simulation Lab
- **Event panel:** build it from `GET /api/events/catalog`, not a hardcoded list. Label overrides: `power_reduction` -> Power shortage (with a magnitude input), `flood_warning` -> Flood, `hospital_demand_spike` -> Hospital demand spike, `water_pump_failure` -> Water pumping failure, `telecom_outage` -> Telecom outage, `agent_disconnect` -> Disconnect agent (select), `recovery` -> Restore supply. Also show `battery_depletion` and `agent_reconnect` if the catalog has them. Submit with `POST /api/events/inject`, with inline success or error feedback. A "Recent events" list reads `GET /api/events/history`.
- **Evaluation:** show the plan (`GET /api/evaluation/plan`). A "Run evaluation" button calls `POST /api/evaluation/run` with a loading state. The table has the four modes as rows and these columns exactly: `weighted_damage`, `critical_service_uptime_pct`, `unmet_demand_mwh`, `mean_fairness_penalty`, `constraint_violations`, `mean_negotiation_latency_ms`, `mean_recovery_time_min`. Until a run exists, show `—` in every cell and "No run recorded". Never invent numbers.

### 8. Audit Logs
- Dense table: time (`created_at`), actor, action, category, details, tick. The backend has no target or outcome field, so do not fake them.
- Filters: actor, category, and text search over action and details. Commander rows (`actor === "commander"` or `category === "commander"`) get a small red marker. Virtualize or paginate.

## Backend contract

**REST** (all under `/api`): simulation (`start`, `pause`, `resume`, `reset`, `step`, `state`, `fairness`, `settings`, `metrics`), events (`inject`, `inject-fake`, `history`, `catalog`), agents (list and `{id}`), negotiation (`start`, `pause`, `resume`, `history`), allocations (`current`, `history`, `validate`, `commit`, `reject`), trust (`incidents`, `incidents/{id}`, `incidents/{id}/resolve`, `reputation`, `quarantine`), audit (`logs`), commander (`explain`, `agents/{id}/isolate`, `agents/{id}/restore`, `override`, `alerts/{id}/acknowledge`), evaluation (`plan`, `results`, `run`), twin (`graph`), meta (`health`, `meta`). Errors are `{ error: { code, message, details } }`; parse them in one `ApiError` class.

**WebSocket** `/ws/simulation`:
- On connect, the first frame is `{ type: "snapshot", data: { state, messages, incidents }, event_seq }`.
- After that, frames are `{ event_seq, type, data, server_time }` with `type` one of `message | message_status | state | agreement | negotiation | trust_incident | audit | alert | reset`. Also `pong` and `error`.
- On reconnect, send `{ type: "sync", since: lastEventSeq }`. The server replays events or sends a fresh snapshot, and the client must handle both.
- Send `{ type: "ping" }` every 25s. Use exponential backoff capped at 10s.
- Upsert messages by `message_id`. A `message_status` event updates an existing message and never adds one. Chat messages are already paced by the server, so add no client-side delays.
- Use REST for commands and the first load only. Do not poll what the socket already pushes.

**Message types (do not invent more):** `supply_report, request, bid, offer, counteroffer, concession, accept, reject, peer_request, emergency_warning, negotiation_round, proposal, validation, agreement, system, event, claim, trust_alert, explanation, commander_action`.
**Message status:** `pending | delivered | verified | accepted | rejected | quarantined | committed | superseded`.
**Agent ids:** `hospital_agent, water_agent, telecom_agent, emergency_agent, battery_agent, grid_agent`.
**Fairness:** 0 priority, 0.5 balanced, 1 equity. The slider triggers renegotiation unless the simulation is idle.
**Ignore** the rainbow `AGENT_META` colors from the backend. Use icons and labels only.

## Highlight rules (exact)

**Never animate on snapshot, sync replay or history merge.** Only a live `message` frame can trigger a highlight.

| Group | `message_type` |
|---|---|
| Request (highlights the agent) | `request`, `bid`, `peer_request`, `emergency_warning` |
| Offers | `offer`, `counteroffer`, `concession`, `accept`, `reject` |
| Agreements | `proposal`, `validation`, `agreement` |
| System | `system`, `event`, `negotiation_round`, `supply_report`, `trust_alert`, `commander_action`, `explanation`, `claim` |

The chat filter tabs map to these groups. Put this in `lib/messageKinds.ts`.

**Agent grid.** The store keeps `activity: agentId -> { at, quantity, unit }`.
- A live Request-group message from a consumer agent sets `activity[sender]`. The card shows a red border, a faint tint and "Requesting N MW" for about 3s. Use a per-agent timestamp, not a shared timer, so overlapping requests stack correctly.
- Skip the highlight if `status === "quarantined"`.
- `supply_report` from `grid_agent` gets only a quiet white 1px flash. No red.

**Agent network.** The store keeps `edgeActivity: edgeId -> lastActiveAt`.
- A live message with a specific agent as `receiver` lights the sender-to-receiver edge. If that pair has no edge yet, create a thin dynamic edge.
- A message whose `receiver` is `negotiation_group` lights the sender-to-hub edge.
- A lit edge turns red with one travelling dot (~800ms), then fades back to grey after ~2s.
- Network nodes read the same `activity` map as the agent grid, so the two always match.

## Architecture

```
src/
  components/  TopBar Sidebar MetricTile AgentCard AgentDrawer MessageBubble
               FairnessSlider AllocationChart ConnectionBadge ProposalList
               AgreementList IncidentDetail OverrideDialog AuditTable
               AgentNetwork TwinGraph CascadeList Toast
  sections/    OverviewSection NegotiationSection TwinSection AgentNetworkSection
               TrustSection AllocationSection LabSection AuditSection
  hooks/       useSimulationSocket useAgentActivity useScrollSpy
  services/    api.ts socket.ts
  store/       useSimStore.ts
  types/       api.ts          (from backend schemas only)
  lib/         format.ts constants.ts agents.ts messageKinds.ts errors.ts
```

Vite proxies `/api` and `/ws` to `:8000` (`ws: true`). One typed API client wraps every endpoint. One socket service handles reconnect, sync and de-duplication. One Zustand store feeds every section. Every commander action is a real call, with pending, success and failure feedback shown inline or as a quiet toast.

## Accessibility and responsive

- Visible keyboard focus (2px red outline), semantic buttons and labelled inputs.
- Never use color as the only signal; pair it with text or an icon. Keep AA contrast.
- Works from 1280px down to tablet. On narrow screens the agent grid and chat stack, and tables scroll horizontally.

## Build order (checkpoints)

1. Shell: top bar, sidebar, scroll-spy, theme tokens
2. Types, API client, socket service, store. **STOP.** Show me the store shape and how snapshot, sync and replay are handled, and wait for my OK.
3. Overview + commander controls + fairness slider
4. Agent grid + live negotiation (with the highlight logic)
5. Agent network (with edge highlighting)
6. Resource allocation charts + override dialog
7. Trust engine
8. City digital twin + cascades
9. Simulation lab + evaluation table
10. Audit logs, loading/error/empty states, accessibility pass

## Acceptance checklist

- [ ] Every button calls a real endpoint and shows its result.
- [ ] No hardcoded or fake messages, metrics or benchmark numbers.
- [ ] A live request highlights the right agent card, and it clears after ~3s.
- [ ] A direct message highlights the right network edge, and it fades.
- [ ] Reconnect restores history with no duplicates and no replayed animations.
- [ ] The fairness slider visibly changes the allocation returned by the backend.
- [ ] The fake crisis shows claim, evidence, decision, quarantine and "Allocation changed".
- [ ] Only red, white, grey and near-black appear. No gradients or glows.
- [ ] `npm run build` and `npm run lint` pass with zero errors.
- [ ] Browser-agent screenshots are attached for each section.

