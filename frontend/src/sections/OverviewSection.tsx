import { useState } from "react";
import {
  Play,
  Pause,
  RotateCcw,
  StepForward,
  AlertTriangle,
  Check,
} from "lucide-react";
import { MetricTile } from "@/components/MetricTile";
import { FairnessSlider } from "@/components/FairnessSlider";
import { CommanderSitRep } from "@/components/CommanderSitRep";
import { CommanderCopilot } from "@/components/CommanderCopilot";
import { Toast, type ToastMessage } from "@/components/Toast";
import { formatMw, formatPct } from "@/lib/format";
import { api } from "@/services/api";
import { errorMessage } from "@/lib/errors";
import { useSimStore } from "@/store/useSimStore";

export function OverviewSection() {
  const snapshot = useSimStore((s) => s.snapshot);
  const alerts = useSimStore((s) => s.alerts);
  const acknowledgeAlertInStore = useSimStore((s) => s.acknowledgeAlert);

  const [toasts, setToasts] = useState<ToastMessage[]>([]);
  const [isActing, setIsActing] = useState<string | null>(null);
  const [isResetConfirmOpen, setIsResetConfirmOpen] = useState(false);

  const addToast = (type: "success" | "error" | "info", message: string) => {
    const id = `${Date.now()}-${Math.random().toString(36).substring(2, 7)}`;
    setToasts((prev) => [...prev, { id, type, message }]);
  };

  const dismissToast = (id: string) => {
    setToasts((prev) => prev.filter((t) => t.id !== id));
  };

  const status = snapshot?.status ?? "idle";
  const isRunning = status === "running";
  const isPaused = status === "paused";

  // Real metric values
  const supplyMw = snapshot?.supply?.total_available_mw ?? 0;
  const demandMw = snapshot?.demand_total_mw ?? 0;
  const deficitMw = snapshot?.deficit_mw ?? 0;
  const totalAgents = snapshot?.agents?.length ?? 6;
  const onlineAgents =
    snapshot?.agents?.filter((a) => a.status === "online").length ??
    totalAgents;
  const consumerCount =
    snapshot?.agents?.filter((a) => a.kind === "consumer").length ?? 4;
  const activeAlertsList = alerts.filter((a) => a.active);
  const round =
    snapshot?.last_negotiation?.rounds ??
    (snapshot?.negotiation_count ? snapshot.negotiation_count : 0);
  const healthPct = snapshot?.infrastructure_health ?? 1.0;

  // Commander Actions
  const handleStart = async () => {
    setIsActing("start");
    try {
      await api.simulation.start();
      addToast("success", "Simulation loop started.");
    } catch (err) {
      addToast("error", errorMessage(err));
    } finally {
      setIsActing(null);
    }
  };

  const handlePause = async () => {
    setIsActing("pause");
    try {
      await api.simulation.pause();
      addToast("info", "Simulation paused by commander.");
    } catch (err) {
      addToast("error", errorMessage(err));
    } finally {
      setIsActing(null);
    }
  };

  const handleResume = async () => {
    setIsActing("resume");
    try {
      await api.simulation.resume();
      addToast("success", "Simulation resumed.");
    } catch (err) {
      addToast("error", errorMessage(err));
    } finally {
      setIsActing(null);
    }
  };

  const handleAdvanceStep = async () => {
    setIsActing("step");
    try {
      await api.simulation.step(1);
      addToast("success", "Advanced simulation by 1 tick (15 min).");
    } catch (err) {
      addToast("error", errorMessage(err));
    } finally {
      setIsActing(null);
    }
  };

  const handleReset = async () => {
    setIsActing("reset");
    try {
      await api.simulation.reset({ scenario: "grid_shortage" });
      addToast("info", "Simulation reset to initial state.");
      setIsResetConfirmOpen(false);
    } catch (err) {
      addToast("error", errorMessage(err));
    } finally {
      setIsActing(null);
    }
  };

  const handleAcknowledgeAlert = async (alertId: string) => {
    try {
      await api.commander.acknowledgeAlert(alertId);
      acknowledgeAlertInStore(alertId);
      addToast("success", "Alert acknowledged.");
    } catch (err) {
      addToast("error", errorMessage(err));
    }
  };

  const handleFairnessCommit = async (value: number) => {
    try {
      await api.simulation.fairness(value);
      addToast("success", `Fairness policy adjusted to ${value.toFixed(2)}.`);
    } catch (err) {
      addToast("error", errorMessage(err));
    }
  };

  return (
    <section id="overview" className="scroll-mt-16 space-y-4">
      {/* Section Header */}
      <div className="flex items-center justify-between pb-1 border-b border-border">
        <div>
          <h2 className="text-11 uppercase font-semibold tracking-wider text-muted">
            Overview
          </h2>
          <h1 className="text-20 font-semibold text-text">System Metrics & Controls</h1>
        </div>
        <div className="flex items-center gap-2">
          {isRunning ? (
            <button
              type="button"
              onClick={handlePause}
              disabled={isActing !== null}
              className="px-3 py-1.5 rounded-control text-12 font-medium bg-surface-2 border border-border text-text hover:bg-border transition-colors flex items-center gap-1.5 cursor-pointer disabled:opacity-50"
            >
              <Pause size={14} strokeWidth={1.5} />
              <span>Pause</span>
            </button>
          ) : isPaused ? (
            <button
              type="button"
              onClick={handleResume}
              disabled={isActing !== null}
              className="px-3 py-1.5 rounded-control text-12 font-medium bg-accent text-white hover:bg-accent/90 transition-colors flex items-center gap-1.5 cursor-pointer disabled:opacity-50"
            >
              <Play size={14} strokeWidth={1.5} />
              <span>Resume</span>
            </button>
          ) : (
            <button
              type="button"
              onClick={handleStart}
              disabled={isActing !== null}
              className="px-3 py-1.5 rounded-control text-12 font-medium bg-accent text-white hover:bg-accent/90 transition-colors flex items-center gap-1.5 cursor-pointer disabled:opacity-50"
            >
              <Play size={14} strokeWidth={1.5} />
              <span>Start</span>
            </button>
          )}

          <button
            type="button"
            onClick={handleAdvanceStep}
            disabled={isRunning || isActing !== null}
            title={isRunning ? "Pause the simulation to advance manually" : "Advance 1 tick"}
            className="px-3 py-1.5 rounded-control text-12 font-medium bg-surface-2 border border-border text-text hover:bg-border transition-colors flex items-center gap-1.5 cursor-pointer disabled:opacity-40 disabled:cursor-not-allowed"
          >
            <StepForward size={14} strokeWidth={1.5} />
            <span>Advance (Step)</span>
          </button>

          <button
            type="button"
            onClick={() => setIsResetConfirmOpen(true)}
            disabled={isActing !== null}
            className="px-3 py-1.5 rounded-control text-12 font-medium bg-surface-2 border border-border text-muted hover:text-text hover:bg-border transition-colors flex items-center gap-1.5 cursor-pointer disabled:opacity-50"
          >
            <RotateCcw size={14} strokeWidth={1.5} />
            <span>Reset</span>
          </button>
        </div>
      </div>

      {/* Confirmation modal for reset */}
      {isResetConfirmOpen && (
        <div className="p-3 bg-surface border border-accent rounded-panel flex items-center justify-between">
          <span className="text-12 text-text">
            Reset simulation to seed and scenario defaults? Current messages and session progress will clear.
          </span>
          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={() => setIsResetConfirmOpen(false)}
              className="px-2.5 py-1 text-12 text-muted hover:text-text rounded-control border border-border"
            >
              Cancel
            </button>
            <button
              type="button"
              onClick={handleReset}
              className="px-2.5 py-1 text-12 bg-accent text-white rounded-control font-medium hover:bg-accent/90"
            >
              Confirm Reset
            </button>
          </div>
        </div>
      )}

      {/* Commander Intelligence Suite */}
      <CommanderSitRep />
      <CommanderCopilot />

      {/* Metric Tiles: 7 key metrics */}
      <div className="grid grid-cols-2 sm:grid-cols-4 lg:grid-cols-7 gap-3">
        <MetricTile
          label="Available Supply"
          value={formatMw(supplyMw)}
          subtext="Grid + Battery"
        />
        <MetricTile
          label="Total Demand"
          value={formatMw(demandMw)}
          subtext={`${consumerCount} consumer utilities`}
        />
        <MetricTile
          label="Deficit"
          value={formatMw(deficitMw)}
          isAccent={deficitMw > 0.05}
          subtext={deficitMw > 0.05 ? "Unmet power demand" : "Nominal"}
        />
        <MetricTile
          label="Active Agents"
          value={`${onlineAgents} / ${totalAgents}`}
          subtext="Online agents"
        />
        <MetricTile
          label="Active Alerts"
          value={activeAlertsList.length}
          isAccent={activeAlertsList.length > 0}
          subtext="Unacknowledged"
        />
        <MetricTile
          label="Round"
          value={round}
          subtext="Negotiation cycle"
        />
        <MetricTile
          label="Infra Health"
          value={formatPct(healthPct)}
          subtext="Grid integrity"
        />
      </div>

      {/* Active Alerts List */}
      <div className="p-4 bg-surface rounded-panel border border-border space-y-3">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <AlertTriangle size={16} strokeWidth={1.5} className="text-accent" />
            <span className="text-11 uppercase font-semibold tracking-wider text-muted">
              Active Alerts
            </span>
          </div>
          <span className="text-11 text-muted tabular-nums">
            {activeAlertsList.length} active
          </span>
        </div>

        {activeAlertsList.length === 0 ? (
          <div className="text-12 text-muted py-1">
            No active alerts recorded.
          </div>
        ) : (
          <div className="divide-y divide-border">
            {activeAlertsList.map((alert) => (
              <div
                key={alert.id}
                className="py-2.5 flex items-start justify-between gap-4 first:pt-0 last:pb-0"
              >
                <div className="space-y-0.5">
                  <div className="flex items-center gap-2">
                    <span className="w-1.5 h-1.5 rounded-full bg-accent shrink-0" />
                    <span className="text-13 font-medium text-text">{alert.title}</span>
                    <span className="text-11 px-1.5 py-0.2 rounded-control bg-surface-2 border border-border text-muted uppercase">
                      {alert.severity}
                    </span>
                  </div>
                  <p className="text-12 text-muted pl-3.5">{alert.detail}</p>
                </div>

                <button
                  type="button"
                  onClick={() => handleAcknowledgeAlert(alert.id)}
                  className="shrink-0 px-2.5 py-1 text-12 text-muted hover:text-text rounded-control border border-border hover:bg-surface-2 flex items-center gap-1 transition-colors cursor-pointer"
                >
                  <Check size={12} strokeWidth={1.5} />
                  <span>Acknowledge</span>
                </button>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Fairness Slider */}
      <FairnessSlider
        initialValue={snapshot?.fairness ?? 0.5}
        onCommit={handleFairnessCommit}
        disabled={false}
      />

      <Toast toasts={toasts} onDismiss={dismissToast} />
    </section>
  );
}
