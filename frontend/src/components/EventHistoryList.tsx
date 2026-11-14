import { History, RefreshCw } from "lucide-react";

interface Props {
  history: Record<string, unknown>[];
  isLoading?: boolean;
  onRefresh?: () => void;
}

export function EventHistoryList({ history, isLoading, onRefresh }: Props) {
  return (
    <div className="p-4 bg-surface rounded-panel border border-border flex flex-col justify-between h-full">
      <div>
        <div className="flex items-center justify-between mb-1">
          <div className="flex items-center gap-2">
            <History className="w-4 h-4 text-muted" />
            <h3 className="text-13 font-medium text-text">Event Injection History</h3>
          </div>
          <div className="flex items-center gap-2">
            <span className="text-11 text-muted tabular-nums">{history.length} logged</span>
            {onRefresh && (
              <button
                type="button"
                onClick={onRefresh}
                disabled={isLoading}
                className="p-1 text-muted hover:text-text rounded transition-colors"
                title="Refresh history"
              >
                <RefreshCw className={`w-3.5 h-3.5 ${isLoading ? "animate-spin text-accent" : ""}`} />
              </button>
            )}
          </div>
        </div>
        <p className="text-11 text-muted mb-3">
          Chronological record of scenario mutations and environmental shocks applied during this run.
        </p>

        {history.length === 0 ? (
          <div className="py-12 flex items-center justify-center border border-dashed border-border rounded text-center">
            <span className="text-12 text-muted">No simulation events injected.</span>
          </div>
        ) : (
          <div className="space-y-2 max-h-[380px] overflow-y-auto pr-1">
            {history
              .slice()
              .reverse()
              .map((item, idx) => {
                const tick = (item.tick as number) ?? "—";
                const eventType = (item.event_type as string) ?? (item.type as string) ?? "event";
                const description =
                  (item.description as string) ||
                  (item.summary as string) ||
                  (item.message as string) ||
                  JSON.stringify(item.params ?? {});
                const time = (item.sim_time as string)?.split("T")[1]?.slice(0, 8) ?? "";

                return (
                  <div
                    key={idx}
                    className="p-2.5 bg-surface-2 rounded border border-border flex flex-col gap-1 text-left"
                  >
                    <div className="flex items-center justify-between gap-2">
                      <div className="flex items-center gap-2 min-w-0">
                        <span className="text-10 uppercase tracking-wider font-semibold text-accent bg-accent-dim px-1.5 py-0.5 rounded border border-accent/20 truncate">
                          {eventType.replace(/_/g, " ")}
                        </span>
                        <span className="text-11 text-muted tabular-nums">Tick {tick}</span>
                      </div>
                      {time && (
                        <span className="text-11 text-muted tabular-nums shrink-0">{time}</span>
                      )}
                    </div>
                    <span className="text-12 text-text break-words">{description}</span>
                  </div>
                );
              })}
          </div>
        )}
      </div>

      <div className="pt-3 mt-3 border-t border-border flex items-center justify-between text-11 text-muted">
        <span>History capacity: 200 events</span>
        <span>Reverse chronological</span>
      </div>
    </div>
  );
}

