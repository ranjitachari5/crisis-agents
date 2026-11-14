# Simulation

Discrete time, 15 simulated minutes per tick (`SIM_MINUTES_PER_TICK`), one tick every `TICK_INTERVAL_S`
real seconds while running. All randomness comes from a seeded NumPy generator, so a seed + scenario fully
determines a run.

## Initial state (illustrative values)

| Utility | Demand | Safe min | Max | Damage w | Critical w (own) | Concession rate |
|---|---|---|---|---|---|---|
| Hospital | 100 | 85 | 130 | 10 | 100 | 0.34 |
| Water | 70 | 55 | 90 | 6 | 60 | 0.30 |
| Telecom | 50 | 30 | 60 | 7 | 70 | 0.50 |
| Emergency | 60 | 35 | 80 | 8 | 80 | 0.30 (0.15 during rescue) |

Grid: 200 MW available of 320 MW nominal. Battery: 120 MWh, 80% SoC, 20% protected reserve, 30 MW max
discharge, 20 MW max charge. Dependencies: hospital ← water (0.35), telecom (0.15); emergency ← water (0.30),
telecom (0.35).

## Tick order
1. Physics for the elapsed interval using the committed allocation: battery discharge/charge from the gap to the
   *real* grid supply; load shedding if the battery cannot cover it; asset health decays below minimum.
   Measured metrics are recorded here.
2. Advance clock; apply scripted scenario events.
3. Read telemetry (3 noisy grid sensors, meters, battery, flood gauges, seismic sensors); check sensor consensus.
4. Agents observe; reassess if a trigger fired → negotiation → validation → commit.
5. Recompute service levels and cascades; broadcast state.

## Events
`power_reduction`, `flood_warning` (rescue active, demand ↑, substation loss), `hospital_demand_spike`
(demand ↑ and ICU minimum ↑), `water_pump_failure`, `telecom_outage`, `battery_depletion`,
`agent_disconnect` / `agent_reconnect`, `recovery` (`grid` or `full`).

## Scenarios
* `grid_shortage` — the illustrative 200 MW state; the battery bridges the deficit for ~2.4 h, then the city
  enters degradation mode until the commander restores supply.
* `flood_cascade` — scripted: surge (t3), flood (t6), pump failure (t9), telecom outage (t12), partial
  recovery (t18), full recovery (t24).
* `normal` — 320 MW, no deficit.

## Cascades
`effective_i = power_service_i · health_i · operational_capacity_i · Π(1 − k·(1 − effective_upstream))`.
Derived services: ICU life support, hospital water availability, firefighting capacity, emergency dispatch.

## Evaluation
`POST /api/evaluation/run` runs FCFS, fixed priority, centralized optimisation and negotiation in fresh headless
engines with identical scenario, seed and ticks. Example measured run (flood_cascade, seed 42, 32 ticks,
f = 0.5) on the development machine:

| Mode | Weighted damage | Critical uptime | Constraint violations | Mean recovery |
|---|---|---|---|---|
| FCFS | 25 859 | 77.3% | 9 | 157.5 min |
| Fixed priority | 29 211 | 71.9% | 12 | 360 min |
| Centralized | 9 939 | 90.6% | 0 | 180 min |
| Negotiation | 9 997 | 90.6% | 0 | 180 min |

Re-run the endpoint to reproduce. Negotiation latency is wall-clock compute time (~2–3 ms here),
not network time.
