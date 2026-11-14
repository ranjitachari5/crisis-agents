import { useState, useEffect, type FormEvent } from "react";
import {
  ShieldAlert,
  ShieldCheck,
  KeyRound,
  Eye,
  EyeOff,
  ArrowRight,
  Loader2,
  AlertTriangle,
  Server,
  Lock,
  Cpu,
} from "lucide-react";
import { useAuthStore } from "@/store/useAuthStore";
import { api } from "@/services/api";

const DEV_DEFAULT_TOKEN = "oEl2NqZqChLfCuYB1EA2ZtK9baudP030";

export function CommanderLoginPage() {
  const setToken = useAuthStore((s) => s.setToken);
  const [inputToken, setInputToken] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [serverOnline, setServerOnline] = useState<boolean | null>(null);

  // Check backend server status on mount
  useEffect(() => {
    let mounted = true;
    fetch("/healthz")
      .then((res) => {
        if (mounted) setServerOnline(res.ok);
      })
      .catch(() => {
        if (mounted) setServerOnline(false);
      });
    return () => {
      mounted = false;
    };
  }, []);

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    const trimmed = inputToken.trim();
    if (!trimmed) {
      setError("Please enter a valid Commander Bearer Token.");
      return;
    }

    setLoading(true);
    setError(null);

    try {
      const res = await api.auth.verify(trimmed);
      if (res.valid) {
        setToken(trimmed);
      } else {
        setError(res.error || "Authentication failed. Token rejected by server.");
      }
    } catch {
      setError("Unable to contact backend authentication service.");
    } finally {
      setLoading(false);
    }
  };

  const handleQuickFill = () => {
    setInputToken(DEV_DEFAULT_TOKEN);
    setError(null);
  };

  return (
    <div className="min-h-screen bg-bg text-text antialiased flex flex-col justify-between selection:bg-accent/30 selection:text-white relative overflow-hidden">
      {/* Background Tactical Grid & Ambient Glow */}
      <div className="absolute inset-0 bg-[linear-gradient(to_right,#17171A_1px,transparent_1px),linear-gradient(to_bottom,#17171A_1px,transparent_1px)] bg-[size:32px_32px] [mask-image:radial-gradient(ellipse_60%_50%_at_50%_50%,#000_70%,transparent_100%)] opacity-60 pointer-events-none" />
      <div className="absolute top-1/4 left-1/2 -translate-x-1/2 w-[600px] h-[350px] bg-accent/5 rounded-full blur-[140px] pointer-events-none" />

      {/* Top Header Bar */}
      <header className="relative z-10 w-full border-b border-border bg-surface/80 backdrop-blur-md px-6 py-3 flex items-center justify-between text-12">
        <div className="flex items-center gap-2.5">
          <div className="w-2 h-2 rounded-full bg-accent animate-pulse" />
          <span className="font-mono uppercase tracking-widest text-11 font-semibold text-text">
            Crisis Agents
          </span>
          <span className="text-border">/</span>
          <span className="text-muted text-11 tracking-wider uppercase">
            Incident Command System
          </span>
        </div>

        <div className="flex items-center gap-4 text-11 font-mono">
          <div className="flex items-center gap-1.5 text-muted">
            <Server size={13} className="text-muted" />
            <span>Backend:</span>
            {serverOnline === null ? (
              <span className="text-muted">Probing...</span>
            ) : serverOnline ? (
              <span className="text-ok font-medium flex items-center gap-1">
                <span className="w-1.5 h-1.5 rounded-full bg-ok" />
                Online (127.0.0.1:8000)
              </span>
            ) : (
              <span className="text-accent font-medium flex items-center gap-1">
                <span className="w-1.5 h-1.5 rounded-full bg-accent" />
                Unreachable
              </span>
            )}
          </div>
          <div className="hidden sm:block text-muted border-l border-border pl-4">
            SecLevel: <span className="text-text font-semibold">COMMANDER</span>
          </div>
        </div>
      </header>

      {/* Main Authentication Card */}
      <main className="relative z-10 flex-1 flex items-center justify-center p-4 sm:p-6">
        <div className="w-full max-w-md bg-surface border border-border rounded-panel shadow-2xl p-6 sm:p-8 space-y-6 relative">
          {/* Tactical Accent Corner Decors */}
          <div className="absolute -top-[1px] -left-[1px] w-3 h-3 border-t-2 border-l-2 border-accent" />
          <div className="absolute -top-[1px] -right-[1px] w-3 h-3 border-t-2 border-r-2 border-accent" />
          <div className="absolute -bottom-[1px] -left-[1px] w-3 h-3 border-b-2 border-l-2 border-accent" />
          <div className="absolute -bottom-[1px] -right-[1px] w-3 h-3 border-b-2 border-r-2 border-accent" />

          {/* Header & Icon */}
          <div className="text-center space-y-2">
            <div className="inline-flex items-center justify-center w-12 h-12 rounded-panel bg-accent-dim border border-accent/40 text-accent mx-auto mb-2 shadow-inner">
              <ShieldAlert size={26} strokeWidth={1.8} />
            </div>

            <div className="text-11 font-mono uppercase tracking-widest text-accent font-bold">
              Classified Access
            </div>

            <h1 className="text-20 font-bold text-text tracking-tight sm:text-28">
              Commander Authorization
            </h1>

            <p className="text-12 text-muted leading-relaxed max-w-xs mx-auto">
              Authoritative command terminal for municipal life-support, power grid, and multi-agent resource allocation.
            </p>
          </div>

          {/* Error Banner */}
          {error && (
            <div className="p-3 rounded-control bg-accent/10 border border-accent/40 text-accent flex items-start gap-2.5 text-12">
              <AlertTriangle size={16} className="shrink-0 mt-0.5" />
              <div className="flex-1 leading-snug font-medium">{error}</div>
            </div>
          )}

          {/* Authentication Form */}
          <form onSubmit={handleSubmit} className="space-y-4">
            <div className="space-y-1.5">
              <label
                htmlFor="commander-token"
                className="block text-11 uppercase font-semibold tracking-wider text-muted flex items-center justify-between"
              >
                <span>Authorization Token</span>
                <span className="text-muted/70 text-[10px] font-mono lowercase">Bearer</span>
              </label>

              <div className="relative">
                <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none text-muted">
                  <KeyRound size={15} />
                </div>

                <input
                  id="commander-token"
                  type={showPassword ? "text" : "password"}
                  value={inputToken}
                  onChange={(e) => {
                    setInputToken(e.target.value);
                    if (error) setError(null);
                  }}
                  placeholder="Paste COMMANDER_AUTH_TOKEN..."
                  autoComplete="off"
                  spellCheck={false}
                  autoFocus
                  disabled={loading}
                  className="w-full pl-9 pr-10 py-2.5 bg-surface-2 border border-border rounded-control text-13 text-text placeholder-muted/60 font-mono focus:outline-none focus:border-accent focus:ring-1 focus:ring-accent transition-all disabled:opacity-50"
                />

                <button
                  type="button"
                  onClick={() => setShowPassword((prev) => !prev)}
                  tabIndex={-1}
                  className="absolute inset-y-0 right-0 pr-3 flex items-center text-muted hover:text-text transition-colors cursor-pointer"
                  title={showPassword ? "Hide token" : "Show token"}
                >
                  {showPassword ? <EyeOff size={15} /> : <Eye size={15} />}
                </button>
              </div>
            </div>

            {/* Quick Fill Dev Token Helper */}
            <div className="flex items-center justify-between text-11">
              <button
                type="button"
                onClick={handleQuickFill}
                className="text-muted hover:text-text hover:underline transition-colors cursor-pointer flex items-center gap-1 font-mono text-[11px]"
              >
                <Cpu size={12} className="text-accent" />
                Fill Local Dev Token
              </button>
              <span className="text-muted/60 text-[10px]">ENV: dev</span>
            </div>

            {/* Submit Button */}
            <button
              type="submit"
              disabled={loading || !inputToken.trim()}
              className="w-full py-2.5 px-4 bg-accent hover:bg-accent/90 disabled:bg-surface-2 disabled:text-muted disabled:border-border disabled:cursor-not-allowed border border-accent/40 rounded-control text-text font-semibold text-13 flex items-center justify-center gap-2 transition-all cursor-pointer shadow-lg shadow-accent/10"
            >
              {loading ? (
                <>
                  <Loader2 size={16} className="animate-spin text-text" />
                  <span>Validating Credentials...</span>
                </>
              ) : (
                <>
                  <span>Take Command & Enter</span>
                  <ArrowRight size={15} />
                </>
              )}
            </button>
          </form>

          {/* Security Guarantee Notice */}
          <div className="pt-2 border-t border-border/80 flex items-start gap-2 text-11 text-muted leading-relaxed">
            <Lock size={13} className="shrink-0 mt-0.5 text-muted" />
            <span>
              <strong>Volatile Memory Policy:</strong> The bearer token is maintained strictly in browser RAM for this active session. It is never persisted to disk, local storage, or cookies.
            </span>
          </div>
        </div>
      </main>

      {/* Footer Bar */}
      <footer className="relative z-10 w-full border-t border-border bg-surface/60 backdrop-blur-md px-6 py-3 flex flex-col sm:flex-row items-center justify-between text-11 text-muted gap-2">
        <div className="flex items-center gap-2">
          <ShieldCheck size={13} className="text-ok" />
          <span>Autonomous Multi-Agent Crisis Resource Allocation System</span>
        </div>
        <div className="font-mono text-[10px] text-muted/70">
          SEC-ID: OP-CRISIS-AGENTS-v0.2.0
        </div>
      </footer>
    </div>
  );
}
