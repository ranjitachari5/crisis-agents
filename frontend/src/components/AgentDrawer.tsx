import { useEffect, useState } from "react";
import { X, ShieldAlert, ShieldCheck } from "lucide-react";
import { isConsumerId, AGENTS } from "@/lib/agents";
import { formatMw, formatPct } from "@/lib/format";
import { api } from "@/services/api";
import { errorMessage } from "@/lib/errors";
import type { AgentDetail, AgentId, ConsumerId } from "@/types/api";

interface Props {
  agentId: AgentId | null;
  isOpen: boolean;
  onClose: () => void;
  onStatusChange?: () => void;
}

export function AgentDrawer({
  agentId,
  isOpen,
  onClose,
  onStatusChange,
}: Props) {
  const [detail, setDetail] = useState<AgentDetail | null>(null);
  const [loading, setLoading] = useState(false);
  const [acting, setActing] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);

  useEffect(() => {
    if (!isOpen || !agentId) {
      setDetail(null);
      return;
    }

    let isCurrent = true;
    setLoading(true);
    setActionError(null);

    api.agents
      .get(agentId)
      .then((res) => {
        if (isCurrent) setDetail(res);
      })
      .catch((err) => {
        if (isCurrent) setActionError(errorMessage(err));
      })
      .finally(() => {
        if (isCurrent) setLoading(false);
      });

    return () => {
      isCurrent = false;
    };
  }, [agentId, isOpen]);

  // Handle ESC key
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape" && isOpen) {
        onClose();
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [isOpen, onClose]);

  if (!isOpen || !agentId) return null;

  const meta = AGENTS[agentId];
  const isConsumer = isConsumerId(agentId);
  const isIsolated = detail?.status === "isolated";

  const handleIsolate = async () => {
    if (!isConsumer) return;
    setActing(true);
    setActionError(null);
    try {
      await api.commander.isolate(agentId as ConsumerId, "Commander requested security isolation");
      const updated = await api.agents.get(agentId);
      setDetail(updated);
      onStatusChange?.();
    } catch (err) {
      setActionError(errorMessage(err));
    } finally {
      setActing(false);
    }
  };

  const handleRestore = async () => {
    if (!isConsumer) return;
    setActing(true);
    setActionError(null);
    try {
      await api.commander.restore(agentId as ConsumerId);
      const updated = await api.agents.get(agentId);
      setDetail(updated);
      onStatusChange?.();
    } catch (err) {
      setActionError(errorMessage(err));
    } finally {
      setActing(false);
    }
  };

  return (
    <div className="fixed inset-0 z-40 flex justify-end">
      {/* Backdrop */}
      <div
        className="fixed inset-0 bg-black/60 transition-opacity"
        onClick={onClose}
        aria-hidden="true"
      />

      {/* Slide-out Drawer */}
      <aside
        className="relative w-full max-w-md bg-surface border-l border-border h-full flex flex-col z-50 overflow-hidden shadow-2xl"
        role="dialog"
        aria-modal="true"
        aria-label={`Agent details for ${meta?.name ?? agentId}`}
      >
        {/* Header */}
        <div className="p-4 border-b border-border flex items-center justify-between">
          <div>
            <div className="flex items-center gap-2">
              <h2 className="text-16 font-semibold text-text">
                {meta?.name ?? agentId}
              </h2>
              <span className="text-11 uppercase px-1.5 py-0.5 rounded-control bg-surface-2 border border-border text-muted">
                {detail?.status ?? "—"}
              </span>
            </div>
            <p className="text-12 text-muted mt-0.5">{meta?.role}</p>
          </div>

          <button
            type="button"
            onClick={onClose}
            className="p-1.5 text-muted hover:text-text rounded-control hover:bg-surface-2 cursor-pointer"
            aria-label="Close drawer"
          >
            <X size={16} strokeWidth={1.5} />
          </button>
        </div>

        {/* Content Area */}
        <div className="flex-1 overflow-y-auto p-4 space-y-6">
          {actionError && (
            <div className="p-3 bg-surface-2 border border-accent rounded-control text-12 text-accent">
              {actionError}
            </div>
          )}

          {loading ? (
            <div className="text-12 text-muted py-8 text-center">
              Fetching agent telemetry…
            </div>
          ) : detail ? (
            <>
              {/* Telemetry Section */}
              <div className="space-y-3">
                <span className="text-11 uppercase font-semibold text-muted tracking-wider">
                  Live Telemetry
                </span>

                {detail.kind === "consumer" && (
                  <div className="grid grid-cols-2 gap-2 text-12">
                    <div className="p-2.5 bg-surface-2 rounded-control border border-border">
                      <span className="text-11 text-muted block">Demand</span>
                      <span className="text-14 font-semibold tabular-nums text-text">
                        {formatMw(detail.demand_mw)}
                      </span>
                    </div>
                    <div className="p-2.5 bg-surface-2 rounded-control border border-border">
                      <span className="text-11 text-muted block">Safe Minimum</span>
                      <span className="text-14 font-semibold tabular-nums text-text">
                        {formatMw(detail.min_safe_mw)}
                      </span>
                    </div>
                    <div className="p-2.5 bg-surface-2 rounded-control border border-border">
                      <span className="text-11 text-muted block">Allocated</span>
                      <span className="text-14 font-semibold tabular-nums text-text">
                        {formatMw(detail.allocation_mw)}
                      </span>
                    </div>
                    <div className="p-2.5 bg-surface-2 rounded-control border border-border">
                      <span className="text-11 text-muted block">Service Level</span>
                      <span className="text-14 font-semibold tabular-nums text-text">
                        {formatPct(detail.service_level)}
                      </span>
                    </div>
                  </div>
                )}

                {detail.kind === "storage" && (
                  <div className="grid grid-cols-2 gap-2 text-12">
                    <div className="p-2.5 bg-surface-2 rounded-control border border-border">
                      <span className="text-11 text-muted block">State of Charge</span>
                      <span className="text-14 font-semibold tabular-nums text-text">
                        {formatPct(detail.soc)}
                      </span>
                    </div>
                    <div className="p-2.5 bg-surface-2 rounded-control border border-border">
                      <span className="text-11 text-muted block">Current Discharge</span>
                      <span className="text-14 font-semibold tabular-nums text-text">
                        {formatMw(detail.discharge_mw)}
                      </span>
                    </div>
                    <div className="p-2.5 bg-surface-2 rounded-control border border-border">
                      <span className="text-11 text-muted block">Usable Energy</span>
                      <span className="text-14 font-semibold tabular-nums text-text">
                        {detail.usable_energy_mwh.toFixed(1)} MWh
                      </span>
                    </div>
                    <div className="p-2.5 bg-surface-2 rounded-control border border-border">
                      <span className="text-11 text-muted block">Max Capability</span>
                      <span className="text-14 font-semibold tabular-nums text-text">
                        {formatMw(detail.max_discharge_mw)}
                      </span>
                    </div>
                  </div>
                )}

                {detail.kind === "supply" && (
                  <div className="grid grid-cols-2 gap-2 text-12">
                    <div className="p-2.5 bg-surface-2 rounded-control border border-border">
                      <span className="text-11 text-muted block">Nominal Supply</span>
                      <span className="text-14 font-semibold tabular-nums text-text">
                        {formatMw(detail.nominal_mw)}
                      </span>
                    </div>
                    <div className="p-2.5 bg-surface-2 rounded-control border border-border">
                      <span className="text-11 text-muted block">Verified Supply</span>
                      <span className="text-14 font-semibold tabular-nums text-text">
                        {detail.verified_supply_mw !== null ? formatMw(detail.verified_supply_mw) : "—"}
                      </span>
                    </div>
                    <div className="p-2.5 bg-surface-2 rounded-control border border-border col-span-2">
                      <span className="text-11 text-muted block">Sensor Consensus</span>
                      <span className="text-13 font-medium uppercase text-text">
                        {detail.sensor_status}
                      </span>
                    </div>
                  </div>
                )}
              </div>

              {/* Commander Actions (Isolate / Restore) */}
              <div className="space-y-2 pt-2 border-t border-border">
                <span className="text-11 uppercase font-semibold text-muted tracking-wider">
                  Commander Control
                </span>

                {isConsumer ? (
                  <div className="flex items-center gap-2">
                    {isIsolated ? (
                      <button
                        type="button"
                        onClick={handleRestore}
                        disabled={acting}
                        className="w-full py-2 px-3 rounded-control text-12 font-medium bg-ok text-black hover:bg-ok/90 flex items-center justify-center gap-1.5 cursor-pointer disabled:opacity-50"
                      >
                        <ShieldCheck size={14} strokeWidth={1.5} />
                        <span>Restore Agent to Grid</span>
                      </button>
                    ) : (
                      <button
                        type="button"
                        onClick={handleIsolate}
                        disabled={acting}
                        className="w-full py-2 px-3 rounded-control text-12 font-medium bg-accent text-white hover:bg-accent/90 flex items-center justify-center gap-1.5 cursor-pointer disabled:opacity-50"
                      >
                        <ShieldAlert size={14} strokeWidth={1.5} />
                        <span>Isolate Agent from Market</span>
                      </button>
                    )}
                  </div>
                ) : (
                  <div className="text-12 text-muted py-1 select-none">
                    Not isolable
                  </div>
                )}
              </div>

              {/* Recent Messages */}
              <div className="space-y-3 pt-2 border-t border-border">
                <span className="text-11 uppercase font-semibold text-muted tracking-wider">
                  Recent Messages ({detail.recent_messages?.length ?? 0})
                </span>

                {!detail.recent_messages || detail.recent_messages.length === 0 ? (
                  <div className="text-12 text-muted">No messages on record for this agent.</div>
                ) : (
                  <div className="space-y-2">
                    {detail.recent_messages.slice(-10).map((msg) => (
                      <div
                        key={msg.message_id}
                        className="p-2.5 bg-surface-2 rounded-control border border-border text-12 space-y-1"
                      >
                        <div className="flex items-center justify-between text-11 text-muted">
                          <span className="uppercase font-medium text-text">
                            {msg.message_type.replace(/_/g, " ")}
                          </span>
                          <span className="tabular-nums">
                            {msg.quantity !== null ? `${msg.quantity} ${msg.unit ?? "MW"}` : ""}
                          </span>
                        </div>
                        <p className="text-muted leading-relaxed">
                          {msg.text || msg.reason || "Telemetry update transmitted."}
                        </p>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </>
          ) : (
            <div className="text-12 text-muted py-8 text-center">
              Failed to load agent profile.
            </div>
          )}
        </div>
      </aside>
    </div>
  );
}

