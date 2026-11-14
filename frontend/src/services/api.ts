import { ApiError } from "@/lib/errors";
import type {
  AgentDetail,
  AgentId,
  AgentView,
  Agreement,
  Alert,
  AllocationProposal,
  AuditLog,
  ConsumerId,
  CurrentAllocations,
  EvaluationPlan,
  EvaluationRun,
  EventCatalog,
  EventType,
  FakeKind,
  HealthResponse,
  IncidentResolveAction,
  NegotiationHistory,
  QuarantineEntry,
  ScenarioName,
  SimulationSnapshot,
  TickMetrics,
  TrustIncident,
  TwinGraph,
  ValidationResult,
} from "@/types/api";

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers);
  if (init.body !== undefined && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }
  const res = await fetch(path, { ...init, headers });
  if (!res.ok) {
    throw await ApiError.fromResponse(res);
  }
  if (res.status === 204) {
    return undefined as T;
  }
  return (await res.json()) as T;
}

function jsonBody(body: unknown): RequestInit {
  return { body: JSON.stringify(body) };
}

export const api = {
  health: () => request<HealthResponse>("/api/health"),
  meta: () => request<Record<string, unknown>>("/api/meta"),

  simulation: {
    start: () => request<{ status: string }>("/api/simulation/start", { method: "POST" }),
    pause: () => request<{ status: string }>("/api/simulation/pause", { method: "POST" }),
    resume: () => request<{ status: string }>("/api/simulation/resume", { method: "POST" }),
    reset: (body?: { scenario?: ScenarioName; seed?: number }) =>
      request<SimulationSnapshot>("/api/simulation/reset", {
        method: "POST",
        ...jsonBody(body ?? {}),
      }),
    step: (ticks = 1) =>
      request<SimulationSnapshot>("/api/simulation/step", {
        method: "POST",
        ...jsonBody({ ticks }),
      }),
    state: () => request<SimulationSnapshot>("/api/simulation/state"),
    fairness: (value: number) =>
      request<{ fairness: number; negotiation: unknown }>(
        "/api/simulation/fairness",
        { method: "PUT", ...jsonBody({ value }) },
      ),
    settings: (body: { approval_mode?: "auto" | "manual"; tick_interval_s?: number }) =>
      request<Record<string, unknown>>("/api/simulation/settings", {
        method: "PUT",
        ...jsonBody(body),
      }),
    metrics: (last = 96) =>
      request<{ summary: Record<string, unknown>; series: TickMetrics[] }>(
        `/api/simulation/metrics?last=${last}`,
      ),
  },

  events: {
    inject: (event_type: EventType | string, params: Record<string, unknown> = {}) =>
      request<Record<string, unknown>>("/api/events/inject", {
        method: "POST",
        ...jsonBody({ event_type, params }),
      }),
    injectFake: (kind: FakeKind = "false_capacity_drop", params: Record<string, unknown> = {}) =>
      request<Record<string, unknown>>("/api/events/inject-fake", {
        method: "POST",
        ...jsonBody({ kind, params }),
      }),
    history: () => request<Record<string, unknown>[]>("/api/events/history"),
    catalog: () => request<EventCatalog>("/api/events/catalog"),
  },

  agents: {
    list: () => request<AgentView[]>("/api/agents"),
    get: (agentId: AgentId) => request<AgentDetail>(`/api/agents/${agentId}`),
  },

  negotiation: {
    start: (reason?: string) =>
      request<Record<string, unknown>>("/api/negotiation/start", {
        method: "POST",
        ...jsonBody({ reason: reason ?? "commander requested reassessment" }),
      }),
    pause: () =>
      request<{ negotiation_paused: boolean }>("/api/negotiation/pause", { method: "POST" }),
    resume: () =>
      request<{ negotiation_paused: boolean }>("/api/negotiation/resume", { method: "POST" }),
    history: (opts?: { since_seq?: number; limit?: number; negotiation_id?: string }) => {
      const q = new URLSearchParams();
      if (opts?.since_seq !== undefined) q.set("since_seq", String(opts.since_seq));
      if (opts?.limit !== undefined) q.set("limit", String(opts.limit));
      if (opts?.negotiation_id) q.set("negotiation_id", opts.negotiation_id);
      const qs = q.toString();
      return request<NegotiationHistory>(`/api/negotiation/history${qs ? `?${qs}` : ""}`);
    },
  },

  allocations: {
    current: () => request<CurrentAllocations>("/api/allocations/current"),
    history: () => request<Agreement[]>("/api/allocations/history"),
    validate: (body: { allocation: Record<ConsumerId, number> } | { proposal_id: string }) =>
      request<ValidationResult>("/api/allocations/validate", {
        method: "POST",
        ...jsonBody(body),
      }),
    commit: (proposal_id: string) =>
      request<Record<string, unknown>>("/api/allocations/commit", {
        method: "POST",
        ...jsonBody({ proposal_id }),
      }),
    reject: (proposal_id: string, reason: string) =>
      request<AllocationProposal | Record<string, unknown>>("/api/allocations/reject", {
        method: "POST",
        ...jsonBody({ proposal_id, reason }),
      }),
  },

  trust: {
    incidents: () => request<TrustIncident[]>("/api/trust/incidents"),
    incident: (id: string) => request<TrustIncident>(`/api/trust/incidents/${id}`),
    resolve: (id: string, action: IncidentResolveAction, note = "", confirmed_supply_mw?: number) =>
      request<TrustIncident>(`/api/trust/incidents/${id}/resolve`, {
        method: "POST",
        ...jsonBody({
          action,
          note,
          ...(confirmed_supply_mw !== undefined ? { confirmed_supply_mw } : {}),
        }),
      }),
    reputation: () => request<Record<string, number>>("/api/trust/reputation"),
    quarantine: () => request<QuarantineEntry[]>("/api/trust/quarantine"),
  },

  audit: {
    logs: (opts?: { limit?: number; category?: string; all_sessions?: boolean }) => {
      const q = new URLSearchParams();
      if (opts?.limit !== undefined) q.set("limit", String(opts.limit));
      if (opts?.category) q.set("category", opts.category);
      if (opts?.all_sessions) q.set("all_sessions", "true");
      const qs = q.toString();
      return request<AuditLog[]>(`/api/audit/logs${qs ? `?${qs}` : ""}`);
    },
  },

  commander: {
    explain: (question?: string) =>
      request<Record<string, unknown>>("/api/commander/explain", {
        method: "POST",
        ...jsonBody({ question: question ?? null }),
      }),
    isolate: (agentId: ConsumerId, reason?: string) =>
      request<Record<string, unknown>>(`/api/commander/agents/${agentId}/isolate`, {
        method: "POST",
        ...jsonBody({ reason: reason ?? "suspicious behaviour reported by trust engine" }),
      }),
    restore: (agentId: ConsumerId) =>
      request<Record<string, unknown>>(`/api/commander/agents/${agentId}/restore`, {
        method: "POST",
      }),
    override: (allocation: Record<ConsumerId, number>, reason: string, authorization: string) =>
      request<Record<string, unknown>>("/api/commander/override", {
        method: "POST",
        ...jsonBody({ allocation, reason, authorization }),
      }),
    acknowledgeAlert: (alertId: string) =>
      request<Alert>(`/api/commander/alerts/${alertId}/acknowledge`, { method: "POST" }),
  },

  evaluation: {
    plan: () => request<EvaluationPlan>("/api/evaluation/plan"),
    run: (body?: {
      scenario?: ScenarioName;
      seed?: number;
      ticks?: number;
      fairness?: number;
      modes?: string[];
    }) =>
      request<EvaluationRun>("/api/evaluation/run", {
        method: "POST",
        ...jsonBody(body ?? {}),
      }),
    results: (limit = 10) => request<EvaluationRun[]>(`/api/evaluation/results?limit=${limit}`),
  },

  twin: {
    graph: () => request<TwinGraph>("/api/twin/graph"),
  },
};
