import type { MessageType } from "@/types/api";

export type ChatFilter = "all" | "requests" | "offers" | "agreements" | "system";

export const FILTER_TABS: { id: ChatFilter; label: string }[] = [
  { id: "all", label: "All" },
  { id: "requests", label: "Requests" },
  { id: "offers", label: "Offers" },
  { id: "agreements", label: "Agreements" },
  { id: "system", label: "System" },
];

const REQUEST_TYPES = new Set<MessageType>([
  "request",
  "bid",
  "peer_request",
  "emergency_warning",
]);

const OFFER_TYPES = new Set<MessageType>([
  "offer",
  "counteroffer",
  "concession",
  "accept",
  "reject",
]);

const AGREEMENT_TYPES = new Set<MessageType>(["proposal", "validation", "agreement"]);

const SYSTEM_TYPES = new Set<MessageType>([
  "system",
  "event",
  "negotiation_round",
  "supply_report",
  "trust_alert",
  "commander_action",
  "explanation",
  "claim",
]);

export function messageGroup(type: MessageType): Exclude<ChatFilter, "all"> {
  if (REQUEST_TYPES.has(type)) return "requests";
  if (OFFER_TYPES.has(type)) return "offers";
  if (AGREEMENT_TYPES.has(type)) return "agreements";
  if (SYSTEM_TYPES.has(type)) return "system";
  return "system";
}

export function isRequestHighlight(type: MessageType): boolean {
  return REQUEST_TYPES.has(type);
}

export function isSystemStyle(type: MessageType): boolean {
  return messageGroup(type) === "system" || messageGroup(type) === "agreements";
}

export function matchesFilter(type: MessageType, filter: ChatFilter): boolean {
  if (filter === "all") return true;
  return messageGroup(type) === filter;
}

export function highlightClass(type: MessageType): "request" | "supply" | "none" {
  if (isRequestHighlight(type)) return "request";
  if (type === "supply_report") return "supply";
  return "none";
}
