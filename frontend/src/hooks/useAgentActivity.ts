import { useEffect } from "react";
import { EDGE_DOT_MS, EDGE_HIGHLIGHT_MS, REQUEST_HIGHLIGHT_MS } from "@/lib/constants";
import { useSimStore } from "@/store/useSimStore";

export function useAgentActivity() {
  const activity = useSimStore((s) => s.activity);
  const edgeActivity = useSimStore((s) => s.edgeActivity);
  const clearExpiredActivity = useSimStore((s) => s.clearExpiredActivity);

  // Periodically garbage collect expired timestamps
  useEffect(() => {
    const interval = window.setInterval(() => {
      clearExpiredActivity(Date.now());
    }, 300);

    return () => clearInterval(interval);
  }, [clearExpiredActivity]);

  const getAgentHighlight = (agentId: string) => {
    const item = activity[agentId];
    if (!item) {
      return {
        isRequesting: false,
        isSupplyFlash: false,
        quantity: null,
        unit: null,
      };
    }
    const elapsed = Date.now() - item.at;
    const isRequesting = !item.isSupplyFlash && elapsed <= REQUEST_HIGHLIGHT_MS;
    const isSupplyFlash = !!item.isSupplyFlash && elapsed <= 1200;

    return {
      isRequesting,
      isSupplyFlash,
      quantity: isRequesting ? item.quantity : null,
      unit: isRequesting ? item.unit : null,
    };
  };

  const getEdgeHighlight = (edgeId: string) => {
    const at = edgeActivity[edgeId];
    if (!at) {
      return { isLit: false, dotActive: false };
    }
    const elapsed = Date.now() - at;
    const dotActive = elapsed <= EDGE_DOT_MS;
    const isLit = elapsed <= EDGE_HIGHLIGHT_MS;

    return { isLit, dotActive };
  };

  return { activity, edgeActivity, getAgentHighlight, getEdgeHighlight };
}

