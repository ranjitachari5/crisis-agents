import { useState, useEffect, useCallback, useMemo } from "react";
import {
  ShieldAlert,
  ShieldCheck,
  RefreshCw,
  Clock,
  Battery,
  AlertTriangle,
  Bot,
  ChevronDown,
  ChevronUp,
  Activity,
  CheckCircle2,
  TrendingDown,
  Layers,
} from "lucide-react";
import { useSimStore } from "@/store/useSimStore";
import { api } from "@/services/api";
import { formatMw } from "@/lib/format";
import type { ExplainResponse } from "@/types/api";

interface Props {
  compact?: boolean;
}

export function CommanderSitRep({ compact = false }: Props) {
  const snapshot = useSimStore((s) => s.snapshot);
  const alerts = useSimStore((s) => s.alerts);
  const messages = useSimStore((s) => s.messages);
  const agreements = useSimStore((s) => s.agreements);

  const [aiSitRep, setAiSitRep] = useState<ExplainResponse | null>(null);
  const [loadingAi, setLoadingAi] = useState(false);
  const [isExpanded, setIsExpanded] = useState(!compact);
  const [lastUpdated, setLastUpdated] = useState<string | null>(null);

  // Compute ground-truth stats from snapshot
  const supplyMw = snapshot?.supply?.total_available_mw ?? 0;
  const demandMw = snapshot?.demand_total_mw ?? 0;
  const deficitMw = snapshot?.deficit_mw ?? 0;
  const activeAlerts = alerts.filter((a) => a.active).length;
  const healthPct = Math.round((snapshot?.infrastructure_health ?? 1.0) * 100);

  // Consumers & Safe floors
  const consumers = useMemo(
    () => snapshot?.agents?.filter((a) => a.kind === "consumer") ?? [],
    [snapshot?.agents]
  );
  const breachedConsumers = useMemo(
    () =>
      consumers.filter(
        (c) => (c.allocation_mw ?? 0) < (c.min_safe_mw ?? 0) - 0.1
      ),
    [consumers]
  );
  const isEmergencyDegradation = breachedConsumers.length > 0;

  // Battery status & endurance
  const batteryAgent = snapshot?.agents?.find((a) => a.agent_id === "battery_agent");
  const batteryDischarge = batteryAgent?.discharge_mw ?? 0;
  const batterySoc = batteryAgent?.soc ?? 0.8;
  const batteryCapMwh = batteryAgent?.max_discharge_mw ? batteryAgent.max_discharge_mw * 3 : 90;
  const batteryEnduranceHours = useMemo(() => {
    if (batteryDischarge <= 0.1) return null;
    const remainingMwh = batterySoc * batteryCapMwh;
    return (remainingMwh / batteryDischarge).toFixed(1);
  }, [batteryDischarge, batterySoc, batteryCapMwh]);

  // Latest agreement & negotiation status
  const currentAgreement = snapshot?.agreement ?? agreements[agreements.length - 1] ?? null;
  const lastNeg = snapshot?.last_negotiation ?? null;

  // Concessions & Safe Lifelines calculation
  const { lifelinesProtected, concessionsMade } = useMemo(() => {
    const protectedList: { name: string; alloc: number }[] = [];
    const cutsList: { name: string; cutMw: number }[] = [];

    for (const c of consumers) {
      const alloc = c.allocation_mw ?? 0;
      const dem = c.demand_mw ?? 0;
      const minSafe = c.min_safe_mw ?? 0;
      const cut = dem - alloc;

      if (alloc >= minSafe - 0.1) {
        protectedList.push({ name: c.display_name, alloc });
      }
      if (cut > 0.5) {
        cutsList.push({ name: c.display_name, cutMw: cut });
      }
    }

    return { lifelinesProtected: protectedList, concessionsMade: cutsList };
  }, [consumers]);

  // Fetch executive AI sitrep
  const fetchAiSitRep = useCallback(async () => {
    setLoadingAi(true);
    try {
      const res = await api.commander.explain(
        "Give an executive situation report of the crisis: what are the key risks and are all critical services safe?"
      );
      setAiSitRep(res);
      const now = new Date();
      setLastUpdated(
        `${now.getHours().toString().padStart(2, "0")}:${now
          .getMinutes()
          .toString()
          .padStart(2, "0")}:${now.getSeconds().toString().padStart(2, "0")}`
      );
    } catch (err) {
      console.warn("Failed fetching AI SitRep:", err);
    } finally {
      setLoadingAi(false);
    }
  }, []);

  // Fetch initial SitRep once snapshot is available
  useEffect(() => {
    if (snapshot && !aiSitRep && !loadingAi) {
      fetchAiSitRep();
    }
  }, [snapshot, aiSitRep, loadingAi, fetchAiSitRep]);

  // Check if an analyst explanation message arrived over WebSocket
  const latestAnalystMsg = useMemo(() => {
    for (let i = messages.length - 1; i >= 0; i--) {
      if (messages[i].message_type === "explanation") {
        return messages[i].content;
      }
    }
    return null;
  }, [messages]);

  // Overall posture status
  let postureStatus: {
    label: string;
    badgeBg: string;
    badgeText: string;
    dotColor: string;
    borderColor: string;
    icon: typeof ShieldCheck;
  };

  if (isEmergencyDegradation) {
    postureStatus = {
      label: "CRITICAL DEFICIT BREACH",
      badgeBg: "bg-accent-dim/50",
      badgeText: "text-accent",
      dotColor: "bg-accent",
      borderColor: "border-accent/60",
      icon: ShieldAlert,
    };
  } else if (deficitMw > 0) {
    postureStatus = {
      label: "CONTROLLED SCARCITY NEGOTIATION",
      badgeBg: "bg-surface-2",
      badgeText: "text-text",
      dotColor: "bg-ok",
      borderColor: "border-border",
      icon: ShieldCheck,
    };
  } else {
    postureStatus = {
      label: "NOMINAL GRID OPERATIONS",
      badgeBg: "bg-surface-2",
      badgeText: "text-ok",
      dotColor: "bg-ok",
      borderColor: "border-ok/40",
      icon: ShieldCheck,
    };
  }

  const PostureIcon = postureStatus.icon;

  // Determine prose text to display
  const displayText =
    latestAnalystMsg ||
    aiSitRep?.text ||
    aiSitRep?.deterministic_summary ||
    (deficitMw > 0
      ? `Active grid deficit of ${deficitMw.toFixed(
          0
        )} MW managed via autonomous negotiation. All ${
          consumers.length
        } consumer utilities are currently protected at or above emergency safe floors.`
      : "Grid operations nominal. All consumer utilities fully supplied.");

  // Compact Variant (Used at top of Live Negotiation)
  if (compact) {
    return (
      <div
        className={`rounded-control border ${postureStatus.borderColor} bg-surface p-3 shadow-sm transition-all text-12`}
      >
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2.5">
          <div className="flex items-center gap-2.5 min-w-0">
            <span className="flex h-2.5 w-2.5 relative shrink-0">
              <span
                className={`animate-ping absolute inline-flex h-full w-full rounded-full ${postureStatus.dotColor} opacity-75`}
              />
              <span
                className={`relative inline-flex rounded-full h-2.5 w-2.5 ${postureStatus.dotColor}`}
              />
            </span>

            <div className="flex items-center gap-2 min-w-0 flex-wrap">
              <span className="text-[10px] uppercase font-mono tracking-wider px-1.5 py-0.5 rounded bg-surface-2 border border-border text-muted">
                SITREP
              </span>
              <span
                className={`font-mono text-11 font-semibold uppercase tracking-wide ${postureStatus.badgeText}`}
              >
                {currentAgreement ? `Agreement v${currentAgreement.version}` : "Live Consensus"}
              </span>
              <span className="text-muted/60 hidden sm:inline">•</span>
              <span className="text-text font-medium truncate">
                {deficitMw > 0
                  ? `${deficitMw.toFixed(0)} MW Deficit Managed (${
                      consumers.length - breachedConsumers.length
                    }/${consumers.length} Safe)`
                  : "Grid Balanced"}
              </span>
              {batteryEnduranceHours && (
                <span className="text-muted text-[11px] font-mono hidden md:inline">
                  (Battery {batteryDischarge.toFixed(0)} MW · ~{batteryEnduranceHours}h reserve)
                </span>
              )}
            </div>
          </div>

          <div className="flex items-center gap-2 shrink-0 self-end sm:self-auto">
            <button
              type="button"
              onClick={fetchAiSitRep}
              disabled={loadingAi}
              className="p-1 px-2 rounded bg-surface-2 hover:bg-border/60 border border-border text-[11px] text-muted hover:text-text transition-colors flex items-center gap-1 cursor-pointer disabled:opacity-50"
              title="Refresh Situation Report"
            >
              <RefreshCw size={11} className={loadingAi ? "animate-spin text-accent" : ""} />
              <span>{loadingAi ? "Updating..." : "Re-Assess"}</span>
            </button>

            <button
              type="button"
              onClick={() => setIsExpanded((prev) => !prev)}
              className="p-1 px-2 rounded hover:bg-surface-2 text-muted hover:text-text cursor-pointer text-[11px] flex items-center gap-1 font-mono"
            >
              <span>{isExpanded ? "Hide Brief" : "Read Brief"}</span>
              {isExpanded ? <ChevronUp size={13} /> : <ChevronDown size={13} />}
            </button>
          </div>
        </div>

        {/* Expandable Brief for Compact Mode */}
        {isExpanded && (
          <div className="mt-2.5 pt-2.5 border-t border-border/70 space-y-2 text-11 animate-in fade-in duration-150">
            <p className="text-text/90 leading-relaxed whitespace-pre-wrap">{displayText}</p>
            {concessionsMade.length > 0 && (
              <div className="flex items-center gap-1.5 flex-wrap text-[10px] text-muted pt-1">
                <span className="font-mono uppercase text-muted/80">Managed Cuts:</span>
                {concessionsMade.map((c, i) => (
                  <span
                    key={i}
                    className="px-1.5 py-0.5 rounded bg-surface-2 border border-border text-text font-mono"
                  >
                    {c.name}: -{c.cutMw.toFixed(1)} MW
                  </span>
                ))}
              </div>
            )}
          </div>
        )}
      </div>
    );
  }

  // Full Executive Variant (Used in Overview)
  return (
    <div
      className={`rounded-panel border ${postureStatus.borderColor} bg-surface p-4 sm:p-5 shadow-sm transition-all`}
    >
      {/* Top Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 pb-3 border-b border-border/80">
        <div className="flex items-center gap-3">
          <div
            className={`w-8 h-8 rounded-lg ${postureStatus.badgeBg} border ${postureStatus.borderColor} flex items-center justify-center shrink-0 shadow-sm`}
          >
            <PostureIcon
              size={18}
              className={
                isEmergencyDegradation ? "text-accent" : deficitMw > 0 ? "text-text" : "text-ok"
              }
            />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <span className="text-[10px] uppercase font-mono tracking-widest text-muted">
                Executive SitRep
              </span>
              <span className="text-muted/60">•</span>
              <span
                className={`text-[11px] font-mono font-bold tracking-wider uppercase ${postureStatus.badgeText}`}
              >
                {postureStatus.label}
              </span>
              {currentAgreement && (
                <span className="text-[10px] font-mono px-1.5 py-0.2 rounded bg-surface-2 border border-border text-muted">
                  Agreement v{currentAgreement.version}
                </span>
              )}
            </div>
            <h3 className="text-14 font-semibold text-text">
              {deficitMw > 0
                ? `${deficitMw.toFixed(0)} MW Deficit Absorbed • ${
                    consumers.length - breachedConsumers.length
                  }/${consumers.length} Critical Lifelines Protected`
                : "Grid In Full Balance • Zero Power Shortfall"}
            </h3>
          </div>
        </div>

        <div className="flex items-center gap-2 self-end sm:self-auto">
          {lastUpdated && (
            <span className="text-10 font-mono text-muted flex items-center gap-1">
              <Clock size={11} />
              Updated {lastUpdated}
            </span>
          )}

          <button
            type="button"
            onClick={fetchAiSitRep}
            disabled={loadingAi}
            className="px-2.5 py-1 rounded bg-surface-2 hover:bg-border/60 border border-border text-11 text-muted hover:text-text transition-colors flex items-center gap-1.5 cursor-pointer disabled:opacity-50"
            title="Refresh AI Executive Briefing"
          >
            <RefreshCw size={12} className={loadingAi ? "animate-spin text-accent" : ""} />
            <span>{loadingAi ? "Analyzing..." : "Re-Assess"}</span>
          </button>

          <button
            type="button"
            onClick={() => setIsExpanded((prev) => !prev)}
            className="p-1 rounded hover:bg-surface-2 text-muted hover:text-text cursor-pointer"
            title={isExpanded ? "Collapse SitRep" : "Expand SitRep"}
          >
            {isExpanded ? <ChevronUp size={16} /> : <ChevronDown size={16} />}
          </button>
        </div>
      </div>

      {/* Expanded Content */}
      {isExpanded && (
        <div className="pt-3.5 space-y-3.5">
          {/* 4 Key Tactical Metric Pills */}
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-2.5 text-12">
            <div className="p-2.5 rounded bg-surface-2 border border-border flex items-center justify-between">
              <div>
                <span className="text-[10px] uppercase font-mono text-muted block">Deficit Status</span>
                <span className="font-semibold text-text font-mono">
                  {deficitMw > 0 ? `-${deficitMw.toFixed(0)} MW` : "0 MW"}
                </span>
              </div>
              <span
                className={`text-[10px] font-mono px-1.5 py-0.5 rounded ${
                  deficitMw > 0 ? "bg-accent-dim text-accent" : "bg-ok-dim text-ok"
                }`}
              >
                {deficitMw > 0 ? "Scarcity" : "Balanced"}
              </span>
            </div>

            <div className="p-2.5 rounded bg-surface-2 border border-border flex items-center justify-between">
              <div>
                <span className="text-[10px] uppercase font-mono text-muted block">Safe Minimums</span>
                <span className="font-semibold text-text font-mono">
                  {consumers.length - breachedConsumers.length} / {consumers.length} Met
                </span>
              </div>
              <span
                className={`text-[10px] font-mono px-1.5 py-0.5 rounded ${
                  isEmergencyDegradation ? "bg-accent-dim text-accent" : "bg-surface text-ok"
                }`}
              >
                {isEmergencyDegradation ? "At Risk" : "100% Safe"}
              </span>
            </div>

            <div className="p-2.5 rounded bg-surface-2 border border-border flex items-center justify-between">
              <div>
                <span className="text-[10px] uppercase font-mono text-muted block">Battery Discharge</span>
                <span className="font-semibold text-text font-mono">
                  {batteryDischarge.toFixed(1)} MW
                </span>
              </div>
              <span className="text-[10px] font-mono text-muted flex items-center gap-1">
                <Battery size={12} className={batteryDischarge > 0 ? "text-accent" : "text-ok"} />
                {Math.round(batterySoc * 100)}%
                {batteryEnduranceHours && ` (~${batteryEnduranceHours}h)`}
              </span>
            </div>

            <div className="p-2.5 rounded bg-surface-2 border border-border flex items-center justify-between">
              <div>
                <span className="text-[10px] uppercase font-mono text-muted block">Grid Integrity</span>
                <span className="font-semibold text-text font-mono">{healthPct}%</span>
              </div>
              <span
                className={`text-[10px] font-mono px-1.5 py-0.5 rounded ${
                  healthPct >= 80
                    ? "bg-ok-dim text-ok"
                    : healthPct >= 50
                    ? "bg-surface text-muted"
                    : "bg-accent-dim text-accent"
                }`}
              >
                {healthPct >= 80 ? "Optimal" : healthPct >= 50 ? "Degraded" : "Critical"}
              </span>
            </div>
          </div>

          {/* Real-World Concessions & Protected Lifelines Strip */}
          <div className="p-3 rounded-control bg-surface-2/60 border border-border/80 flex flex-col md:flex-row md:items-center justify-between gap-3 text-11">
            <div className="space-y-1">
              <span className="text-[10px] font-mono uppercase tracking-wider text-muted flex items-center gap-1">
                <CheckCircle2 size={12} className="text-ok" />
                Guaranteed Critical Lifelines
              </span>
              <div className="flex items-center gap-1.5 flex-wrap">
                {lifelinesProtected.map((p, i) => (
                  <span
                    key={i}
                    className="px-2 py-0.5 rounded bg-surface border border-border text-text font-mono text-[11px]"
                  >
                    {p.name}: <span className="font-semibold">{p.alloc.toFixed(1)} MW</span>
                  </span>
                ))}
              </div>
            </div>

            {concessionsMade.length > 0 && (
              <div className="space-y-1 md:border-l md:border-border md:pl-4">
                <span className="text-[10px] font-mono uppercase tracking-wider text-muted flex items-center gap-1">
                  <TrendingDown size={12} className="text-accent" />
                  Absorbed Power Deferrals
                </span>
                <div className="flex items-center gap-1.5 flex-wrap">
                  {concessionsMade.map((c, i) => (
                    <span
                      key={i}
                      className="px-2 py-0.5 rounded bg-surface border border-border text-muted font-mono text-[11px]"
                    >
                      {c.name}: <span className="text-accent">-{c.cutMw.toFixed(1)} MW</span>
                    </span>
                  ))}
                </div>
              </div>
            )}
          </div>

          {/* AI Executive Summary Prose */}
          <div className="p-3.5 rounded-control bg-surface-2 border border-border text-12 text-text/90 leading-relaxed">
            <div className="flex items-center gap-1.5 text-11 font-medium text-text mb-1.5">
              <Bot size={14} className="text-accent" />
              <span>Commander Advisory Assessment</span>
              {aiSitRep?.source && (
                <span className="text-[10px] font-mono text-muted ml-auto">
                  {aiSitRep.source.replace("groq:", "Groq: ")}
                </span>
              )}
            </div>

            {loadingAi ? (
              <div className="py-2 flex items-center gap-2 text-muted text-11 font-mono">
                <RefreshCw size={12} className="animate-spin text-accent" />
                <span>Synthesizing multi-agent consensus and telemetry...</span>
              </div>
            ) : (
              <p className="whitespace-pre-wrap">{displayText}</p>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
