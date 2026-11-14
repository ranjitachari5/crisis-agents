import { useState, useEffect, useCallback } from "react";
import { ShieldCheck } from "lucide-react";
import { AuditTable } from "@/components/AuditTable";
import { api } from "@/services/api";
import type { AuditLog } from "@/types/api";

export function AuditSection() {
  const [logs, setLogs] = useState<AuditLog[]>([]);
  const [isLoading, setIsLoading] = useState(false);

  const fetchLogs = useCallback(async () => {
    setIsLoading(true);
    try {
      const data = await api.audit.logs({ limit: 200 });
      setLogs(data);
    } catch (err) {
      console.warn("Failed fetching audit logs:", err);
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchLogs();
  }, [fetchLogs]);

  return (
    <section id="audit-logs" className="scroll-mt-16 space-y-4">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 pb-1 border-b border-border">
        <div>
          <div className="flex items-center gap-2">
            <span className="text-11 uppercase font-semibold tracking-wider text-muted">
              Governance
            </span>
            <span className="text-border">/</span>
            <span className="text-11 text-muted">Traceability & Compliance</span>
          </div>
          <h1 className="text-20 font-semibold text-text flex items-center gap-2">
            <ShieldCheck className="w-5 h-5 text-muted" />
            <span>Audit Logs</span>
          </h1>
        </div>
      </div>

      <AuditTable logs={logs} isLoading={isLoading} onRefresh={fetchLogs} />
    </section>
  );
}
