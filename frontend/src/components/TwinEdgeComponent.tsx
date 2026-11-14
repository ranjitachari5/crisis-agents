import { memo } from "react";
import { type EdgeProps, getBezierPath } from "reactflow";
import type { TwinEdgeKind } from "@/types/api";

export interface TwinEdgeData {
  kind: TwinEdgeKind;
  mw?: number;
  coupling?: number;
  active_cascade?: boolean;
  isHighlighted?: boolean;
}

export const TwinEdgeComponent = memo(function TwinEdgeComponent({
  id,
  sourceX,
  sourceY,
  targetX,
  targetY,
  sourcePosition,
  targetPosition,
  data,
  markerEnd,
}: EdgeProps<TwinEdgeData>) {
  const [edgePath, labelX, labelY] = getBezierPath({
    sourceX,
    sourceY,
    sourcePosition,
    targetX,
    targetY,
    targetPosition,
  });

  const kind = data?.kind ?? "power";
  const mw = data?.mw;
  const isHighlighted = data?.isHighlighted || data?.active_cascade;

  let strokeColor = "#26262B"; // default border
  let strokeWidth = 1;
  let strokeDasharray: string | undefined = undefined;

  if (kind === "power") {
    // Solid, scaled from data.mw, clamped 1-6px
    const powerMw = mw ?? 0;
    // Base formula: 1px minimum, scaling smoothly with MW capacity (e.g. 50 MW = 4px, 100 MW = 6px)
    strokeWidth = Math.min(6, Math.max(1, 1 + Math.round((powerMw / 25) * 1.5)));
    strokeColor = isHighlighted ? "#E5484D" : powerMw > 0 ? "#F4F4F5" : "#8B8B94";
  } else if (kind === "dependency") {
    // Dashed edge
    strokeWidth = 1.5;
    strokeDasharray = "4 4";
    strokeColor = isHighlighted ? "#E5484D" : "#8B8B94";
  } else if (kind === "service") {
    // Thin grey service lifeline edge
    strokeWidth = 1;
    strokeColor = isHighlighted ? "#E5484D" : "#52525B";
  }

  return (
    <>
      <path
        id={id}
        className="react-flow__edge-path transition-colors duration-200"
        d={edgePath}
        markerEnd={markerEnd}
        style={{
          stroke: strokeColor,
          strokeWidth,
          strokeDasharray,
          fill: "none",
        }}
      />

      {/* Edge label for power with MW or coupling info if significant */}
      {kind === "power" && mw !== undefined && mw > 0 && (
        <foreignObject
          width={64}
          height={20}
          x={labelX - 32}
          y={labelY - 10}
          className="pointer-events-none"
          requiredExtensions="http://www.w3.org/1999/xhtml"
        >
          <div className="flex items-center justify-center h-full">
            <span className="text-10 font-medium tabular-nums bg-surface-2/90 border border-border px-1 rounded text-muted">
              {mw.toFixed(0)} MW
            </span>
          </div>
        </foreignObject>
      )}

      {kind === "dependency" && data?.coupling !== undefined && (
        <foreignObject
          width={48}
          height={18}
          x={labelX - 24}
          y={labelY - 9}
          className="pointer-events-none"
          requiredExtensions="http://www.w3.org/1999/xhtml"
        >
          <div className="flex items-center justify-center h-full">
            <span className="text-10 tabular-nums bg-surface-2/90 border border-border px-1 rounded text-muted">
              k={data.coupling}
            </span>
          </div>
        </foreignObject>
      )}
    </>
  );
});

