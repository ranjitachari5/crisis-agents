import { useState, useEffect, useCallback } from "react";
import { ShieldAlert, RefreshCw } from "lucide-react";
import { IncidentDetail } from "@/components/IncidentDetail";
import { ReputationList } from "@/components/ReputationList";
import { QuarantineTable } from "@/components/QuarantineTable";
import { Toast, type ToastMessage } from "@/components/Toast";
import { AGENTS } from "@/lib/agents";
import { api } from "@/services/api";
import { errorMessage } from "@/lib/errors";
import { useSimStore } from "@/store/useSimStore";
import type { TrustIncident, QuarantineEntry, AgentId } from "@/types/api";

export function TrustSection() {
  const storeIncidents = useSimStore((s) => s.incidents);
  const storeReputation = useSimStore((s) => s.reputation);

  const [incidents, setIncidents] = useState<TrustIncident[]>(storeIncidents);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [quarantine, setQuarantine] = useState<QuarantineEntry[]>([]);
  const [reputation, setReputation] = useState<Record<string, number>>(storeReputation);

  const [isInjecting, setIsInjecting] = useState(false);
  const [isLoading, setIsLoading] = useState(false);
  const [toasts, setToasts] = useState<ToastMessage[]>([]);

  const addToast = (type: "success" | "error" | "info", message: string) => {
    const id = `${Date.now()}-${Math.random().toString(36).substring(2, 7)}`;
    setToasts((prev) => [...prev, { id, type, message }]);
  };

  const dismissToast = (id: string) => {
    setToasts((prev) => prev.filter((t) => t.id !== id));
  };

  // Sync with store when new incident arrives via WS
  useEffect(() => {
    if (storeIncidents.length > 0) {
      setIncidents((prev) => {
        const merged = [...storeIncidents];
        for (const item of prev) {
          if (!merged.some((m) => m.incident_id === item.incident_id)) {
            merged.push(item);
          }
        }
        return merged;
      });
    }
  }, [storeIncidents]);

  useEffect(() => {
    if (Object.keys(storeReputation).length > 0) {
      setReputation(storeReputation);
    }
  }, [storeReputation]);

  // Initial load of incidents, quarantine, and reputation
  const fetchTrustData = useCallback(async () => {
    setIsLoading(true);
    try {
      const [incRes, quatRes, repRes] = await Promise.all([
        api.trust.incidents(),
        api.trust.quarantine(),
        api.trust.reputation(),
      ]);
      setIncidents(incRes);
      setQuarantine(quatRes);
      setReputation(repRes);
      if (incRes.length > 0) {
        setSelectedId((prev) => prev ?? incRes[0].incident_id);
      }
    } catch (err) {
      // Keep store fallback
      console.warn("Failed fetching trust data:", err);
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchTrustData();
  }, [fetchTrustData]);

  // Set default selected if none selected
  useEffect(() => {
    if (!selectedId && incidents.length > 0) {
      setSelectedId(incidents[0].incident_id);
    }
  }, [incidents, selectedId]);

  const selectedIncident = incidents.find((i) => i.incident_id === selectedId) ?? null;

  // Handler for Inject Fake Crisis
  const handleInjectFake = async () => {
    setIsInjecting(true);
    try {
      await api.events.injectFake("false_capacity_drop");
      addToast("info", "Injected simulated false capacity drop crisis event.");
      // Refresh trust lists after short delay
      setTimeout(fetchTrustData, 500);
    } catch (err) {
      addToast("error", errorMessage(err));
    } finally {
      setIsInjecting(false);
    }
  };

  const handleIncidentResolved = (updated: TrustIncident) => {
    setIncidents((prev) =>
      prev.map((i) => (i.incident_id === updated.incident_id ? updated : i))
    );
    addToast(
      "success",
      `Incident ${updated.incident_id.slice(0, 8)} resolved: ${String(updated.resolution?.action ?? "confirmed")}`
    );
  };

  return (
    <section id="crisis-trust-engine" className="scroll-mt-16 space-y-4">
      {/* Header and Inject Fake Action */}
      <div className="flex flex-wrap items-center justify-between pb-1 border-b border-border gap-3">
        <div>
          <h2 className="text-11 uppercase font-semibold tracking-wider text-muted">
            Verification
          </h2>
          <h1 className="text-20 font-semibold text-text">Crisis Trust Engine</h1>
        </div>

        <div className="flex items-center gap-2">
          <button
            onClick={fetchTrustData}
            disabled={isLoading}
            title="Refresh trust telemetry"
            className="p-1.5 rounded border border-border bg-surface hover:bg-surface-2 text-muted hover:text-text transition-colors cursor-pointer disabled:opacity-50"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${isLoading ? "animate-spin" : ""}`} />
          </button>

          {/* Outlined red Inject Fake Crisis button per spec */}
          <button
            onClick={handleInjectFake}
            disabled={isInjecting}
            className="inline-flex items-center gap-2 px-3 py-1.5 rounded bg-surface hover:bg-surface-2 text-accent border border-accent/60 hover:border-accent text-12 font-medium transition-colors cursor-pointer disabled:opacity-50"
          >
            <ShieldAlert className="w-4 h-4 text-accent" />
            <span>{isInjecting ? "Injecting Crisis…" : "Inject Fake Crisis"}</span>
          </button>
        </div>
      </div>

      {/* Main Trust Workspace: Incident List + Incident Detail */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-4">
        {/* Incidents List (5 cols) */}
        <div className="lg:col-span-5 p-4 bg-surface rounded-panel border border-border flex flex-col justify-between">
          <div>
            <div className="flex items-center justify-between mb-1">
              <h3 className="text-13 font-medium text-text">Anomalies & Trust Incidents</h3>
              <span className="text-11 text-muted tabular-nums">
                {incidents.length} recorded
              </span>
            </div>
            <p className="text-11 text-muted mb-3">
              Claims audited against multi-sensor consensus and digital twin telemetry.
            </p>
          </div>

          {incidents.length === 0 ? (
            <div className="py-12 flex items-center justify-center border border-dashed border-border rounded">
              <span className="text-12 text-muted">No trust incidents recorded.</span>
            </div>
          ) : (
            <div className="space-y-2 max-h-[380px] overflow-y-auto pr-1">
              {incidents.map((inc) => {
                const isSelected = inc.incident_id === selectedId;
                const senderDef = AGENTS[inc.sender as AgentId];
                return (
                  <div
                    key={inc.incident_id}
                    onClick={() => setSelectedId(inc.incident_id)}
                    className={`p-3 rounded border text-left cursor-pointer transition-all duration-150 select-none ${
                      isSelected
                        ? "bg-surface-2 border-accent text-text"
                        : "bg-surface-2/60 border-border hover:border-muted/40 text-text"
                    }`}
                  >
                    <div className="flex items-start justify-between gap-2">
                      <div className="min-w-0">
                        <div className="flex items-center gap-1.5">
                          <span className="text-12 font-semibold text-text truncate">
                            {senderDef?.name ?? inc.sender}
                          </span>
                          <span className="text-11 text-muted">·</span>
                          <span className="text-11 text-muted uppercase tracking-wider">
                            {inc.kind.replace(/_/g, " ")}
                          </span>
                        </div>
                        <p className="text-12 text-muted truncate mt-0.5">
                          {inc.summary || "Inconsistent claim identified"}
                        </p>
                      </div>

                      <span
                        className={`text-11 px-1.5 py-0.5 rounded border shrink-0 font-medium ${
                          inc.resolved
                            ? "border-ok/30 bg-ok/10 text-ok"
                            : inc.escalated
                            ? "border-accent/40 bg-accent-dim text-accent"
                            : "border-border bg-surface text-muted"
                        }`}
                      >
                        {inc.resolved ? "Resolved" : inc.escalated ? "Escalated" : "Flagged"}
                      </span>
                    </div>

                    <div className="flex items-center justify-between text-11 text-muted mt-2 pt-2 border-t border-border/50 tabular-nums">
                      <span>Sim: {inc.sim_time}</span>
                      <span>Trust: {(inc.trust_score * 100).toFixed(0)}%</span>
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </div>

        {/* Incident Detail (7 cols) */}
        <div className="lg:col-span-7">
          <IncidentDetail incident={selectedIncident} onResolved={handleIncidentResolved} />
        </div>
      </div>

      {/* Secondary Trust Telemetry: Reputation & Quarantine Tables */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <ReputationList reputation={reputation} />
        <QuarantineTable
          quarantine={quarantine}
          onSelectIncident={(id) => {
            setSelectedId(id);
            const el = document.getElementById("crisis-trust-engine");
            if (el) el.scrollIntoView({ behavior: "smooth", block: "start" });
          }}
        />
      </div>

      <Toast toasts={toasts} onDismiss={dismissToast} />
    </section>
  );
}
