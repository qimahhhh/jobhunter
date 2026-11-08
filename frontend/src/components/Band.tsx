type Props = {
  step: number;
  total: number;
  label: string;
  action?: { label: string; onClick: () => void };
  tone?: "ink" | "yellow";
};

export default function Band({ step, total, label, action, tone = "ink" }: Props) {
  return (
    <div className={tone === "yellow" ? "band y" : "band"}>
      <div className="b-l">
        <b>
          {String(step).padStart(2, "0")} / {String(total).padStart(2, "0")}
        </b>
        <span>{label}</span>
      </div>
      <div className="b-r">
        <span className="ticks" aria-hidden="true">
          {Array.from({ length: total }, (_, i) => (
            <i key={i} className={i < step ? "on" : ""} />
          ))}
        </span>
        {action && (
          <button
            className={tone === "yellow" ? "pill sm solid" : "pill sm y"}
            onClick={action.onClick}
            type="button"
          >
            {action.label}
          </button>
        )}
      </div>
    </div>
  );
}
