import { useState, type FormEvent } from "react";
import {
  X,
  PlusCircle,
  Cpu,
  Building2,
  Train,
  Factory,
  Shield,
  Loader2,
  AlertTriangle,
  CheckCircle2,
  Zap,
} from "lucide-react";
import { api } from "@/services/api";
import { useSimStore } from "@/store/useSimStore";
import type { CreateAgentRequest } from "@/types/api";

interface Props {
  open: boolean;
  onClose: () => void;
}

interface Preset {
  label: string;
  icon: typeof Cpu;
  data: CreateAgentRequest;
}

const PRESETS: Preset[] = [
  {
    label: "Data Center Core",
    icon: Cpu,
    data: {
      agent_id: "datacenter_agent",
      name: "Data Center Core Agent",
      role: "Cloud compute, banking & public records",
      icon: "Cpu",
      color: "#38bdf8",
      base_demand: 40,
      min_safe: 20,
      max_allowed: 65,
      damage_weight: 8,
      critical_weight: 80,
      concession_rate: 0.35,
      peer_grant_fraction: 0.5,
      feeder: "feeder_south",
      start_negotiation: true,
    },
  },
  {
    label: "Evacuation Shelter",
    icon: Building2,
    data: {
      agent_id: "shelter_agent",
      name: "Evacuation Shelter Agent",
      role: "Emergency heating, shelter & medical logistics",
      icon: "Building2",
      color: "#f59e0b",
      base_demand: 35,
      min_safe: 18,
      max_allowed: 50,
      damage_weight: 9,
      critical_weight: 90,
      concession_rate: 0.25,
      peer_grant_fraction: 0.4,
      feeder: "feeder_north",
      start_negotiation: true,
    },
  },
  {
    label: "Metro Transit Grid",
    icon: Train,
    data: {
      agent_id: "transit_agent",
      name: "Metro Transit & Traction",
      role: "Electric subway, rail signaling & evacuation trains",
      icon: "Train",
      color: "#a78bfa",
      base_demand: 50,
      min_safe: 28,
      max_allowed: 75,
      damage_weight: 7,
      critical_weight: 70,
      concession_rate: 0.4,
      peer_grant_fraction: 0.6,
      feeder: "feeder_south",
      start_negotiation: true,
    },
  },
  {
    label: "Industrial Cryo & Hazmat",
    icon: Factory,
    data: {
      agent_id: "hazmat_agent",
      name: "Industrial Cryo & Hazmat",
      role: "Chemical storage cooling & containment scrubbers",
      icon: "Factory",
      color: "#f43f5e",
      base_demand: 30,
      min_safe: 15,
      max_allowed: 45,
      damage_weight: 9.5,
      critical_weight: 95,
      concession_rate: 0.2,
      peer_grant_fraction: 0.3,
      feeder: "feeder_north",
      start_negotiation: true,
    },
  },
];

