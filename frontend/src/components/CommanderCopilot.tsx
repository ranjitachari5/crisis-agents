import { useState, type FormEvent } from "react";
import {
  Sparkles,
  Send,
  Loader2,
  Bot,
  ShieldCheck,
  ChevronDown,
  ChevronUp,
  X,
  HelpCircle,
  Zap,
  Activity,
  Layers,
} from "lucide-react";
import { api } from "@/services/api";
import { errorMessage } from "@/lib/errors";
import type { ExplainResponse } from "@/types/api";

const PRESET_QUESTIONS = [
  {
    label: "Hospital Allocation Rationale",
    question: "Why is Hospital Agent allocated 85 MW?",
    icon: "🏥",
  },
  {
    label: "Battery Endurance",
    question: "How long will the current battery discharge rate last before depletion?",
    icon: "🔋",
  },
  {
    label: "Safe Minimums Check",
    question: "Are all consumer utilities receiving their mandatory safe minimum power?",
    icon: "🛡️",
  },
  {
    label: "Cascading Risks",
    question: "What are the most dangerous active cascade failure risks right now?",
    icon: "⚡",
  },
  {
    label: "Negotiation Dynamics",
    question: "Summarize the last negotiation: who conceded power and why?",
    icon: "🤝",
  },
];

export function CommanderCopilot() {
  const [query, setQuery] = useState("");
  const [loading, setLoading] = useState(false);
  const [response, setResponse] = useState<ExplainResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [showFacts, setShowFacts] = useState(false);
  const [lastQuestion, setLastQuestion] = useState<string | null>(null);

  const handleAsk = async (questionText: string) => {
    const trimmed = questionText.trim();
    if (!trimmed || loading) return;

    setLoading(true);
    setError(null);
    setLastQuestion(trimmed);

    try {
      const res = await api.commander.explain(trimmed);
      setResponse(res);
    } catch (err) {
      setError(errorMessage(err) || "Failed to retrieve explanation from Copilot.");
    } finally {
      setLoading(false);
    }
  };

  const handleSubmit = (e: FormEvent) => {
    e.preventDefault();
    handleAsk(query);
  };

  const handleClear = () => {
    setResponse(null);
    setLastQuestion(null);
    setError(null);
    setShowFacts(false);
  };

  return (
    <div className="bg-surface rounded-panel border border-border/80 shadow-md p-4 sm:p-5 relative overflow-hidden transition-all">
      {/* Decorative tactical accent line */}
      <div className="absolute top-0 left-0 right-0 h-0.5 bg-gradient-to-r from-accent/20 via-accent to-accent/20" />

      {/* Header bar */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 mb-3">
        <div className="flex items-center gap-2.5">
          <div className="w-7 h-7 rounded-lg bg-accent/15 border border-accent/40 flex items-center justify-center text-accent shadow-sm">
            <Sparkles size={16} strokeWidth={2} />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <h2 className="text-14 font-semibold text-text tracking-tight">
                Ask Commander Copilot
              </h2>
              <span className="px-1.5 py-0.5 text-[10px] font-mono font-medium rounded bg-surface-2 border border-border text-muted">
                LLM Grounded QA
              </span>
            </div>
            <p className="text-11 text-muted">
              Ask any natural-language question about allocations, agent decisions, or operational risks.
            </p>
          </div>
        </div>

        {response && (
          <button
            type="button"
            onClick={handleClear}
            className="self-end sm:self-auto text-11 text-muted hover:text-text flex items-center gap-1 px-2 py-1 rounded bg-surface-2 hover:bg-border/60 border border-border transition-colors cursor-pointer"
          >
            <X size={12} />
            <span>Clear Answer</span>
          </button>
        )}
      </div>

      {/* Search & Query Input */}
      <form onSubmit={handleSubmit} className="relative flex items-center gap-2">
        <div className="relative flex-1">
          <input
            type="text"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Ask Copilot: e.g. Why did Water concede power? How safe is the grid right now?"
            disabled={loading}
            className="w-full pl-3.5 pr-10 py-2.5 bg-surface-2 border border-border rounded-control text-13 text-text placeholder-muted/60 focus:outline-none focus:border-accent focus:ring-1 focus:ring-accent transition-all disabled:opacity-50"
          />
          {query && !loading && (
            <button
              type="button"
              onClick={() => setQuery("")}
              className="absolute right-3 top-1/2 -translate-y-1/2 text-muted hover:text-text cursor-pointer"
            >
              <X size={14} />
            </button>
          )}
        </div>

        <button
          type="submit"
          disabled={loading || !query.trim()}
          className="px-4 py-2.5 rounded-control text-12 font-medium bg-accent text-white hover:bg-accent/90 disabled:opacity-40 disabled:cursor-not-allowed transition-colors flex items-center gap-1.5 shrink-0 cursor-pointer shadow-sm"
        >
          {loading ? (
            <>
              <Loader2 size={14} className="animate-spin" />
              <span>Analyzing...</span>
            </>
          ) : (
            <>
              <Send size={13} />
              <span>Ask Copilot</span>
            </>
          )}
        </button>
      </form>

      {/* One-Tap Commander Prompt Pills */}
      <div className="flex items-center gap-1.5 flex-wrap mt-2.5">
        <span className="text-[11px] text-muted flex items-center gap-1 mr-1">
          <HelpCircle size={12} className="text-muted/80" />
          Quick Prompts:
        </span>
        {PRESET_QUESTIONS.map((item, idx) => (
          <button
            key={idx}
            type="button"
            disabled={loading}
            onClick={() => {
              setQuery(item.question);
              handleAsk(item.question);
            }}
            className="px-2.5 py-1 rounded-full text-11 bg-surface-2 hover:bg-border/70 border border-border text-text/90 hover:text-text transition-colors flex items-center gap-1.5 cursor-pointer disabled:opacity-50"
          >
            <span className="text-xs">{item.icon}</span>
            <span>{item.label}</span>
          </button>
        ))}
      </div>

      {/* Error Banner */}
      {error && (
        <div className="mt-3 p-3 rounded bg-accent-dim/30 border border-accent/40 text-accent text-12 flex items-center justify-between">
          <span>{error}</span>
          <button
            type="button"
            onClick={() => setError(null)}
            className="text-accent hover:underline cursor-pointer"
          >
            Dismiss
          </button>
        </div>
      )}

      {/* Copilot Answer Display Card */}
      {response && (
        <div className="mt-4 pt-4 border-t border-border space-y-3 animate-in fade-in duration-200">
          <div className="flex items-center justify-between flex-wrap gap-2">
            <div className="flex items-center gap-2">
              <div className="flex items-center gap-1.5 text-12 font-medium text-text">
                <Bot size={15} className="text-accent" />
                <span>Copilot Briefing</span>
              </div>
              {lastQuestion && (
                <span className="text-11 text-muted italic truncate max-w-md">
                  &ldquo;{lastQuestion}&rdquo;
                </span>
              )}
            </div>

            <div className="flex items-center gap-2 text-[11px]">
              <span className="px-2 py-0.5 rounded bg-surface-2 border border-border text-muted font-mono flex items-center gap-1">
                <ShieldCheck size={12} className="text-ok" />
                {response.source.replace("groq:", "Groq: ")}
              </span>
              <span className="text-muted/70 text-[10px] uppercase font-mono">
                {response.advisory_only ? "Advisory Guidance" : "System Fact"}
              </span>
            </div>
          </div>

          {/* Main Answer Prose */}
          <div className="p-3.5 rounded-control bg-surface-2 border border-border/80 text-13 text-text leading-relaxed">
            <p className="whitespace-pre-wrap">{response.text}</p>
          </div>

          {/* Facts Collapsible Accordion */}
          {response.facts && (
            <div className="rounded border border-border bg-surface/50 overflow-hidden">
              <button
                type="button"
                onClick={() => setShowFacts((prev) => !prev)}
                className="w-full px-3 py-2 text-11 font-medium text-muted hover:text-text flex items-center justify-between bg-surface-2/40 hover:bg-surface-2 transition-colors cursor-pointer"
              >
                <span className="flex items-center gap-1.5">
                  <Layers size={13} className="text-muted" />
                  Grounded Fact Sheet ({Object.keys(response.facts.agents || {}).length} agents cross-referenced)
                </span>
                {showFacts ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
              </button>

              {showFacts && (
                <div className="p-3 border-t border-border space-y-3 text-11">
                  {/* High level grid telemetry */}
                  <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
                    <div className="p-2 rounded bg-surface-2 border border-border">
                      <span className="text-muted block text-[10px] uppercase font-mono">Verified Supply</span>
                      <span className="font-semibold text-text text-12">
                        {response.facts.verified_supply_mw.toFixed(1)} MW
                      </span>
                    </div>
                    <div className="p-2 rounded bg-surface-2 border border-border">
                      <span className="text-muted block text-[10px] uppercase font-mono">Battery Reserve</span>
                      <span className="font-semibold text-text text-12">
                        {response.facts.battery_capability_mw.toFixed(1)} MW
                      </span>
                    </div>
                    <div className="p-2 rounded bg-surface-2 border border-border">
                      <span className="text-muted block text-[10px] uppercase font-mono">Fairness Policy</span>
                      <span className="font-semibold text-text text-12">
                        {response.facts.fairness.toFixed(2)}
                      </span>
                    </div>
                    <div className="p-2 rounded bg-surface-2 border border-border">
                      <span className="text-muted block text-[10px] uppercase font-mono">Negotiation Rounds</span>
                      <span className="font-semibold text-text text-12">
                        {response.facts.last_negotiation?.rounds ?? 1} rounds
                      </span>
                    </div>
                  </div>

                  {/* Agents allocation table */}
                  <div>
                    <span className="text-[10px] uppercase tracking-wider font-mono text-muted block mb-1">
                      Individual Utility Allocations
                    </span>
                    <div className="border border-border rounded overflow-hidden">
                      <table className="w-full text-left">
                        <thead className="bg-surface-2 text-muted text-[10px] font-mono border-b border-border">
                          <tr>
                            <th className="p-1.5 pl-2.5">Agent</th>
                            <th className="p-1.5">Allocated</th>
                            <th className="p-1.5">Safe Min</th>
                            <th className="p-1.5">Demand</th>
                            <th className="p-1.5">Margin</th>
                          </tr>
                        </thead>
                        <tbody className="divide-y divide-border/60">
                          {Object.entries(response.facts.agents || {}).map(([aid, a]) => {
                            const margin = (a.allocation_mw ?? 0) - (a.min_safe_mw ?? 0);
                            const isAtFloor = Math.abs(margin) < 0.05;
                            return (
                              <tr key={aid} className="hover:bg-surface-2/30">
                                <td className="p-1.5 pl-2.5 font-medium text-text capitalize">
                                  {aid.replace("_agent", "").replace("_", " ")}
                                </td>
                                <td className="p-1.5 font-mono text-text">
                                  {a.allocation_mw?.toFixed(1) ?? "—"} MW
                                </td>
                                <td className="p-1.5 font-mono text-muted">
                                  {a.min_safe_mw?.toFixed(1) ?? "—"} MW
                                </td>
                                <td className="p-1.5 font-mono text-muted">
                                  {a.demand_mw?.toFixed(1) ?? "—"} MW
                                </td>
                                <td className="p-1.5 font-mono">
                                  {isAtFloor ? (
                                    <span className="text-muted text-[10px]">Exact Floor (0.0)</span>
                                  ) : margin > 0 ? (
                                    <span className="text-ok text-[10px]">+{margin.toFixed(1)} MW</span>
                                  ) : (
                                    <span className="text-accent text-[10px]">{margin.toFixed(1)} MW</span>
                                  )}
                                </td>
                              </tr>
                            );
                          })}
                        </tbody>
                      </table>
                    </div>
                  </div>

                  {/* Cascading risks if present */}
                  {response.facts.cascades && response.facts.cascades.length > 0 && (
                    <div className="p-2 rounded bg-surface-2 border border-border space-y-1">
                      <span className="text-[10px] uppercase font-mono text-muted flex items-center gap-1">
                        <Activity size={12} className="text-accent" />
                        Active Cascade Paths
                      </span>
                      <div className="space-y-1 text-[11px] text-muted">
                        {response.facts.cascades.slice(0, 2).map((c, idx) => (
                          <div key={idx} className="font-mono text-[10px] text-text/80">
                            • {c.path.join(" → ")}
                          </div>
                        ))}
                      </div>
                    </div>
                  )}
                </div>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
