import { useState } from "react";
import { Play, Loader2, BarChart2, ShieldCheck, Scale, Cpu, Layers } from "lucide-react";
import { api } from "@/services/api";
import { errorMessage } from "@/lib/errors";
import { formatPct } from "@/lib/format";
import type { EvaluationPlan, EvaluationRun } from "@/types/api";

const MODE_LABELS: Record<string, { name: string; desc: string; icon: typeof Layers }> = {
  fcfs: {
    name: "First-Come First-Served",
    desc: "Seeded sequential order without crisis prioritization",
    icon: Layers,
  },
  fixed_priority: {
    name: "Fixed Priority",
    desc: "Hospital > Emergency > Telecom > Water, greedy allocation",
    icon: ShieldCheck,
  },
  centralized: {
    name: "Centralized Optimizer",
    desc: "Single omniscient solver with full global information",
    icon: Cpu,
  },
  negotiation: {
    name: "Multi-Agent Consensus",
    desc: "Autonomous decentralized negotiation under scarce power",
    icon: Scale,
  },
};

const MODES = ["fcfs", "fixed_priority", "centralized", "negotiation"];

interface Props {
  plan: EvaluationPlan | null;
  scenario?: string;
  fairness?: number;
}

export function EvaluationPanel({ plan, scenario = "flood_cascade", fairness = 0.5 }: Props) {
  const [isRunning, setIsRunning] = useState(false);
  const [evaluationRun, setEvaluationRun] = useState<EvaluationRun | null>(null);
  const [error, setError] = useState<string | null>(null);

  const handleRunEvaluation = async () => {
    setIsRunning(true);
    setError(null);

    try {
      const res = await api.evaluation.run({
        scenario: scenario as "flood_cascade",
        seed: 42,
        ticks: 32,
        fairness,
        modes: MODES as ("fcfs" | "fixed_priority" | "centralized" | "negotiation")[],
      });
      setEvaluationRun(res);
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setIsRunning(false);
    }
  };

  const results = evaluationRun?.results ?? null;

  return (
    <div className="space-y-4">
      {/* Plan & Benchmark Action Card */}
      <div className="p-4 bg-surface rounded-panel border border-border">
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 pb-3 border-b border-border">
          <div>
            <div className="flex items-center gap-2">
              <BarChart2 className="w-4 h-4 text-accent" />
              <h3 className="text-13 font-medium text-text">Comparative Allocation Benchmark</h3>
            </div>
            <p className="text-11 text-muted mt-0.5">
              Identical scenario shocks, seed (42), and 32 evaluation ticks executed head-to-head across 4 allocation paradigms.
            </p>
          </div>

          <button
            type="button"
            onClick={handleRunEvaluation}
            disabled={isRunning}
            className="inline-flex items-center justify-center gap-2 px-4 py-2 rounded bg-accent hover:bg-accent/90 text-text font-medium text-12 transition-colors disabled:opacity-50 shrink-0 shadow-sm"
          >
            {isRunning ? (
              <>
                <Loader2 className="w-3.5 h-3.5 animate-spin" />
                <span>Running Benchmark…</span>
              </>
            ) : (
              <>
                <Play className="w-3.5 h-3.5 fill-current" />
                <span>Run Evaluation</span>
              </>
            )}
          </button>
        </div>

        {/* Running Banner */}
        {isRunning && (
          <div className="py-3 px-3.5 my-3 rounded border border-border bg-surface-2 flex items-center gap-3">
            <Loader2 className="w-4 h-4 text-accent animate-spin shrink-0" />
            <div className="text-12 text-text">
              <span className="font-medium">
                Running comparative benchmark across 4 allocation modes…
              </span>
              <span className="text-muted ml-2">(~5-10s headless execution)</span>
            </div>
          </div>
        )}

        {/* Error Notification */}
        {error && (
          <div className="p-3 my-3 rounded border border-accent/40 bg-accent-dim text-12 text-text">
            Evaluation failed: {error}
          </div>
        )}

        {/* Evaluation Parameters Strip */}
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 pt-3 text-11 text-muted">
          <div>
            <span className="block text-10 uppercase tracking-wider font-semibold text-muted">
              Scenario
            </span>
            <span className="text-12 font-medium text-text capitalize">
              {scenario.replace(/_/g, " ")}
            </span>
          </div>

          <div>
            <span className="block text-10 uppercase tracking-wider font-semibold text-muted">
              Simulation Ticks
            </span>
            <span className="text-12 font-medium text-text tabular-nums">32 ticks</span>
          </div>

          <div>
            <span className="block text-10 uppercase tracking-wider font-semibold text-muted">
              Fairness Weight
            </span>
            <span className="text-12 font-medium text-text tabular-nums">
              {fairness.toFixed(2)}
            </span>
          </div>

          <div>
            <span className="block text-10 uppercase tracking-wider font-semibold text-muted">
              Benchmark Protocol
            </span>
            <span className="text-12 font-medium text-text">Headless Identical Seed</span>
          </div>
        </div>
      </div>

      {/* 4x7 Evaluation Matrix Table */}
      <div className="bg-surface rounded-panel border border-border overflow-hidden">
        <div className="px-4 py-3 border-b border-border flex items-center justify-between">
          <h4 className="text-12 font-medium text-text">4-Mode Comparative Evaluation Matrix</h4>
          {evaluationRun && (
            <span className="text-11 text-muted tabular-nums">
              Run ID: <span className="text-text font-mono">{evaluationRun.run_id}</span> ({evaluationRun.duration_s.toFixed(2)}s)
            </span>
          )}
        </div>

        <div className="overflow-x-auto">
          <table className="w-full text-left border-collapse text-12">
            <thead>
              <tr className="border-b border-border bg-surface-2 text-11 text-muted font-medium select-none">
                <th className="py-2.5 px-4">Allocation Paradigm</th>
                <th className="py-2.5 px-3 text-right">Weighted Damage</th>
                <th className="py-2.5 px-3 text-right">Uptime %</th>
                <th className="py-2.5 px-3 text-right">Unmet Demand</th>
                <th className="py-2.5 px-3 text-right">Fairness Penalty</th>
                <th className="py-2.5 px-3 text-center">Violations</th>
                <th className="py-2.5 px-3 text-right">Latency</th>
                <th className="py-2.5 px-4 text-right">Recovery Time</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border">
              {MODES.map((modeKey) => {
                const modeMeta = MODE_LABELS[modeKey] ?? {
                  name: modeKey,
                  desc: "",
                  icon: Layers,
                };
                const Icon = modeMeta.icon;
                const mRes = results ? results[modeKey] : null;
                const isNegotiation = modeKey === "negotiation";

                return (
                  <tr
                    key={modeKey}
                    className={`transition-colors ${
                      isNegotiation
                        ? "bg-accent-dim/30 hover:bg-accent-dim/50"
                        : "hover:bg-surface-2/40"
                    }`}
                  >
                    {/* Mode Name & Description */}
                    <td className="py-3 px-4">
                      <div className="flex items-center gap-2">
                        <Icon
                          className={`w-4 h-4 shrink-0 ${
                            isNegotiation ? "text-accent" : "text-muted"
                          }`}
                        />
                        <div>
                          <div className="flex items-center gap-2">
                            <span className="font-medium text-text">{modeMeta.name}</span>
                            {isNegotiation && (
                              <span className="text-10 uppercase tracking-wider font-semibold text-accent bg-accent-dim px-1.5 py-0.2 rounded border border-accent/30">
                                This System
                              </span>
                            )}
                          </div>
                          <span className="text-11 text-muted block">{modeMeta.desc}</span>
                        </div>
                      </div>
                    </td>

                    {/* Weighted Damage */}
                    <td className="py-3 px-3 text-right tabular-nums">
                      {mRes?.weighted_damage !== undefined ? (
                        <span className="text-text font-medium">
                          {mRes.weighted_damage.toFixed(1)}
                        </span>
                      ) : (
                        <span className="text-muted">—</span>
                      )}
                    </td>

                    {/* Critical Service Uptime % */}
                    <td className="py-3 px-3 text-right tabular-nums">
                      {mRes?.critical_service_uptime_pct !== undefined ? (
                        <span
                          className={`font-medium ${
                            mRes.critical_service_uptime_pct >= 90
                              ? "text-ok"
                              : mRes.critical_service_uptime_pct >= 70
                              ? "text-text"
                              : "text-accent"
                          }`}
                        >
                          {formatPct(mRes.critical_service_uptime_pct)}
                        </span>
                      ) : (
                        <span className="text-muted">—</span>
                      )}
                    </td>

                    {/* Unmet Demand (MWh) */}
                    <td className="py-3 px-3 text-right tabular-nums">
                      {mRes?.unmet_demand_mwh !== undefined ? (
                        <span className="text-text font-medium">
                          {mRes.unmet_demand_mwh.toFixed(1)} MWh
                        </span>
                      ) : (
                        <span className="text-muted">—</span>
                      )}
                    </td>

                    {/* Mean Fairness Penalty */}
                    <td className="py-3 px-3 text-right tabular-nums">
                      {mRes?.mean_fairness_penalty !== undefined ? (
                        <span className="text-muted">
                          {mRes.mean_fairness_penalty.toFixed(4)}
                        </span>
                      ) : (
                        <span className="text-muted">—</span>
                      )}
                    </td>

                    {/* Constraint Violations */}
                    <td className="py-3 px-3 text-center tabular-nums">
                      {mRes?.constraint_violations !== undefined ? (
                        <span
                          className={`inline-block px-1.5 py-0.5 rounded text-11 ${
                            mRes.constraint_violations > 0
                              ? "bg-accent-dim text-accent font-semibold border border-accent/30"
                              : "text-ok font-medium"
                          }`}
                        >
                          {mRes.constraint_violations}
                        </span>
                      ) : (
                        <span className="text-muted">—</span>
                      )}
                    </td>

                    {/* Mean Latency (ms) */}
                    <td className="py-3 px-3 text-right tabular-nums">
                      {mRes?.mean_negotiation_latency_ms !== undefined &&
                      mRes?.mean_negotiation_latency_ms !== null ? (
                        <span className="text-text font-medium">
                          {mRes.mean_negotiation_latency_ms.toFixed(1)} ms
                        </span>
                      ) : (
                        <span className="text-muted">—</span>
                      )}
                    </td>

                    {/* Mean Recovery Time (min) */}
                    <td className="py-3 px-4 text-right tabular-nums">
                      {mRes?.mean_recovery_time_min !== undefined ? (
                        <span className="text-text font-medium">
                          {mRes.mean_recovery_time_min.toFixed(1)} min
                        </span>
                      ) : (
                        <span className="text-muted">—</span>
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>

        {/* Empty State Banner */}
        {!results && (
          <div className="py-4 px-4 bg-surface-2/30 border-t border-border text-center">
            <span className="text-11 text-muted">
              No benchmark run for the current session. Run evaluation above to generate comparison metrics.
            </span>
          </div>
        )}
      </div>

      {/* Plan Protocol Note */}
      {plan?.protocol && (
        <div className="text-11 text-muted px-1">
          <span className="font-medium text-text">Benchmark Protocol:</span> {plan.protocol}
        </div>
      )}
    </div>
  );
}

