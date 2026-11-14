import { useState } from "react";
import { TopBar } from "@/components/TopBar";
import { Sidebar } from "@/components/Sidebar";
import { useScrollSpy } from "@/hooks/useScrollSpy";
import { useSimulationSocket } from "@/hooks/useSimulationSocket";
import { OverviewSection } from "@/sections/OverviewSection";
import { NegotiationSection } from "@/sections/NegotiationSection";
import { TwinSection } from "@/sections/TwinSection";
import { AgentNetworkSection } from "@/sections/AgentNetworkSection";
import { TrustSection } from "@/sections/TrustSection";
import { AllocationSection } from "@/sections/AllocationSection";
import { LabSection } from "@/sections/LabSection";
import { AuditSection } from "@/sections/AuditSection";
import { useSimStore } from "@/store/useSimStore";

export function App() {
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);
  const { activeId, scrollTo } = useScrollSpy(90);

  // Initialize live simulation WebSocket feed
  useSimulationSocket();

  // Read live state from Zustand store
  const connectionState = useSimStore((s) => s.connectionState);
  const snapshot = useSimStore((s) => s.snapshot);

  const status = snapshot?.status ?? "idle";
  const scenario = snapshot?.scenario ?? "grid_shortage";
  const simTime = snapshot?.sim_time;

  return (
    <div className="min-h-screen bg-bg text-text antialiased">
      <TopBar
        status={status}
        scenario={scenario}
        simTime={simTime}
        connectionState={connectionState}
        mobileMenuOpen={mobileMenuOpen}
        onToggleMobileMenu={() => setMobileMenuOpen((prev) => !prev)}
      />

      <Sidebar
        activeId={activeId}
        onSelect={scrollTo}
        mobileMenuOpen={mobileMenuOpen}
        onCloseMobileMenu={() => setMobileMenuOpen(false)}
      />

      <main className="md:ml-52 mt-12 p-4 sm:p-6 lg:p-8 max-w-7xl mx-auto space-y-12 pb-24">
        <OverviewSection />
        <NegotiationSection />
        <TwinSection />
        <AgentNetworkSection />
        <TrustSection />
        <AllocationSection />
        <LabSection />
        <AuditSection />
      </main>
    </div>
  );
}

export default App;
