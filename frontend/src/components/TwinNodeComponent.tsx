import { memo } from "react";
import { Handle, Position, type NodeProps } from "reactflow";
import {
  Zap,
  BatteryCharging,
  Cpu,
  HeartPulse,
  Droplets,
  RadioTower,
  Siren,
  Flame,
  PhoneCall,
  Activity,
} from "lucide-react";
import type { TwinNodeStatus } from "@/types/api";

export interface TwinNodeData {
  id: string;
  type: string;
  label: string;
  status?: TwinNodeStatus;
  isHighlighted?: boolean;
  isCascadeRoot?: boolean;
  available_mw?: number;
  nominal_mw?: number;
  soc?: number;
  discharge_mw?: number;
  grid_flow_mw?: number;
  battery_flow_mw?: number;
  allocation_mw?: number;
  demand_mw?: number;
  level?: number;
  health?: number;
}

function getNodeIcon(id: string, type: string) {
  const props = { size: 14, strokeWidth: 1.5, className: "shrink-0" };
  if (id === "grid_agent") return <Zap {...props} />;
  if (id === "battery_agent") return <BatteryCharging {...props} />;
  if (id === "power_bus") return <Cpu {...props} />;
  if (id === "hospital_agent") return <HeartPulse {...props} />;
  if (id === "water_agent") return <Droplets {...props} />;
  if (id === "telecom_agent") return <RadioTower {...props} />;
  if (id === "emergency_agent") return <Siren {...props} />;
  if (id === "svc_icu" || id === "icu") return <HeartPulse {...props} className="text-accent shrink-0" />;
  if (id === "svc_hospital_water" || id === "hospital_water") return <Droplets {...props} className="text-[#38BDF8] shrink-0" />;
  if (id === "svc_firefighting" || id === "firefighting") return <Flame {...props} className="text-[#FB923C] shrink-0" />;
  if (id === "svc_dispatch" || id === "dispatch") return <PhoneCall {...props} className="text-[#A78BFA] shrink-0" />;
  if (type === "service") return <Activity {...props} />;
  return <Zap {...props} />;
}

export const TwinNodeComponent = memo(function TwinNodeComponent({
  data,
}: NodeProps<TwinNodeData>) {
  const {
    id,
    type,
    label,
    status = "ok",
    isHighlighted,
    isCascadeRoot,
    available_mw,
    nominal_mw,
    soc,
    discharge_mw,
    grid_flow_mw,
    battery_flow_mw,
    allocation_mw,
    demand_mw,
    level,
  } = data;

  const isCritical = status === "critical";
  const isDegraded = status === "degraded";

  let statusDotColor = "bg-ok";
  let statusText = "Normal";
  if (isCritical) {
    statusDotColor = "bg-accent";
    statusText = "Critical";
  } else if (isDegraded) {
    statusDotColor = "bg-muted";
    statusText = "Degraded";
  }

  let borderBgClass = "border-border bg-surface";
  if (isHighlighted) {
    borderBgClass = "border-accent bg-accent-dim ring-2 ring-accent transition-all duration-200";
  } else if (isCritical) {
    borderBgClass = "border-accent/60 bg-surface shadow-sm";
  }

  const isService = type === "service";

  return (
    <div
      className={`px-3 py-2 rounded-panel border text-left select-none transition-all duration-150 shadow-sm min-w-[175px] max-w-[205px] ${borderBgClass}`}
    >
      {/* Handles */}
      {type !== "supply" && type !== "storage" && (
        <Handle
          type="target"
          position={Position.Left}
          className="!w-2.5 !h-2.5 !bg-border !border-2 !border-surface !opacity-80 -ml-1"
        />
      )}
      {!isService && (
        <Handle
          type="source"
          position={Position.Right}
          className="!w-2.5 !h-2.5 !bg-border !border-2 !border-surface !opacity-80 -mr-1"
        />
      )}

      {/* Header */}
      <div className="flex items-center justify-between gap-1.5 mb-1">
        <div className="flex items-center gap-1.5 min-w-0">
          <div className={isHighlighted ? "text-accent" : "text-muted"}>
            {getNodeIcon(id, type)}
          </div>
          <span className="text-12 font-medium text-text truncate" title={label}>
            {label}
          </span>
        </div>
        <div className="flex items-center gap-1 shrink-0">
          <span className={`w-1.5 h-1.5 rounded-full ${statusDotColor}`} />
          <span className="text-10 text-muted">{statusText}</span>
        </div>
      </div>

      {/* Metrics Row */}
      <div className="text-11 text-muted tabular-nums pt-1 border-t border-border/80 flex items-center justify-between">
        {type === "supply" && (
          <>
            <span>Available</span>
            <span className="text-text font-medium">
              {available_mw !== undefined ? Math.round(available_mw) : "—"} /{" "}
              {nominal_mw !== undefined ? Math.round(nominal_mw) : "—"} MW
            </span>
          </>
        )}

        {type === "storage" && (
          <>
            <span>SoC: {soc !== undefined ? `${(soc * 100).toFixed(0)}%` : "—"}</span>
            <span className="text-text font-medium">
              {discharge_mw !== undefined ? `${discharge_mw.toFixed(1)} MW` : "0.0 MW"}
            </span>
          </>
        )}

        {type === "bus" && (
          <>
            <span>Throughput</span>
            <span className="text-text font-medium">
              {grid_flow_mw !== undefined && battery_flow_mw !== undefined
                ? `${(grid_flow_mw + battery_flow_mw).toFixed(1)} MW`
                : "—"}
            </span>
          </>
        )}

        {type === "utility" && (
          <>
            <span>Allocated</span>
            <span className="text-text font-medium">
              {allocation_mw !== undefined ? allocation_mw.toFixed(1) : "—"} /{" "}
              {demand_mw !== undefined ? Math.round(demand_mw) : "—"} MW
            </span>
          </>
        )}

        {isService && (
          <>
            <span>Lifeline Integrity</span>
            <span
              className={`font-semibold ${
                level !== undefined && level < 0.6
                  ? "text-accent"
                  : level !== undefined && level < 0.95
                  ? "text-muted"
                  : "text-ok"
              }`}
            >
              {level !== undefined ? `${(level * 100).toFixed(0)}%` : "—"}
            </span>
          </>
        )}
      </div>

      {isCascadeRoot && (
        <div className="mt-1 text-10 uppercase tracking-wider text-accent font-semibold flex items-center gap-1">
          <span className="w-1.5 h-1.5 rounded-full bg-accent animate-ping" />
          <span>Cascade Origin</span>
        </div>
      )}
    </div>
  );
});
