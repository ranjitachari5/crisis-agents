import { formatMw, formatSimTime } from "@/lib/format";
import { agentName } from "@/lib/agents";
import type { Agreement } from "@/types/api";

interface Props {
  agreements: Agreement[];
}

export function AgreementList({ agreements }: Props) {
  if (agreements.length === 0) {
    return (
      <div className="p-3 bg-surface rounded-panel border border-border text-12 text-muted">
        No committed agreements recorded.
      </div>
    );
  }

  return (
    <div className="space-y-2">
      {agreements.slice(0, 5).map((agr) => (
        <div
          key={agr.version}
          className="p-3 bg-surface rounded-panel border border-border text-12 space-y-2"
        >
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <span className="font-semibold text-text tabular-nums">
                Agreement v{agr.version}
              </span>
              <span className="text-11 uppercase px-1.5 py-0.2 rounded-control bg-surface-2 border border-border text-muted">
                {agr.method}
              </span>
              {agr.degradation_mode && (
                <span className="text-11 px-1.5 py-0.2 rounded-control bg-accent/20 border border-accent/40 text-accent font-medium">
                  Degraded
                </span>
              )}
            </div>

            <span className="text-11 text-muted tabular-nums">
              {formatSimTime(agr.committed_at)}
            </span>
          </div>

          <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 pt-1 border-t border-border/60">
            {agr.allocation &&
              Object.entries(agr.allocation).map(([agentId, mw]) => (
                <div key={agentId} className="p-1.5 bg-surface-2 rounded-control">
                  <span className="text-11 text-muted block truncate">
                    {agentName(agentId)}
                  </span>
                  <span className="font-medium text-text tabular-nums">
                    {formatMw(mw)}
                  </span>
                </div>
              ))}
          </div>
        </div>
      ))}
    </div>
  );
}

