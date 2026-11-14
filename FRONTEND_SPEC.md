MASTER PROMPT: CRISIS AGENTS Frontend
Role

You are a senior frontend engineer and UI/UX designer working in React and Tailwind. The backend (FastAPI + WebSocket) is already built and working. Your job is to build the single-page commander dashboard for CRISIS AGENTS, a multi-agent system where utility agents (Hospital, Water, Telecom, Emergency, Battery, Grid) negotiate scarce electricity during disasters.

The result must look like a product a small team of careful human developers built over several weeks. It must not look generated.

Step 0: Read the backend first

Before writing any UI:

Open backend/ and read the Pydantic schemas, the REST routes, and the WebSocket handler at /ws/simulation.
List the real message types, event types, and state shapes you found.
Build the TypeScript types from those schemas. Do not invent fields.
If something I describe below doesn’t exist in the backend, tell me, and show an honest empty state in the UI. Never fake data.
Stack

React, Vite, TypeScript (strict), Tailwind CSS, Framer Motion, Recharts, Lucide React, React Flow.

Design direction

Mood: a quiet, serious operations console. Minimal, flat, and dense with information but not crowded.

Palette (define as Tailwind theme tokens, don’t hardcode hex in components):

Token	Value	Use
bg	
#0B0B0C	page background
surface	
#111113	panels
surface-2	
#17171A	raised elements, inputs
border	
#26262B	all dividers (1px)
text	
#F4F4F5	primary text
muted	
#8B8B94	secondary text
accent	
#E5484D	red: active, urgent, selected, primary action
accent-dim	
#E5484D at 15%	red tint backgrounds
ok	
#4ADE80, used sparingly	verified or healthy only

Rules for color:

Red is the only accent. Use it for the one thing that matters in each area (active agent, current round, primary button, critical alert). If everything is red, nothing is.
No gradients, no glassmorphism, no glow or neon shadows, no purple or blue.
Status is communicated by text plus a small dot, not by large colored blocks.

Typography: font-family: sans-serif (system sans stack, e.g. ui-sans-serif, system-ui, sans-serif). No custom display fonts. Use tabular-nums for every number so values don’t jitter when they update. Sizes: 12 / 13 / 14 / 16 / 20 / 28 only. Weights: 400, 500, 600 only. Small uppercase labels at 11px with letter-spacing are allowed for section headings.

Shape and spacing: 4px grid. Border radius 6px on panels and 4px on small controls. 1px borders instead of shadows. Consistent 16px or 24px panel padding. No emoji anywhere. Icons are Lucide at 16px, stroke 1.5.

What makes it feel human-built (follow strictly)
No decorative elements: no hero banners, no floating blobs, no fake 3D, no sparkle icons, no “AI-powered” badges.
Copy is plain and specific. Write “Grid supply dropped to 80 MW”, not “Unleashing resilience”. No exclamation marks.
Use real, slightly uneven information density, like real dashboards. Not every card has to be the same size.
Every panel has real loading, empty, and error states. Empty states are one line of muted text.
Number formatting is consistent: 120 MW, 3 / 6 agents, 14:32:07.
Components are small and named by job (AgentCard, MessageBubble, AllocationChart), not GlassCard or FancyButton.
Keep code idiomatic: custom hooks, no giant files, no commented-out blocks, no placeholder lorem ipsum.
Motion (minimal, functional only)

Use Framer Motion sparingly. Every animation must communicate a state change.

Durations 150–250ms, ease-out. No bounce, no spring overshoot, no looping decorations.
New chat message: fade in + 4px upward slide.
Agent card on request: border animates to red and a faint red tint holds for ~3s, then fades back.
Network edge on communication: stroke turns red and a small dot travels along the edge once (~800ms), then the edge fades back to grey.
Number changes: a short cross-fade, no counting-up effects.
Allocation bars: width transitions at 300ms.
Respect prefers-reduced-motion: disable the travelling dot and slides, and keep color changes only.
Layout: single page

One page, no router. A fixed top bar, a slim left sidebar whose items smooth-scroll to sections on the same page (with scroll-spy highlighting the active one), and a scrolling main column.

