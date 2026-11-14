import { useState, useEffect, useRef } from "react";
import { fairnessPolicyLine, fairnessStopLabel } from "@/lib/format";

interface Props {
  initialValue: number;
  onCommit: (value: number) => Promise<void>;
  disabled?: boolean;
}

export function FairnessSlider({
  initialValue,
  onCommit,
  disabled = false,
}: Props) {
  const [value, setValue] = useState(initialValue);
  const [isUpdating, setIsUpdating] = useState(false);
  const debounceRef = useRef<number | null>(null);

  // Synchronize if server state updates externally
  useEffect(() => {
    setValue(initialValue);
  }, [initialValue]);

  const commitValue = async (v: number) => {
    setIsUpdating(true);
    try {
      await onCommit(v);
    } finally {
      setIsUpdating(false);
    }
  };

  const handleSliderChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const nextVal = parseFloat(e.target.value);
    setValue(nextVal);

    if (debounceRef.current !== null) {
      clearTimeout(debounceRef.current);
    }

    // Debounce on release / drag settle
    debounceRef.current = window.setTimeout(() => {
      commitValue(nextVal);
    }, 300);
  };

  const setStop = (stopValue: number) => {
    setValue(stopValue);
    if (debounceRef.current !== null) {
      clearTimeout(debounceRef.current);
    }
    commitValue(stopValue);
  };

  return (
    <div className="p-4 bg-surface rounded-panel border border-border space-y-3">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <span className="text-11 uppercase font-semibold tracking-wider text-muted">
            Fairness Setting
          </span>
          {isUpdating && (
            <span className="text-11 text-muted animate-pulse">updating…</span>
          )}
        </div>
        <div className="flex items-baseline gap-1.5 tabular-nums">
          <span className="text-14 font-semibold text-text">{value.toFixed(2)}</span>
          <span className="text-12 text-muted">({fairnessStopLabel(value)})</span>
        </div>
      </div>

      <div className="space-y-2">
        <input
          type="range"
          min="0"
          max="1"
          step="0.05"
          value={value}
          onChange={handleSliderChange}
          disabled={disabled}
          className="w-full h-1.5 bg-surface-2 rounded-control appearance-none cursor-pointer accent-accent disabled:opacity-50"
          aria-label="Fairness allocation slider"
        />

        <div className="flex justify-between text-11 text-muted">
          <button
            type="button"
            onClick={() => setStop(0)}
            disabled={disabled}
            className={`hover:text-text cursor-pointer transition-colors ${
              value === 0 ? "text-accent font-medium" : ""
            }`}
          >
            0.0 Priority
          </button>
          <button
            type="button"
            onClick={() => setStop(0.5)}
            disabled={disabled}
            className={`hover:text-text cursor-pointer transition-colors ${
              value === 0.5 ? "text-accent font-medium" : ""
            }`}
          >
            0.5 Balanced
          </button>
          <button
            type="button"
            onClick={() => setStop(1)}
            disabled={disabled}
            className={`hover:text-text cursor-pointer transition-colors ${
              value === 1 ? "text-accent font-medium" : ""
            }`}
          >
            1.0 Equity
          </button>
        </div>
      </div>

      <div className="pt-2 border-t border-border flex flex-col sm:flex-row sm:items-center justify-between gap-1 text-12 text-muted">
        <div>{fairnessPolicyLine(value)}</div>
        <div className="text-11 text-muted sm:text-right">
          Safety minimums are not affected by this setting.
        </div>
      </div>
    </div>
  );
}

