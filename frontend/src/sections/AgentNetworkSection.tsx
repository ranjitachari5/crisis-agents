import { useState } from "react";
import { PlusCircle } from "lucide-react";
import { AgentNetwork } from "@/components/AgentNetwork";
import { CreateAgentDialog } from "@/components/CreateAgentDialog";

export function AgentNetworkSection() {
  const [dialogOpen, setDialogOpen] = useState(false);

  return (
    <section id="agent-network" className="scroll-mt-16 space-y-4">
      <div className="flex items-center justify-between pb-1 border-b border-border">
        <div>
          <h2 className="text-11 uppercase font-semibold tracking-wider text-muted">
            Topology
          </h2>
          <h1 className="text-20 font-semibold text-text">
            Agent Communication Network
          </h1>
        </div>

        <button
          type="button"
          onClick={() => setDialogOpen(true)}
          className="px-3 py-1.5 rounded-control bg-accent/15 hover:bg-accent/25 border border-accent/40 text-accent font-medium text-12 flex items-center gap-1.5 transition-colors cursor-pointer shadow-sm shadow-accent/10"
        >
          <PlusCircle size={14} />
          <span>Deploy Custom Agent</span>
        </button>
      </div>

      <AgentNetwork onDeployAgent={() => setDialogOpen(true)} />

      <CreateAgentDialog open={dialogOpen} onClose={() => setDialogOpen(false)} />
    </section>
  );
}
