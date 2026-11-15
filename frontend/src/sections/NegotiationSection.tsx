import { useState, useRef, useEffect, useMemo } from "react";
import { Play, Pause, ArrowDown } from "lucide-react";
import { AgentCard } from "@/components/AgentCard";
import { AgentDrawer } from "@/components/AgentDrawer";
import { MessageBubble } from "@/components/MessageBubble";
import { ProposalList } from "@/components/ProposalList";
import { AgreementList } from "@/components/AgreementList";
import { Toast, type ToastMessage } from "@/components/Toast";
import { CommanderSitRep } from "@/components/CommanderSitRep";
import { FILTER_TABS, matchesFilter, type ChatFilter } from "@/lib/messageKinds";
import { AGENT_IDS } from "@/lib/agents";
import { api } from "@/services/api";
import { errorMessage } from "@/lib/errors";
import { useAgentActivity } from "@/hooks/useAgentActivity";
import { useSimStore } from "@/store/useSimStore";
import type { AgentView } from "@/types/api";

export function NegotiationSection() {
  const snapshot = useSimStore((s) => s.snapshot);
  const messages = useSimStore((s) => s.messages);
  const proposals = useSimStore((s) => s.proposals);
  const agreements = useSimStore((s) => s.agreements);
  const chatFilter = useSimStore((s) => s.chatFilter);
  const setChatFilter = useSimStore((s) => s.setChatFilter);

  const selectedAgentId = useSimStore((s) => s.selectedAgentId);
  const isDrawerOpen = useSimStore((s) => s.isDrawerOpen);
  const setSelectedAgent = useSimStore((s) => s.setSelectedAgent);
  const setDrawerOpen = useSimStore((s) => s.setDrawerOpen);

  const { getAgentHighlight } = useAgentActivity();

  const [toasts, setToasts] = useState<ToastMessage[]>([]);
  const [isNegotiationActing, setIsNegotiationActing] = useState(false);
  const [hasScrolledUp, setHasScrolledUp] = useState(false);

  const chatContainerRef = useRef<HTMLDivElement>(null);
  const isPaused = snapshot?.negotiation_paused ?? false;

  const addToast = (type: "success" | "error" | "info", message: string) => {
    const id = `${Date.now()}-${Math.random().toString(36).substring(2, 7)}`;
    setToasts((prev) => [...prev, { id, type, message }]);
  };

  const dismissToast = (id: string) => {
    setToasts((prev) => prev.filter((t) => t.id !== id));
  };

  // Scroll management
  const handleScroll = () => {
    const el = chatContainerRef.current;
    if (!el) return;
    const isAtBottom = el.scrollHeight - el.scrollTop - el.clientHeight < 60;
    setHasScrolledUp(!isAtBottom);
  };

  const scrollToBottom = () => {
    const el = chatContainerRef.current;
    if (el) {
      el.scrollTo({ top: el.scrollHeight, behavior: "smooth" });
      setHasScrolledUp(false);
    }
  };

  useEffect(() => {
    if (!hasScrolledUp) {
      const el = chatContainerRef.current;
      if (el) {
        el.scrollTop = el.scrollHeight;
      }
    }
  }, [messages, hasScrolledUp]);

  // Fallback agents array if snapshot not yet arrived
  const agentsMap = new Map<string, AgentView>();
  if (snapshot?.agents) {
    for (const a of snapshot.agents) {
      agentsMap.set(a.agent_id, a);
    }
  }

  // Ensure all base agents exist in order, then append any custom registered agents
  const orderedAgents: AgentView[] = useMemo(() => {
    const list: AgentView[] = [];
    const addedIds = new Set<string>();

    for (const id of AGENT_IDS) {
      const found = agentsMap.get(id);
      if (found) {
        list.push(found);
      } else {
        if (id === "battery_agent") {
          list.push({
            agent_id: "battery_agent",
            display_name: "Battery Agent",
            role: "Grid-scale storage",
            icon: "BatteryCharging",
            kind: "storage",
            status: "online",
            soc: 0.8,
            reserve_fraction: 0.2,
            capacity_mwh: 120,
            usable_energy_mwh: 72,
            capability_mw: 30,
            discharge_mw: 0,
            max_discharge_mw: 30,
            reputation: 1.0,
          });
        } else if (id === "grid_agent") {
          list.push({
            agent_id: "grid_agent",
            display_name: "Grid Agent",
            role: "Supply & grid telemetry",
            icon: "Zap",
            kind: "supply",
            status: "online",
            nominal_mw: 200,
            verified_supply_mw: 200,
            sensor_status: "consensus",
            sensors: {},
            reserve_margin_mw: 0,
            override_mw: null,
            reputation: 1.0,
          });
        } else {
          list.push({
            agent_id: id,
            display_name: id.replace(/_/g, " "),
            role: "Utility service",
            icon: "Activity",
            kind: "consumer",
            status: "online",
            demand_mw: 80,
            min_safe_mw: 50,
            max_allowed_mw: 100,
            allocation_mw: 50,
            service_level: 1.0,
            health: 1.0,
            operational_capacity: 1.0,
            active_operations: false,
            ticks_below_min: 0,
            ticks_conceding: 0,
            urgency: 0.5,
            reputation: 1.0,
            policy: {
              concession_rate: 0.3,
              peer_grant_fraction: 0.5,
              critical_weight: 50,
              dependencies: {},
            },
          });
        }
      }
      addedIds.add(id);
    }

    // Append any custom utilities present in the simulation snapshot
    if (snapshot?.agents) {
      for (const a of snapshot.agents) {
        if (!addedIds.has(a.agent_id)) {
          list.push(a);
          addedIds.add(a.agent_id);
        }
      }
    }

    return list;
  }, [snapshot?.agents, agentsMap]);

  // Filter messages
  const filteredMessages = messages.filter((m) =>
    matchesFilter(m.message_type, chatFilter)
  );

  // Negotiation Controls
  const handleNegotiationStart = async () => {
    setIsNegotiationActing(true);
    try {
      await api.negotiation.start("Commander triggered reassessment");
      addToast("success", "Negotiation session initiated.");
    } catch (err) {
      addToast("error", errorMessage(err));
    } finally {
      setIsNegotiationActing(false);
    }
  };

  const handleNegotiationPause = async () => {
    setIsNegotiationActing(true);
    try {
      await api.negotiation.pause();
      addToast("info", "Negotiation protocol paused.");
    } catch (err) {
      addToast("error", errorMessage(err));
    } finally {
      setIsNegotiationActing(false);
    }
  };

  const handleNegotiationResume = async () => {
    setIsNegotiationActing(true);
    try {
      await api.negotiation.resume();
      addToast("success", "Negotiation protocol resumed.");
    } catch (err) {
      addToast("error", errorMessage(err));
    } finally {
      setIsNegotiationActing(false);
    }
  };

  return (
    <section id="live-negotiation" className="scroll-mt-16 space-y-4">
      {/* Section Header */}
      <div className="flex items-center justify-between pb-1 border-b border-border">
        <div>
          <h2 className="text-11 uppercase font-semibold tracking-wider text-muted">
            Live Operations
          </h2>
          <h1 className="text-20 font-semibold text-text">
            City Emergency: Live Negotiation
          </h1>
        </div>

        {/* Negotiation protocol controls */}
        <div className="flex items-center gap-2">
          {isPaused ? (
            <button
              type="button"
              onClick={handleNegotiationResume}
              disabled={isNegotiationActing}
              className="px-3 py-1.5 rounded-control text-12 font-medium bg-ok text-black hover:bg-ok/90 flex items-center gap-1.5 cursor-pointer disabled:opacity-50"
            >
              <Play size={13} strokeWidth={1.5} />
              <span>Resume Negotiation</span>
            </button>
          ) : (
            <button
              type="button"
              onClick={handleNegotiationPause}
              disabled={isNegotiationActing}
              className="px-3 py-1.5 rounded-control text-12 font-medium bg-surface-2 border border-border text-muted hover:text-text flex items-center gap-1.5 cursor-pointer disabled:opacity-50"
            >
              <Pause size={13} strokeWidth={1.5} />
              <span>Pause Negotiation</span>
            </button>
          )}

          <button
            type="button"
            onClick={handleNegotiationStart}
            disabled={isNegotiationActing}
            className="px-3 py-1.5 rounded-control text-12 font-medium bg-surface-2 border border-border text-text hover:bg-border flex items-center gap-1.5 cursor-pointer disabled:opacity-50"
          >
            <span>Trigger Round</span>
          </button>
        </div>
      </div>

      {/* Pinned Executive SitRep Banner */}
      <CommanderSitRep compact />

      {/* Side-by-side grid */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-5">
        {/* Left column: 6 Agent Cards */}
        <div className="lg:col-span-5 space-y-3">
          <div className="flex items-center justify-between">
            <span className="text-11 uppercase font-semibold text-muted tracking-wider">
              Utility Agents ({orderedAgents.length})
            </span>
            <span className="text-11 text-muted">Click card for detail</span>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-1 gap-2.5">
            {orderedAgents.map((agent) => {
              const highlight = getAgentHighlight(agent.agent_id);
              return (
                <AgentCard
                  key={agent.agent_id}
                  agent={agent}
                  isRequesting={highlight.isRequesting}
                  requestQuantity={highlight.quantity}
                  requestUnit={highlight.unit}
                  isSupplyFlash={highlight.isSupplyFlash}
                  onClick={(id) => {
                    setSelectedAgent(id);
                    setDrawerOpen(true);
                  }}
                />
              );
            })}
          </div>
        </div>

        {/* Right column: Live Negotiation Chat & Proposals */}
        <div className="lg:col-span-7 flex flex-col space-y-4">
          <div className="flex items-center justify-between">
            <span className="text-11 uppercase font-semibold text-muted tracking-wider">
              Live Negotiation Feed
            </span>

            {/* Filter Tabs */}
            <div className="flex items-center gap-1 p-0.5 bg-surface-2 rounded-control border border-border">
              {FILTER_TABS.map((tab) => (
                <button
                  key={tab.id}
                  type="button"
                  onClick={() => setChatFilter(tab.id as ChatFilter)}
                  className={`px-2 py-0.5 text-11 rounded-control transition-colors cursor-pointer ${
                    chatFilter === tab.id
                      ? "bg-surface text-text font-medium border border-border/80"
                      : "text-muted hover:text-text"
                  }`}
                >
                  {tab.label}
                </button>
              ))}
            </div>
          </div>

          {/* Chat Messages Box */}
          <div className="relative">
            <div
              ref={chatContainerRef}
              onScroll={handleScroll}
              aria-live="polite"
              className="p-3 bg-surface rounded-panel border border-border h-[460px] overflow-y-auto space-y-2.5 relative"
            >
              {filteredMessages.length === 0 ? (
                <div className="h-full flex items-center justify-center text-12 text-muted">
                  No messages matching current filter.
                </div>
              ) : (
                filteredMessages.map((msg) => (
                  <MessageBubble key={msg.message_id} message={msg} />
                ))
              )}
            </div>

            {/* "New messages" jump button if user scrolled up */}
            {hasScrolledUp && (
              <button
                type="button"
                onClick={scrollToBottom}
                className="absolute bottom-3 right-3 px-2.5 py-1 text-11 rounded-control bg-accent text-white font-medium flex items-center gap-1 shadow-md cursor-pointer hover:bg-accent/90 transition-colors"
              >
                <ArrowDown size={12} strokeWidth={2} />
                <span>New messages</span>
              </button>
            )}
          </div>

          {/* Pending Proposals Section */}
          <div className="space-y-2 pt-2">
            <span className="text-11 uppercase font-semibold text-muted tracking-wider block">
              Pending Proposals ({proposals.length})
            </span>
            <ProposalList
              proposals={proposals}
              onToast={addToast}
            />
          </div>

          {/* Verified Agreements Section */}
          <div className="space-y-2 pt-2">
            <span className="text-11 uppercase font-semibold text-muted tracking-wider block">
              Verified Agreements ({agreements.length})
            </span>
            <AgreementList agreements={agreements} />
          </div>
        </div>
      </div>

      {/* Agent Detail Drawer */}
      <AgentDrawer
        agentId={selectedAgentId}
        isOpen={isDrawerOpen}
        onClose={() => setDrawerOpen(false)}
      />

      <Toast toasts={toasts} onDismiss={dismissToast} />
    </section>
  );
}
