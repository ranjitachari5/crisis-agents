import { useState, useEffect, useCallback } from "react";
import { RefreshCw, Activity, Cpu, BatteryCharging, Zap } from "lucide-react";
import { TwinGraph } from "@/components/TwinGraph";
import { CascadeList } from "@/components/CascadeList";
import { api } from "@/services/api";
import { useSimStore } from "@/store/useSimStore";
import type { TwinGraph as TwinGraphType, CascadeChain } from "@/types/api";

export function TwinSection() {
  const snapshot = useSimStore((s) => s.snapshot);
  const [graph, setGraph] = useState<TwinGraphType | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [activeCascadeIndex, setActiveCascadeIndex] = useState<number | null>(null);

  // Fetch twin graph topology
  const fetchGraph = useCallback(async () => {
    setIsLoading(true);
    try {
      const data = await api.twin.graph();
      setGraph(data);
    } catch (err) {
      console.warn("Failed fetching digital twin graph:", err);
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchGraph();
  }, [fetchGraph]);

  const cascades = snapshot?.cascades ?? graph?.cascades ?? [];
  const activeCascade: CascadeChain | null =
    activeCascadeIndex !== null && cascades[activeCascadeIndex]
      ? cascades[activeCascadeIndex]
      : null;

  const handleTraceCascade = (index: number) => {
    setActiveCascadeIndex(index);
  };

  const handleClearCascadeTrace = () => {
    setActiveCascadeIndex(null);
  };

  // Extract quick metrics from graph data
  const gridNode = graph?.nodes?.find((n) => n.id === "grid_agent");
  const batteryNode = graph?.nodes?.find((n) => n.id === "battery_agent");
  const busNode = graph?.nodes?.find((n) => n.id === "power_bus");

  const gridAvailable = (gridNode?.data?.available_mw as number | undefined) ?? snapshot?.supply?.grid_verified_mw ?? 0;
  const gridNominal = (gridNode?.data?.nominal_mw as number | undefined) ?? snapshot?.supply?.grid_nominal_mw ?? 200;
  const batterySoc = (batteryNode?.data?.soc as number | undefined) ?? graph?.battery_soc ?? 0;
  const batteryDischarge = (batteryNode?.data?.discharge_mw as number | undefined) ?? 0;
  const gridFlow = (busNode?.data?.grid_flow_mw as number | undefined) ?? 0;
  const batteryFlow = (busNode?.data?.battery_flow_mw as number | undefined) ?? 0;
  const busThroughput = gridFlow + batteryFlow;

  return (
    <section id="city-digital-twin" className="scroll-mt-16 space-y-4">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 pb-1 border-b border-border">
        <div>
          <div className="flex items-center gap-2">
            <span className="text-11 uppercase font-semibold tracking-wider text-muted">
              Infrastructure
            </span>
            <span className="text-border">/</span>
            <span className="text-11 text-muted">Physics & Dependencies</span>
          </div>
          <h1 className="text-20 font-semibold text-text">City Digital Twin</h1>
        </div>

        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={fetchGraph}
            disabled={isLoading}
            className="inline-flex items-center gap-1.5 px-3 py-1.5 text-12 rounded border border-border bg-surface-2 hover:bg-surface text-text transition-colors disabled:opacity-50"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${isLoading ? "animate-spin text-accent" : "text-muted"}`} />
            <span>Reload Topology</span>
          </button>
        </div>
      </div>

      {/* Top Telemetry Strip */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <div className="p-3 bg-surface rounded-panel border border-border">
          <div className="flex items-center gap-1.5 text-muted mb-1">
            <Zap className="w-3.5 h-3.5 text-muted" />
            <span className="text-11 font-medium">Grid Generation</span>
          </div>
          <div className="text-16 font-semibold text-text tabular-nums">
            {gridAvailable.toFixed(1)} <span className="text-12 font-normal text-muted">/ {gridNominal.toFixed(0)} MW</span>
          </div>
        </div>

        <div className="p-3 bg-surface rounded-panel border border-border">
          <div className="flex items-center gap-1.5 text-muted mb-1">
            <BatteryCharging className="w-3.5 h-3.5 text-muted" />
            <span className="text-11 font-medium">Battery Storage</span>
          </div>
          <div className="text-16 font-semibold text-text tabular-nums">
            {(batterySoc * 100).toFixed(0)}% <span className="text-12 font-normal text-muted">({batteryDischarge.toFixed(1)} MW)</span>
          </div>
        </div>

        <div className="p-3 bg-surface rounded-panel border border-border">
          <div className="flex items-center gap-1.5 text-muted mb-1">
            <Cpu className="w-3.5 h-3.5 text-muted" />
            <span className="text-11 font-medium">Bus Throughput</span>
          </div>
          <div className="text-16 font-semibold text-text tabular-nums">
            {busThroughput.toFixed(1)} <span className="text-12 font-normal text-muted">MW total</span>
          </div>
        </div>

        <div className="p-3 bg-surface rounded-panel border border-border">
          <div className="flex items-center gap-1.5 text-muted mb-1">
            <Activity className="w-3.5 h-3.5 text-accent" />
            <span className="text-11 font-medium">Cascading Risks</span>
          </div>
          <div className={`text-16 font-semibold tabular-nums ${cascades.length > 0 ? "text-accent" : "text-ok"}`}>
            {cascades.length} <span className="text-12 font-normal text-muted">active chain{cascades.length === 1 ? "" : "s"}</span>
          </div>
        </div>
      </div>

      {/* Main Grid: Twin Graph + Cascade Chains */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-4 items-stretch">
        <div className="lg:col-span-8 min-h-[480px]">
          <TwinGraph
            graph={graph}
            activeCascade={activeCascade}
            onClearCascadeTrace={handleClearCascadeTrace}
          />
        </div>

        <div className="lg:col-span-4 min-h-[480px]">
          <CascadeList
            cascades={cascades}
            activeCascadeIndex={activeCascadeIndex}
            onTraceCascade={handleTraceCascade}
          />
        </div>
      </div>
    </section>
  );
}
