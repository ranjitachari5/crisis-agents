import { ShieldAlert } from "lucide-react";
import { AGENTS } from "@/lib/agents";
import type { QuarantineEntry, AgentId } from "@/types/api";

interface Props {
  quarantine: QuarantineEntry[];
  onSelectIncident?: (incidentId: string) => void;
}

export function QuarantineTable({ quarantine, onSelectIncident }: Props) {
  return (
    <div className="p-4 bg-surface rounded-panel border border-border flex flex-col justify-between">
      <div>
        <div className="flex items-center justify-between mb-1">
          <div className="flex items-center gap-2">
            <ShieldAlert className="w-4 h-4 text-accent" />
            <h3 className="text-13 font-medium text-text">Quarantine Log</h3>
          </div>
          <span className="text-11 text-muted tabular-nums">
            {quarantine.length} isolated messages
          </span>
        </div>
        <p className="text-11 text-muted mb-3">
          Messages sequestered by the trust engine due to anomaly detection or falsified claims.
        </p>
      </div>

      {quarantine.length === 0 ? (
        <div className="py-8 flex items-center justify-center border border-dashed border-border rounded">
          <span className="text-12 text-muted">No quarantined messages recorded.</span>
        </div>
      ) : (
        <div className="border border-border rounded overflow-hidden max-h-[220px] overflow-y-auto">
          <table className="w-full text-left text-12 border-collapse">
            <thead>
              <tr className="bg-surface-2 text-muted font-semibold text-11 uppercase tracking-wider border-b border-border sticky top-0">
                <th className="py-2 px-3">Time</th>
                <th className="py-2 px-3">Sender</th>
                <th className="py-2 px-3">Message Type</th>
                <th className="py-2 px-3 text-right">Action</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border">
              {quarantine.map((item, idx) => {
                const senderDef = AGENTS[item.message.sender as AgentId];
                return (
                  <tr key={`${item.incident_id}-${idx}`} className="hover:bg-surface-2/40 transition-colors">
                    <td className="py-2 px-3 tabular-nums text-muted text-11">
                      {item.message.sim_time || item.message.timestamp}
                    </td>
                    <td className="py-2 px-3 font-medium text-text">
                      {senderDef?.name ?? item.message.sender}
                    </td>
                    <td className="py-2 px-3">
                      <span className="text-11 px-1.5 py-0.5 rounded border border-accent/40 bg-accent-dim text-accent uppercase font-medium">
                        {item.message.message_type}
                      </span>
                    </td>
                    <td className="py-2 px-3 text-right">
                      {onSelectIncident && (
                        <button
                          onClick={() => onSelectIncident(item.incident_id)}
                          className="text-11 text-muted hover:text-text hover:underline cursor-pointer"
                        >
                          View Incident
                        </button>
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
