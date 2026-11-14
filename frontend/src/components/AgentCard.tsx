import {
  HeartPulse,
  Droplets,
  RadioTower,
  Siren,
  BatteryCharging,
  Zap,
} from "lucide-react";
import { formatMw, formatPct } from "@/lib/format";
import { AGENTS } from "@/lib/agents";
import type { AgentId, AgentView } from "@/types/api";

interface Props {
  agent: AgentView;
  isRequesting?: boolean;
  requestQuantity?: number | null;
  requestUnit?: string | null;
  isSupplyFlash?: boolean;
  onClick: (agentId: AgentId) => void;
}

export function AgentCard({
  agent,
  isRequesting = false,
  requestQuantity,
  requestUnit = "MW",
  isSupplyFlash = false,
  onClick,
}: Props) {
  const meta = AGENTS[agent.agent_id];
  const isConsumer = agent.kind === "consumer";
  const isBattery = agent.agent_id === "battery_agent";
  const isGrid = agent.agent_id === "grid_agent";

  const isIsolated = agent.status === "isolated";
  const isDisconnected = agent.status === "disconnected";
  const isDimmed = isIsolated || isDisconnected;

  // Render correct Lucide icon
  const renderIcon = () => {
    const props = { size: 16, strokeWidth: 1.5, className: "shrink-0" };
    switch (agent.agent_id) {
      case "hospital_agent":
        return <HeartPulse {...props} />;
      case "water_agent":
        return <Droplets {...props} />;
      case "telecom_agent":
        return <RadioTower {...props} />;
      case "emergency_agent":
        return <Siren {...props} />;
      case "battery_agent":
        return <BatteryCharging {...props} />;
      case "grid_agent":
        return <Zap {...props} />;
      default:
        return <Zap {...props} />;
    }
  };

  // Status styling
  const statusColor =
    agent.status === "online"
      ? "bg-ok"
      : agent.status === "isolated"
      ? "bg-accent"
      : "bg-muted";

  // Allocation bar calculation for consumers
  let allocPct = 0;
  if (isConsumer && agent.demand_mw > 0) {
    allocPct = Math.min(100, Math.max(0, (agent.allocation_mw / agent.demand_mw) * 100));
  }

  // Border & background highlight classes
  let containerHighlightClass = "border-border bg-surface";
  if (isRequesting) {
    containerHighlightClass = "border-accent bg-accent-dim shadow-none transition-all duration-200";
  } else if (isSupplyFlash) {
    containerHighlightClass = "border-white/80 bg-surface transition-all duration-200";
  }

  return (
    <div
      onClick={() => onClick(agent.agent_id)}
      role="button"
      tabIndex={0}
      onKeyDown={(e) => {
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault();
          onClick(agent.agent_id);
        }
      }}
      className={`p-3.5 rounded-panel border text-left cursor-pointer select-none transition-all duration-200 hover:border-muted/50 ${containerHighlightClass} ${
        isDimmed ? "opacity-50" : ""
      }`}
    >
      {/* Header */}
      <div className="flex items-center justify-between gap-2">
        <div className="flex items-center gap-2 min-w-0">
          <div className="text-muted">{renderIcon()}</div>
          <span className="text-13 font-medium text-text truncate">
            {meta?.name ?? agent.display_name}
          </span>
        </div>

        <div className="flex items-center gap-1.5 shrink-0 text-11 text-muted">
          <span className={`w-1.5 h-1.5 rounded-full ${statusColor}`} />
          <span className="capitalize">{agent.status}</span>
        </div>
      </div>

      {/* Role / Subtitle */}
      <div className="mt-1 text-11 text-muted truncate">{meta?.role ?? agent.role}</div>

      {/* Highlighting badge when requesting */}
      {isRequesting && (
        <div className="mt-2 py-0.5 px-1.5 bg-accent/20 border border-accent/40 rounded-control text-11 text-accent font-medium inline-block">
          Requesting {requestQuantity !== null ? `${requestQuantity} ${requestUnit}` : ""}
        </div>
      )}

      {/* Metrics Row */}
      <div className="mt-3 pt-2.5 border-t border-border/60">
        {isConsumer ? (
          <div className="space-y-2">
            <div className="grid grid-cols-3 gap-1 text-12 tabular-nums">
              <div>
                <span className="text-11 text-muted block">Demand</span>
                <span className="text-text font-medium">{formatMw(agent.demand_mw)}</span>
              </div>
              <div>
                <span className="text-11 text-muted block">Min Safe</span>
                <span className="text-text font-medium">{formatMw(agent.min_safe_mw)}</span>
              </div>
              <div>
                <span className="text-11 text-muted block">Allocated</span>
                <span className={`font-semibold ${
                  agent.allocation_mw < agent.min_safe_mw ? "text-accent" : "text-text"
                }`}>
                  {formatMw(agent.allocation_mw)}
                </span>
              </div>
            </div>

            {/* Thin allocation bar (300ms transition) */}
            <div className="w-full h-1 bg-surface-2 rounded-control overflow-hidden">
              <div
                className={`h-full transition-all duration-300 ease-out ${
                  agent.allocation_mw < agent.min_safe_mw ? "bg-accent" : "bg-text/80"
                }`}
                style={{ width: `${allocPct}%` }}
              />
            </div>
          </div>
        ) : isBattery ? (
          <div className="grid grid-cols-3 gap-1 text-12 tabular-nums">
            <div>
              <span className="text-11 text-muted block">SOC</span>
              <span className="text-text font-medium">{formatPct(agent.soc)}</span>
            </div>
            <div>
              <span className="text-11 text-muted block">Discharge</span>
              <span className="text-text font-medium">{formatMw(agent.discharge_mw)}</span>
            </div>
            <div>
              <span className="text-11 text-muted block">Max Cap</span>
              <span className="text-text font-medium">{formatMw(agent.max_discharge_mw)}</span>
            </div>
          </div>
        ) : isGrid ? (
          <div className="grid grid-cols-3 gap-1 text-12 tabular-nums">
            <div>
              <span className="text-11 text-muted block">Available</span>
              <span className="text-text font-medium">{formatMw(agent.nominal_mw)}</span>
            </div>
            <div>
              <span className="text-11 text-muted block">Verified</span>
              <span className="text-text font-medium">
                {agent.verified_supply_mw !== null ? formatMw(agent.verified_supply_mw) : "—"}
              </span>
            </div>
            <div>
              <span className="text-11 text-muted block">Sensors</span>
              <span className="text-text font-medium uppercase text-11">
                {agent.sensor_status}
              </span>
            </div>
          </div>
        ) : null}
      </div>
    </div>
  );
}

