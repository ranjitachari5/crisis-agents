export type ScenarioName = "grid_shortage" | "flood_cascade" | "normal";
export type ConsumerId =
  | "hospital_agent"
  | "water_agent"
  | "telecom_agent"
  | "emergency_agent"
  | (string & {});
export type SupplierId = "battery_agent" | "grid_agent";
export type AgentId = ConsumerId | SupplierId | (string & {});
export type SimulationStatus = "idle" | "running" | "paused";
export type AgentStatus = "online" | "isolated" | "disconnected";
export type AgentKind = "consumer" | "storage" | "supply";
export type ApprovalMode = "auto" | "manual";
export type AllocationMode = "negotiation" | "centralized" | "fixed_priority" | "fcfs";
export type ConnectionState = "idle" | "connecting" | "connected" | "reconnecting";

export type MessageType =
  | "supply_report"
  | "request"
  | "bid"
  | "offer"
  | "counteroffer"
  | "concession"
  | "accept"
  | "reject"
  | "peer_request"
  | "emergency_warning"
  | "negotiation_round"
  | "proposal"
  | "validation"
  | "agreement"
  | "system"
  | "event"
  | "claim"
  | "trust_alert"
  | "explanation"
  | "commander_action";

export type MessageStatus =
  | "pending"
  | "delivered"
  | "verified"
  | "accepted"
  | "rejected"
  | "quarantined"
  | "committed"
  | "superseded";

export type TrustDecision = "accepted" | "quarantined" | "escalated" | "rejected";
export type TwinNodeStatus = "ok" | "degraded" | "critical";
export type TwinEdgeKind = "power" | "dependency" | "service";
export type ProposalStatus = "pending" | "validated" | "rejected" | "committed" | "stale";
export type IncidentResolveAction = "confirm_claim" | "dismiss";

export type EventType =
  | "power_reduction"
  | "flood_warning"
  | "hospital_demand_spike"
  | "water_pump_failure"
  | "telecom_outage"
  | "battery_depletion"
  | "agent_disconnect"
  | "agent_reconnect"
  | "recovery";

export type FakeKind =
  | "false_capacity_drop"
  | "fake_disaster_alert"
  | "inflated_bid"
  | "replay_message"
  | "false_recovery"
  | "contradictory_sensors";

export interface ApiErrorBody {
  code: string;
  message: string;
  details: unknown;
}

export interface ApiErrorResponse {
  error: ApiErrorBody;
}

export interface AgentMessage {
  message_id: string;
  seq: number | null;
  round_id: number;
  negotiation_id: string | null;
  tick: number;
  sender: string;
  receiver: string;
  message_type: MessageType;
  resource: string | null;
  quantity: number | null;
  unit: string | null;
  reason: string | null;
  text: string;
  mentions: string[];
  in_reply_to: string | null;
  proposal_id: string | null;
  data: Record<string, unknown>;
  timestamp: string;
  sim_time: string;
  status: MessageStatus;
  signature: string | null;
  trust: { decision?: string; score?: number; summary?: string } | null;
}

export interface AgentMeta {
  display_name: string;
  role: string;
  icon: string;
  color?: string;
}

export interface AgentReputation {
  [agentId: string]: number;
}

export interface ConsumerAgentView extends AgentMeta {
  agent_id: ConsumerId;
  kind: "consumer";
  status: AgentStatus;
  demand_mw: number;
  min_safe_mw: number;
  max_allowed_mw: number;
  allocation_mw: number;
  service_level: number;
  health: number;
  operational_capacity: number;
  active_operations: boolean;
  ticks_below_min: number;
  ticks_conceding: number;
  urgency: number;
  reputation: number | undefined;
  policy: {
    concession_rate: number;
    peer_grant_fraction: number;
    critical_weight: number;
    dependencies: Record<string, number>;
  };
}

export interface BatteryAgentView extends AgentMeta {
  agent_id: "battery_agent";
  kind: "storage";
  status: "online" | "disconnected";
  soc: number;
  reserve_fraction: number;
  capacity_mwh: number;
  usable_energy_mwh: number;
  capability_mw: number;
  discharge_mw: number;
  max_discharge_mw: number;
  reputation: number | undefined;
}

