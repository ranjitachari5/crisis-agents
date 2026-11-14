import { useMemo } from "react";
import ReactFlow, {
  type Node,
  type Edge,
  type EdgeProps,
  type NodeProps,
  getStraightPath,
} from "reactflow";
import "reactflow/dist/style.css";
import {
  HeartPulse,
  Droplets,
  RadioTower,
  Siren,
  BatteryCharging,
  Zap,
  Scale,
} from "lucide-react";
import { AGENTS, edgeId } from "@/lib/agents";
import { HUB_NODE_ID } from "@/lib/constants";
import { useAgentActivity } from "@/hooks/useAgentActivity";
import { useSimStore } from "@/store/useSimStore";
import type { AgentId, AgentView } from "@/types/api";

// ---------------------------------------------------- Custom Node Component
function AgentNetworkNode({ data }: NodeProps<{ agentId: string; isHub?: boolean }>) {
  const { getAgentHighlight } = useAgentActivity();
  const snapshot = useSimStore((s) => s.snapshot);
  const setSelectedAgent = useSimStore((s) => s.setSelectedAgent);

  const { agentId, isHub } = data;

  if (isHub) {
    return (
      <div className="px-3.5 py-2.5 rounded-panel bg-surface-2 border border-border text-center select-none shadow-sm min-w-[130px]">
        <div className="flex items-center justify-center gap-1.5 text-muted mb-0.5">
          <Scale size={14} strokeWidth={1.5} />
          <span className="text-11 uppercase font-semibold tracking-wider text-text">Hub</span>
        </div>
        <span className="text-11 text-muted">Negotiation Group</span>
      </div>
    );
  }

  const meta = AGENTS[agentId as AgentId];
  const agentView = snapshot?.agents?.find((a: AgentView) => a.agent_id === agentId);
  const status = agentView?.status ?? "online";
  const isIsolated = status === "isolated";
  const isDisconnected = status === "disconnected";
  const isDimmed = isIsolated || isDisconnected;

  const highlight = getAgentHighlight(agentId);

  let borderBgClass = "border-border bg-surface";
  if (highlight.isRequesting) {
    borderBgClass = "border-accent bg-accent-dim transition-all duration-200";
  } else if (highlight.isSupplyFlash) {
    borderBgClass = "border-white/80 bg-surface transition-all duration-200";
  }

  const renderIcon = () => {
    const props = { size: 14, strokeWidth: 1.5, className: "shrink-0" };
    switch (agentId) {
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

  const statusColor =
    status === "online"
      ? "bg-ok"
      : status === "isolated"
      ? "bg-accent"
      : "bg-muted";

  return (
    <div
      onClick={() => setSelectedAgent(agentId as AgentId)}
      className={`px-3 py-2 rounded-panel border text-left cursor-pointer select-none transition-all duration-200 min-w-[140px] ${borderBgClass} ${
        isDimmed ? "opacity-50" : ""
      }`}
    >
      <div className="flex items-center justify-between gap-1.5">
        <div className="flex items-center gap-1.5 min-w-0">
          <div className="text-muted">{renderIcon()}</div>
          <span className="text-12 font-medium text-text truncate">
            {meta?.name ?? agentId}
          </span>
        </div>
        <span className={`w-1.5 h-1.5 rounded-full shrink-0 ${statusColor}`} />
      </div>

      <div className="mt-1 flex items-center justify-between text-11 text-muted">
        <span className="truncate">{meta?.role?.split("&")[0] ?? ""}</span>
        {highlight.isRequesting && (
          <span className="text-accent font-medium ml-1">Req</span>
        )}
      </div>
    </div>
  );
}

// ---------------------------------------------------- Custom Edge Component
function AgentNetworkEdge({
  id,
  sourceX,
  sourceY,
  targetX,
  targetY,
  data,
}: EdgeProps<{ isDashed?: boolean }>) {
  const { getEdgeHighlight } = useAgentActivity();
  const { isLit, dotActive } = getEdgeHighlight(id);

  const [edgePath] = getStraightPath({
    sourceX,
    sourceY,
    targetX,
    targetY,
  });

  const strokeColor = isLit ? "#E5484D" : "#26262B";
  const strokeWidth = isLit ? 2 : 1.5;
  const isDashed = data?.isDashed ?? false;

  return (
    <>
      <path
        id={id}
        className="react-flow__edge-path transition-colors duration-200"
        d={edgePath}
        stroke={strokeColor}
        strokeWidth={strokeWidth}
        strokeDasharray={isDashed ? "4 4" : undefined}
      />

      {dotActive && (
        <circle r={3.5} fill="#E5484D">
          <animateMotion
            dur="800ms"
            repeatCount="1"
            fill="freeze"
            path={edgePath}
          />
        </circle>
      )}
    </>
  );
}

// Node types registry
const nodeTypes = {
  agentNode: AgentNetworkNode,
};

const edgeTypes = {
  customEdge: AgentNetworkEdge,
};

// ---------------------------------------------------- Main Network Component
export function AgentNetwork() {
  const snapshot = useSimStore((s) => s.snapshot);
  const twinGraph = useSimStore((s) => s.twinGraph);
  const edgeActivity = useSimStore((s) => s.edgeActivity);

  // Position nodes radially around the central hub (center: 360, 220, radius: 180)
  const nodes: Node[] = useMemo(() => {
    const cx = 360;
    const cy = 200;
    const r = 160;

    // Ordered layout
    const agentOrder: AgentId[] = [
      "grid_agent",
      "battery_agent",
      "hospital_agent",
      "water_agent",
      "telecom_agent",
      "emergency_agent",
    ];

    const result: Node[] = [
      // Central Hub Node
      {
        id: HUB_NODE_ID,
        type: "agentNode",
        position: { x: cx - 65, y: cy - 25 },
        data: { agentId: HUB_NODE_ID, isHub: true },
        draggable: false,
      },
    ];

    // Radial Agent Nodes
    agentOrder.forEach((aid, idx) => {
      // Offset by -pi/2 so grid_agent is at the very top
      const angle = (idx * 2 * Math.PI) / agentOrder.length - Math.PI / 2;
      const x = cx + r * Math.cos(angle) - 70;
      const y = cy + r * Math.sin(angle) - 25;

      result.push({
        id: aid,
        type: "agentNode",
        position: { x, y },
        data: { agentId: aid, isHub: false },
        draggable: false,
      });
    });

    return result;
  }, []);

  // Build edges:
  // 1. Hub edges from every agent to negotiation_group
  // 2. Twin dependency & power edges between agents
  // 3. Dynamic edges if active message pair doesn't exist
  const edges: Edge[] = useMemo(() => {
    const edgeMap = new Map<string, Edge>();

    const agentsList = snapshot?.agents ?? [];
    const isAgentDisconnected = (aid: string) => {
      const a = agentsList.find((v: AgentView) => v.agent_id === aid);
      return a?.status === "isolated" || a?.status === "disconnected";
    };

    // 1. Base edges: every agent to hub
    const agentIds: AgentId[] = [
      "grid_agent",
      "battery_agent",
      "hospital_agent",
      "water_agent",
      "telecom_agent",
      "emergency_agent",
    ];

    agentIds.forEach((aid) => {
      const eId = edgeId(aid, HUB_NODE_ID);
      const dashed = isAgentDisconnected(aid);
      edgeMap.set(eId, {
        id: eId,
        source: aid,
        target: HUB_NODE_ID,
        type: "customEdge",
        data: { isDashed: dashed },
      });
    });

    // 2. Inter-agent edges derived from twin dependency & power edges
    if (twinGraph?.edges) {
      twinGraph.edges.forEach((te) => {
        // Only if both source and target are among the 6 agents
        if (agentIds.includes(te.source as AgentId) && agentIds.includes(te.target as AgentId)) {
          const eId = edgeId(te.source, te.target);
          if (!edgeMap.has(eId)) {
            const dashed =
              te.kind === "dependency" ||
              isAgentDisconnected(te.source) ||
              isAgentDisconnected(te.target);
            edgeMap.set(eId, {
              id: eId,
              source: te.source,
              target: te.target,
              type: "customEdge",
              data: { isDashed: dashed },
            });
          }
        }
      });
    }

    // 3. Dynamic edges for live peer messages in edgeActivity that lack a base edge
    Object.keys(edgeActivity).forEach((activePairId) => {
      if (!edgeMap.has(activePairId)) {
        const parts = activePairId.split("|");
        if (parts.length === 2) {
          edgeMap.set(activePairId, {
            id: activePairId,
            source: parts[0],
            target: parts[1],
            type: "customEdge",
            data: { isDashed: true },
          });
        }
      }
    });

    return Array.from(edgeMap.values());
  }, [snapshot, twinGraph, edgeActivity]);

  return (
    <div className="w-full h-[460px] bg-surface rounded-panel border border-border relative overflow-hidden select-none">
      <div className="absolute top-3 left-4 z-10 flex items-center gap-4 text-11 text-muted">
        <div className="flex items-center gap-1.5">
          <span className="w-2.5 h-0.5 bg-muted/60" />
          <span>Hub Edge</span>
        </div>
        <div className="flex items-center gap-1.5">
          <span className="w-2.5 h-0.5 border-b border-dashed border-muted/60" />
          <span>Dependency / Isolated</span>
        </div>
        <div className="flex items-center gap-1.5">
          <span className="w-2 h-2 rounded-full bg-accent" />
          <span>Live Message Pulse</span>
        </div>
      </div>

      <ReactFlow
        nodes={nodes}
        edges={edges}
        nodeTypes={nodeTypes}
        edgeTypes={edgeTypes}
        nodesDraggable={false}
        nodesConnectable={false}
        elementsSelectable={false}
        panOnDrag={false}
        zoomOnScroll={false}
        preventScrolling={false}
        fitView
        fitViewOptions={{ padding: 0.2 }}
        proOptions={{ hideAttribution: true }}
      />
    </div>
  );
}