Top bar: “CRISIS AGENTS” wordmark (plain text, semibold), simulation status (Running / Paused / Idle with a dot), current scenario, simulation time, WebSocket connection state (Connected / Reconnecting), commander name.

Sidebar anchors: Overview, Live Negotiation, City Digital Twin, Agent Network, Crisis Trust Engine, Resource Allocation, Simulation Lab, Audit Logs. On mobile it collapses to a top drawer.

Sections (in order)

1. Overview
A row of metric tiles from live state: total supply, total demand, deficit (red when above 0), active agents (x / 6), active alerts, current negotiation round, infrastructure health %. Beside them, the Commander Controls: Start, Pause, Resume, Reset, Advance Time, and the Fairness slider.

The slider runs from Priority to Equity with three labelled stops (Priority / Balanced / Equity). It shows the current value and one line of text explaining the current policy. It sends the value to the backend on release (debounced) and re-renders from the returned allocation. Add a small note: “Safety minimums are not affected by this setting.”

2. Agent Grid + Live Negotiation (side by side on desktop)

Agent Grid (left, 6 cards in a 2×3 or 3×2 grid). Each card shows agent name, a Lucide icon, status (online / isolated / disconnected), demand, minimum, allocated, and a thin allocation bar.

Highlight rule: whenever a message arrives where sender is an agent and message_type is a request, bid, or emergency warning, that agent’s card enters the “requesting” state (red border + faint red tint + small “Requesting 100 MW” line) for about 3 seconds. Overlapping requests must stack correctly using a timestamp per agent, not a shared timer.
Isolated or disconnected agents are shown dimmed with a label.
Clicking a card opens a right-side drawer with that agent’s state, recent messages, and an “Isolate agent” action.

Live Negotiation (right). Group chat titled CITY EMERGENCY: LIVE NEGOTIATION.

Each agent has a distinct identity: small icon plus name. Differentiate by label and icon, not by rainbow colors. System / Protocol / Agreement messages use a centered, muted, full-width style.
Each message shows: sender, text (built from the structured fields, with reason shown), quantity + unit as a monospace-style chip, message_type tag, round number, timestamp, and status (pending / accepted / rejected / quarantined).
Mentions of other agents render as plain highlighted text.
Auto-scroll to the newest message, but stop auto-scrolling if the user has scrolled up and show a “New messages” button.
A filter row: All / Requests / Offers / Agreements / System.
Below the chat: Pending proposals list with Reject and Request explanation actions, and Verified agreements with version numbers.
On WebSocket reconnect, fetch /api/negotiation/history and merge by message_id (idempotent, no duplicates).

3. Agent Network
A React Flow graph. Six agent nodes plus one small “Negotiation channel” hub node. Edges represent real relationships (supply, dependency, negotiation).

Highlight rule: when a message is direct (receiver is a specific agent), the edge between sender and receiver turns red with a one-time travelling dot. When receiver is the group, the sender’s edge to the hub lights up. Edges fade back to grey after about 2 seconds. Keep an in-memory map of edgeId → lastActiveAt so many simultaneous messages are handled correctly.
Nodes mirror the same “requesting” state as the Agent Grid, from the same shared store.
Disabled, isolated, or disconnected agents are shown dimmed with dashed edges.
Locked layout (no dragging), subtle zoom controls only, minimap off.

4. City Digital Twin
A clean 2D schematic, not an illustration: grid, battery, hospital, water plant, telecom tower, and emergency station as simple nodes (React Flow or SVG) with lines showing energy flow. Line thickness represents allocated MW. Node outline color reflects health (normal, degraded, failed in red), read from simulation state.

Next to it, the dependency graph, which shows cascading failures. When an asset fails, downstream dependents show a degraded state in sequence (staggered ~150ms) and a short text list reads “Water pumping failure → reduced hospital water → reduced firefighting capacity” from backend data.

5. Crisis Trust Engine

Prominent but understated Inject Fake Crisis button (outlined red).
Incident list from /api/trust/incidents. Selecting one shows a detail panel with: the incoming claim, the verification evidence (claimed value vs. trusted telemetry vs. corroborating reports), the trust decision, quarantine status, agent responses, and a clear line saying “Allocation changed: Yes / No”.
Ambiguous high-impact incidents show an “Escalated to commander” state with Approve / Reject buttons.
Quarantined messages also appear in the chat, visually muted with a “Quarantined” tag.

