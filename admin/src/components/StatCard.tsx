interface StatCardProps {
  label: string;
  value: string;
  sub?: string;
  valueClass?: string;
}

export default function StatCard({ label, value, sub, valueClass }: StatCardProps) {
  return (
    <div className="kpi-card">
      <div className="kpi-label">{label}</div>
      <div className={`kpi-value ${valueClass || ""}`}>{value}</div>
      {sub && <div className="kpi-sub">{sub}</div>}
    </div>
  );
}
