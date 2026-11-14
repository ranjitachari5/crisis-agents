export const COMMANDER_NAME = "Commander";

export const SECTIONS = [
  { id: "overview", label: "Overview" },
  { id: "live-negotiation", label: "Live Negotiation" },
  { id: "city-digital-twin", label: "City Digital Twin" },
  { id: "agent-network", label: "Agent Network" },
  { id: "crisis-trust-engine", label: "Crisis Trust Engine" },
  { id: "resource-allocation", label: "Resource Allocation" },
  { id: "simulation-lab", label: "Simulation Lab" },
  { id: "audit-logs", label: "Audit Logs" },
] as const;

export const HUB_NODE_ID = "negotiation_group";

export const REQUEST_HIGHLIGHT_MS = 3000;
export const GRID_SUPPLY_FLASH_MS = 1200;
export const EDGE_HIGHLIGHT_MS = 2000;
export const EDGE_DOT_MS = 800;
export const CASCADE_STAGGER_MS = 150;

export const PING_INTERVAL_MS = 25_000;
export const BACKOFF_INITIAL_MS = 500;
export const BACKOFF_MAX_MS = 10_000;
export const SYNC_SETTLE_MS = 80;

export const EVENT_LABELS: Record<string, string> = {
  power_reduction: "Power shortage",
  flood_warning: "Flood",
  hospital_demand_spike: "Hospital demand spike",
  water_pump_failure: "Water pumping failure",
  telecom_outage: "Telecom outage",
  agent_disconnect: "Disconnect agent",
  recovery: "Restore supply",
};
