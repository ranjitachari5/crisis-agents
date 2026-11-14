import { useEffect, useRef } from "react";
import { SimulationSocketService } from "@/services/socket";
import { useSimStore } from "@/store/useSimStore";
import type {
  AgentMessage,
  Agreement,
  Alert,
  AuditLog,
  MessageStatusEvent,
  ResetEvent,
  SimulationSnapshot,
  TrustIncident,
  WsEnvelope,
} from "@/types/api";

export function useSimulationSocket() {
  const serviceRef = useRef<SimulationSocketService | null>(null);

  const setConnectionState = useSimStore((s) => s.setConnectionState);
  const ingestSnapshot = useSimStore((s) => s.ingestSnapshot);
  const ingestLiveMessage = useSimStore((s) => s.ingestLiveMessage);
  const ingestMessageStatus = useSimStore((s) => s.ingestMessageStatus);
  const ingestStateUpdate = useSimStore((s) => s.ingestStateUpdate);
  const ingestAgreement = useSimStore((s) => s.ingestAgreement);
  const ingestTrustIncident = useSimStore((s) => s.ingestTrustIncident);
  const ingestAuditLog = useSimStore((s) => s.ingestAuditLog);
  const ingestAlert = useSimStore((s) => s.ingestAlert);
  const handleReset = useSimStore((s) => s.handleReset);

  useEffect(() => {
    const service = new SimulationSocketService({
      onConnectionChange: (state) => {
        setConnectionState(state);
      },
      onSnapshot: (data, eventSeq) => {
        ingestSnapshot(data, eventSeq);
      },
      onEvent: (env: WsEnvelope, isLive: boolean) => {
        switch (env.type) {
          case "message":
            ingestLiveMessage(env.data as AgentMessage, isLive);
            break;
          case "message_status":
            ingestMessageStatus(env.data as MessageStatusEvent);
            break;
          case "state":
            ingestStateUpdate(env.data as SimulationSnapshot, isLive);
            break;
          case "agreement":
            ingestAgreement(env.data as Agreement);
            break;
          case "trust_incident":
            ingestTrustIncident(env.data as TrustIncident);
            break;
          case "audit":
            ingestAuditLog(env.data as AuditLog);
            break;
          case "alert":
            ingestAlert(env.data as Alert);
            break;
          case "reset":
            handleReset(env.data as ResetEvent);
            break;
          default:
            break;
        }
      },
      onError: (err) => {
        console.warn("WebSocket error:", err);
      },
    });

    serviceRef.current = service;
    service.connect();

    return () => {
      service.disconnect();
      serviceRef.current = null;
    };
  }, [
    setConnectionState,
    ingestSnapshot,
    ingestLiveMessage,
    ingestMessageStatus,
    ingestStateUpdate,
    ingestAgreement,
    ingestTrustIncident,
    ingestAuditLog,
    ingestAlert,
    handleReset,
  ]);

  return serviceRef;
}

