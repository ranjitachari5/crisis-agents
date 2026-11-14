import { useState, useMemo } from "react";
import {
  Search,
  ChevronLeft,
  ChevronRight,
  RefreshCw,
  Terminal,
} from "lucide-react";
import type { AuditLog } from "@/types/api";

interface Props {
  logs: AuditLog[];
  isLoading?: boolean;
  onRefresh?: () => void;
}

const PAGE_SIZE = 25;

export function AuditTable({ logs, isLoading, onRefresh }: Props) {
  const [search, setSearch] = useState("");
  const [selectedActor, setSelectedActor] = useState("all");
  const [selectedCategory, setSelectedCategory] = useState("all");
  const [currentPage, setCurrentPage] = useState(1);
  const [expandedId, setExpandedId] = useState<string | number | null>(null);

  // Extract unique actors and categories for filters
  const { actors, categories } = useMemo(() => {
    const actSet = new Set<string>();
    const catSet = new Set<string>();

    logs.forEach((log) => {
      if (log.actor) actSet.add(log.actor);
      if (log.category) catSet.add(log.category);
    });

    return {
      actors: Array.from(actSet).sort(),
      categories: Array.from(catSet).sort(),
    };
  }, [logs]);

  // Filter logs
  const filteredLogs = useMemo(() => {
    return logs.filter((log) => {
      if (selectedActor !== "all" && log.actor !== selectedActor) return false;
      if (selectedCategory !== "all" && log.category !== selectedCategory) return false;

      if (search.trim()) {
        const query = search.toLowerCase();
        const actionMatch = log.action.toLowerCase().includes(query);
        const actorMatch = log.actor.toLowerCase().includes(query);
        const detailsMatch = JSON.stringify(log.details || {}).toLowerCase().includes(query);
        return actionMatch || actorMatch || detailsMatch;
      }

      return true;
    });
  }, [logs, selectedActor, selectedCategory, search]);

  // Pagination
  const totalPages = Math.max(1, Math.ceil(filteredLogs.length / PAGE_SIZE));
  const paginatedLogs = useMemo(() => {
    const start = (currentPage - 1) * PAGE_SIZE;
    return filteredLogs.slice(start, start + PAGE_SIZE);
  }, [filteredLogs, currentPage]);

  const handlePageChange = (newPage: number) => {
    if (newPage >= 1 && newPage <= totalPages) {
      setCurrentPage(newPage);
    }
  };

  const formatTime = (isoString?: string) => {
    if (!isoString) return "—";
    try {
      const d = new Date(isoString);
      return d.toTimeString().split(" ")[0];
    } catch {
      return isoString.split("T")[1]?.slice(0, 8) ?? isoString;
    }
  };

  return (
    <div className="bg-surface rounded-panel border border-border overflow-hidden flex flex-col">
      {/* Header and Filter Controls */}
      <div className="p-4 border-b border-border space-y-3">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
          <div className="flex items-center gap-2">
            <Terminal className="w-4 h-4 text-accent" />
            <h3 className="text-13 font-medium text-text">Tamper-Evident Governance Trail</h3>
            <span className="text-11 text-muted tabular-nums">
              ({filteredLogs.length} / {logs.length} entries)
            </span>
          </div>

          <div className="flex items-center gap-2">
            {onRefresh && (
              <button
                type="button"
                onClick={onRefresh}
                disabled={isLoading}
                aria-label="Reload audit logs"
                className="inline-flex items-center gap-1.5 px-3 py-1.5 text-12 rounded border border-border bg-surface-2 hover:bg-surface text-text transition-colors disabled:opacity-50 focus:outline-none focus:ring-2 focus:ring-accent"
              >
                <RefreshCw
                  className={`w-3.5 h-3.5 ${isLoading ? "animate-spin text-accent" : "text-muted"}`}
                />
                <span>Reload Logs</span>
              </button>
            )}
          </div>
        </div>

        {/* Filter bar */}
        <div className="grid grid-cols-1 sm:grid-cols-12 gap-2 pt-1">
          {/* Search input */}
          <div className="sm:col-span-6 relative">
            <Search className="w-3.5 h-3.5 text-muted absolute left-2.5 top-1/2 -translate-y-1/2" />
            <input
              type="text"
              value={search}
              onChange={(e) => {
                setSearch(e.target.value);
                setCurrentPage(1);
              }}
              placeholder="Search action or details…"
              aria-label="Search audit action or details"
              className="w-full bg-surface-2 border border-border text-12 text-text rounded pl-8 pr-3 py-1.5 placeholder:text-muted focus:outline-none focus:ring-2 focus:ring-accent"
            />
          </div>

          {/* Actor filter */}
          <div className="sm:col-span-3 relative">
            <select
              value={selectedActor}
              onChange={(e) => {
                setSelectedActor(e.target.value);
                setCurrentPage(1);
              }}
              aria-label="Filter by actor"
              className="w-full bg-surface-2 border border-border text-12 text-text rounded px-2.5 py-1.5 focus:outline-none focus:ring-2 focus:ring-accent"
            >
              <option value="all">All Actors</option>
              {actors.map((act) => (
                <option key={act} value={act}>
                  {act}
                </option>
              ))}
            </select>
          </div>

          {/* Category filter */}
          <div className="sm:col-span-3 relative">
            <select
              value={selectedCategory}
              onChange={(e) => {
                setSelectedCategory(e.target.value);
                setCurrentPage(1);
              }}
              aria-label="Filter by category"
              className="w-full bg-surface-2 border border-border text-12 text-text rounded px-2.5 py-1.5 focus:outline-none focus:ring-2 focus:ring-accent"
            >
              <option value="all">All Categories</option>
              {categories.map((cat) => (
                <option key={cat} value={cat}>
                  {cat}
                </option>
              ))}
            </select>
          </div>
        </div>
      </div>

      {/* Dense Table */}
      <div className="overflow-x-auto min-h-[360px]">
        {isLoading ? (
          <div className="py-20 flex items-center justify-center">
            <span className="text-12 text-muted">Loading audit log entries…</span>
          </div>
        ) : filteredLogs.length === 0 ? (
          <div className="py-20 flex items-center justify-center border-t border-border">
            <span className="text-12 text-muted">
              No audit log entries found matching criteria.
            </span>
          </div>
        ) : (
          <table className="w-full text-left border-collapse text-12">
            <thead>
              <tr className="border-b border-border bg-surface-2 text-11 text-muted font-medium select-none">
                <th className="py-2.5 px-3 w-24">Time</th>
                <th className="py-2.5 px-2.5 w-16 text-right">Tick</th>
                <th className="py-2.5 px-3 w-32">Category</th>
                <th className="py-2.5 px-3 w-40">Actor</th>
                <th className="py-2.5 px-3 w-48">Action</th>
                <th className="py-2.5 px-4">Details</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border">
              {paginatedLogs.map((log) => {
                const isCommander =
                  log.actor === "commander" ||
                  log.category === "commander" ||
                  log.action.includes("override");
                const isExpanded = expandedId === log.id;
                const detailsStr = JSON.stringify(log.details || {});

                return (
                  <tr
                    key={log.id}
                    onClick={() => setExpandedId(isExpanded ? null : log.id)}
                    className={`cursor-pointer transition-colors ${
                      isCommander
                        ? "bg-accent-dim/15 hover:bg-accent-dim/30"
                        : "hover:bg-surface-2/40"
                    }`}
                  >
                    {/* Time */}
                    <td className="py-2.5 px-3 text-muted tabular-nums whitespace-nowrap">
                      {formatTime(log.created_at || log.sim_time)}
                    </td>

                    {/* Tick */}
                    <td className="py-2.5 px-2.5 text-right text-muted tabular-nums">
                      {log.tick}
                    </td>

                    {/* Category */}
                    <td className="py-2.5 px-3">
                      <span className="text-10 uppercase tracking-wider font-semibold px-1.5 py-0.5 rounded border border-border bg-surface-2 text-muted">
                        {log.category}
                      </span>
                    </td>

                    {/* Actor */}
                    <td className="py-2.5 px-3 font-medium">
                      <div className="flex items-center gap-1.5">
                        {isCommander ? (
                          <>
                            <span
                              className="w-1.5 h-1.5 rounded-full bg-accent shrink-0"
                              title="Commander Authority Action"
                            />
                            <span className="sr-only">Commander Action: </span>
                            <span className="text-accent">{log.actor}</span>
                          </>
                        ) : (
                          <span className="text-text">{log.actor}</span>
                        )}
                      </div>
                    </td>

                    {/* Action */}
                    <td className="py-2.5 px-3 font-mono text-11 text-text">
                      {log.action}
                    </td>

                    {/* Details */}
                    <td className="py-2.5 px-4 text-muted max-w-xs sm:max-w-md truncate">
                      {isExpanded ? (
                        <pre className="text-11 font-mono text-text bg-surface-2 p-2 rounded border border-border whitespace-pre-wrap break-all mt-1">
                          {JSON.stringify(log.details, null, 2)}
                        </pre>
                      ) : (
                        <span className="text-11 truncate block font-mono text-muted/90">
                          {detailsStr}
                        </span>
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        )}
      </div>

      {/* Pagination Bar */}
      <div className="px-4 py-3 border-t border-border bg-surface-2/40 flex items-center justify-between text-11 text-muted select-none">
        <div className="flex items-center gap-1 tabular-nums">
          <span>Page</span>
          <span className="font-medium text-text">{currentPage}</span>
          <span>of</span>
          <span className="font-medium text-text">{totalPages}</span>
        </div>

        <div className="flex items-center gap-1.5">
          <button
            type="button"
            onClick={() => handlePageChange(currentPage - 1)}
            disabled={currentPage <= 1}
            aria-label="Previous audit logs page"
            className="p-1.5 rounded border border-border bg-surface hover:bg-surface-2 text-text disabled:opacity-30 disabled:pointer-events-none transition-colors focus:outline-none focus:ring-2 focus:ring-accent"
          >
            <ChevronLeft className="w-3.5 h-3.5" />
          </button>

          <button
            type="button"
            onClick={() => handlePageChange(currentPage + 1)}
            disabled={currentPage >= totalPages}
            aria-label="Next audit logs page"
            className="p-1.5 rounded border border-border bg-surface hover:bg-surface-2 text-text disabled:opacity-30 disabled:pointer-events-none transition-colors focus:outline-none focus:ring-2 focus:ring-accent"
          >
            <ChevronRight className="w-3.5 h-3.5" />
          </button>
        </div>
      </div>
    </div>
  );
}