export interface GridAgentView extends AgentMeta {
  agent_id: "grid_agent";
  kind: "supply";
  status: "online";
  nominal_mw: number;
  verified_supply_mw: number | null;
  sensor_status: string;
  sensors: Record<string, number>;
  reserve_margin_mw: number;
  override_mw: number | null;
  reputation: number | undefined;
}

export type AgentView = ConsumerAgentView | BatteryAgentView | GridAgentView;

export type AgentDetail = AgentView & {
  recent_messages: AgentMessage[];
};

export interface ValidationResult {
  valid: boolean;
  degradation_mode: boolean;
  violations: { code: string; detail: string; agent_id: string | null }[];
  checks: { check: string; passed: boolean; detail: string; agent_id: string | null }[];
  total_allocated: number;
  total_supply: number;
  unavoidable_shortages: Record<string, number>;
  battery_discharge: number;
}

export interface AllocationProposal {
  allocation: Record<string, number>;
  base_version: number;
  method: string;
  supply_total: number;
  grid_supply: number;
  battery_offer: number;
  negotiation_id: string | null;
  proposal_id: string;
  objective: Record<string, unknown>;
  rounds: number;
  converged: boolean;
  status: ProposalStatus;
  validation: ValidationResult | Record<string, unknown> | null;
  created_at: string;
  tick: number;
  notes: string[];
}

export interface Agreement {
  version: number;
  proposal_id: string;
  allocation: Record<string, number>;
  method: string;
  committed_by: string;
  tick: number;
  degradation_mode: boolean;
  battery_discharge: number;
  supply_total: number;
  negotiation_id: string | null;
  committed_at: string;
  validation: ValidationResult | Record<string, unknown> | null;
}

export interface NegotiationSummary {
  negotiation_id: string;
  proposal_id: string;
  method: string;
  rounds: number;
  converged: boolean;
  fallback_used: boolean;
  degradation: boolean;
  latency_ms: number;
  demands: Record<string, number>;
  final_positions: Record<string, number>;
  allocation: Record<string, number>;
  supply_total: number;
  battery_offer: number;
  timeline: Record<string, unknown>[];
  outcome?: Record<string, unknown>;
}

export interface Alert {
  id: string;
  severity: string;
  title: string;
  detail: string;
  source: string;
  tick: number;
  sim_time: string;
  active: boolean;
}

export interface Evidence {
  check: string;
  passed: boolean;
  detail: string;
  observed: number | string | null;
  expected: number | string | null;
}

export interface TrustIncident {
  incident_id: string;
  kind: string;
  message_id: string;
  sender: string;
  claim: Record<string, unknown>;
  decision: string;
  trust_score: number;
  evidence: Evidence[];
  summary: string;
  tick: number;
  sim_time: string;
  quarantined: boolean;
  escalated: boolean;
  allocation_version_before: number;
  allocation_version_after: number | null;
  allocation_changed: boolean | null;
  agent_responses: string[];
  resolved: boolean;
  resolution: Record<string, unknown> | null;
  analyst_note: Record<string, unknown> | null;
  created_at: string;
}

export interface QuarantineEntry {
  incident_id: string;
  message: AgentMessage;
}

export interface AuditLog {
  id: string | number;
  session_id?: string;
  tick: number;
  sim_time?: string;
  category: string;
  actor: string;
  action: string;
  details: Record<string, unknown>;
  created_at: string;
}

export interface MetricsSummary {
  ticks: number;
  weighted_damage?: number;
  critical_service_uptime_pct?: number;
  unmet_demand_mwh?: number;
  mean_fairness_penalty?: number;
  constraint_violations?: number;
  physical_load_shed_mwh?: number;
  degradation_ticks?: number;
  negotiations?: number;
  mean_negotiation_latency_ms?: number | null;
  mean_negotiation_rounds?: number | null;
  shortfall_episodes?: number;
  mean_recovery_time_min?: number;
}

export interface TickMetrics {
  tick: number;
  weighted_damage: number;
  unmet_mwh: number;
  critical_met: number;
  critical_total: number;
  fairness_penalty: number;
  constraint_violations: number;
  shed_mw: number;
  degradation: boolean;
  supply_mw: number;
  demand_mw: number;
  allocated_mw: number;
}

export interface ServiceLevel {
  power_service: number;
  asset_service: number;
  effective: number;
  cascade_from: { from: string; loss: number }[];
}

export interface DerivedService {
  label: string;
  level: number;
  inputs: string[];
}

export interface CascadeChain {
  root: string;
  cause: string;
  path: string[];
}

