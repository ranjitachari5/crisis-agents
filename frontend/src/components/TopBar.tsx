import { useState, useRef, useEffect } from "react";
import { Menu, X, KeyRound, Check } from "lucide-react";
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

  const isAuthenticated = useAuthStore((s) => s.isAuthenticated);
  const setToken = useAuthStore((s) => s.setToken);
  const clearToken = useAuthStore((s) => s.clearToken);

  const [showTokenInput, setShowTokenInput] = useState(false);
  const [tokenDraft, setTokenDraft] = useState("");
  const popoverRef = useRef<HTMLDivElement>(null);
  const buttonRef = useRef<HTMLButtonElement>(null);

  // Close popover on outside click
  useEffect(() => {
    if (!showTokenInput) return;
    const handler = (e: MouseEvent) => {
      if (
        popoverRef.current &&
        !popoverRef.current.contains(e.target as Node) &&
        buttonRef.current &&
        !buttonRef.current.contains(e.target as Node)
      ) {
        setShowTokenInput(false);
      }
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, [showTokenInput]);

  const handleTokenSubmit = () => {
    if (tokenDraft.trim()) {
      setToken(tokenDraft.trim());
      setTokenDraft("");
      setShowTokenInput(false);
    }
  };

  const handleTokenClear = () => {
    clearToken();
    setTokenDraft("");
  };

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

      <div className="flex items-center gap-3">
        {/* Auth Token Button */}
        <div className="relative">
          <button
            ref={buttonRef}
            type="button"
            onClick={() => setShowTokenInput((prev) => !prev)}
            className={`p-1.5 rounded-control border transition-colors cursor-pointer flex items-center gap-1.5 text-11 font-medium ${
              isAuthenticated
                ? "border-ok/40 text-ok bg-ok/10 hover:bg-ok/20"
                : "border-border text-muted hover:text-text hover:bg-surface-2"
            }`}
            title={isAuthenticated ? "Authenticated — click to manage token" : "Set auth token"}
          >
            <KeyRound size={14} strokeWidth={1.5} />
            {isAuthenticated && <Check size={12} strokeWidth={2} />}
          </button>

          {/* Token Input Popover */}
          {showTokenInput && (
            <div
              ref={popoverRef}
              className="absolute right-0 top-10 w-80 bg-surface border border-border rounded-panel shadow-lg p-3 space-y-2 z-50"
            >
              <div className="text-11 uppercase font-semibold tracking-wider text-muted">
                Commander Auth Token
              </div>
              <p className="text-11 text-muted leading-relaxed">
                Enter your <code className="text-text">COMMANDER_AUTH_TOKEN</code> to
                authorize control actions. Token is kept in memory only.
              </p>
              {isAuthenticated ? (
                <div className="space-y-2">
                  <div className="flex items-center gap-2 p-2 rounded bg-ok/10 border border-ok/30 text-12 text-text">
                    <Check size={14} strokeWidth={2} className="text-ok shrink-0" />
                    <span>Token set — all requests include bearer auth</span>
                  </div>
                  <button
                    type="button"
                    onClick={handleTokenClear}
                    className="w-full px-3 py-1.5 text-12 rounded border border-border text-muted hover:text-text hover:bg-surface-2 transition-colors cursor-pointer"
                  >
                    Clear Token
                  </button>
                </div>
              ) : (
                <div className="flex gap-2">
                  <input
                    type="password"
                    value={tokenDraft}
                    onChange={(e) => setTokenDraft(e.target.value)}
                    onKeyDown={(e) => e.key === "Enter" && handleTokenSubmit()}
                    placeholder="Paste token here"
                    className="flex-1 px-2.5 py-1.5 text-12 bg-surface-2 rounded border border-border text-text placeholder:text-muted/60 focus:outline-none focus:border-accent font-mono"
                    autoFocus
                  />
                  <button
                    type="button"
                    onClick={handleTokenSubmit}
                    disabled={!tokenDraft.trim()}
                    className="px-3 py-1.5 text-12 font-medium rounded bg-accent text-white hover:bg-accent/90 transition-colors cursor-pointer disabled:opacity-40 disabled:cursor-not-allowed"
                  >
                    Set
                  </button>
                </div>
              )}
            </div>
          )}
        </div>

        <ConnectionBadge state={connectionState} />
      </div>
    </header>
  );
}
