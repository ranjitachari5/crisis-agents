import { useMemo, useState } from "react";
import {
  HeartPulse,
  Droplets,
  RadioTower,
  Siren,
  BatteryCharging,
  Zap,
  Scale,
  Layers,
  ArrowRightLeft,
} from "lucide-react";
import { AGENTS, edgeId } from "@/lib/agents";
import { HUB_NODE_ID } from "@/lib/constants";
import { useAgentActivity } from "@/hooks/useAgentActivity";
import { useSimStore } from "@/store/useSimStore";
import { formatMw } from "@/lib/format";
import type { AgentId, AgentView } from "@/types/api";

interface AgentCoord {
  id: AgentId;
  x: number; // SVG viewBox X (0..1000)
  y: number; // SVG viewBox Y (0..600)
  pctX: number; // CSS % left
  pctY: number; // CSS % top
}

export function AgentNetwork() {
  const snapshot = useSimStore((s) => s.snapshot);
  const setSelectedAgent = useSimStore((s) => s.setSelectedAgent);
  const { getAgentHighlight, getEdgeHighlight } = useAgentActivity();
  const [hoveredNode, setHoveredNode] = useState<string | null>(null);

  // SVG canvas geometry: 1000 x 600
  const cx = 500;
  const cy = 300;

  // 6 Radial Agent Positions: generous margins so all text sits cleanly with zero overlap
  const agentCoords: AgentCoord[] = useMemo(() => [
    // Top: Grid Supply
    { id: "grid_agent", x: 500, y: 85, pctX: 50, pctY: 14 },
    // Top-Right: Battery Storage
    { id: "battery_agent", x: 800, y: 175, pctX: 80, pctY: 29 },
    // Bottom-Right: Hospital Agent (Critical Consumer)
    { id: "hospital_agent", x: 800, y: 425, pctX: 80, pctY: 71 },
    // Bottom: Water Utility
    { id: "water_agent", x: 500, y: 515, pctX: 50, pctY: 86 },
    // Bottom-Left: Telecom Utility
    { id: "telecom_agent", x: 200, y: 425, pctX: 20, pctY: 71 },
    // Top-Left: Emergency Services
    { id: "emergency_agent", x: 200, y: 175, pctX: 20, pctY: 29 },
  ], []);

  // Hub Spoke Edges (Agent <-> Hub)
  const hubEdges = useMemo(() => {
    return agentCoords.map((c, idx) => {
      const eId = edgeId(c.id, HUB_NODE_ID);
      const isHovered = hoveredNode === c.id || hoveredNode === HUB_NODE_ID;
      const { isLit } = getEdgeHighlight(eId);
      const duration = isLit ? 1.0 : 2.5 + (idx % 3) * 0.4;

      return {
        id: eId,
        source: c.id,
        target: HUB_NODE_ID,
        path: `M ${c.x},${c.y} L ${cx},${cy}`,
        reversePath: `M ${cx},${cy} L ${c.x},${c.y}`,
        isLit,
        isHovered,
        duration,
      };
    });
  }, [agentCoords, hoveredNode, getEdgeHighlight]);

  // Peer Dependency Edges between utilities
  const peerEdges = useMemo(() => {
    const list = [
      { from: "water_agent", to: "hospital_agent", path: `M 500,515 Q 670,515 800,425`, d: 3.2 },
      { from: "telecom_agent", to: "hospital_agent", path: `M 200,425 Q 500,465 800,425`, d: 3.8 },
      { from: "water_agent", to: "emergency_agent", path: `M 500,515 Q 310,420 200,175`, d: 3.5 },
      { from: "telecom_agent", to: "emergency_agent", path: `M 200,425 L 200,175`, d: 2.8 },
    ];

    return list.map((item) => {
      const eId = edgeId(item.from, item.to);
      const isHovered = hoveredNode === item.from || hoveredNode === item.to;
      const { isLit } = getEdgeHighlight(eId);

      return {
        id: eId,
        path: item.path,
        isLit,
        isHovered,
        duration: isLit ? 1.2 : item.d,
      };
    });
  }, [hoveredNode, getEdgeHighlight]);

  const renderIcon = (agentId: string) => {
    const props = { size: 15, strokeWidth: 1.8, className: "shrink-0" };
    switch (agentId) {
      case "hospital_agent":
        return <HeartPulse {...props} className="text-[#F43F5E]" />;
      case "water_agent":
        return <Droplets {...props} className="text-[#38BDF8]" />;
      case "telecom_agent":
        return <RadioTower {...props} className="text-[#A78BFA]" />;
      case "emergency_agent":
        return <Siren {...props} className="text-[#FB923C]" />;
      case "battery_agent":
        return <BatteryCharging {...props} className="text-[#34D399]" />;
      case "grid_agent":
        return <Zap {...props} className="text-[#FBBF24]" />;
      default:
        return <Zap {...props} />;
    }
  };

  const getAgentMetric = (agentId: string) => {
    const a = snapshot?.agents?.find((v: AgentView) => v.agent_id === agentId);
    if (!a) return { label: "Telemetry", val: "Connecting…" };
    if (a.kind === "consumer") {
      return {
        label: "Allocated / Demand",
        val: `${formatMw(a.allocation_mw)} / ${formatMw(a.demand_mw)}`,
      };
    }
    if (a.kind === "storage") {
      return {
        label: "State of Charge",
        val: `${(a.soc * 100).toFixed(0)}% · ${a.discharge_mw.toFixed(1)} MW`,
      };
    }
    if (a.kind === "supply") {
      return {
        label: "Verified / Nominal",
        val: `${Math.round(a.verified_supply_mw ?? a.nominal_mw)} / ${Math.round(a.nominal_mw)} MW`,
      };
    }
    return { label: "Status", val: "Active" };
  };

  const activeRound = snapshot?.last_negotiation?.rounds ?? snapshot?.negotiation_count ?? 0;

  return (
    <div className="w-full bg-surface rounded-panel border border-border relative overflow-hidden select-none shadow-sm">
      {/* Top Topology Controls / Legend Header */}
      <div className="px-5 py-3 border-b border-border bg-surface-2/40 flex flex-wrap items-center justify-between gap-4 text-11 text-muted">
        <div className="flex items-center gap-2">
          <Layers className="w-4 h-4 text-accent" />
          <span className="font-semibold uppercase tracking-wider text-text">
            Agent Communication & Negotiation Topology
          </span>
          <span className="text-border">|</span>
          <span>Click any node to view telemetry & controls</span>
        </div>

        {/* Legend */}
        <div className="flex items-center gap-5">
          <div className="flex items-center gap-1.5">
            <span className="w-4 h-0.5 bg-muted/70" />
            <span>Negotiation Protocol</span>
          </div>
          <div className="flex items-center gap-1.5">
            <span className="w-4 border-t border-dashed border-muted/80" />
            <span>Dependency Flow</span>
          </div>
          <div className="flex items-center gap-1.5">
            <span className="w-2.5 h-2.5 rounded-full bg-accent animate-pulse" />
            <span className="text-text font-medium">Live Message Packet</span>
          </div>
        </div>
      </div>

      {/* Main Graph Viewport */}
      <div className="relative w-full h-[540px] bg-bg/40">
        {/* SVG Network Layer: Lines and Moving Communication Particles */}
        <svg
          viewBox="0 0 1000 600"
          className="absolute inset-0 w-full h-full pointer-events-none"
          preserveAspectRatio="none"
        >
          <defs>
            <radialGradient id="hub-ambient-glow" cx="50%" cy="50%" r="50%">
              <stop offset="0%" stopColor="#E5484D" stopOpacity="0.16" />
              <stop offset="60%" stopColor="#E5484D" stopOpacity="0.04" />
              <stop offset="100%" stopColor="#E5484D" stopOpacity="0" />
            </radialGradient>

            <filter id="particle-glow" x="-50%" y="-50%" width="200%" height="200%">
              <feGaussianBlur in="SourceGraphic" stdDeviation="2.5" result="blur" />
              <feMerge>
                <feMergeNode in="blur" />
                <feMergeNode in="SourceGraphic" />
              </feMerge>
            </filter>
          </defs>

          {/* Central Hub Ambient Aura */}
          <circle cx={cx} cy={cy} r={140} fill="url(#hub-ambient-glow)" />

          {/* Concentric Architectural Rings */}
          <circle
            cx={cx}
            cy={cy}
            r={210}
            fill="none"
            stroke="#26262B"
            strokeWidth="1"
            strokeDasharray="4 6"
            opacity="0.5"
          />

          {/* 1. PEER DEPENDENCY EDGES */}
          {peerEdges.map((e) => (
            <g key={e.id}>
              <path
                d={e.path}
                fill="none"
                stroke={e.isLit ? "#E5484D" : e.isHovered ? "#A1A1AA" : "#3F3F46"}
                strokeWidth={e.isLit ? 2.5 : 1.5}
                strokeDasharray="4 4"
                opacity={e.isLit ? 1 : 0.6}
                className="transition-colors duration-200"
              />

              {/* Moving Communication Dot along dependency */}
              <circle r={e.isLit ? 4.5 : 3} fill={e.isLit ? "#E5484D" : "#38BDF8"}>
                <animateMotion
                  dur={`${e.duration}s`}
                  repeatCount="indefinite"
                  path={e.path}
                />
              </circle>
            </g>
          ))}

          {/* 2. HUB COMMUNICATION SPOKES */}
          {hubEdges.map((e) => {
            const strokeColor = e.isLit
              ? "#E5484D"
              : e.isHovered
              ? "#E4E4E7"
              : "#3F3F46";
            const strokeWidth = e.isLit ? 3 : e.isHovered ? 2 : 1.5;

            return (
              <g key={e.id}>
                {/* Communication Line */}
                <path
                  d={e.path}
                  fill="none"
                  stroke={strokeColor}
                  strokeWidth={strokeWidth}
                  className="transition-colors duration-200"
                />

                {/* Moving Dot: Agent -> Hub */}
                <circle
                  r={e.isLit ? 5 : 3.5}
                  fill={e.isLit ? "#E5484D" : "#E4E4E7"}
                  filter={e.isLit ? "url(#particle-glow)" : undefined}
                >
                  <animateMotion
                    dur={`${e.duration}s`}
                    repeatCount="indefinite"
                    path={e.path}
                  />
                </circle>

                {/* Counter-flow Dot: Hub -> Agent */}
                <circle
                  r={2.5}
                  fill={e.isLit ? "#E5484D" : "#A1A1AA"}
                  opacity="0.75"
                >
                  <animateMotion
                    dur={`${e.duration * 1.3}s`}
                    repeatCount="indefinite"
                    path={e.reversePath}
                  />
                </circle>
              </g>
            );
          })}
        </svg>

        {/* Central Hub Node (HTML Overlay) */}
        <div
          style={{ left: "50%", top: "50%", transform: "translate(-50%, -50%)" }}
          onMouseEnter={() => setHoveredNode(HUB_NODE_ID)}
          onMouseLeave={() => setHoveredNode(null)}
          className="absolute z-20 w-[180px] p-3 rounded-panel bg-surface border border-accent/40 shadow-xl flex flex-col items-center justify-center text-center select-none backdrop-blur-md hover:border-accent hover:shadow-accent/10 transition-all cursor-default"
        >
          <div className="flex items-center gap-1.5 text-accent font-semibold text-12 mb-0.5">
            <Scale size={15} strokeWidth={2} />
            <span className="tracking-wide text-text uppercase text-11">
              Consensus Hub
            </span>
          </div>
          <div className="text-11 text-muted font-medium">
            Multi-Agent Protocol
          </div>
          <div className="mt-1 px-2 py-0.5 rounded bg-surface-2 border border-border text-10 font-mono text-text flex items-center gap-1.5">
            <span className="w-1.5 h-1.5 rounded-full bg-ok animate-pulse" />
            <span>Round {activeRound} Active</span>
          </div>
        </div>

        {/* 6 Radial Agent Cards (HTML Overlay with clean typography) */}
        {agentCoords.map((coord) => {
          const meta = AGENTS[coord.id];
          const aView = snapshot?.agents?.find((a: AgentView) => a.agent_id === coord.id);
          const status = aView?.status ?? "online";
          const isIsolated = status === "isolated";
          const isDisconnected = status === "disconnected";
          const isDimmed = isIsolated || isDisconnected;
          const highlight = getAgentHighlight(coord.id);
          const metric = getAgentMetric(coord.id);

          let borderClass = "border-border bg-surface/95";
          if (highlight.isRequesting) {
            borderClass = "border-accent bg-accent-dim ring-2 ring-accent";
          } else if (highlight.isSupplyFlash) {
            borderClass = "border-white bg-surface ring-2 ring-white/60";
          } else if (hoveredNode === coord.id) {
            borderClass = "border-accent/70 bg-surface shadow-md";
          }

          const statusDotColor =
            status === "online"
              ? "bg-ok"
              : status === "isolated"
              ? "bg-accent"
              : "bg-muted";

          return (
            <div
              key={coord.id}
              style={{
                left: `${coord.pctX}%`,
                top: `${coord.pctY}%`,
                transform: "translate(-50%, -50%)",
              }}
              onClick={() => setSelectedAgent(coord.id)}
              onMouseEnter={() => setHoveredNode(coord.id)}
              onMouseLeave={() => setHoveredNode(null)}
              role="button"
              tabIndex={0}
              className={`absolute z-20 w-[196px] p-2.5 rounded-panel border text-left cursor-pointer select-none transition-all duration-150 shadow-md flex flex-col justify-between backdrop-blur-md hover:scale-[1.03] hover:shadow-lg ${borderClass} ${
                isDimmed ? "opacity-50" : ""
              }`}
            >
              {/* Header: Agent Icon + Full Name + Status Dot */}
              <div className="flex items-center justify-between gap-1.5 mb-1">
                <div className="flex items-center gap-2 min-w-0">
                  <div className="p-1 rounded bg-surface-2 border border-border shrink-0">
                    {renderIcon(coord.id)}
                  </div>
                  <span className="text-12 font-semibold text-text truncate">
                    {meta?.name ?? coord.id}
                  </span>
                </div>
                <span
                  className={`w-2 h-2 rounded-full shrink-0 ${statusDotColor} ${
                    status === "online" ? "shadow-xs" : ""
                  }`}
                  title={`Status: ${status}`}
                />
              </div>

              {/* Middle: Full Role Specification (clean text sitting comfortably) */}
              <div className="text-11 text-muted truncate mb-1.5 pl-0.5">
                {meta?.role ?? "Utility Agent"}
              </div>

              {/* Bottom: Live Telemetry Metric Row */}
              <div className="flex items-center justify-between text-10 pt-1.5 border-t border-border/70 text-muted">
                <span className="truncate">{metric.label}</span>
                <span className="text-text font-semibold font-mono text-10 shrink-0 ml-1">
                  {metric.val}
                </span>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
