import {
  ResponsiveContainer,
  BarChart,
  Bar,
  LineChart,
  Line,
  XAxis,
  YAxis,
  Tooltip,
  Legend,
} from "recharts";
import { ShieldAlert, AlertTriangle } from "lucide-react";
import { AGENTS, CONSUMER_IDS } from "@/lib/agents";
import { formatMw } from "@/lib/format";
import { useSimStore } from "@/store/useSimStore";
import type { ConsumerId } from "@/types/api";

interface Props {
  onOpenOverride: () => void;
}

export function AllocationChart({ onOpenOverride }: Props) {
  const snapshot = useSimStore((s) => s.snapshot);
  const liveSeries = useSimStore((s) => s.liveSupplyDemandSeries);

  const activeAgreement = snapshot?.allocation ?? null;
  const isDegradation = activeAgreement?.degradation_mode ?? false;
  const version = activeAgreement?.version ?? null;

  // Prepare data for per-agent bar chart
  const barData = CONSUMER_IDS.map((agentId) => {
    const agentDef = AGENTS[agentId];
    const agentView = snapshot?.agents?.find((a) => a.agent_id === agentId);
    const demand = agentView && "demand_mw" in agentView ? (agentView.demand_mw ?? 0) : 0;
    const minSafe = agentView && "min_safe_mw" in agentView ? (agentView.min_safe_mw ?? 0) : 0;
    const allocated = activeAgreement?.allocation?.[agentId] ?? 0;
    const unmet = Math.max(0, demand - allocated);

    return {
      agentId,
      name: agentDef?.name.replace(" Agent", "") ?? agentId,
      minSafe,
      allocated,
      unmet,
      demand,
    };
  });

  // Extract unavoidable shortages from validation result if present
  const validation = activeAgreement?.validation as
    | { unavoidable_shortages?: Record<string, number> }
    | null
    | undefined;
  const shortages = validation?.unavoidable_shortages ?? {};
  const shortageEntries = Object.entries(shortages);

  return (
    <div className="space-y-4">
      {/* Allocation Status Header Panel */}
      <div className="p-4 bg-surface rounded-panel border border-border flex flex-wrap items-center justify-between gap-4">
        <div className="flex flex-wrap items-center gap-4">
          <div>
            <span className="text-11 uppercase font-semibold tracking-wider text-muted block">
              Active Agreement
            </span>
            <div className="flex items-center gap-2 mt-0.5">
              <span className="text-20 font-semibold text-text tabular-nums">
                {version !== null ? `v${version}` : "—"}
              </span>
              {version !== null && (
                <span
                  className={`text-11 px-2 py-0.5 rounded border font-medium ${
                    isDegradation
                      ? "border-accent/40 bg-accent-dim text-accent"
                      : "border-ok/30 bg-ok/10 text-ok"
                  }`}
                >
                  {isDegradation ? "DEGRADATION MODE" : "NORMAL MODE"}
                </span>
              )}
            </div>
          </div>

          <div className="h-8 w-[1px] bg-border hidden sm:block" />

          <div>
            <span className="text-11 uppercase font-semibold tracking-wider text-muted block">
              Committed By
            </span>
            <span className="text-13 text-text font-medium mt-0.5 block">
              {activeAgreement?.committed_by ?? "None"}
            </span>
          </div>

          <div className="h-8 w-[1px] bg-border hidden sm:block" />

          <div>
            <span className="text-11 uppercase font-semibold tracking-wider text-muted block">
              Battery Discharge
            </span>
            <span className="text-13 text-text tabular-nums font-medium mt-0.5 block">
              {activeAgreement?.battery_discharge != null
                ? formatMw(activeAgreement.battery_discharge)
                : "—"}
            </span>
          </div>

          <div className="h-8 w-[1px] bg-border hidden sm:block" />

          <div>
            <span className="text-11 uppercase font-semibold tracking-wider text-muted block">
              Verified Supply
            </span>
            <span className="text-13 text-text tabular-nums font-medium mt-0.5 block">
              {activeAgreement?.supply_total != null
                ? formatMw(activeAgreement.supply_total)
                : "—"}
            </span>
          </div>
        </div>

        <button
          onClick={onOpenOverride}
          className="inline-flex items-center gap-2 px-3 py-1.5 rounded bg-surface-2 hover:bg-surface-2/80 text-accent border border-accent/40 hover:border-accent text-12 font-medium transition-colors cursor-pointer"
        >
          <ShieldAlert className="w-4 h-4" />
          <span>Override Allocation</span>
        </button>
      </div>

      {/* Reported Shortages Alert if Degradation */}
      {isDegradation && shortageEntries.length > 0 && (
        <div className="p-3 bg-surface-2 rounded-panel border border-accent/30 text-12">
          <div className="flex items-center gap-2 text-accent font-medium mb-1.5">
            <AlertTriangle className="w-4 h-4" />
            <span>Unavoidable Consumer Shortages Reported</span>
          </div>
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 pt-1">
            {shortageEntries.map(([agent, mw]) => (
              <div
                key={agent}
                className="p-2 rounded bg-surface border border-border flex items-center justify-between"
              >
                <span className="text-muted text-11">
                  {AGENTS[agent as ConsumerId]?.name ?? agent}
                </span>
                <span className="text-accent font-medium tabular-nums">
                  {formatMw(mw)}
                </span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Dual Charts Grid */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        {/* 1. Bar Chart: Minimum, Allocated, Unmet per agent */}
        <div className="p-4 bg-surface rounded-panel border border-border flex flex-col justify-between">
          <div>
            <div className="flex items-center justify-between mb-1">
              <h3 className="text-13 font-medium text-text">Consumer Allocation Status</h3>
              <span className="text-11 text-muted">MW per utility</span>
            </div>
            <p className="text-11 text-muted mb-4">
              Safe minimum (grey), verified allocated (white), unmet demand (red).
            </p>
          </div>

          <div className="h-64 w-full">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart
                data={barData}
                margin={{ top: 8, right: 12, left: -16, bottom: 4 }}
              >
                <XAxis
                  dataKey="name"
                  stroke="#8B8B94"
                  fontSize={11}
                  tickLine={false}
                  axisLine={{ stroke: "#26262B" }}
                />
                <YAxis
                  stroke="#8B8B94"
                  fontSize={11}
                  tickLine={false}
                  axisLine={{ stroke: "#26262B" }}
                  className="tabular-nums"
                />
                <Tooltip
                  content={({ active, payload }) => {
                    if (!active || !payload?.length) return null;
                    const data = payload[0].payload as (typeof barData)[0];
                    return (
                      <div className="p-2.5 rounded bg-surface-2 border border-border shadow-none text-12 tabular-nums">
                        <div className="font-medium text-text mb-1">{data.name}</div>
                        <div className="text-muted flex justify-between gap-4">
                          <span>Safe Minimum:</span>
                          <span className="text-text">{formatMw(data.minSafe)}</span>
                        </div>
                        <div className="text-muted flex justify-between gap-4">
                          <span>Allocated:</span>
                          <span className="text-text">{formatMw(data.allocated)}</span>
                        </div>
                        <div className="text-muted flex justify-between gap-4">
                          <span>Unmet Demand:</span>
                          <span className={data.unmet > 0 ? "text-accent" : "text-text"}>
                            {formatMw(data.unmet)}
                          </span>
                        </div>
                      </div>
                    );
                  }}
                />
                <Legend
                  wrapperStyle={{ fontSize: 11, paddingTop: 8 }}
                  formatter={(value) => (
                    <span className="text-muted text-11 mr-2">{value}</span>
                  )}
                />
                <Bar
                  name="Safe Minimum"
                  dataKey="minSafe"
                  fill="#8B8B94"
                  radius={[2, 2, 0, 0]}
                  maxBarSize={28}
                />
                <Bar
                  name="Allocated"
                  dataKey="allocated"
                  fill="#F4F4F5"
                  radius={[2, 2, 0, 0]}
                  maxBarSize={28}
                />
                <Bar
                  name="Unmet Demand"
                  dataKey="unmet"
                  fill="#E5484D"
                  radius={[2, 2, 0, 0]}
                  maxBarSize={28}
                />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>

        {/* 2. Line Chart: Live Supply vs Demand */}
        <div className="p-4 bg-surface rounded-panel border border-border flex flex-col justify-between">
          <div>
            <div className="flex items-center justify-between mb-1">
              <h3 className="text-13 font-medium text-text">Supply vs Demand Dynamics</h3>
              <span className="text-11 text-muted tabular-nums">
                {liveSeries.length} points recorded
              </span>
            </div>
            <p className="text-11 text-muted mb-4">
              Built from state events received since page load.
            </p>
          </div>

          {liveSeries.length === 0 ? (
            <div className="h-64 flex items-center justify-center border border-dashed border-border rounded">
              <span className="text-12 text-muted">
                Waiting for state events since page load…
              </span>
            </div>
          ) : (
            <div className="h-64 w-full">
              <ResponsiveContainer width="100%" height="100%">
                <LineChart
                  data={liveSeries}
                  margin={{ top: 8, right: 12, left: -16, bottom: 4 }}
                >
                  <XAxis
                    dataKey="tick"
                    stroke="#8B8B94"
                    fontSize={11}
                    tickLine={false}
                    axisLine={{ stroke: "#26262B" }}
                    className="tabular-nums"
                  />
                  <YAxis
                    stroke="#8B8B94"
                    fontSize={11}
                    tickLine={false}
                    axisLine={{ stroke: "#26262B" }}
                    className="tabular-nums"
                  />
                  <Tooltip
                    content={({ active, payload, label }) => {
                      if (!active || !payload?.length) return null;
                      return (
                        <div className="p-2.5 rounded bg-surface-2 border border-border shadow-none text-12 tabular-nums">
                          <div className="font-medium text-text mb-1">Tick {label}</div>
                          {payload.map((item) => (
                            <div
                              key={item.dataKey as string}
                              className="text-muted flex justify-between gap-4"
                            >
                              <span>{item.name}:</span>
                              <span className="text-text font-medium">
                                {formatMw(Number(item.value))}
                              </span>
                            </div>
                          ))}
                        </div>
                      );
                    }}
                  />
                  <Legend
                    wrapperStyle={{ fontSize: 11, paddingTop: 8 }}
                    formatter={(value) => (
                      <span className="text-muted text-11 mr-2">{value}</span>
                    )}
                  />
                  <Line
                    type="monotone"
                    name="Available Supply"
                    dataKey="supply"
                    stroke="#F4F4F5"
                    strokeWidth={1.5}
                    dot={false}
                    isAnimationActive={false}
                  />
                  <Line
                    type="monotone"
                    name="Total Demand"
                    dataKey="demand"
                    stroke="#8B8B94"
                    strokeWidth={1.5}
                    dot={false}
                    isAnimationActive={false}
                  />
                  <Line
                    type="monotone"
                    name="Total Allocated"
                    dataKey="allocated"
                    stroke="#E5484D"
                    strokeWidth={1.5}
                    dot={false}
                    isAnimationActive={false}
                  />
                </LineChart>
              </ResponsiveContainer>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
