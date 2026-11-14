import { GitCommit, Play, CheckCircle2 } from "lucide-react";
import type { CascadeChain } from "@/types/api";

interface Props {
  cascades: CascadeChain[];
  activeCascadeIndex: number | null;
  onTraceCascade: (index: number) => void;
}

export function CascadeList({ cascades, activeCascadeIndex, onTraceCascade }: Props) {
  return (
    <div className="p-4 bg-surface rounded-panel border border-border flex flex-col justify-between h-full">
      <div>
        <div className="flex items-center justify-between mb-1">
          <div className="flex items-center gap-2">
            <GitCommit className="w-4 h-4 text-accent" />
            <h3 className="text-13 font-medium text-text">Cascading Failure Chains</h3>
          </div>
          <span className="text-11 text-muted tabular-nums">
            {cascades.length} detected
          </span>
        </div>
        <p className="text-11 text-muted mb-3">
          Cross-sector dependency paths where upstream power deficits propagate into municipal lifelines.
        </p>

        {cascades.length === 0 ? (
          <div className="py-10 flex flex-col items-center justify-center border border-dashed border-border rounded text-center px-4">
            <CheckCircle2 className="w-5 h-5 text-ok mb-2" />
            <span className="text-12 text-muted">
              No cascading service failures detected.
            </span>
            <span className="text-11 text-muted mt-1">
              All infrastructure lifelines operating above degradation thresholds.
            </span>
          </div>
        ) : (
          <div className="space-y-2">
            {cascades.map((cascade, index) => {
              const isPlaying = activeCascadeIndex === index;
              const formattedPath = cascade.path.join(" → ");

              return (
                <div
                  key={`${cascade.root}-${index}`}
                  className={`p-3 rounded border text-left transition-colors duration-150 ${
                    isPlaying
                      ? "border-accent bg-accent-dim"
                      : "border-border bg-surface-2 hover:border-muted/60"
                  }`}
                >
                  <div className="flex items-start justify-between gap-2 mb-1.5">
                    <div className="min-w-0">
                      <div className="flex items-center gap-1.5 flex-wrap">
                        <span className="text-10 uppercase tracking-wider font-semibold text-accent bg-accent-dim px-1.5 py-0.5 rounded border border-accent/30">
                          Root: {cascade.root}
                        </span>
                        {cascade.cause && (
                          <span className="text-11 text-muted truncate">
                            {cascade.cause}
                          </span>
                        )}
                      </div>
                    </div>

                    <button
                      type="button"
                      onClick={() => onTraceCascade(index)}
                      className="inline-flex items-center gap-1 px-2 py-1 text-11 rounded border border-border bg-surface hover:bg-surface-2 text-text transition-colors shrink-0"
                    >
                      <Play className="w-3 h-3 text-accent" />
                      <span>{isPlaying ? "Tracing…" : "Trace"}</span>
                    </button>
                  </div>

                  <div className="text-11 font-mono text-muted bg-surface/80 p-1.5 rounded border border-border/80 break-all select-all">
                    {formattedPath}
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>

      <div className="pt-3 mt-3 border-t border-border flex items-center justify-between text-11 text-muted">
        <span>Sequential cascade trace (~150ms per hop)</span>
        <span className="tabular-nums">Propagation delay: 150ms</span>
      </div>
    </div>
  );
}

