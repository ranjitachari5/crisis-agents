export function formatMw(value: number | null | undefined, digits = 0): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "—";
  return `${value.toFixed(digits)} MW`;
}

export function formatPct(value: number | null | undefined, digits = 0): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "—";
  const pct = value <= 1.5 ? value * 100 : value;
  return `${pct.toFixed(digits)}%`;
}

export function formatSimTime(iso: string | null | undefined): string {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toISOString().slice(11, 19);
}

export function formatClock(iso: string | null | undefined): string {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleTimeString("en-GB", { hour12: false });
}

export function statusLabel(status: string): string {
  if (status === "running") return "Running";
  if (status === "paused") return "Paused";
  if (status === "idle") return "Idle";
  return status;
}

export function fairnessPolicyLine(value: number): string {
  if (value < 0.34) return "Priority-focused: critical weights dominate the blend.";
  if (value < 0.67) return "Balanced: priority and equal-share terms are mixed.";
  return "Equity-focused: equal-share allocation is weighted more heavily.";
}

export function fairnessStopLabel(value: number): string {
  if (value <= 0.25) return "Priority";
  if (value >= 0.75) return "Equity";
  return "Balanced";
}
