import { AgentNetwork } from "@/components/AgentNetwork";

export function AgentNetworkSection() {
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
      </div>

      <AgentNetwork />
    </section>
  );
}
