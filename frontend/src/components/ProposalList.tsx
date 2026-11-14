import { useState } from "react";
import { HelpCircle, ThumbsDown, CheckCircle2 } from "lucide-react";
import { formatMw } from "@/lib/format";
import { api } from "@/services/api";
import { errorMessage } from "@/lib/errors";
import { agentName } from "@/lib/agents";
import type { AllocationProposal } from "@/types/api";

interface Props {
  proposals: AllocationProposal[];
  onActionComplete?: () => void;
  onToast: (type: "success" | "error" | "info", msg: string) => void;
}

export function ProposalList({
  proposals,
  onActionComplete,
  onToast,
}: Props) {
  const [rejectingId, setRejectingId] = useState<string | null>(null);
  const [rejectReason, setRejectReason] = useState("Commander rejected proposed allocation balance");
  const [explainingId, setExplainingId] = useState<string | null>(null);
  const [acting, setActing] = useState(false);

  const handleCommit = async (id: string) => {
    setActing(true);
    try {
      await api.allocations.commit(id);
      onToast("success", `Proposal ${id} approved and committed.`);
      onActionComplete?.();
    } catch (err) {
      onToast("error", errorMessage(err));
    } finally {
      setActing(false);
    }
  };

  const handleReject = async (id: string) => {
    setActing(true);
    try {
      await api.allocations.reject(id, rejectReason);
      onToast("info", `Proposal ${id} rejected.`);
      setRejectingId(null);
      onActionComplete?.();
    } catch (err) {
      onToast("error", errorMessage(err));
    } finally {
      setActing(false);
    }
  };

  const handleExplain = async (id: string) => {
    setExplainingId(id);
    try {
      const res = await api.commander.explain(`Explain rationale and safety margins for proposal ${id}`);
      const text = (res as { text?: string }).text ?? "Explanation requested.";
      onToast("info", text);
    } catch (err) {
      onToast("error", errorMessage(err));
    } finally {
      setExplainingId(null);
    }
  };

  if (proposals.length === 0) {
    return (
      <div className="p-3 bg-surface rounded-panel border border-border text-12 text-muted">
        No pending allocation proposals awaiting approval.
      </div>
    );
  }

  return (
    <div className="space-y-3">
      {proposals.map((p) => {
        const isExplaining = explainingId === p.proposal_id;
        const isRejecting = rejectingId === p.proposal_id;

        return (
          <div
            key={p.proposal_id}
            className="p-3 bg-surface rounded-panel border border-border space-y-3 text-12"
          >
            {/* Header */}
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <span className="font-semibold text-text tabular-nums">
                  Proposal {p.proposal_id.slice(0, 8)}
                </span>
                <span className="text-11 uppercase px-1.5 py-0.2 rounded-control bg-surface-2 border border-border text-muted">
                  {p.method}
                </span>
                <span className="text-11 text-muted tabular-nums">
                  Round {p.rounds}
                </span>
              </div>

              <div className="flex items-center gap-2 tabular-nums text-muted text-11">
                <span>Supply: {formatMw(p.supply_total)}</span>
              </div>
            </div>

            {/* Allocation breakdown */}
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 pt-1 border-t border-border/60">
              {Object.entries(p.allocation).map(([agentId, mw]) => (
                <div key={agentId} className="p-2 bg-surface-2 rounded-control">
                  <span className="text-11 text-muted block truncate">
                    {agentName(agentId)}
                  </span>
                  <span className="font-semibold text-text tabular-nums">
                    {formatMw(mw)}
                  </span>
                </div>
              ))}
            </div>

            {/* Reject reason input */}
            {isRejecting && (
              <div className="p-2.5 bg-surface-2 rounded-control border border-border space-y-2">
                <span className="text-11 uppercase text-muted font-medium">Rejection Reason</span>
                <input
                  type="text"
                  value={rejectReason}
                  onChange={(e) => setRejectReason(e.target.value)}
                  className="w-full px-2 py-1 bg-surface border border-border rounded-control text-12 text-text"
                />
                <div className="flex justify-end gap-2">
                  <button
                    type="button"
                    onClick={() => setRejectingId(null)}
                    className="px-2 py-1 text-11 text-muted hover:text-text"
                  >
                    Cancel
                  </button>
                  <button
                    type="button"
                    onClick={() => handleReject(p.proposal_id)}
                    disabled={acting}
                    className="px-2.5 py-1 text-11 bg-accent text-white rounded-control font-medium hover:bg-accent/90"
                  >
                    Confirm Rejection
                  </button>
                </div>
              </div>
            )}

            {/* Actions toolbar */}
            <div className="flex items-center justify-between pt-2 border-t border-border/60">
              <button
                type="button"
                onClick={() => handleExplain(p.proposal_id)}
                disabled={isExplaining || acting}
                className="px-2.5 py-1 text-11 rounded-control border border-border text-muted hover:text-text hover:bg-surface-2 flex items-center gap-1 cursor-pointer disabled:opacity-50"
              >
                <HelpCircle size={13} strokeWidth={1.5} />
                <span>{isExplaining ? "Analyzing rationale…" : "Request Explanation"}</span>
              </button>

              <div className="flex items-center gap-2">
                {!isRejecting && (
                  <button
                    type="button"
                    onClick={() => setRejectingId(p.proposal_id)}
                    disabled={acting}
                    className="px-2.5 py-1 text-11 rounded-control border border-border text-muted hover:text-accent hover:border-accent flex items-center gap-1 cursor-pointer disabled:opacity-50"
                  >
                    <ThumbsDown size={13} strokeWidth={1.5} />
                    <span>Reject</span>
                  </button>
                )}

                <button
                  type="button"
                  onClick={() => handleCommit(p.proposal_id)}
                  disabled={acting}
                  className="px-3 py-1 text-11 rounded-control bg-ok text-black font-medium hover:bg-ok/90 flex items-center gap-1 cursor-pointer disabled:opacity-50"
                >
                  <CheckCircle2 size={13} strokeWidth={1.5} />
                  <span>Approve & Commit</span>
                </button>
              </div>
            </div>
          </div>
        );
      })}
    </div>
  );
}