export interface SimulationSnapshot {
  session_id: string;
  status: SimulationStatus;
  scenario: ScenarioName | string;
  seed: number;
  scenario_description: string;
  tick: number;
  sim_time: string;
  minutes_per_tick: number;
  allocation_mode: AllocationMode | string;
  fairness: number;
  approval_mode: ApprovalMode;
  negotiation_paused: boolean;
  frozen: boolean;
  supply: {
    grid_actual_mw: number;
    grid_verified_mw: number | null;
    grid_nominal_mw: number;
    battery_capability_mw: number;
    total_available_mw: number;
    sensor_status: string;
  };
  demand_total_mw: number;
  min_safe_total_mw: number;
  deficit_mw: number;
  degradation_mode: boolean;
  agents: AgentView[];
  allocation: Agreement | null;
  allocation_version: number;
  pending_proposals: AllocationProposal[];
  last_negotiation: NegotiationSummary | null;
  negotiation_count: number;
  alerts: Alert[];
  infrastructure_health: number;
  service_levels: Record<string, ServiceLevel>;
  derived_services: Record<string, DerivedService>;
  cascades: CascadeChain[];
  metrics: MetricsSummary;
  trust: {
    incidents: number;
    open_escalations: number;
    quarantined: number;
    reputation: AgentReputation;
  };
  last_seq: number;
}

export interface TwinNode {
  id: string;
  type: string;
  label: string;
  data: Record<string, unknown> & { status?: TwinNodeStatus };
}

export interface TwinEdge {
  id: string;
  source: string;
  target: string;
  kind: TwinEdgeKind;
  data: Record<string, unknown> & { mw?: number };
}

export interface TwinGraph {
  nodes: TwinNode[];
  edges: TwinEdge[];
  cascades: CascadeChain[];
  service_levels: Record<string, ServiceLevel>;
  derived_services: Record<string, DerivedService>;
  battery_soc?: number;
}

export interface EventCatalogEntry {
  label: string;
  params: Record<string, string | string[]>;
  description?: string;
}

export interface EventCatalog {
  events: Record<string, EventCatalogEntry>;
  fake_events: Record<string, EventCatalogEntry>;
}

export interface EvaluationPlan {
  modes: Record<string, string>;
  metrics: Record<string, string>;
  protocol: string;
}

export interface EvaluationModeResult extends MetricsSummary {
  wall_time_s: number;
  messages_exchanged: number;
}

export interface EvaluationRun {
  run_id: string;
  scenario: string;
  seed: number;
  ticks: number;
  fairness: number;
  minutes_per_tick?: number;
  modes: string[];
  results: Record<string, EvaluationModeResult>;
  metric_definitions: Record<string, string>;
  duration_s: number;
  created_at?: string;
}

export interface HealthResponse {
  status: string;
  version: string;
  database: boolean;
  llm: Record<string, unknown>;
  simulation_status: string;
  session_id: string;
  run_id: string;
}

export type WsEventType =
  | "snapshot"
  | "message"
  | "message_status"
  | "state"
  | "agreement"
  | "negotiation"
  | "trust_incident"
  | "audit"
  | "alert"
  | "reset"
  | "pong"
  | "error";

export interface WsEnvelope {
  event_seq?: number;
  type: WsEventType | string;
  data?: unknown;
  server_time?: string;
}

export interface WsSnapshotData {
  state: SimulationSnapshot;
  messages: AgentMessage[];
  incidents: TrustIncident[];
}

export interface MessageStatusEvent {
  message_id: string;
  seq: number;
  status: MessageStatus;
}

export interface ResetEvent {
  session_id: string;
}

export interface CurrentAllocations {
  version: number;
  agreement: Agreement | null;
  pending: AllocationProposal[];
}

export interface NegotiationHistory {
  session_id: string;
  messages: AgentMessage[];
  negotiations: NegotiationSummary[];
  last_seq: number;
}

export interface CreateAgentRequest {
  agent_id: string;
  name: string;
  role?: string;
  icon?: string;
  color?: string;
  base_demand: number;
  min_safe: number;
  max_allowed: number;
  damage_weight?: number;
  critical_weight?: number;
  concession_rate?: number;
  peer_grant_fraction?: number;
  feeder?: "feeder_north" | "feeder_south";
  dependencies?: Record<string, number>;
  start_negotiation?: boolean;
}
