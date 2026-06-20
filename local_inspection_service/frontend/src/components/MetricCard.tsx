export function MetricCard({
  label,
  value,
  tone = "neutral",
  detail
}: {
  label: string;
  value: React.ReactNode;
  tone?: "neutral" | "ok" | "fail" | "warn";
  detail?: React.ReactNode;
}) {
  return (
    <div className="metric-card">
      <label>{label}</label>
      <strong className={`metric-value ${tone}`}>{value}</strong>
      {detail ? <span>{detail}</span> : null}
    </div>
  );
}
