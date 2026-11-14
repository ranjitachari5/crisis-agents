import { create } from "zustand";
import { edgeId, isAgentId } from "@/lib/agents";
import { HUB_NODE_ID } from "@/lib/constants";
import { isRequestHighlight, type ChatFilter } from "@/lib/messageKinds";
import type {
  AgentDetail,
  AgentId,
  AgentMessage,
  Agreement,
  Alert,
  AllocationProposal,
  AuditLog,
  ConnectionState,
  MessageStatusEvent,
  QuarantineEntry,
  ResetEvent,
  SimulationSnapshot,
  TrustIncident,
  TwinGraph,
  WsSnapshotData,
} from "@/types/api";

export interface AgentActivityItem {
  at: number;
  quantity: number | null;
  unit: string | null;
  isSupplyFlash?: boolean;
}

export interface SupplyDemandPoint {
  tick: number;
  supply: number;
  demand: number;
  allocated: number;
}

export interface SimStoreState {
  // Connection
  connectionState: ConnectionState;
  lastEventSeq: number;

  // Snapshot / Simulation State
  snapshot: SimulationSnapshot | null;
  twinGraph: TwinGraph | null;

  // Real-time Lists
  messages: AgentMessage[];
  proposals: AllocationProposal[];
  agreements: Agreement[];
  incidents: TrustIncident[];
  reputation: Record<string, number>;
  quarantine: QuarantineEntry[];
  alerts: Alert[];
  auditLogs: AuditLog[];

  // Charts
  liveSupplyDemandSeries: SupplyDemandPoint[];

  // Highlighting & Activity (live frames only)
  activity: Record<string, AgentActivityItem>;
  edgeActivity: Record<string, number>;

  // UI state
  chatFilter: ChatFilter;
  selectedAgentId: AgentId | null;
  selectedAgentDetail: AgentDetail | null;
  isDrawerOpen: boolean;

  // Actions
  setConnectionState: (state: ConnectionState) => void;
  ingestSnapshot: (data: WsSnapshotData, eventSeq: number) => void;
  ingestLiveMessage: (message: AgentMessage, isLive: boolean) => void;
  ingestMessageStatus: (statusEvent: MessageStatusEvent) => void;
  ingestStateUpdate: (state: SimulationSnapshot, isLive: boolean) => void;
  ingestAgreement: (agreement: Agreement) => void;
  ingestTrustIncident: (incident: TrustIncident) => void;
  ingestAuditLog: (log: AuditLog) => void;
  ingestAlert: (alert: Alert) => void;
  handleReset: (event: ResetEvent) => void;

  setTwinGraph: (graph: TwinGraph) => void;
  setChatFilter: (filter: ChatFilter) => void;
  setSelectedAgent: (agentId: AgentId | null, detail?: AgentDetail | null) => void;
  setDrawerOpen: (open: boolean) => void;
  acknowledgeAlert: (alertId: string) => void;
  clearExpiredActivity: (now?: number) => void;
}

