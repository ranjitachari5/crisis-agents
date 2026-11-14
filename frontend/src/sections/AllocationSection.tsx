import { useState } from "react";
import { AllocationChart } from "@/components/AllocationChart";
import { OverrideDialog } from "@/components/OverrideDialog";
import { Toast, type ToastMessage } from "@/components/Toast";

export function AllocationSection() {
  const [isOverrideOpen, setIsOverrideOpen] = useState(false);
  const [toasts, setToasts] = useState<ToastMessage[]>([]);

  const addToast = (type: "success" | "error" | "info", message: string) => {
    const id = `${Date.now()}-${Math.random().toString(36).substring(2, 7)}`;
    setToasts((prev) => [...prev, { id, type, message }]);
  };

  const dismissToast = (id: string) => {
    setToasts((prev) => prev.filter((t) => t.id !== id));
  };

  return (
    <section id="resource-allocation" className="scroll-mt-16 space-y-4">
      <div className="flex items-center justify-between pb-1 border-b border-border">
        <div>
          <h2 className="text-11 uppercase font-semibold tracking-wider text-muted">
            Optimization
          </h2>
          <h1 className="text-20 font-semibold text-text">Resource Allocation</h1>
        </div>
      </div>

      {/* Main Allocation Charts & Metadata */}
      <AllocationChart onOpenOverride={() => setIsOverrideOpen(true)} />

      {/* Commander Override Dialog */}
      <OverrideDialog
        isOpen={isOverrideOpen}
        onClose={() => setIsOverrideOpen(false)}
        onSuccess={(msg) => addToast("success", msg)}
      />

      {/* Local Toast Feedback */}
      <Toast toasts={toasts} onDismiss={dismissToast} />
    </section>
  );
}
