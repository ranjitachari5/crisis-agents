import { useMemo, useState, useEffect, useCallback, useRef } from "react";
import ReactFlow, {
  type Node,
  type Edge,
  Background,
  BackgroundVariant,
  Controls,
} from "reactflow";
import "reactflow/dist/style.css";
import { TwinNodeComponent, type TwinNodeData } from "@/components/TwinNodeComponent";
import { TwinEdgeComponent, type TwinEdgeData } from "@/components/TwinEdgeComponent";
import type { TwinGraph as TwinGraphType, CascadeChain, TwinNodeStatus, TwinEdgeKind } from "@/types/api";

const nodeTypes = {
  twinNode: TwinNodeComponent,
};

const edgeTypes = {
  twinEdge: TwinEdgeComponent,
};

/**
 * Clean, non-overlapping 4-stage municipal infrastructure topology.
 *
 * Stage 1: Generation & Storage (Grid & Battery)
 * Stage 2: City Power Bus (Transmission Backbone)
 * Stage 3: Municipal Utilities (Water & Telecom feed Hospital & Emergency)
 * Stage 4: Critical Lifeline Services (ICU, Water Supply, Comms Dispatch, Firefighting)
 *
 * Every single edge flows cleanly from left to right with zero backward loops or node overlaps.
 */
const NODE_COORDINATES: Record<string, { x: number; y: number }> = {
  // Column 1: Generation & Storage
  grid_agent: { x: 30, y: 70 },
  battery_agent: { x: 30, y: 270 },

  // Column 2: Grid Distribution Bus
  power_bus: { x: 235, y: 170 },

  // Column 3: Municipal Utilities
  // Water and Telecom supply resources & telemetry to Hospital and Emergency
  water_agent: { x: 440, y: 80 },
  telecom_agent: { x: 440, y: 260 },
  hospital_agent: { x: 645, y: 20 },
  emergency_agent: { x: 645, y: 320 },

  // Column 4: Critical Lifeline Services (backend IDs: svc_*)
  svc_icu: { x: 860, y: 20 },
  svc_hospital_water: { x: 860, y: 120 },
  svc_dispatch: { x: 860, y: 220 },
  svc_firefighting: { x: 860, y: 320 },

  // Fallback aliases for resilience
  icu: { x: 860, y: 20 },
  hospital_water: { x: 860, y: 120 },
  dispatch: { x: 860, y: 220 },
  firefighting: { x: 860, y: 320 },
};

interface Props {
  graph: TwinGraphType | null;
  activeCascade: CascadeChain | null;
  onClearCascadeTrace?: () => void;
}

