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

  let strokeColor = "#3F3F46";
  let strokeWidth = 1.5;
  let strokeDasharray: string | undefined = undefined;

  if (kind === "power") {
    // Solid line, scaled with power MW
    const powerMw = mw ?? 0;
    strokeWidth = Math.min(5, Math.max(1.5, 1.5 + Math.round((powerMw / 30) * 1.5)));
    strokeColor = isHighlighted ? "#E5484D" : powerMw > 0 ? "#E4E4E7" : "#52525B";
  } else if (kind === "dependency") {
    // Elegant dashed dependency link
    strokeWidth = 1.5;
    strokeDasharray = "5 5";
    strokeColor = isHighlighted ? "#E5484D" : "#71717A";
  } else if (kind === "service") {
    // Subtle service lifeline link
    strokeWidth = 1.5;
    strokeDasharray = "2 3";
    strokeColor = isHighlighted ? "#E5484D" : "#52525B";
  }

  return (
    <>
      <path
        id={id}
        className="react-flow__edge-path transition-all duration-200"
        d={edgePath}
        markerEnd={markerEnd}
        style={{
          stroke: strokeColor,
          strokeWidth,
          strokeDasharray,
          fill: "none",
        }}
      />

      {/* Floating MW Badge only on primary power lines carrying active load */}
      {kind === "power" && mw !== undefined && mw >= 10 && (
        <foreignObject
          width={56}
          height={18}
          x={labelX - 28}
          y={labelY - 9}
          className="pointer-events-none select-none"
          requiredExtensions="http://www.w3.org/1999/xhtml"
        >
          <div className="flex items-center justify-center h-full">
            <span
              className={`text-10 font-semibold tabular-nums px-1.5 py-0.2 rounded border shadow-xs ${
                isHighlighted
                  ? "bg-accent text-white border-accent"
                  : "bg-surface border-border text-text/90"
              }`}
            >
              {mw.toFixed(0)} MW
            </span>
          </div>
        </foreignObject>
      )}

      {/* Subtle coupling badge for critical dependencies */}
      {kind === "dependency" && isHighlighted && data?.coupling !== undefined && (
        <foreignObject
          width={44}
          height={16}
          x={labelX - 22}
          y={labelY - 8}
          className="pointer-events-none select-none"
          requiredExtensions="http://www.w3.org/1999/xhtml"
        >
          <div className="flex items-center justify-center h-full">
            <span className="text-9 font-medium tabular-nums bg-accent-dim border border-accent/40 text-accent px-1 rounded">
              k={data.coupling}
            </span>
          </div>
        </foreignObject>
      )}
    </>
  );
});
