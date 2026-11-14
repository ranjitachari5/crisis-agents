import type { ConnectionState } from "@/types/api";

interface Props {
  state: ConnectionState;
}

export function ConnectionBadge({ state }: Props) {
  const isConnected = state === "connected";
  const isReconnecting = state === "reconnecting";

  const dotClass = isConnected
    ? "bg-ok"
    : isReconnecting
    ? "bg-accent"
    : "bg-muted";

  const label =
    state === "connected"
      ? "Connected"
      : state === "reconnecting"
      ? "Reconnecting"
      : state === "connecting"
      ? "Connecting"
      : "Disconnected";

  return (
    <div
      className="inline-flex items-center gap-1.5 text-12 text-muted select-none"
      title={`Live stream status: ${label}`}
    >
      <span className={`w-1.5 h-1.5 rounded-full ${dotClass}`} />
      <span>{label}</span>
    </div>
  );
}