export function TwinGraph({ graph, activeCascade, onClearCascadeTrace }: Props) {
  // Highlighted node IDs during cascade playback
  const [highlightedNodeIds, setHighlightedNodeIds] = useState<Set<string>>(new Set());
  const [highlightedEdgeIds, setHighlightedEdgeIds] = useState<Set<string>>(new Set());
  const timerRef = useRef<NodeJS.Timeout[]>([]);

  // Clear timers on unmount
  useEffect(() => {
    return () => {
      timerRef.current.forEach(clearTimeout);
    };
  }, []);

  // Sequential cascade playback: ~150ms apart
  const playCascadeAnimation = useCallback((cascade: CascadeChain) => {
    timerRef.current.forEach(clearTimeout);
    timerRef.current = [];
    setHighlightedNodeIds(new Set());
    setHighlightedEdgeIds(new Set());

    const path = cascade.path;
    if (!path || path.length === 0) return;

    // Step through hops with 150ms intervals
    path.forEach((nodeId, idx) => {
      const timer = setTimeout(() => {
        setHighlightedNodeIds((prev) => new Set([...prev, nodeId]));

        if (idx > 0) {
          const prevNodeId = path[idx - 1];
          const edgeId = `e-${prevNodeId}-${nodeId}`;
          const altEdgeId = `e-bus-${nodeId}`;
          setHighlightedEdgeIds((prev) => new Set([...prev, edgeId, altEdgeId]));
        }
      }, idx * 150);
      timerRef.current.push(timer);
    });

    // Reset after 3 seconds
    const resetTimer = setTimeout(() => {
      setHighlightedNodeIds(new Set());
      setHighlightedEdgeIds(new Set());
      onClearCascadeTrace?.();
    }, path.length * 150 + 2500);
    timerRef.current.push(resetTimer);
  }, [onClearCascadeTrace]);

  // Trigger cascade animation whenever activeCascade changes
  useEffect(() => {
    if (activeCascade) {
      playCascadeAnimation(activeCascade);
    }
  }, [activeCascade, playCascadeAnimation]);

  // Construct React Flow Nodes
  const nodes: Node<TwinNodeData>[] = useMemo(() => {
    if (!graph || !graph.nodes) return [];

    return graph.nodes.map((n, idx) => {
      const pos =
        NODE_COORDINATES[n.id] ?? {
          x: 540,
          y: 90 + ((idx * 85) % 340),
        };
      const isHighlighted = highlightedNodeIds.has(n.id);
      const isCascadeRoot = activeCascade?.root === n.id;

      // Extract specific fields safely
      const rawData = n.data ?? {};
      const status: TwinNodeStatus = (rawData.status as TwinNodeStatus) ?? "ok";

      return {
        id: n.id,
        type: "twinNode",
        position: pos,
        data: {
          id: n.id,
          type: n.type,
          label: n.label,
          status,
          isHighlighted,
          isCascadeRoot,
          available_mw: rawData.available_mw as number | undefined,
          nominal_mw: rawData.nominal_mw as number | undefined,
          soc: rawData.soc as number | undefined,
          discharge_mw: rawData.discharge_mw as number | undefined,
          grid_flow_mw: rawData.grid_flow_mw as number | undefined,
          battery_flow_mw: rawData.battery_flow_mw as number | undefined,
          allocation_mw: rawData.allocation_mw as number | undefined,
          demand_mw: rawData.demand_mw as number | undefined,
          level: rawData.level as number | undefined,
          health: rawData.health as number | undefined,
        },
      };
    });
  }, [graph, highlightedNodeIds, activeCascade]);

  // Construct React Flow Edges
  const edges: Edge<TwinEdgeData>[] = useMemo(() => {
    if (!graph || !graph.edges) return [];

    return graph.edges.map((e) => {
      const rawData = e.data ?? {};
      const isHighlighted =
        highlightedEdgeIds.has(e.id) ||
        (highlightedNodeIds.has(e.source) && highlightedNodeIds.has(e.target));

      return {
        id: e.id,
        source: e.source,
        target: e.target,
        type: "twinEdge",
        data: {
          kind: e.kind as TwinEdgeKind,
          mw: rawData.mw as number | undefined,
          coupling: rawData.coupling as number | undefined,
          active_cascade: rawData.active_cascade as boolean | undefined,
          isHighlighted,
        },
      };
    });
  }, [graph, highlightedEdgeIds, highlightedNodeIds]);

  return (
    <div className="flex flex-col h-full bg-surface rounded-panel border border-border overflow-hidden">
      {/* Top Topology Column Labels */}
      <div className="grid grid-cols-4 px-6 py-2 border-b border-border text-11 uppercase font-semibold tracking-wider text-muted select-none bg-surface-2/40">
        <div>1. Generation & Storage</div>
        <div className="text-center">2. Grid Distribution</div>
        <div className="text-center">3. Municipal Utilities</div>
        <div className="text-right">4. Critical Services</div>
      </div>

      {/* Flow Canvas */}
      <div className="h-[480px] w-full relative">
        <ReactFlow
          nodes={nodes}
          edges={edges}
          nodeTypes={nodeTypes}
          edgeTypes={edgeTypes}
          fitView
          fitViewOptions={{ padding: 0.12 }}
          nodesDraggable={true}
          nodesConnectable={false}
          elementsSelectable={true}
          zoomOnScroll={true}
          panOnDrag={true}
          preventScrolling={false}
          proOptions={{ hideAttribution: true }}
        >
          <Background color="#1C1C21" gap={16} variant={BackgroundVariant.Dots} />
          <Controls
            showInteractive={false}
            className="!bg-surface !border !border-border !rounded-control !shadow-md [&>button]:!bg-surface-2 [&>button]:!border-border [&>button]:!text-text [&>button:hover]:!bg-border"
          />
        </ReactFlow>
      </div>

      {/* Legend & Semantics Bar */}
      <div className="px-4 py-2.5 border-t border-border bg-surface flex flex-wrap items-center justify-between gap-3 text-11 text-muted select-none">
        <div className="flex items-center gap-4">
          <span className="font-medium text-text">Edge Semantics:</span>
          <div className="flex items-center gap-1.5">
            <span className="w-5 h-0.5 bg-text inline-block" />
            <span>Power Flow</span>
          </div>
          <div className="flex items-center gap-1.5">
            <span className="w-5 border-t border-dashed border-muted inline-block" />
            <span>Operational Dependency</span>
          </div>
          <div className="flex items-center gap-1.5">
            <span className="w-5 border-t border-[#52525B] inline-block" />
            <span>Lifeline Service</span>
          </div>
        </div>

        <div className="flex items-center gap-3">
          <span className="font-medium text-text">Status:</span>
          <div className="flex items-center gap-1">
            <span className="w-2 h-2 rounded-full bg-ok inline-block" />
            <span>Normal</span>
          </div>
          <div className="flex items-center gap-1">
            <span className="w-2 h-2 rounded-full bg-muted inline-block" />
            <span>Degraded</span>
          </div>
          <div className="flex items-center gap-1">
            <span className="w-2 h-2 rounded-full bg-accent inline-block" />
            <span>Critical</span>
          </div>
        </div>
      </div>
    </div>
  );
}