6. Resource Allocation

A Recharts stacked/grouped bar chart: per agent, minimum vs. allocated vs. demand. Use white, grey, and red only. Red marks unmet critical demand.
A line chart of supply vs. total demand over simulation time.
Allocation version number, mode (Normal / Emergency degradation), and a list of reported unavoidable shortages.
Commander override is a deliberately heavy action: open a dialog, require typing a reason, show the validation result from /api/allocations/validate before enabling “Commit override”.

7. Simulation Lab

Event injection panel: Power shortage (with a magnitude input), Hospital demand spike, Flood, Water pumping failure, Telecom outage, Disconnect agent (select), Restore supply. Each is a plain button/form that calls /api/events/inject, with inline success or error feedback.
Baseline comparison table: the four modes (FCFS, Fixed priority, Centralized optimization, Multi-agent negotiation) × metrics (weighted damage, critical uptime, unmet demand, fairness penalty, constraint violations, negotiation latency, recovery time). Show only values returned by the backend. Where no run exists, show — and a line saying “No run recorded”. Never invent numbers.

8. Audit Logs
A dense table: time, actor (agent / system / commander), action, target, outcome. Filters by actor and outcome, plus text search. Commander actions are marked. Paginated or virtualized if long.

State and architecture
src/
  components/   (AgentCard, MessageBubble, MetricTile, ...)
  sections/     (one file per dashboard section)
  hooks/        (useSimulationSocket, useAgentActivity, useScrollSpy)
  services/     (api.ts, socket.ts)
  store/        (single store, e.g. Zustand)
  types/        (generated from backend schemas)
  lib/          (format.ts, constants.ts)
One typed API client (services/api.ts) wrapping every REST endpoint with consistent error handling.
One WebSocket service with automatic reconnect (exponential backoff, capped), connection state exposed to the top bar, and message de-duplication by message_id.
One shared store holding: simulation state, agents, messages, proposals, agreements, incidents, audit logs, and a transient activity map (agentId → lastRequestAt, edgeId → lastActiveAt). The Agent Grid and Agent Network both read from it so highlights always match.
No polling where the WebSocket already pushes data. Use REST for commands and for the initial load.
Every commander action is a real API call and shows pending, success, and failure feedback (inline text or a quiet toast, not a modal for everything).
Accessibility and responsiveness
Visible keyboard focus (2px red outline), semantic buttons, labelled inputs, aria-live="polite" on the chat.
Never use color as the only signal. Pair it with text or an icon.
Contrast at least AA on the dark background.
Works from 1280px wide down to tablet. On narrow screens the Agent Grid and Live Negotiation stack, and tables scroll horizontally.
Process
Read the backend and report what you found: endpoints, message types, state shape, and any gaps.
Propose the file structure and the Tailwind theme tokens. Wait for my OK.
Build in this order, running npm run build and npm run lint after each step:
Shell: top bar, sidebar, scroll-spy, theme
API client, socket service, store, types
Overview + commander controls + fairness slider
Agent Grid + Live Negotiation (with the highlight logic)
Agent Network (with edge highlighting)
Resource Allocation charts
Trust Engine
City Digital Twin + dependency graph
Simulation Lab + baseline table
Audit Logs, loading/error/empty states, accessibility pass
After each step, tell me what works and what doesn’t. Do not move on while the build is failing.
Acceptance checklist
[ ] Every button calls a real endpoint and shows its result.
[ ] No hardcoded or fake messages, metrics, or benchmark numbers anywhere.
[ ] A request message highlights the correct agent card.
[ ] A message between agents highlights the correct network edge, and the highlight fades.
[ ] Reconnecting the socket restores history with no duplicates.
[ ] The fairness slider visibly changes allocations returned by the backend.
[ ] Fake crisis shows the claim, evidence, decision, quarantine, and “allocation changed” status.
[ ] Only red, white, grey, and near-black are used. No gradients or glows.
[ ] The page is calm at rest. Nothing animates unless something happened.
[ ] npm run build and npm run lint pass with zero errors