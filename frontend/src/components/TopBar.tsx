import { Menu, X } from "lucide-react";
import { ConnectionBadge } from "@/components/ConnectionBadge";
import { formatSimTime, statusLabel } from "@/lib/format";
import type { ConnectionState, SimulationStatus } from "@/types/api";

interface Props {
  status?: SimulationStatus;
  scenario?: string;
  simTime?: string;
  connectionState: ConnectionState;
  mobileMenuOpen: boolean;
  onToggleMobileMenu: () => void;
}

export function TopBar({
  status = "idle",
  scenario = "grid_shortage",
  simTime,
  connectionState,
  mobileMenuOpen,
  onToggleMobileMenu,
}: Props) {
  const statusColor =
    status === "running"
      ? "bg-ok"
      : status === "paused"
      ? "bg-muted"
      : "bg-muted";

  return (
    <header className="fixed top-0 left-0 right-0 h-12 bg-surface border-b border-border z-30 px-4 flex items-center justify-between select-none">
      <div className="flex items-center gap-6">
        <button
          type="button"
          onClick={onToggleMobileMenu}
          className="md:hidden p-1.5 -ml-1 text-muted hover:text-text rounded-control hover:bg-surface-2"
          aria-label={mobileMenuOpen ? "Close menu" : "Open menu"}
        >
          {mobileMenuOpen ? (
            <X size={16} strokeWidth={1.5} />
          ) : (
            <Menu size={16} strokeWidth={1.5} />
          )}
        </button>

        <div className="flex items-center gap-2">
          <span className="font-semibold text-16 text-text tracking-tight">
            CRISIS AGENTS
          </span>
          <span className="text-11 uppercase px-1.5 py-0.5 rounded-control bg-surface-2 text-muted border border-border font-medium">
            Commander
          </span>
        </div>

        <div className="hidden lg:flex items-center gap-6 text-12 text-muted border-l border-border pl-6">
          <div className="flex items-center gap-2">
            <span className="text-muted">Status</span>
            <div className="flex items-center gap-1.5 text-text">
              <span className={`w-1.5 h-1.5 rounded-full ${statusColor}`} />
              <span className="font-medium">{statusLabel(status)}</span>
            </div>
          </div>

          <div className="flex items-center gap-2">
            <span className="text-muted">Scenario</span>
            <span className="text-text font-medium font-mono">
              {scenario.replace(/_/g, " ")}
            </span>
          </div>

          <div className="flex items-center gap-2">
            <span className="text-muted">Sim Time</span>
            <span className="text-text font-medium tabular-nums">
              {formatSimTime(simTime)}
            </span>
          </div>
        </div>
      </div>

      <div className="flex items-center gap-4">
        <ConnectionBadge state={connectionState} />
      </div>
    </header>
  );
}

