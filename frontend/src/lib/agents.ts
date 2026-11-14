import type { AgentId, ConsumerId } from "@/types/api";
import { HUB_NODE_ID } from "@/lib/constants";

export interface AgentDef {
  id: AgentId;
  name: string;
  icon: string;
  role: string;
  canIsolate: boolean;
}

export const CONSUMER_IDS: ConsumerId[] = [
  "hospital_agent",
  "water_agent",
  "telecom_agent",
  "emergency_agent",
];

export const AGENT_IDS: AgentId[] = [
  "hospital_agent",
  "water_agent",
  "telecom_agent",
  "emergency_agent",
  "battery_agent",
  "grid_agent",
];

export const AGENTS: Record<AgentId, AgentDef> = {
  hospital_agent: {
    id: "hospital_agent",
    name: "Hospital Agent",
    icon: "HeartPulse",
    role: "Critical care & ICU",
    canIsolate: true,
  },
  water_agent: {
    id: "water_agent",
    name: "Water Agent",
    icon: "Droplets",
    role: "Water treatment & pumping",
    canIsolate: true,
  },
  telecom_agent: {
    id: "telecom_agent",
    name: "Telecom Agent",
    icon: "RadioTower",
    role: "Emergency communications",
    canIsolate: true,
  },
  emergency_agent: {
    id: "emergency_agent",
    name: "Emergency Services Agent",
    icon: "Siren",
    role: "Rescue & firefighting",
    canIsolate: true,
  },
  battery_agent: {
    id: "battery_agent",
    name: "Battery Agent",
    icon: "BatteryCharging",
    role: "Grid-scale storage",
    canIsolate: false,
  },
  grid_agent: {
    id: "grid_agent",
    name: "Grid Agent",
    icon: "Zap",
    role: "Supply & grid telemetry",
    canIsolate: false,
  },
};

export const TWIN_NODE_TO_AGENT: Record<string, AgentId | null> = {
  grid_agent: "grid_agent",
  battery_agent: "battery_agent",
  hospital_agent: "hospital_agent",
  water_agent: "water_agent",
  telecom_agent: "telecom_agent",
  emergency_agent: "emergency_agent",
  power_bus: null,
  svc_icu: null,
  svc_hospital_water: null,
  svc_firefighting: null,
  svc_dispatch: null,
};

export function isAgentId(id: string): id is AgentId {
  return id in AGENTS;
}

export function isConsumerId(id: string): id is ConsumerId {
  return CONSUMER_IDS.includes(id as ConsumerId);
}

export function agentName(id: string): string {
  return isAgentId(id) ? AGENTS[id].name : id.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}

export function getAgentDef(id: string, name?: string): AgentDef {
  if (id in AGENTS) return AGENTS[id as AgentId];
  return {
    id: id as AgentId,
    name: name || id.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase()),
    icon: "Cpu",
    role: "Autonomous Utility",
    canIsolate: true,
  };
}

export function edgeId(a: string, b: string): string {
  return [a, b].sort().join("|");
}

export function hubEdgeId(agentId: string): string {
  return edgeId(agentId, HUB_NODE_ID);
}

export function mapTwinNodeToAgent(nodeId: string): AgentId | null {
  if (nodeId in TWIN_NODE_TO_AGENT) {
    return TWIN_NODE_TO_AGENT[nodeId];
  }
  return isAgentId(nodeId) ? nodeId : null;
}
