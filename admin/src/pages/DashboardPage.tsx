import { useEffect, useState, useCallback } from "react";
import { Link } from "react-router-dom";
import { AreaChart, Area, XAxis, YAxis, Tooltip, ResponsiveContainer } from "recharts";
import { getBalance, getPositions, getBalanceHistory, getBalanceHistorySnapshots } from "../api/balance";
import type { SnapshotHistory } from "../api/balance";
import { getCurrentMarket } from "../api/market";
import { getTrades } from "../api/trades";
import { getActiveStrategies } from "../api/strategies";
import type { BalanceResponse, PositionsResponse, BalanceHistory } from "../types/balance";
import type { MarketSnapshot } from "../types/market";
import type { Trade } from "../types/trades";
import type { Strategy } from "../types/strategies";
import StatCard from "../components/StatCard";
import { formatKRW, formatPercent, formatNumber, formatDateTime } from "../utils/format";

const CHART_PERIODS = [
  { label: "1시간", hours: 1 },
  { label: "6시간", hours: 6 },
  { label: "12시간", hours: 12 },
  { label: "1일", hours: 24 },
  { label: "3일", hours: 72 },
  { label: "7일", hours: 168 },
  { label: "30일", hours: 720 },
] as const;

export default function DashboardPage() {
  const [balance, setBalance] = useState<BalanceResponse | null>(null);
  const [positions, setPositions] = useState<PositionsResponse | null>(null);
  const [history, setHistory] = useState<BalanceHistory[]>([]);
  const [snapshotHistory, setSnapshotHistory] = useState<SnapshotHistory[]>([]);
  const [chartPeriod, setChartPeriod] = useState(1);
  const [market, setMarket] = useState<MarketSnapshot | null>(null);
  const [recentTrades, setRecentTrades] = useState<Trade[]>([]);
  const [activeStrategies, setActiveStrategies] = useState<Strategy[]>([]);
  const [loading, setLoading] = useState(true);
  const [chartLoading, setChartLoading] = useState(false);

  useEffect(() => {
    Promise.all([
      getBalance().catch(() => null),
      getPositions().catch(() => null),
      getBalanceHistory(30).catch(() => []),
      getBalanceHistorySnapshots(1).catch(() => []),
      getCurrentMarket().catch(() => null),
      getTrades({ limit: 5 }).catch(() => ({ items: [] })),
      getActiveStrategies().catch(() => []),
    ]).then(([bal, pos, hist, snapHist, mkt, trades, strats]) => {
      setBalance(bal);
      setPositions(pos as PositionsResponse | null);
      setHistory(hist as BalanceHistory[]);
      setSnapshotHistory(snapHist as SnapshotHistory[]);
      setMarket(mkt as MarketSnapshot | null);
      setRecentTrades((trades as { items: Trade[] }).items);
      setActiveStrategies(strats as Strategy[]);
      setLoading(false);
    });
  }, []);

  const handlePeriodChange = useCallback(async (hours: number) => {
    setChartPeriod(hours);
    setChartLoading(true);
    try {
      const data = await getBalanceHistorySnapshots(hours);
      setSnapshotHistory(data);
    } catch {
      setSnapshotHistory([]);
    } finally {
      setChartLoading(false);
    }
  }, []);

  if (loading) return <div className="loading">로딩 중...</div>;

  const marketState = market && "market_state" in market ? market.market_state : null;

  return (
    <div>
      <div className="page-header">
        <h1>Dashboard</h1>
        <p>전체 현황 요약</p>
      </div>

      {/* KPI Cards */}
      <div className="kpi-grid">
        <StatCard
          label="총 자산"
          value={balance ? formatKRW(balance.total_asset_krw) : "-"}
        />
        <StatCard
          label="KRW 잔고"
          value={balance ? formatKRW(balance.krw_balance) : "-"}
        />
        <StatCard
          label="코인 가치"
          value={balance ? formatKRW(balance.coin_value_krw) : "-"}
        />
        <StatCard
          label="API 연결"
          value={balance?.api_connected ? "Connected" : "Disconnected"}
          valueClass={balance?.api_connected ? "positive" : "negative"}
        />
      </div>

      <div className="grid-2">
        {/* Position Card */}
        <div className="card">
          <div className="card-title">현재 포지션</div>
          {positions?.has_position && positions.position ? (
            <div>
              <div style={{ fontSize: 18, fontWeight: 600, marginBottom: 8 }}>
                {positions.position.coin}
              </div>
              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8 }}>
                <div>
                  <div style={{ fontSize: 12, color: "var(--text-muted)" }}>매수가</div>
                  <div>{formatKRW(positions.position.price)}</div>
                </div>
                <div>
                  <div style={{ fontSize: 12, color: "var(--text-muted)" }}>현재가</div>
                  <div>{formatKRW(positions.position.current_price)}</div>
                </div>
                <div>
                  <div style={{ fontSize: 12, color: "var(--text-muted)" }}>수량</div>
                  <div>{formatNumber(positions.position.amount, 8)}</div>
                </div>
                <div>
                  <div style={{ fontSize: 12, color: "var(--text-muted)" }}>미실현 손익</div>
                  <div className={positions.position.unrealized_pnl_pct >= 0 ? "positive" : "negative"}>
                    {formatPercent(positions.position.unrealized_pnl_pct)} ({formatKRW(positions.position.unrealized_pnl_krw)})
                  </div>
                </div>
              </div>
            </div>
          ) : (
            <div className="empty-state">보유 포지션 없음</div>
          )}
        </div>

        {/* Market Status */}
        <div className="card">
          <div className="card-title">시장 현황</div>
          {market && marketState ? (
            <div>
              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8 }}>
                <div>
                  <div style={{ fontSize: 12, color: "var(--text-muted)" }}>BTC 가격</div>
                  <div style={{ fontSize: 18, fontWeight: 600 }}>{formatKRW(market.btc_price)}</div>
                </div>
                <div>
                  <div style={{ fontSize: 12, color: "var(--text-muted)" }}>24h 변동</div>
                  <div className={market.btc_change_pct_24h >= 0 ? "positive" : "negative"} style={{ fontSize: 18, fontWeight: 600 }}>
                    {formatPercent(market.btc_change_pct_24h)}
                  </div>
                </div>
                <div>
                  <div style={{ fontSize: 12, color: "var(--text-muted)" }}>RSI (14)</div>
                  <div>{market.btc_rsi_14?.toFixed(1) ?? "-"}</div>
                </div>
                <div>
                  <div style={{ fontSize: 12, color: "var(--text-muted)" }}>시장 상태</div>
                  <span className={`badge ${marketState === "bullish" ? "badge-green" : marketState === "bearish" ? "badge-red" : "badge-yellow"}`}>
                    {marketState}
                  </span>
                </div>
                <div>
                  <div style={{ fontSize: 12, color: "var(--text-muted)" }}>변동성</div>
                  <span className={`badge ${market.volatility_level === "high" ? "badge-red" : market.volatility_level === "medium" ? "badge-yellow" : "badge-green"}`}>
                    {market.volatility_level}
                  </span>
                </div>
              </div>
            </div>
          ) : (
            <div className="empty-state">시장 데이터 없음</div>
          )}
        </div>
      </div>

      {/* Asset History Chart */}
      <div className="card" style={{ marginBottom: 24 }}>
        <div className="card-title" style={{ display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: 8 }}>
          <span>BTC 가격 추이</span>
          <div style={{ display: "flex", gap: 4 }}>
            {CHART_PERIODS.map((p) => (
              <button
                key={p.hours}
                onClick={() => handlePeriodChange(p.hours)}
                style={{
                  padding: "4px 10px",
                  fontSize: 12,
                  borderRadius: 6,
                  border: "none",
                  cursor: "pointer",
                  background: chartPeriod === p.hours ? "#4a9eff" : "#2a2d3e",
                  color: chartPeriod === p.hours ? "#fff" : "#8b8fa3",
                  transition: "all 0.15s",
                }}
              >
                {p.label}
              </button>
            ))}
          </div>
        </div>
        {chartLoading ? (
          <div className="empty-state">로딩 중...</div>
        ) : snapshotHistory.length > 0 ? (
          <ResponsiveContainer width="100%" height={250}>
            <AreaChart data={snapshotHistory}>
              <defs>
                <linearGradient id="assetGradient" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor="#4a9eff" stopOpacity={0.3} />
                  <stop offset="100%" stopColor="#4a9eff" stopOpacity={0} />
                </linearGradient>
              </defs>
              <XAxis
                dataKey="timestamp"
                tick={{ fill: "#8b8fa3", fontSize: 11 }}
                tickFormatter={(v) => {
                  const d = new Date(v);
                  return chartPeriod <= 24
                    ? d.toLocaleTimeString("ko-KR", { hour: "2-digit", minute: "2-digit" })
                    : d.toLocaleDateString("ko-KR", { month: "short", day: "numeric" });
                }}
              />
              <YAxis
                tick={{ fill: "#8b8fa3", fontSize: 11 }}
                domain={["auto", "auto"]}
                tickFormatter={(v) => `${(v / 10000).toFixed(0)}만`}
              />
              <Tooltip
                contentStyle={{ background: "#1e2130", border: "1px solid #2a2d3e", borderRadius: 8, color: "#e4e6f0" }}
                labelFormatter={(v) => new Date(v).toLocaleString("ko-KR")}
                formatter={(value) => [formatKRW(Number(value)), "BTC 가격"]}
              />
              <Area type="monotone" dataKey="btc_price" stroke="#4a9eff" fill="url(#assetGradient)" />
            </AreaChart>
          </ResponsiveContainer>
        ) : (
          <div className="empty-state">데이터 없음 (봇이 수집 중이면 잠시 후 표시됩니다)</div>
        )}
      </div>

      <div className="grid-2">
        {/* Recent Trades */}
        <div className="card">
          <div className="card-title" style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
            <span>최근 매매</span>
            <Link to="/trades" style={{ fontSize: 12 }}>전체 보기</Link>
          </div>
          {recentTrades.length > 0 ? (
            <div className="table-container">
              <table>
                <thead>
                  <tr>
                    <th>시간</th>
                    <th>종목</th>
                    <th>방향</th>
                    <th>금액</th>
                  </tr>
                </thead>
                <tbody>
                  {recentTrades.map((t) => (
                    <tr key={t.id}>
                      <td style={{ fontSize: 12 }}>{formatDateTime(t.timestamp)}</td>
                      <td>{t.coin}</td>
                      <td>
                        <span className={`badge ${t.side === "buy" ? "badge-green" : "badge-red"}`}>
                          {t.side === "buy" ? "매수" : "매도"}
                        </span>
                      </td>
                      <td>{formatKRW(t.total_krw)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <div className="empty-state">매매 내역 없음</div>
          )}
        </div>

        {/* Active Strategies */}
        <div className="card">
          <div className="card-title">활성 전략</div>
          {activeStrategies.length > 0 ? (
            <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
              {activeStrategies.map((s) => (
                <span key={s.name} className="badge badge-blue">{s.display_name}</span>
              ))}
            </div>
          ) : (
            <div className="empty-state">활성화된 전략 없음</div>
          )}
        </div>
      </div>
    </div>
  );
}