export const useSimStore = create<SimStoreState>((set, get) => ({
  connectionState: "idle",
  lastEventSeq: 0,
  snapshot: null,
  twinGraph: null,

  messages: [],
  proposals: [],
  agreements: [],
  incidents: [],
  reputation: {},
  quarantine: [],
  alerts: [],
  auditLogs: [],

  liveSupplyDemandSeries: [],
  activity: {},
  edgeActivity: {},

  chatFilter: "all",
  selectedAgentId: null,
  selectedAgentDetail: null,
  isDrawerOpen: false,

  setConnectionState: (connectionState) => set({ connectionState }),

  ingestSnapshot: (data, eventSeq) => {
    const s = data.state;
    set({
      snapshot: s,
      lastEventSeq: Math.max(get().lastEventSeq, eventSeq),
      messages: data.messages ?? [],
      incidents: data.incidents ?? [],
      proposals: s.pending_proposals ?? [],
      agreements: s.allocation ? [s.allocation] : [],
      alerts: s.alerts ?? [],
      reputation: s.trust?.reputation ?? {},
      // Do NOT trigger any highlights on snapshot load
    });
  },

  ingestLiveMessage: (msg, isLive) => {
    set((state) => {
      // Upsert by message_id
      const existingIdx = state.messages.findIndex(
        (m) => m.message_id === msg.message_id
      );
      let updatedMessages = state.messages;
      if (existingIdx >= 0) {
        updatedMessages = [...state.messages];
        updatedMessages[existingIdx] = msg;
      } else {
        updatedMessages = [...state.messages, msg];
      }

      // If this is NOT a live frame (e.g. sync replay or historical merge), skip animation
      if (!isLive) {
        return { messages: updatedMessages };
      }

      const now = Date.now();
      const newActivity = { ...state.activity };
      const newEdgeActivity = { ...state.edgeActivity };

      // Highlight logic for Agent Card
      if (msg.status !== "quarantined") {
        if (isRequestHighlight(msg.message_type) && isAgentId(msg.sender)) {
          newActivity[msg.sender] = {
            at: now,
            quantity: msg.quantity ?? null,
            unit: msg.unit ?? "MW",
            isSupplyFlash: false,
          };
        } else if (msg.sender === "grid_agent" && msg.message_type === "supply_report") {
          // Quiet 1px white flash for grid supply report
          newActivity["grid_agent"] = {
            at: now,
            quantity: msg.quantity ?? null,
            unit: msg.unit ?? "MW",
            isSupplyFlash: true,
          };
        }
      }

      // Highlight logic for Agent Network Edge
      if (msg.receiver === HUB_NODE_ID || msg.receiver === "negotiation_group") {
        if (isAgentId(msg.sender)) {
          const eId = edgeId(msg.sender, HUB_NODE_ID);
          newEdgeActivity[eId] = now;
        }
      } else if (isAgentId(msg.sender) && isAgentId(msg.receiver)) {
        const eId = edgeId(msg.sender, msg.receiver);
        newEdgeActivity[eId] = now;
      }

      return {
        messages: updatedMessages,
        activity: newActivity,
        edgeActivity: newEdgeActivity,
      };
    });
  },

  ingestMessageStatus: (statusEvent) => {
    set((state) => {
      const idx = state.messages.findIndex(
        (m) => m.message_id === statusEvent.message_id
      );
      if (idx === -1) {
        return state; // never insert a new message on message_status
      }
      const updated = [...state.messages];
      updated[idx] = {
        ...updated[idx],
        status: statusEvent.status,
      };
      return { messages: updated };
    });
  },

  ingestStateUpdate: (newState, isLive) => {
    set((state) => {
      const totalAvailable = newState.supply?.total_available_mw ?? 0;
      const totalDemand = newState.demand_total_mw ?? 0;
      const allocated =
        newState.allocation?.allocation
          ? Object.values(newState.allocation.allocation).reduce((a, b) => a + b, 0)
          : 0;

      let newSeries = state.liveSupplyDemandSeries;
      // Only append live state events received since page load
      if (isLive) {
        newSeries = [
          ...state.liveSupplyDemandSeries,
          {
            tick: newState.tick,
            supply: totalAvailable,
            demand: totalDemand,
            allocated,
          },
        ];
      }

      return {
        snapshot: newState,
        proposals: newState.pending_proposals ?? state.proposals,
        alerts: newState.alerts ?? state.alerts,
        reputation: newState.trust?.reputation ?? state.reputation,
        liveSupplyDemandSeries: newSeries,
      };
    });
  },

  ingestAgreement: (agreement) => {
    set((state) => {
      const existing = state.agreements.some(
        (a) => a.version === agreement.version
      );
      const agreements = existing
        ? state.agreements
        : [agreement, ...state.agreements];

      // Remove accepted proposal from pending list if present
      const proposals = state.proposals.filter(
        (p) => p.proposal_id !== agreement.proposal_id
      );

      return { agreements, proposals };
    });
  },

  ingestTrustIncident: (incident) => {
    set((state) => {
      const idx = state.incidents.findIndex(
        (i) => i.incident_id === incident.incident_id
      );
      let incidents = state.incidents;
      if (idx >= 0) {
        incidents = [...state.incidents];
        incidents[idx] = incident;
      } else {
        incidents = [incident, ...state.incidents];
      }
      return { incidents };
    });
  },

  ingestAuditLog: (log) => {
    set((state) => ({
      auditLogs: [log, ...state.auditLogs].slice(0, 500),
    }));
  },

  ingestAlert: (alert) => {
    set((state) => {
      const idx = state.alerts.findIndex((a) => a.id === alert.id);
      let alerts = state.alerts;
      if (idx >= 0) {
        alerts = [...state.alerts];
        alerts[idx] = alert;
      } else {
        alerts = [alert, ...state.alerts];
      }
      return { alerts };
    });
  },

  handleReset: () => {
    set({
      messages: [],
      proposals: [],
      agreements: [],
      incidents: [],
      alerts: [],
      liveSupplyDemandSeries: [],
      activity: {},
      edgeActivity: {},
    });
  },

  setTwinGraph: (twinGraph) => set({ twinGraph }),
  setChatFilter: (chatFilter) => set({ chatFilter }),
  setSelectedAgent: (selectedAgentId, selectedAgentDetail = null) =>
    set({ selectedAgentId, selectedAgentDetail, isDrawerOpen: !!selectedAgentId }),
  setDrawerOpen: (isDrawerOpen) => set({ isDrawerOpen }),

  acknowledgeAlert: (alertId) => {
    set((state) => ({
      alerts: state.alerts.map((a) =>
        a.id === alertId ? { ...a, active: false } : a
      ),
    }));
  },

  clearExpiredActivity: (now = Date.now()) => {
    const { activity, edgeActivity } = get();
    let activityChanged = false;
    let edgeChanged = false;

    const newActivity = { ...activity };
    for (const [k, v] of Object.entries(activity)) {
      if (now - v.at > 3500) {
        delete newActivity[k];
        activityChanged = true;
      }
    }

    const newEdgeActivity = { ...edgeActivity };
    for (const [k, at] of Object.entries(edgeActivity)) {
      if (now - at > 2500) {
        delete newEdgeActivity[k];
        edgeChanged = true;
      }
    }

    if (activityChanged || edgeChanged) {
      set({
        activity: activityChanged ? newActivity : activity,
        edgeActivity: edgeChanged ? newEdgeActivity : edgeActivity,
      });
    }
  },
}));
