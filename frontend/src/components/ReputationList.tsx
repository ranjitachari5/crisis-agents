import { Shield } from "lucide-react";
import { AGENTS, AGENT_IDS } from "@/lib/agents";

interface Props {
  reputation: Record<string, number>;
}

export function ReputationList({ reputation }: Props) {
  const entries = AGENT_IDS.map((agentId) => {
    const def = AGENTS[agentId];
    const score = reputation[agentId] ?? 1.0;
    return {
      agentId,
      name: def?.name ?? agentId,
      role: def?.role ?? "",
      score,
    };
  });

  return (
    <div className="p-4 bg-surface rounded-panel border border-border flex flex-col justify-between">
      <div>
        <div className="flex items-center justify-between mb-1">
          <div className="flex items-center gap-2">
            <Shield className="w-4 h-4 text-muted" />
            <h3 className="text-13 font-medium text-text">Agent Trust Reputation</h3>
          </div>
          <span className="text-11 text-muted">Baseline: 1.00</span>
        </div>
        <p className="text-11 text-muted mb-3">
          Dynamic reputation scores updated from negotiation claims and cross-sensor audits.
        </p>
      </div>

      <div className="space-y-2">
        {entries.map(({ agentId, name, score }) => {
          const isDegraded = score < 0.7;
          return (
            <div
              key={agentId}
              className="p-2 rounded bg-surface-2 border border-border flex items-center justify-between gap-3 text-12"
            >
              <div className="min-w-0">
                <span className="font-medium text-text block truncate">{name}</span>
              </div>

              <div className="flex items-center gap-3 shrink-0">
                {/* Thin Score Bar */}
                <div className="w-20 h-1.5 bg-border rounded-full overflow-hidden">
                  <div
                    className={`h-full transition-all duration-300 ${
                      isDegraded ? "bg-accent" : "bg-text"
                    }`}
                    style={{ width: `${Math.min(100, Math.max(0, score * 100))}%` }}
                  />
                </div>

                <span
                  className={`tabular-nums font-medium text-right w-12 ${
                    isDegraded ? "text-accent" : "text-text"
                  }`}
                >
                  {score.toFixed(2)}
                </span>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
