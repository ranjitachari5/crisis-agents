import { useState, useEffect, useCallback } from "react";
import { FlaskConical } from "lucide-react";
import { EventInjector } from "@/components/EventInjector";
import { EventHistoryList } from "@/components/EventHistoryList";
import { EvaluationPanel } from "@/components/EvaluationPanel";
import { api } from "@/services/api";
import { useSimStore } from "@/store/useSimStore";
import type { EventCatalog, EvaluationPlan } from "@/types/api";

export function LabSection() {
  const snapshot = useSimStore((s) => s.snapshot);
  const [catalog, setCatalog] = useState<EventCatalog | null>(null);
  const [history, setHistory] = useState<Record<string, unknown>[]>([]);
  const [plan, setPlan] = useState<EvaluationPlan | null>(null);
  const [isLoadingHistory, setIsLoadingHistory] = useState(false);

  // Fetch initial catalog, history, and evaluation plan
  const fetchCatalogAndPlan = useCallback(async () => {
    try {
      const [catRes, planRes] = await Promise.all([
        api.events.catalog(),
        api.evaluation.plan(),
      ]);
      setCatalog(catRes);
      setPlan(planRes);
    } catch (err) {
      console.warn("Failed fetching simulation catalog or plan:", err);
    }
  }, []);

  const fetchHistory = useCallback(async () => {
    setIsLoadingHistory(true);
    try {
      const histRes = await api.events.history();
      setHistory(histRes);
    } catch (err) {
      console.warn("Failed fetching event history:", err);
    } finally {
      setIsLoadingHistory(false);
    }
  }, []);

  useEffect(() => {
    fetchCatalogAndPlan();
    fetchHistory();
  }, [fetchCatalogAndPlan, fetchHistory]);

  const scenario = snapshot?.scenario ?? "flood_cascade";
  const fairness = snapshot?.fairness ?? 0.5;

  return (
    <section id="simulation-lab" className="scroll-mt-16 space-y-6">
      {/* Section Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 pb-1 border-b border-border">
        <div>
          <div className="flex items-center gap-2">
            <span className="text-11 uppercase font-semibold tracking-wider text-muted">
              Experimentation
            </span>
            <span className="text-border">/</span>
            <span className="text-11 text-muted">Stress Tests & Benchmarks</span>
          </div>
          <h1 className="text-20 font-semibold text-text flex items-center gap-2">
            <FlaskConical className="w-5 h-5 text-accent" />
            <span>Simulation Lab</span>
          </h1>
        </div>
      </div>

      {/* Top Half: Event Injector + History */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-4 items-stretch">
        <div className="lg:col-span-7">
          <EventInjector catalog={catalog} onEventInjected={fetchHistory} />
        </div>
        <div className="lg:col-span-5">
          <EventHistoryList
            history={history}
            isLoading={isLoadingHistory}
            onRefresh={fetchHistory}
          />
        </div>
      </div>

      {/* Bottom Half: Evaluation Benchmark Panel & 4x7 Matrix */}
      <EvaluationPanel plan={plan} scenario={scenario} fairness={fairness} />
    </section>
  );
}