export function CreateAgentDialog({ open, onClose }: Props) {
  const ingestStateUpdate = useSimStore((s) => s.ingestStateUpdate);
  const setTwinGraph = useSimStore((s) => s.setTwinGraph);
  const [formData, setFormData] = useState<CreateAgentRequest>(PRESETS[0].data);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);

  if (!open) return null;

  const handleSelectPreset = (p: Preset) => {
    setFormData({ ...p.data });
    setError(null);
  };

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setError(null);
    setSuccess(null);

    try {
      const res = await api.commander.createAgent(formData);
      if (res.state) {
        ingestStateUpdate(res.state, true);
      }
      try {
        const graph = await api.twin.graph();
        setTwinGraph(graph);
      } catch {
        // graph fallback
      }
      setSuccess(`Agent '${formData.name}' successfully deployed and entered negotiation!`);
      setTimeout(() => {
        onClose();
        setSuccess(null);
      }, 1400);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Failed to deploy agent";
      setError(msg);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/70 backdrop-blur-sm">
      <div className="w-full max-w-2xl bg-surface border border-border rounded-panel shadow-2xl overflow-hidden flex flex-col max-h-[90vh]">
        {/* Modal Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-border bg-surface-2/60">
          <div className="flex items-center gap-2.5">
            <div className="p-1.5 rounded-control bg-accent/10 border border-accent/30 text-accent">
              <PlusCircle size={18} />
            </div>
            <div>
              <h2 className="text-14 font-semibold text-text uppercase tracking-wide">
                Deploy Custom Utility Agent
              </h2>
              <p className="text-11 text-muted">
                Provisions cryptographic keys and registers autonomous agent into the negotiation mesh
              </p>
            </div>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="p-1 rounded-control text-muted hover:text-text hover:bg-surface-2 transition-colors cursor-pointer"
          >
            <X size={18} />
          </button>
        </div>

        {/* Modal Body */}
        <div className="p-6 space-y-6 overflow-y-auto">
          {/* Presets Selection */}
          <div className="space-y-2">
            <span className="text-11 font-mono uppercase tracking-wider text-muted font-semibold">
              Select Preset Archetype
            </span>
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
              {PRESETS.map((p) => {
                const Icon = p.icon;
                const isSelected = formData.agent_id === p.data.agent_id;
                return (
                  <button
                    key={p.data.agent_id}
                    type="button"
                    onClick={() => handleSelectPreset(p)}
                    className={`p-2.5 rounded-control border text-left flex flex-col gap-1 transition-all cursor-pointer ${
                      isSelected
                        ? "border-accent bg-accent/10 text-text shadow-sm"
                        : "border-border bg-surface-2/40 text-muted hover:text-text hover:border-border/80"
                    }`}
                  >
                    <Icon size={16} className={isSelected ? "text-accent" : "text-muted"} />
                    <span className="text-12 font-medium line-clamp-1">{p.label}</span>
                    <span className="text-10 font-mono text-muted/70">{p.data.base_demand} MW</span>
                  </button>
                );
              })}
            </div>
          </div>

          {/* Form */}
          <form id="create-agent-form" onSubmit={handleSubmit} className="space-y-4">
            {error && (
              <div className="p-3 rounded-control bg-accent/10 border border-accent/40 text-accent text-12 flex items-start gap-2">
                <AlertTriangle size={15} className="shrink-0 mt-0.5" />
                <span>{error}</span>
              </div>
            )}

            {success && (
              <div className="p-3 rounded-control bg-ok/10 border border-ok/40 text-ok text-12 flex items-center gap-2">
                <CheckCircle2 size={16} className="shrink-0" />
                <span>{success}</span>
              </div>
            )}

            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              <div className="space-y-1">
                <label className="text-11 font-semibold uppercase tracking-wider text-muted">
                  Agent ID (Identifier)
                </label>
                <input
                  type="text"
                  value={formData.agent_id}
                  onChange={(e) =>
                    setFormData({ ...formData, agent_id: e.target.value.toLowerCase().replace(/[^a-z0-9_]/g, "") })
                  }
                  required
                  placeholder="e.g. datacenter_agent"
                  className="w-full px-3 py-1.5 bg-surface-2 border border-border rounded-control text-12 font-mono text-text focus:outline-none focus:border-accent"
                />
              </div>

              <div className="space-y-1">
                <label className="text-11 font-semibold uppercase tracking-wider text-muted">
                  Display Name
                </label>
                <input
                  type="text"
                  value={formData.name}
                  onChange={(e) => setFormData({ ...formData, name: e.target.value })}
                  required
                  placeholder="e.g. Data Center Core Agent"
                  className="w-full px-3 py-1.5 bg-surface-2 border border-border rounded-control text-12 text-text focus:outline-none focus:border-accent"
                />
              </div>
            </div>

            <div className="space-y-1">
              <label className="text-11 font-semibold uppercase tracking-wider text-muted">
                Role & Critical Mandate
              </label>
              <input
                type="text"
                value={formData.role ?? ""}
                onChange={(e) => setFormData({ ...formData, role: e.target.value })}
                required
                placeholder="Description of utility mission"
                className="w-full px-3 py-1.5 bg-surface-2 border border-border rounded-control text-12 text-text focus:outline-none focus:border-accent"
              />
            </div>

            {/* Power Parameters */}
            <div className="grid grid-cols-3 gap-3">
              <div className="space-y-1">
                <label className="text-11 font-semibold uppercase tracking-wider text-muted flex items-center gap-1">
                  <Zap size={11} className="text-muted" /> Base Demand
                </label>
                <div className="relative">
                  <input
                    type="number"
                    step="1"
                    min="1"
                    max="1000"
                    value={formData.base_demand}
                    onChange={(e) => setFormData({ ...formData, base_demand: Number(e.target.value) })}
                    required
                    className="w-full px-3 py-1.5 pr-8 bg-surface-2 border border-border rounded-control text-12 font-mono text-text focus:outline-none focus:border-accent"
                  />
                  <span className="absolute right-2.5 top-1.5 text-10 font-mono text-muted">MW</span>
                </div>
              </div>

              <div className="space-y-1">
                <label className="text-11 font-semibold uppercase tracking-wider text-muted">
                  Safe Minimum
                </label>
                <div className="relative">
                  <input
                    type="number"
                    step="1"
                    min="1"
                    max={formData.base_demand}
                    value={formData.min_safe}
                    onChange={(e) => setFormData({ ...formData, min_safe: Number(e.target.value) })}
                    required
                    className="w-full px-3 py-1.5 pr-8 bg-surface-2 border border-border rounded-control text-12 font-mono text-text focus:outline-none focus:border-accent"
                  />
                  <span className="absolute right-2.5 top-1.5 text-10 font-mono text-muted">MW</span>
                </div>
              </div>

              <div className="space-y-1">
                <label className="text-11 font-semibold uppercase tracking-wider text-muted">
                  Max Allowed
                </label>
                <div className="relative">
                  <input
                    type="number"
                    step="1"
                    min={formData.base_demand}
                    max="2000"
                    value={formData.max_allowed}
                    onChange={(e) => setFormData({ ...formData, max_allowed: Number(e.target.value) })}
                    required
                    className="w-full px-3 py-1.5 pr-8 bg-surface-2 border border-border rounded-control text-12 font-mono text-text focus:outline-none focus:border-accent"
                  />
                  <span className="absolute right-2.5 top-1.5 text-10 font-mono text-muted">MW</span>
                </div>
              </div>
            </div>

            {/* Grid & Policy Settings */}
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 pt-1">
              <div className="space-y-1">
                <label className="text-11 font-semibold uppercase tracking-wider text-muted">
                  Feeder Circuit
                </label>
                <select
                  value={formData.feeder ?? "feeder_south"}
                  onChange={(e) =>
                    setFormData({ ...formData, feeder: e.target.value as "feeder_north" | "feeder_south" })
                  }
                  className="w-full px-3 py-1.5 bg-surface-2 border border-border rounded-control text-12 font-mono text-text focus:outline-none focus:border-accent"
                >
                  <option value="feeder_north">North Feeder (Capacity: 210 MW)</option>
                  <option value="feeder_south">South Feeder (Capacity: 150 MW)</option>
                </select>
              </div>

              <div className="space-y-1">
                <label className="text-11 font-semibold uppercase tracking-wider text-muted flex items-center justify-between">
                  <span>Concession Rate</span>
                  <span className="font-mono text-accent">
                    {Math.round((formData.concession_rate ?? 0.3) * 100)}% / round
                  </span>
                </label>
                <input
                  type="range"
                  min="0.05"
                  max="0.8"
                  step="0.05"
                  value={formData.concession_rate ?? 0.3}
                  onChange={(e) => setFormData({ ...formData, concession_rate: Number(e.target.value) })}
                  className="w-full accent-accent cursor-pointer"
                />
              </div>
            </div>

            {/* Negotiation Option */}
            <label className="flex items-center gap-2.5 pt-2 text-12 text-text cursor-pointer select-none">
              <input
                type="checkbox"
                checked={formData.start_negotiation ?? true}
                onChange={(e) => setFormData({ ...formData, start_negotiation: e.target.checked })}
                className="rounded border-border text-accent focus:ring-accent"
              />
              <span className="text-muted">
                Immediately trigger an autonomous negotiation round upon registration
              </span>
            </label>
          </form>
        </div>

        {/* Modal Footer */}
        <div className="px-6 py-3 border-t border-border bg-surface-2/60 flex items-center justify-between text-12">
          <div className="flex items-center gap-1.5 text-11 text-muted">
            <Shield size={13} className="text-ok" />
            <span>Auto-signed with Ed25519 Key</span>
          </div>

          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={onClose}
              disabled={loading}
              className="px-3 py-1.5 rounded-control border border-border text-muted hover:text-text hover:bg-surface-2 transition-colors cursor-pointer text-12"
            >
              Cancel
            </button>

            <button
              type="submit"
              form="create-agent-form"
              disabled={loading}
              className="px-4 py-1.5 rounded-control bg-accent hover:bg-accent/90 disabled:bg-surface-2 disabled:text-muted border border-accent/40 text-text font-medium text-12 flex items-center gap-1.5 transition-all cursor-pointer shadow-sm shadow-accent/20"
            >
              {loading ? (
                <>
                  <Loader2 size={13} className="animate-spin" />
                  <span>Provisioning Agent...</span>
                </>
              ) : (
                <>
                  <PlusCircle size={14} />
                  <span>Authorize & Deploy</span>
                </>
              )}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
