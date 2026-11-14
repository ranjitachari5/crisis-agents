interface Props {
  label: string;
  value: string | number;
  unit?: string;
  isAccent?: boolean;
  subtext?: string;
}

export function MetricTile({
  label,
  value,
  unit,
  isAccent = false,
  subtext,
}: Props) {
  return (
    <div className="p-3 bg-surface rounded-panel border border-border flex flex-col justify-between">
      <div className="flex items-center justify-between">
        <span className="text-11 uppercase font-semibold tracking-wider text-muted">
          {label}
        </span>
      </div>

      <div className="mt-2 flex items-baseline gap-1.5">
        <span
          className={`text-20 font-semibold tabular-nums transition-colors duration-150 ${
            isAccent ? "text-accent" : "text-text"
          }`}
        >
          {value}
        </span>
        {unit && <span className="text-12 text-muted select-none">{unit}</span>}
      </div>

      {subtext && (
        <div className="mt-1 text-11 text-muted truncate">{subtext}</div>
      )}
    </div>
  );
}

