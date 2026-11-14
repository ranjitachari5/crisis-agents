import {
  HeartPulse,
  Droplets,
  RadioTower,
  Siren,
  BatteryCharging,
  Zap,
  Scale,
  ShieldCheck,
  Activity,
  UserCog,
  Sparkles,
} from "lucide-react";
import { formatSimTime } from "@/lib/format";
import { isSystemStyle } from "@/lib/messageKinds";
import { agentName } from "@/lib/agents";
import type { AgentMessage } from "@/types/api";

interface Props {
  message: AgentMessage;
}

export function MessageBubble({ message }: Props) {
  const isSystem = isSystemStyle(message.message_type);
  const isQuarantined =
    message.status === "quarantined" || message.trust?.decision === "quarantine";

  const renderIcon = (sender: string) => {
    const props = { size: 14, strokeWidth: 1.5, className: "shrink-0" };
    switch (sender) {
      case "hospital_agent":
        return <HeartPulse {...props} />;
      case "water_agent":
        return <Droplets {...props} />;
      case "telecom_agent":
        return <RadioTower {...props} />;
      case "emergency_agent":
        return <Siren {...props} />;
      case "battery_agent":
        return <BatteryCharging {...props} />;
      case "grid_agent":
        return <Zap {...props} />;
      case "negotiation_protocol":
        return <Scale {...props} />;
      case "trust_engine":
        return <ShieldCheck {...props} />;
      case "simulation":
        return <Activity {...props} />;
      case "commander":
        return <UserCog {...props} />;
      case "analyst":
        return <Sparkles {...props} />;
      default:
        return <Activity {...props} />;
    }
  };

  // Centered system/protocol/agreement message
  if (isSystem) {
    return (
      <div className="py-2 px-4 my-1 flex justify-center text-center">
        <div className="max-w-xl py-1.5 px-3 bg-surface-2/60 border border-border/80 rounded-control text-12 text-muted flex items-center justify-center gap-2">
          <span className="text-muted/80">{renderIcon(message.sender)}</span>
          <span className="font-medium text-text">{agentName(message.sender)}:</span>
          <span>{message.text || message.reason}</span>
          {message.quantity !== null && (
            <span className="px-1.5 py-0.2 rounded-control bg-surface border border-border text-11 tabular-nums text-text">
              {message.quantity} {message.unit ?? "MW"}
            </span>
          )}
          <span className="text-11 tabular-nums text-muted/60">
            {formatSimTime(message.sim_time)}
          </span>
        </div>
      </div>
    );
  }

  // Normal negotiation message
  return (
    <div
      className={`p-3 bg-surface rounded-panel border text-12 space-y-2 transition-all duration-200 ${
        isQuarantined
          ? "border-accent/40 bg-accent-dim/30 opacity-75"
          : "border-border"
      }`}
    >
      {/* Header */}
      <div className="flex items-center justify-between gap-2">
        <div className="flex items-center gap-2 min-w-0">
          <div className="text-muted">{renderIcon(message.sender)}</div>
          <span className="font-semibold text-text truncate">
            {agentName(message.sender)}
          </span>

          <span className="text-11 uppercase px-1.5 py-0.5 rounded-control bg-surface-2 border border-border text-muted">
            {message.message_type.replace(/_/g, " ")}
          </span>

          {message.round_id > 0 && (
            <span className="text-11 px-1.5 py-0.5 rounded-control bg-surface-2 text-muted tabular-nums">
              R{message.round_id}
            </span>
          )}

          {isQuarantined && (
            <span className="text-11 px-1.5 py-0.5 rounded-control bg-accent/20 border border-accent/40 text-accent font-medium">
              Quarantined
            </span>
          )}
        </div>

        <div className="flex items-center gap-2 text-11 text-muted shrink-0 tabular-nums">
          <span className="capitalize">{message.status}</span>
          <span>•</span>
          <span>{formatSimTime(message.sim_time)}</span>
        </div>
      </div>

      {/* Body Text */}
      <p className="text-text/90 leading-relaxed break-words">
        {message.text || message.reason || "Transmission sent."}
      </p>

      {/* Quantity Chip & Mentions */}
      <div className="flex items-center justify-between pt-1 text-11">
        <div className="flex items-center gap-2">
          {message.quantity !== null && (
            <span className="px-2 py-0.5 rounded-control bg-surface-2 border border-border font-medium text-text tabular-nums">
              {message.quantity} {message.unit ?? "MW"}
            </span>
          )}

          {message.mentions && message.mentions.length > 0 && (
            <div className="flex items-center gap-1 text-muted">
              <span>to:</span>
              {message.mentions.map((m) => (
                <span
                  key={m}
                  className="px-1.5 py-0.2 rounded-control bg-surface-2 text-text font-medium"
                >
                  @{agentName(m)}
                </span>
              ))}
            </div>
          )}
        </div>

        {message.receiver && message.receiver !== "negotiation_group" && (
          <span className="text-muted">
            via direct link to @{agentName(message.receiver)}
          </span>
        )}
      </div>
    </div>
  );
}

