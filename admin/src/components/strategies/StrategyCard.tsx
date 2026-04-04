import type { Strategy } from "../../types/strategies";
import { formatPercent } from "../../utils/format";

interface Props {
  strategy: Strategy;
  hasSwitching: boolean;
  activeCoins: string[];
  onEdit: () => void;
  onActivate: () => void;
  onDeactivate: () => void;
}

export default function StrategyCard({ strategy: s, hasSwitching, activeCoins, onEdit, onActivate, onDeactivate }: Props) {
  return (
    <div
      className="strategy-card"
      onClick={onEdit}
      style={{ cursor: "pointer" }}
    >
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start" }}>
        <div>
          <h3>{s.display_name}</h3>
          <div style={{ display: "flex", gap: 6, marginBottom: 4 }}>
            <span className="badge badge-purple">{s.category}</span>
            <span className="badge badge-blue">{s.difficulty}</span>
          </div>
        </div>
        {activeCoins.length > 0 ? (
          <div style={{ display: "flex", gap: 4, flexWrap: "wrap" }}>
            {activeCoins.map((c) => (
              <span key={c} className="badge badge-green" style={{ fontSize: 10 }}>{c}</span>
            ))}
          </div>
        ) : (
          <span className="badge badge-red" style={{ fontSize: 10 }}>미사용</span>
        )}
      </div>
      <p className="strategy-desc">{s.description}</p>
      <div className="strategy-stats">
        <div className="strategy-stat-item">
          <div className="stat-label">총 거래</div>
          <div className="stat-value">{s.stats?.total_trades ?? 0}</div>
        </div>
        <div className="strategy-stat-item">
          <div className="stat-label">승률</div>
          <div className="stat-value">{s.stats?.total_trades > 0 && s.stats?.win_rate != null ? `${s.stats.win_rate.toFixed(1)}%` : "N/A"}</div>
        </div>
        <div className="strategy-stat-item">
          <div className="stat-label">평균 수익률</div>
          <div className={`stat-value ${(s.stats?.avg_profit_pct ?? 0) >= 0 ? "positive" : "negative"}`}>
            {s.stats?.avg_profit_pct != null ? formatPercent(s.stats.avg_profit_pct) : "-"}
          </div>
        </div>
      </div>
      <div style={{ display: "flex", gap: 8 }}>
        <span className="badge badge-blue">{s.timeframe}</span>
      </div>
    </div>
  );
}
