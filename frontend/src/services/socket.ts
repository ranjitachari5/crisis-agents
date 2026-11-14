import { BACKOFF_INITIAL_MS, BACKOFF_MAX_MS, PING_INTERVAL_MS } from "@/lib/constants";
import { useAuthStore } from "@/store/useAuthStore";
import type { ConnectionState, WsEnvelope, WsSnapshotData } from "@/types/api";

export type SocketEventHandler = {
  onConnectionChange: (state: ConnectionState) => void;
  onSnapshot: (data: WsSnapshotData, eventSeq: number) => void;
  onEvent: (envelope: WsEnvelope, isLive: boolean) => void;
  onError: (err: unknown) => void;
};

export class SimulationSocketService {
  private ws: WebSocket | null = null;
  private pingTimer: number | null = null;
  private reconnectTimer: number | null = null;
  private reconnectAttempts = 0;
  private lastEventSeq = 0;
  private isExplicitlyClosed = false;
  private handlers: SocketEventHandler | null = null;
  private isSyncing = false;

  constructor(handlers: SocketEventHandler) {
    this.handlers = handlers;
  }

  public setLastSeq(seq: number) {
    if (seq > this.lastEventSeq) {
      this.lastEventSeq = seq;
    }
  }

  public getLastSeq(): number {
    return this.lastEventSeq;
  }

  public connect(): void {
    this.isExplicitlyClosed = false;
    this.cleanupSocket();

    const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
    const host = window.location.host;
    const url = `${protocol}//${host}/ws/simulation`;

    this.handlers?.onConnectionChange(
      this.lastEventSeq > 0 ? "reconnecting" : "connecting"
    );

    try {
      this.ws = new WebSocket(url);
    } catch (err) {
      this.handlers?.onError(err);
      this.scheduleReconnect();
      return;
    }

    this.ws.onopen = () => {
      this.reconnectAttempts = 0;
      this.startPing();

      // Send auth frame if a token is configured.
      // Backend expects {"type": "auth", "token": "<token>"} as the first frame
      // when VIEWER_AUTH_TOKEN is set. When viewer routes are public (default dev
      // mode), the server accepts connections without auth, but sending auth with
      // a valid commander/admin token still works and returns auth_ok.
      const token = useAuthStore.getState().token;
      if (token) {
        this.send({ type: "auth", token });
      }

      if (this.lastEventSeq > 0) {
        // Reconnected: request missed events from last seq
        this.isSyncing = true;
        this.send({ type: "sync", since: this.lastEventSeq });
      }

      this.handlers?.onConnectionChange("connected");
    };

    this.ws.onmessage = (event) => {
      try {
        const raw = JSON.parse(event.data);
        this.handleMessage(raw);
      } catch (err) {
        console.error("Failed to parse WebSocket frame:", err);
      }
    };

    this.ws.onerror = (err) => {
      this.handlers?.onError(err);
    };

    this.ws.onclose = () => {
      this.stopPing();
      if (!this.isExplicitlyClosed) {
        this.handlers?.onConnectionChange("reconnecting");
        this.scheduleReconnect();
      } else {
        this.handlers?.onConnectionChange("idle");
      }
    };
  }

  private handleMessage(msg: WsEnvelope): void {
    if (msg.event_seq !== undefined && msg.event_seq > this.lastEventSeq) {
      this.lastEventSeq = msg.event_seq;
    }

    if (msg.type === "pong") {
      return;
    }

    if (msg.type === "snapshot") {
      this.isSyncing = false;
      const data = msg.data as WsSnapshotData;
      this.handlers?.onSnapshot(data, msg.event_seq ?? this.lastEventSeq);
      return;
    }

    // If we're syncing and receiving replayed frames, isLive = false
    const isLive = !this.isSyncing;
    this.handlers?.onEvent(msg, isLive);

    // After processing events up to the latest, syncing clears
    if (this.isSyncing) {
      this.isSyncing = false;
    }
  }

  public send(payload: unknown): void {
    if (this.ws && this.ws.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify(payload));
    }
  }

  public disconnect(): void {
    this.isExplicitlyClosed = true;
    this.stopPing();
    this.clearReconnectTimer();
    this.cleanupSocket();
    this.handlers?.onConnectionChange("idle");
  }

  private cleanupSocket(): void {
    if (this.ws) {
      this.ws.onopen = null;
      this.ws.onmessage = null;
      this.ws.onerror = null;
      this.ws.onclose = null;
      try {
        this.ws.close();
      } catch {
        // ignore close exceptions
      }
      this.ws = null;
    }
  }

  private startPing(): void {
    this.stopPing();
    this.pingTimer = window.setInterval(() => {
      this.send({ type: "ping" });
    }, PING_INTERVAL_MS);
  }

  private stopPing(): void {
    if (this.pingTimer !== null) {
      clearInterval(this.pingTimer);
      this.pingTimer = null;
    }
  }

  private scheduleReconnect(): void {
    this.clearReconnectTimer();
    this.reconnectAttempts++;
    const backoff = Math.min(
      BACKOFF_MAX_MS,
      BACKOFF_INITIAL_MS * Math.pow(1.5, this.reconnectAttempts - 1)
    );
    this.reconnectTimer = window.setTimeout(() => {
      this.connect();
    }, backoff);
  }

  private clearReconnectTimer(): void {
    if (this.reconnectTimer !== null) {
      clearTimeout(this.reconnectTimer);
      this.reconnectTimer = null;
    }
  }
}

