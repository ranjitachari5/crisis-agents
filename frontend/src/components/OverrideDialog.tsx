import { useState, useId, useMemo } from "react";
import { X, ShieldAlert, CheckCircle2, AlertTriangle, AlertOctagon, KeyRound } from "lucide-react";
import { AGENTS, CONSUMER_IDS, getAgentDef } from "@/lib/agents";
import { formatMw } from "@/lib/format";
import { api } from "@/services/api";
import { errorMessage } from "@/lib/errors";
import { useSimStore } from "@/store/useSimStore";
import { useAuthStore } from "@/store/useAuthStore";
import type { ConsumerId, ValidationResult } from "@/types/api";

interface Props {
  isOpen: boolean;
  onClose: () => void;
  onSuccess: (message: string) => void;
}

export function OverrideDialog({ isOpen, onClose, onSuccess }: Props) {
  const snapshot = useSimStore((s) => s.snapshot);
  const activeAgreement = snapshot?.allocation;
  const verifiedSupply =
    snapshot?.supply?.grid_verified_mw ?? snapshot?.supply?.total_available_mw ?? 200;

  const consumerIds = useMemo(() => {
    const list: ConsumerId[] = [...CONSUMER_IDS];
    const set = new Set(list as string[]);
    if (snapshot?.agents) {
      for (const a of snapshot.agents) {
        if (a.kind === "consumer" && !set.has(a.agent_id)) {
          list.push(a.agent_id as ConsumerId);
          set.add(a.agent_id);
        }
      }
    }
    return list;
  }, [snapshot?.agents]);

  // Initialize allocation values from current allocation or min safe
  const getInitialAllocations = (): Record<ConsumerId, number> => {
    const initial: Partial<Record<ConsumerId, number>> = {};
    for (const id of consumerIds) {
      if (activeAgreement?.allocation?.[id] != null) {
        initial[id] = activeAgreement.allocation[id];
      } else {
        const agent = snapshot?.agents?.find((a) => a.agent_id === id);
        initial[id] = (agent && "min_safe_mw" in agent ? agent.min_safe_mw : 50) ?? 50;
      }
    }
    return initial as Record<ConsumerId, number>;
  };

  const [allocations, setAllocations] = useState<Record<ConsumerId, number>>(getInitialAllocations);
  const [reason, setReason] = useState<string>("Emergency manual rebalancing by Commander");
  // Auth token from centralized store — sent via Authorization header, not in the request body
  const isAuthenticated = useAuthStore((s) => s.isAuthenticated);

  const [isValidating, setIsValidating] = useState(false);
  const [isCommitting, setIsCommitting] = useState(false);
  const [validated, setValidated] = useState(false);
  const [validationResult, setValidationResult] = useState<ValidationResult | null>(null);
  const [apiError, setApiError] = useState<string | null>(null);

  const titleId = useId();

  if (!isOpen) return null;

  const totalAllocated = Object.values(allocations).reduce((sum, val) => sum + (Number(val) || 0), 0);

  const handleAllocationChange = (id: ConsumerId, value: number) => {
    setAllocations((prev) => ({ ...prev, [id]: value }));
    // Invalidate prior validation since numbers changed
    setValidated(false);
    setValidationResult(null);
    setApiError(null);
  };

  // Step 1: Validate proposed numbers
  const handleValidate = async () => {
    setIsValidating(true);
    setApiError(null);
    try {
      const res = await api.allocations.validate({ allocation: allocations });
      setValidationResult(res);
      setValidated(res.valid);
    } catch (err) {
      setApiError(errorMessage(err));
      setValidated(false);
    } finally {
      setIsValidating(false);
    }
  };

  // Step 2: Commit override — token is sent via the Authorization header automatically
  const handleCommit = async () => {
    if (!validated) return;
    if (!isAuthenticated) {
      setApiError("Commander authorization token is required — set it in the top bar");
      return;
    }
    if (reason.trim().length < 5) {
      setApiError("Override reason must be at least 5 characters");
      return;
    }

    setIsCommitting(true);
    setApiError(null);
    try {
      await api.commander.override(allocations, reason.trim());
      onSuccess("Allocation override committed successfully by Commander.");
      onClose();
    } catch (err) {
      // Inline API error on invalid token, keep form intact
      setApiError(errorMessage(err));
    } finally {
      setIsCommitting(false);
    }
  };

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-labelledby={titleId}
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4"
    >
      <div className="w-full max-w-xl bg-surface border border-border rounded-panel flex flex-col max-h-[90vh] overflow-hidden">
        {/* Header */}
        <div className="px-5 py-3.5 border-b border-border flex items-center justify-between bg-surface-2/60">
          <div className="flex items-center gap-2">
            <ShieldAlert className="w-4 h-4 text-accent" />
            <h2 id={titleId} className="text-14 font-semibold text-text">
              Commander Allocation Override
            </h2>
          </div>
          <button
            onClick={onClose}
            aria-label="Close dialog"
            className="p-1 rounded text-muted hover:text-text hover:bg-surface-2 transition-colors cursor-pointer"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        {/* Content Body */}
        <div className="p-5 overflow-y-auto space-y-4 text-13">
          <p className="text-12 text-muted leading-relaxed">
            Manual directive overrides autonomous multi-agent negotiation. Proposed allocations
            must be validated for system safety prior to committing.
          </p>

          {/* Allocation Inputs */}
          <div className="space-y-2.5">
            <div className="flex items-center justify-between text-11 uppercase font-semibold text-muted tracking-wider">
              <span>Consumer Utility</span>
              <span>Allocated (MW)</span>
            </div>

            {consumerIds.map((agentId) => {
              const agentView = snapshot?.agents?.find((a) => a.agent_id === agentId);
              const def = getAgentDef(agentId, agentView?.display_name);
              const demand = agentView && "demand_mw" in agentView ? agentView.demand_mw : 0;
              const minSafe = agentView && "min_safe_mw" in agentView ? agentView.min_safe_mw : 0;
              const value = allocations[agentId] ?? 0;

              return (
                <div
                  key={agentId}
                  className="p-3 rounded bg-surface-2 border border-border flex items-center justify-between gap-4"
                >
                  <div className="min-w-0">
                    <span className="text-13 font-medium text-text block truncate">
                      {def?.name ?? agentId}
                    </span>
                    <span className="text-11 text-muted tabular-nums">
                      Demand: {formatMw(demand)} · Min safe: {formatMw(minSafe)}
                    </span>
                  </div>

                  <div className="flex items-center gap-1.5 shrink-0">
                    <input
                      type="number"
                      step="1"
                      min="0"
                      max="500"
                      value={value}
                      onChange={(e) =>
                        handleAllocationChange(agentId, Math.max(0, parseFloat(e.target.value) || 0))
                      }
                      className="w-24 px-2.5 py-1 text-right text-13 tabular-nums font-medium bg-surface rounded border border-border text-text focus:outline-none focus:border-accent"
                    />
                    <span className="text-11 text-muted">MW</span>
                  </div>
                </div>
              );
            })}

            {/* Total vs Verified Supply */}
            <div className="flex items-center justify-between pt-1 px-1 text-12 text-muted tabular-nums">
              <span>
                Total Proposed:{" "}
                <strong className="text-text font-semibold">{formatMw(totalAllocated)}</strong>
              </span>
              <span>
                Verified Supply:{" "}
                <strong className="text-text font-semibold">{formatMw(verifiedSupply)}</strong>
              </span>
            </div>
          </div>

          {/* Step 1: Validation Results */}
          {validationResult && (
            <div
              className={`p-3 rounded border text-12 ${
                validationResult.valid
                  ? validationResult.degradation_mode
                    ? "bg-accent-dim/30 border-accent/40 text-text"
                    : "bg-ok/10 border-ok/30 text-text"
                  : "bg-accent-dim border-accent/50 text-text"
              }`}
            >
              <div className="flex items-center gap-2 font-medium mb-1.5">
                {validationResult.valid ? (
                  validationResult.degradation_mode ? (
                    <AlertTriangle className="w-4 h-4 text-accent shrink-0" />
                  ) : (
                    <CheckCircle2 className="w-4 h-4 text-ok shrink-0" />
                  )
                ) : (
                  <AlertOctagon className="w-4 h-4 text-accent shrink-0" />
                )}
                <span>
                  {validationResult.valid
                    ? validationResult.degradation_mode
                      ? "Validation Passed — Degradation Mode Active"
                      : "Validation Passed — Safe & Verified"
                    : "Validation Failed — Violations Found"}
                </span>
              </div>

              {/* Violations List */}
              {validationResult.violations?.length > 0 && (
                <ul className="space-y-1 mt-2 text-11 text-accent">
                  {validationResult.violations.map((v, i) => (
                    <li key={i} className="flex items-start gap-1.5">
                      <span>•</span>
                      <span>
                        <strong>{v.code}:</strong> {v.detail}
                      </span>
                    </li>
                  ))}
                </ul>
              )}

              {/* Checks Summary */}
              {validationResult.valid && (
                <div className="text-11 text-muted mt-1 space-y-0.5">
                  <div>Battery discharge required: {formatMw(validationResult.battery_discharge)}</div>
                  {Object.entries(validationResult.unavoidable_shortages || {}).length > 0 && (
                    <div className="text-accent">
                      Unavoidable shortages:{" "}
                      {Object.entries(validationResult.unavoidable_shortages)
                        .map(([k, v]) => `${AGENTS[k as ConsumerId]?.name ?? k}: ${formatMw(v)}`)
                        .join(", ")}
                    </div>
                  )}
                </div>
              )}
            </div>
          )}

          {/* Reason Field */}
          <div>
            <label className="text-11 uppercase font-semibold text-muted tracking-wider block mb-1">
              Directive Reason
            </label>
            <input
              type="text"
              value={reason}
              onChange={(e) => setReason(e.target.value)}
              placeholder="e.g. Critical ICU life-safety priority override"
              className="w-full px-3 py-1.5 text-13 bg-surface-2 rounded border border-border text-text placeholder:text-muted/60 focus:outline-none focus:border-accent"
            />
          </div>

          {/* Commander Auth Status */}
          <div>
            <div className="flex items-center justify-between mb-1">
              <label className="text-11 uppercase font-semibold text-muted tracking-wider block">
                Commander Authorization
              </label>
              <span className="text-11 text-muted">Via bearer token header</span>
            </div>
            <div className={`p-2.5 rounded border text-12 flex items-center gap-2 ${
              isAuthenticated
                ? "bg-ok/10 border-ok/30 text-text"
                : "bg-accent-dim border-accent/40 text-accent"
            }`}>
              <KeyRound className="w-4 h-4 shrink-0" />
              <span>
                {isAuthenticated
                  ? "Token configured — authorization will be sent via HTTP header"
                  : "No token set — enter your COMMANDER_AUTH_TOKEN in the top bar first"}
              </span>
            </div>
          </div>

          {/* Inline API Error */}
          {apiError && (
            <div className="p-2.5 rounded bg-accent-dim border border-accent/40 text-12 text-accent flex items-start gap-2">
              <AlertTriangle className="w-4 h-4 shrink-0 mt-0.5" />
              <span>{apiError}</span>
            </div>
          )}
        </div>

        {/* Action Footer */}
        <div className="px-5 py-3 border-t border-border bg-surface-2/60 flex items-center justify-between gap-3">
          <button
            type="button"
            onClick={onClose}
            className="px-3 py-1.5 rounded text-muted hover:text-text hover:bg-surface-2 text-12 transition-colors cursor-pointer"
          >
            Cancel
          </button>

          <div className="flex items-center gap-2">
            {/* Step 1: Validate */}
            <button
              type="button"
              onClick={handleValidate}
              disabled={isValidating}
              className="px-3 py-1.5 rounded bg-surface-2 hover:bg-surface-2/80 text-text border border-border text-12 font-medium transition-colors cursor-pointer disabled:opacity-50"
            >
              {isValidating ? "Validating…" : "Step 1: Validate"}
            </button>

            {/* Step 2: Commit Override */}
            <button
              type="button"
              onClick={handleCommit}
              disabled={!validated || isCommitting || !isAuthenticated}
              className="px-3 py-1.5 rounded bg-accent hover:bg-accent/90 text-white text-12 font-medium transition-colors cursor-pointer disabled:opacity-40 disabled:cursor-not-allowed"
            >
              {isCommitting ? "Committing…" : "Step 2: Commit Override"}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
