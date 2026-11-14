import { useState } from "react";
import { Zap, Radio, AlertOctagon, CheckCircle2 } from "lucide-react";
import { api } from "@/services/api";
import { errorMessage } from "@/lib/errors";
import { CONSUMER_IDS } from "@/lib/agents";
import type { EventCatalog } from "@/types/api";

const LABEL_OVERRIDES: Record<string, string> = {
  power_reduction: "Power shortage (magnitude)",
  telecom_fiber_cut: "Telecom fiber line cut",
  telecom_outage: "Telecom tower outage",
  battery_fire: "Substation battery thermal event",
  battery_depletion: "Battery depletion",
  hospital_surge: "Hospital mass casualty surge",
  hospital_demand_spike: "Hospital demand surge",
  water_contamination: "Water treatment contamination",
  water_pump_failure: "Water pumping failure",
  sensor_spoof: "Grid sensor spoof attack",
  flood_warning: "Flood inundation warning",
  agent_disconnect: "Agent network disconnect",
  agent_reconnect: "Agent network reconnect",
  recovery: "Grid capacity restoration",
};

interface Props {
  catalog: EventCatalog | null;
  onEventInjected?: () => void;
}

export function EventInjector({ catalog, onEventInjected }: Props) {
  const [selectedType, setSelectedType] = useState<string>("power_reduction");

  // Dynamic parameter states
  const [powerPercent, setPowerPercent] = useState<number>(40);
  const [hospitalExtraMw, setHospitalExtraMw] = useState<number>(20);
  const [pumpFraction, setPumpFraction] = useState<number>(0.4);
  const [telecomFraction, setTelecomFraction] = useState<number>(0.5);
  const [batterySoc, setBatterySoc] = useState<number>(0.2);
  const [floodSeverity, setFloodSeverity] = useState<number>(2);
  const [targetAgent, setTargetAgent] = useState<string>("hospital_agent");
  const [recoveryScope, setRecoveryScope] = useState<string>("full");

  const [isSubmitting, setIsSubmitting] = useState(false);
  const [feedback, setFeedback] = useState<{ type: "success" | "error"; text: string } | null>(
    null
  );

  const eventEntries = catalog?.events ? Object.entries(catalog.events) : [];

  const handleInject = async () => {
    setIsSubmitting(true);
    setFeedback(null);

    const params: Record<string, unknown> = {};

    switch (selectedType) {
      case "power_reduction":
        params.percent = powerPercent;
        break;
      case "flood_warning":
        params.severity = floodSeverity;
        break;
      case "hospital_demand_spike":
        params.additional_mw = hospitalExtraMw;
        break;
      case "water_pump_failure":
        params.capacity_fraction = pumpFraction;
        break;
      case "telecom_outage":
        params.capacity_fraction = telecomFraction;
        break;
      case "battery_depletion":
        params.soc = batterySoc;
        break;
      case "agent_disconnect":
      case "agent_reconnect":
        params.agent_id = targetAgent;
        break;
      case "recovery":
        params.scope = recoveryScope;
        if (recoveryScope === "grid") {
          params.available_mw = 320;
        }
        break;
      default:
        break;
    }

    try {
      const res = await api.events.inject(selectedType, params);
      const eventObj =
        res?.event && typeof res.event === "object"
          ? (res.event as Record<string, unknown>)
          : null;
      const desc =
        (res?.description as string) ||
        (res?.message as string) ||
        (eventObj?.description as string) ||
        (eventObj?.message as string) ||
        (typeof res?.event === "string" ? res.event : null) ||
        `Event '${LABEL_OVERRIDES[selectedType] ?? selectedType}' injected successfully`;

      setFeedback({ type: "success", text: desc });
      onEventInjected?.();
    } catch (err) {
      setFeedback({ type: "error", text: errorMessage(err) });
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div className="p-4 bg-surface rounded-panel border border-border flex flex-col justify-between">
      <div>
        <div className="flex items-center justify-between mb-1">
          <div className="flex items-center gap-2">
            <Zap className="w-4 h-4 text-accent" />
            <h3 className="text-13 font-medium text-text">Inject Disaster Event</h3>
          </div>
          <span className="text-11 text-muted">Direct Simulation Trigger</span>
        </div>
        <p className="text-11 text-muted mb-4">
          Inject real ground-truth physical shocks into the city state to observe autonomous agent negotiation.
        </p>

        {/* Radio Group of Events */}
        <div className="mb-4">
          <label className="text-11 uppercase font-semibold tracking-wider text-muted block mb-2">
            Select Shock Type
          </label>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 max-h-[220px] overflow-y-auto pr-1">
            {eventEntries.map(([key]) => {
              const label = LABEL_OVERRIDES[key] ?? key.replace(/_/g, " ");
              const isSelected = selectedType === key;

              return (
                <button
                  key={key}
                  type="button"
                  onClick={() => setSelectedType(key)}
                  className={`flex items-center gap-2 px-3 py-2 text-left rounded border text-12 transition-colors ${
                    isSelected
                      ? "border-accent bg-accent-dim text-text"
                      : "border-border bg-surface-2 text-muted hover:text-text hover:border-muted/50"
                  }`}
                >
                  <Radio
                    className={`w-3.5 h-3.5 shrink-0 ${isSelected ? "text-accent" : "text-muted"}`}
                  />
                  <span className="truncate">{label}</span>
                </button>
              );
            })}
          </div>
        </div>

        {/* Dynamic Parameter Controls */}
        <div className="p-3 bg-surface-2 rounded border border-border mb-4">
          <span className="text-11 uppercase font-semibold tracking-wider text-muted block mb-2">
            Event Parameters
          </span>

          {selectedType === "power_reduction" && (
            <div className="space-y-2">
              <div className="flex items-center justify-between text-12">
                <span className="text-muted">Generation Capacity Loss</span>
                <span className="text-text font-medium tabular-nums">{powerPercent}%</span>
              </div>
              <input
                type="range"
                min="5"
                max="90"
                step="5"
                value={powerPercent}
                onChange={(e) => setPowerPercent(Number(e.target.value))}
                className="w-full h-1 bg-border rounded-lg appearance-none cursor-pointer accent-accent"
              />
              <div className="flex justify-between text-10 text-muted tabular-nums">
                <span>5% (mild)</span>
                <span>40% (severe)</span>
                <span>90% (catastrophic)</span>
              </div>
            </div>
          )}

          {selectedType === "hospital_demand_spike" && (
            <div className="space-y-2">
              <div className="flex items-center justify-between text-12">
                <span className="text-muted">Surge Demand</span>
                <span className="text-text font-medium tabular-nums">+{hospitalExtraMw} MW</span>
              </div>
              <input
                type="range"
                min="5"
                max="40"
                step="5"
                value={hospitalExtraMw}
                onChange={(e) => setHospitalExtraMw(Number(e.target.value))}
                className="w-full h-1 bg-border rounded-lg appearance-none cursor-pointer accent-accent"
              />
            </div>
          )}

          {selectedType === "water_pump_failure" && (
            <div className="space-y-2">
              <div className="flex items-center justify-between text-12">
                <span className="text-muted">Pumping Capacity Residual</span>
                <span className="text-text font-medium tabular-nums">
                  {(pumpFraction * 100).toFixed(0)}%
                </span>
              </div>
              <input
                type="range"
                min="0.1"
                max="0.9"
                step="0.05"
                value={pumpFraction}
                onChange={(e) => setPumpFraction(Number(e.target.value))}
                className="w-full h-1 bg-border rounded-lg appearance-none cursor-pointer accent-accent"
              />
            </div>
          )}

          {selectedType === "telecom_outage" && (
            <div className="space-y-2">
              <div className="flex items-center justify-between text-12">
                <span className="text-muted">Tower Capacity Residual</span>
                <span className="text-text font-medium tabular-nums">
                  {(telecomFraction * 100).toFixed(0)}%
                </span>
              </div>
              <input
                type="range"
                min="0.1"
                max="0.9"
                step="0.05"
                value={telecomFraction}
                onChange={(e) => setTelecomFraction(Number(e.target.value))}
                className="w-full h-1 bg-border rounded-lg appearance-none cursor-pointer accent-accent"
              />
            </div>
          )}

          {selectedType === "battery_depletion" && (
            <div className="space-y-2">
              <div className="flex items-center justify-between text-12">
                <span className="text-muted">Target Battery SoC</span>
                <span className="text-text font-medium tabular-nums">
                  {(batterySoc * 100).toFixed(0)}%
                </span>
              </div>
              <input
                type="range"
                min="0.15"
                max="0.8"
                step="0.05"
                value={batterySoc}
                onChange={(e) => setBatterySoc(Number(e.target.value))}
                className="w-full h-1 bg-border rounded-lg appearance-none cursor-pointer accent-accent"
              />
            </div>
          )}

          {selectedType === "flood_warning" && (
            <div className="space-y-1.5">
              <span className="text-11 text-muted block">Flood Inundation Severity</span>
              <div className="grid grid-cols-3 gap-2">
                {[1, 2, 3].map((lvl) => (
                  <button
                    key={lvl}
                    type="button"
                    onClick={() => setFloodSeverity(lvl)}
                    className={`py-1 text-12 rounded border text-center ${
                      floodSeverity === lvl
                        ? "border-accent bg-accent-dim text-text font-medium"
                        : "border-border bg-surface text-muted hover:text-text"
                    }`}
                  >
                    Level {lvl}
                  </button>
                ))}
              </div>
            </div>
          )}

          {(selectedType === "agent_disconnect" || selectedType === "agent_reconnect") && (
            <div>
              <span className="text-11 text-muted block mb-1">Target Utility Agent</span>
              <select
                value={targetAgent}
                onChange={(e) => setTargetAgent(e.target.value)}
                className="w-full bg-surface border border-border text-12 text-text rounded p-1.5 focus:border-accent focus:outline-none"
              >
                {CONSUMER_IDS.map((aid: string) => (
                  <option key={aid} value={aid}>
                    {aid.replace(/_/g, " ")}
                  </option>
                ))}
                <option value="battery_agent">battery agent</option>
              </select>
            </div>
          )}

          {selectedType === "recovery" && (
            <div className="space-y-1.5">
              <span className="text-11 text-muted block">Restoration Scope</span>
              <div className="grid grid-cols-2 gap-2">
                {["full", "grid"].map((scope) => (
                  <button
                    key={scope}
                    type="button"
                    onClick={() => setRecoveryScope(scope)}
                    className={`py-1 text-12 rounded border capitalize ${
                      recoveryScope === scope
                        ? "border-accent bg-accent-dim text-text font-medium"
                        : "border-border bg-surface text-muted hover:text-text"
                    }`}
                  >
                    {scope === "full" ? "Full Grid & Storage" : "Grid Only (320 MW)"}
                  </button>
                ))}
              </div>
            </div>
          )}
        </div>

        {/* Inline Feedback Banner */}
        {feedback && (
          <div
            className={`p-2.5 rounded border text-12 mb-4 flex items-start gap-2 ${
              feedback.type === "success"
                ? "border-ok/40 bg-ok/10 text-text"
                : "border-accent/40 bg-accent-dim text-text"
            }`}
          >
            {feedback.type === "success" ? (
              <CheckCircle2 className="w-4 h-4 text-ok shrink-0 mt-0.5" />
            ) : (
              <AlertOctagon className="w-4 h-4 text-accent shrink-0 mt-0.5" />
            )}
            <span className="leading-snug">{feedback.text}</span>
          </div>
        )}
      </div>

      {/* Outlined Red Action Button */}
      <button
        type="button"
        onClick={handleInject}
        disabled={isSubmitting}
        className="w-full py-2 px-4 rounded border border-accent bg-transparent hover:bg-accent-dim text-accent hover:text-text font-medium text-13 transition-colors flex items-center justify-center gap-2 disabled:opacity-50"
      >
        <Zap className="w-4 h-4" />
        <span>{isSubmitting ? "Injecting Shock…" : "Inject Shock Event"}</span>
      </button>
    </div>
  );
}
