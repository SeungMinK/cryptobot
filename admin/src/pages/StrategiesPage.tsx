import { useEffect, useState } from "react";
import { getStrategies, getActivationHistory, activateStrategy, deactivateStrategy } from "../api/strategies";
import type { Strategy, StrategyActivation } from "../types/strategies";
import ConfirmDialog from "../components/ConfirmDialog";
import { formatPercent, formatDateTime } from "../utils/format";

export default function StrategiesPage() {
  const [strategies, setStrategies] = useState<Strategy[]>([]);
  const [activations, setActivations] = useState<StrategyActivation[]>([]);
  const [loading, setLoading] = useState(true);
  const [confirm, setConfirm] = useState<{ name: string; action: "activate" | "deactivate" } | null>(null);

  const fetchData = async () => {
    try {
      const [strats, hist] = await Promise.all([
        getStrategies(),
        getActivationHistory(20),
      ]);
      setStrategies(strats);
      setActivations(hist);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchData();
  }, []);

  const handleToggle = async () => {
    if (!confirm) return;
    try {
      if (confirm.action === "activate") {
        await activateStrategy(confirm.name, "Dashboard에서 수동 활성화");
      } else {
        await deactivateStrategy(confirm.name, "Dashboard에서 수동 비활성화");
      }
      await fetchData();
    } finally {
      setConfirm(null);
    }
  };

  if (loading) return <div className="loading">로딩 중...</div>;

  const activeStrategies = strategies.filter((s) => s.is_active);

  return (
    <div>
      <div className="page-header">
        <h1>전략 관리</h1>
        <p>매매 전략 조회 및 활성화/비활성화</p>
      </div>

      {/* Active strategies banner */}
      {activeStrategies.length > 0 && (
        <div className="card" style={{ marginBottom: 24, borderColor: "var(--accent-green)" }}>
          <div className="card-title">활성 전략</div>
          <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
            {activeStrategies.map((s) => (
              <span key={s.name} className="badge badge-green">{s.display_name}</span>
            ))}
          </div>
        </div>
      )}

      {/* Strategy cards */}
      <div className="strategy-grid">
        {strategies.map((s) => (
          <div key={s.name} className={`strategy-card ${s.is_active ? "active-strategy" : ""}`}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start" }}>
              <div>
                <h3>{s.display_name}</h3>
                <div style={{ display: "flex", gap: 6, marginBottom: 4 }}>
                  <span className="badge badge-purple">{s.category}</span>
                  <span className="badge badge-blue">{s.difficulty}</span>
                </div>
              </div>
              <span className={`badge ${s.is_active ? "badge-green" : "badge-red"}`}>
                {s.is_active ? "활성" : "비활성"}
              </span>
            </div>
            <p className="strategy-desc">{s.description}</p>
            <div className="strategy-stats">
              <div className="strategy-stat-item">
                <div className="stat-label">총 거래</div>
                <div className="stat-value">{s.stats?.total_trades ?? 0}</div>
              </div>
              <div className="strategy-stat-item">
                <div className="stat-label">승률</div>
                <div className="stat-value">{s.stats?.win_rate != null ? formatPercent(s.stats.win_rate * 100).replace("+", "") : "-"}</div>
              </div>
              <div className="strategy-stat-item">
                <div className="stat-label">평균 수익률</div>
                <div className={`stat-value ${(s.stats?.avg_profit_pct ?? 0) >= 0 ? "positive" : "negative"}`}>
                  {s.stats?.avg_profit_pct != null ? formatPercent(s.stats.avg_profit_pct) : "-"}
                </div>
              </div>
              <div className="strategy-stat-item">
                <div className="stat-label">최대 손실</div>
                <div className="stat-value negative">
                  {s.stats?.max_loss_pct != null ? formatPercent(s.stats.max_loss_pct) : "-"}
                </div>
              </div>
            </div>
            <div style={{ display: "flex", gap: 8 }}>
              <span className="badge badge-yellow">{s.market_states}</span>
              <span className="badge badge-blue">{s.timeframe}</span>
            </div>
            <div style={{ marginTop: 12 }}>
              {s.is_active ? (
                <button className="btn btn-danger btn-sm" onClick={() => setConfirm({ name: s.name, action: "deactivate" })}>
                  비활성화
                </button>
              ) : (
                <button
                  className="btn btn-primary btn-sm"
                  disabled={!s.is_available}
                  onClick={() => setConfirm({ name: s.name, action: "activate" })}
                >
                  활성화
                </button>
              )}
            </div>
          </div>
        ))}
      </div>

      {/* Activation History */}
      <div className="card">
        <div className="card-title">활성화 이력</div>
        {activations.length > 0 ? (
          <div className="table-container">
            <table>
              <thead>
                <tr>
                  <th>시간</th>
                  <th>전략</th>
                  <th>동작</th>
                  <th>소스</th>
                  <th>시장 상태</th>
                  <th>사유</th>
                </tr>
              </thead>
              <tbody>
                {activations.map((a) => (
                  <tr key={a.id}>
                    <td style={{ fontSize: 12 }}>{formatDateTime(a.timestamp)}</td>
                    <td>{a.strategy_name}</td>
                    <td>
                      <span className={`badge ${a.action === "activate" ? "badge-green" : "badge-red"}`}>
                        {a.action === "activate" ? "활성화" : "비활성화"}
                      </span>
                    </td>
                    <td><span className="badge badge-blue">{a.source}</span></td>
                    <td>{a.market_state}</td>
                    <td style={{ fontSize: 12, color: "var(--text-secondary)" }}>{a.reason || "-"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <div className="empty-state">활성화 이력 없음</div>
        )}
      </div>

      {confirm && (
        <ConfirmDialog
          title={`전략 ${confirm.action === "activate" ? "활성화" : "비활성화"}`}
          message={`'${confirm.name}' 전략을 ${confirm.action === "activate" ? "활성화" : "비활성화"}하시겠습니까?`}
          onConfirm={handleToggle}
          onCancel={() => setConfirm(null)}
        />
      )}
    </div>
  );
}
