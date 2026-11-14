import { useState } from "react";
import {
  ShieldAlert,
  ShieldCheck,
  CheckCircle2,
  XCircle,
  AlertTriangle,
  Clock,
  User,
  Scale,
} from "lucide-react";
import { AGENTS } from "@/lib/agents";
import { api } from "@/services/api";
import { errorMessage } from "@/lib/errors";
import type { TrustIncident, AgentId } from "@/types/api";

interface Props {
  incident: TrustIncident | null;
  onResolved: (updated: TrustIncident) => void;
}

export function IncidentDetail({ incident, onResolved }: Props) {
  const [isResolving, setIsResolving] = useState(false);
  const [resolutionNote, setResolutionNote] = useState("");
  const [error, setError] = useState<string | null>(null);

  if (!incident) {
    return (
      <div className="p-6 bg-surface rounded-panel border border-border flex items-center justify-center min-h-[320px]">
        <span className="text-12 text-muted">Select an incident to view full verification details.</span>
      </div>
    );
  }

  const senderDef = AGENTS[incident.sender as AgentId];
  const isEscalatedUnresolved = incident.escalated && !incident.resolved;

  const handleResolve = async (action: "confirm_claim" | "dismiss") => {
    setIsResolving(true);
    setError(null);
    try {
      const res = await api.trust.resolve(incident.incident_id, action, resolutionNote.trim());
      onResolved(res);
      setResolutionNote("");
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setIsResolving(false);
    }
  };

  return (
    <div className="p-5 bg-surface rounded-panel border border-border space-y-4 text-13">
      {/* Header */}
      <div className="flex flex-wrap items-start justify-between gap-3 pb-3 border-b border-border">
        <div>
          <div className="flex items-center gap-2">
            <span className="text-11 uppercase font-semibold text-muted tracking-wider">
              Incident {incident.incident_id.slice(0, 8)}
            </span>
            <span
              className={`text-11 px-2 py-0.5 rounded font-medium border ${
                incident.resolved
                  ? "bg-ok/10 text-ok border-ok/30"
                  : incident.escalated
                  ? "bg-accent-dim text-accent border-accent/40"
                  : "bg-surface-2 text-text border-border"
              }`}
            >
              {incident.resolved ? "RESOLVED" : incident.escalated ? "ESCALATED" : "FLAGGED"}
            </span>
          </div>
          <h3 className="text-16 font-semibold text-text mt-1">{incident.summary || incident.kind}</h3>
        </div>

        <div className="flex items-center gap-4 text-12 text-muted tabular-nums">
          <div className="flex items-center gap-1.5">
            <Clock className="w-3.5 h-3.5" />
            <span>{incident.sim_time}</span>
          </div>
          <div className="flex items-center gap-1.5">
            <User className="w-3.5 h-3.5" />
            <span>{senderDef?.name ?? incident.sender}</span>
          </div>
        </div>
      </div>

      {/* Metadata Chips Grid */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
        <div className="p-2.5 rounded bg-surface-2 border border-border">
          <span className="text-11 uppercase font-semibold text-muted tracking-wider block">Decision</span>
          <span className="text-13 font-medium text-text mt-0.5 block capitalize">
            {incident.decision}
          </span>
        </div>

        <div className="p-2.5 rounded bg-surface-2 border border-border">
          <span className="text-11 uppercase font-semibold text-muted tracking-wider block">Trust Score</span>
          <span className="text-13 font-semibold text-text mt-0.5 block tabular-nums">
            {(incident.trust_score * 100).toFixed(0)}%
          </span>
        </div>

        <div className="p-2.5 rounded bg-surface-2 border border-border">
          <span className="text-11 uppercase font-semibold text-muted tracking-wider block">Quarantined</span>
          <span
            className={`text-13 font-medium mt-0.5 block ${
              incident.quarantined ? "text-accent" : "text-muted"
            }`}
          >
            {incident.quarantined ? "Yes" : "No"}
          </span>
        </div>

        <div className="p-2.5 rounded bg-surface-2 border border-border">
          <span className="text-11 uppercase font-semibold text-muted tracking-wider block">Escalated</span>
          <span
            className={`text-13 font-medium mt-0.5 block ${
              incident.escalated ? "text-accent" : "text-muted"
            }`}
          >
            {incident.escalated ? "Yes" : "No"}
          </span>
        </div>
      </div>

      {/* Spec Requirement: Clear line "Allocation changed: Yes / No" */}
      <div className="p-3 rounded bg-surface-2 border border-border flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Scale className="w-4 h-4 text-muted" />
          <span className="text-12 text-muted">Impact on Resource Allocation:</span>
        </div>
        <span
          className={`text-13 font-semibold ${
            incident.allocation_changed ? "text-accent" : "text-text"
          }`}
        >
          Allocation changed: {incident.allocation_changed ? "Yes" : "No"}
        </span>
      </div>

      {/* Claim Object */}
      <div>
        <h4 className="text-11 uppercase font-semibold text-muted tracking-wider mb-1.5">
          Incident Claim
        </h4>
        <div className="p-3 rounded bg-surface-2 border border-border font-mono text-12 text-text/90 overflow-x-auto">
          {Object.keys(incident.claim || {}).length > 0 ? (
            <div className="space-y-1">
              {Object.entries(incident.claim).map(([key, value]) => (
                <div key={key} className="flex gap-2">
                  <span className="text-muted">{key}:</span>
                  <span className="text-text font-medium">{String(value)}</span>
                </div>
              ))}
            </div>
          ) : (
            <span className="text-muted font-sans text-12">No structured claim payload attached.</span>
          )}
        </div>
      </div>

      {/* Evidence Table */}
      <div>
        <h4 className="text-11 uppercase font-semibold text-muted tracking-wider mb-1.5">
          Cross-Sensor Evidence Validation
        </h4>
        <div className="border border-border rounded overflow-hidden">
          <table className="w-full text-left text-12 border-collapse">
            <thead>
              <tr className="bg-surface-2 text-muted font-semibold text-11 uppercase tracking-wider border-b border-border">
                <th className="py-2 px-3">Check</th>
                <th className="py-2 px-3">Status</th>
                <th className="py-2 px-3">Observed</th>
                <th className="py-2 px-3">Expected</th>
                <th className="py-2 px-3">Detail</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border">
              {incident.evidence?.length > 0 ? (
                incident.evidence.map((ev, i) => (
                  <tr key={i} className="hover:bg-surface-2/40 transition-colors">
                    <td className="py-2 px-3 font-medium text-text">{ev.check}</td>
                    <td className="py-2 px-3">
                      <div className="flex items-center gap-1.5">
                        {ev.passed ? (
                          <>
                            <CheckCircle2 className="w-3.5 h-3.5 text-ok shrink-0" />
                            <span className="text-ok font-medium">Passed</span>
                          </>
                        ) : (
                          <>
                            <XCircle className="w-3.5 h-3.5 text-accent shrink-0" />
                            <span className="text-accent font-medium">Failed</span>
                          </>
                        )}
                      </div>
                    </td>
                    <td className="py-2 px-3 tabular-nums text-text font-mono">
                      {ev.observed != null ? String(ev.observed) : "—"}
                    </td>
                    <td className="py-2 px-3 tabular-nums text-muted font-mono">
                      {ev.expected != null ? String(ev.expected) : "—"}
                    </td>
                    <td className="py-2 px-3 text-muted text-11">{ev.detail}</td>
                  </tr>
                ))
              ) : (
                <tr>
                  <td colSpan={5} className="py-3 px-3 text-center text-muted text-12">
                    No evidence records evaluated for this incident.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>

      {/* Agent Responses if any */}
      {incident.agent_responses?.length > 0 && (
        <div>
          <h4 className="text-11 uppercase font-semibold text-muted tracking-wider mb-1.5">
            Peer Agent Responses
          </h4>
          <ul className="space-y-1.5">
            {incident.agent_responses.map((resp, i) => (
              <li
                key={i}
                className="p-2.5 rounded bg-surface-2 border border-border text-12 text-muted"
              >
                {resp}
              </li>
            ))}
          </ul>
        </div>
      )}

      {/* Commander Resolution Controls (Escalated & Unresolved) */}
      {isEscalatedUnresolved && (
        <div className="p-4 rounded-panel bg-surface-2 border border-accent/40 space-y-3">
          <div className="flex items-center gap-2 text-accent font-medium text-13">
            <AlertTriangle className="w-4 h-4 shrink-0" />
            <span>Commander Intervention Required</span>
          </div>

          <p className="text-12 text-muted">
            The autonomous trust engine flagged this claim as inconsistent with telemetry. Confirm the
            claim to accept the altered supply/demand or dismiss it to preserve current consensus.
          </p>

          <div>
            <label className="text-11 uppercase font-semibold text-muted tracking-wider block mb-1">
              Resolution Note (Optional)
            </label>
            <input
              type="text"
              value={resolutionNote}
              onChange={(e) => setResolutionNote(e.target.value)}
              placeholder="e.g. Telemetry sensor fault confirmed via auxiliary line"
              className="w-full px-3 py-1.5 text-12 bg-surface rounded border border-border text-text placeholder:text-muted/60 focus:outline-none focus:border-accent"
            />
          </div>

          {error && (
            <div className="text-11 text-accent flex items-center gap-1.5">
              <AlertTriangle className="w-3.5 h-3.5" />
              <span>{error}</span>
            </div>
          )}

          <div className="flex items-center gap-2 pt-1">
            <button
              onClick={() => handleResolve("confirm_claim")}
              disabled={isResolving}
              className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded bg-surface border border-ok/40 hover:border-ok text-ok text-12 font-medium transition-colors cursor-pointer disabled:opacity-50"
            >
              <ShieldCheck className="w-3.5 h-3.5" />
              <span>Approve (Confirm Claim)</span>
            </button>

            <button
              onClick={() => handleResolve("dismiss")}
              disabled={isResolving}
              className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded bg-surface border border-accent/40 hover:border-accent text-accent text-12 font-medium transition-colors cursor-pointer disabled:opacity-50"
            >
              <ShieldAlert className="w-3.5 h-3.5" />
              <span>Reject (Dismiss Incident)</span>
            </button>
          </div>
        </div>
      )}

      {/* Resolution summary if resolved */}
      {incident.resolved && incident.resolution && (
        <div className="p-3 rounded bg-surface-2 border border-border text-12 text-muted">
          <span className="font-semibold text-text uppercase text-11 tracking-wider block mb-1">
            Resolution Summary
          </span>
          <div>Action: <strong className="text-text">{String(incident.resolution.action)}</strong></div>
          {incident.resolution.note != null && incident.resolution.note !== "" && (
            <div>Note: {String(incident.resolution.note)}</div>
          )}
        </div>
      )}
    </div>
  );
}

