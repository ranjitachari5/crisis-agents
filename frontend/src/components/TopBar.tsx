import { Menu, X, LogOut, ShieldCheck } from "lucide-react";
import { ConnectionBadge } from "@/components/ConnectionBadge";
import { formatSimTime, statusLabel } from "@/lib/format";
import { useAuthStore } from "@/store/useAuthStore";
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

  const clearToken = useAuthStore((s) => s.clearToken);

  return (
    <header className="fixed top-0 left-0 right-0 h-12 bg-surface border-b border-border z-30 px-4 flex items-center justify-between select-none">
      <div className="flex items-center gap-6">
        <button
          type="button"
          onClick={onToggleMobileMenu}
          className="md:hidden p-1.5 text-muted hover:text-text rounded-control hover:bg-surface-2 transition-colors cursor-pointer"
          aria-label="Toggle navigation menu"
        >
          {mobileMenuOpen ? <X size={18} /> : <Menu size={18} />}
        </button>

        <div className="flex items-center gap-2">
          <span className="font-mono font-semibold tracking-wider text-13 text-text">
            CRISIS AGENTS
          </span>
          <span className="text-11 uppercase px-1.5 py-0.5 rounded-control bg-accent/15 text-accent border border-accent/30 font-medium font-mono">
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

      <div className="flex items-center gap-3">
        {/* Commander Authorized Badge */}
        <div className="hidden sm:flex items-center gap-1.5 px-2 py-1 rounded-control bg-ok/10 border border-ok/30 text-ok text-11 font-medium font-mono">
          <ShieldCheck size={13} className="text-ok" />
          <span>AUTHORIZED</span>
        </div>

        {/* Exit Command / Logout Button */}
        <button
          type="button"
          onClick={() => clearToken()}
          className="p-1.5 px-2.5 rounded-control border border-border text-muted hover:text-accent hover:border-accent/40 hover:bg-accent/10 transition-colors cursor-pointer flex items-center gap-1.5 text-11 font-medium"
          title="Exit Commander Session (Logs out and clears token from memory)"
        >
          <LogOut size={13} />
          <span className="hidden md:inline">Exit Command</span>
        </button>

        <ConnectionBadge state={connectionState} />
      </div>
    </header>
  );
}
