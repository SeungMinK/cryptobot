import { useEffect, useState } from "react";
import {
  LineChart, Line, BarChart, Bar, AreaChart, Area,
  XAxis, YAxis, Tooltip, ResponsiveContainer, Cell, PieChart, Pie,
} from "recharts";
import { getBalanceHistory } from "../api/balance";
import { getTradeStats, getDailyReturns } from "../api/trades";
import type { BalanceHistory } from "../types/balance";
import type { TradeStats, DailyReturn } from "../types/trades";
import StatCard from "../components/StatCard";
import { formatKRW, formatPercent } from "../utils/format";

const PERIODS = [
  { label: "7일", value: 7 },
  { label: "30일", value: 30 },
  { label: "90일", value: 90 },
];

const CHART_TOOLTIP_STYLE = {
  contentStyle: { background: "#1e2130", border: "1px solid #2a2d3e", borderRadius: 8, color: "#e4e6f0" },
};

export default function ProfitAnalysisPage() {
  const [days, setDays] = useState(30);
  const [stats, setStats] = useState<TradeStats | null>(null);
  const [daily, setDaily] = useState<DailyReturn[]>([]);
  const [history, setHistory] = useState<BalanceHistory[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setLoading(true);
    Promise.all([
      getTradeStats(days).catch(() => null),
      getDailyReturns(days).catch(() => []),
      getBalanceHistory(days).catch(() => []),
    ]).then(([s, d, h]) => {
      setStats(s);
      setDaily(d as DailyReturn[]);
      setHistory(h as BalanceHistory[]);
      setLoading(false);
    });
  }, [days]);

  if (loading) return <div className="loading">로딩 중...</div>;

  const winLossData = stats
    ? [
        { name: "승", value: stats.wins, color: "#34d399" },
        { name: "패", value: stats.losses, color: "#f87171" },
      ]
    : [];

  return (
    <div>
      <div className="page-header">
        <h1>수익률 분석</h1>
        <p>매매 성과 및 수익률 추이</p>
      </div>

      {/* Period Selector */}
      <div className="period-selector">
        {PERIODS.map((p) => (
          <button key={p.value} className={days === p.value ? "active" : ""} onClick={() => setDays(p.value)}>
            {p.label}
          </button>
        ))}
      </div>

      {/* KPI */}
      {stats && (
        <div className="kpi-grid">
          <StatCard label="총 거래" value={stats.total_trades.toString()} />
          <StatCard
            label="승률"
            value={formatPercent(stats.win_rate).replace("+", "")}
            sub={`${stats.wins}승 ${stats.losses}패`}
            valueClass={stats.win_rate >= 50 ? "positive" : "negative"}
          />
          <StatCard
            label="평균 수익률"
            value={formatPercent(stats.avg_profit_pct)}
            valueClass={stats.avg_profit_pct >= 0 ? "positive" : "negative"}
          />
          <StatCard
            label="총 수익"
            value={formatKRW(stats.total_profit_krw)}
            sub={`수수료: ${formatKRW(stats.total_fees)}`}
            valueClass={stats.total_profit_krw >= 0 ? "positive" : "negative"}
          />
        </div>
      )}

      {/* Cumulative Return Line Chart */}
      <div className="card" style={{ marginBottom: 24 }}>
        <div className="card-title">누적 수익률</div>
        {history.length > 0 ? (
          <ResponsiveContainer width="100%" height={250}>
            <LineChart data={history}>
              <XAxis dataKey="date" tick={{ fill: "#8b8fa3", fontSize: 11 }} />
              <YAxis tick={{ fill: "#8b8fa3", fontSize: 11 }} tickFormatter={(v) => `${v.toFixed(1)}%`} />
              <Tooltip {...CHART_TOOLTIP_STYLE} formatter={(value) => [formatPercent(Number(value)), "누적 수익률"]} />
              <Line type="monotone" dataKey="cumulative_return_pct" stroke="#4a9eff" strokeWidth={2} dot={false} />
            </LineChart>
          </ResponsiveContainer>
        ) : (
          <div className="empty-state">데이터 없음</div>
        )}
      </div>

      <div className="grid-2">
        {/* Daily PnL Bar Chart */}
        <div className="card">
          <div className="card-title">일별 손익</div>
          {daily.length > 0 ? (
            <ResponsiveContainer width="100%" height={220}>
              <BarChart data={daily}>
                <XAxis dataKey="date" tick={{ fill: "#8b8fa3", fontSize: 10 }} />
                <YAxis tick={{ fill: "#8b8fa3", fontSize: 11 }} tickFormatter={(v) => `${(v / 10000).toFixed(0)}만`} />
                <Tooltip {...CHART_TOOLTIP_STYLE} formatter={(value) => [formatKRW(Number(value)), "손익"]} />
                <Bar dataKey="daily_pnl_krw">
                  {daily.map((entry, index) => (
                    <Cell key={index} fill={entry.daily_pnl_krw >= 0 ? "#34d399" : "#f87171"} />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          ) : (
            <div className="empty-state">데이터 없음</div>
          )}
        </div>

        {/* Win/Loss Pie Chart */}
        <div className="card">
          <div className="card-title">승/패 비율</div>
          {winLossData.length > 0 && (stats?.wins ?? 0) + (stats?.losses ?? 0) > 0 ? (
            <ResponsiveContainer width="100%" height={220}>
              <PieChart>
                <Pie
                  data={winLossData}
                  cx="50%"
                  cy="50%"
                  innerRadius={50}
                  outerRadius={80}
                  dataKey="value"
                  label={({ name, value }) => `${name} ${value}`}
                >
                  {winLossData.map((entry, index) => (
                    <Cell key={index} fill={entry.color} />
                  ))}
                </Pie>
                <Tooltip {...CHART_TOOLTIP_STYLE} />
              </PieChart>
            </ResponsiveContainer>
          ) : (
            <div className="empty-state">데이터 없음</div>
          )}
        </div>
      </div>

      {/* Asset Balance Trend */}
      <div className="card" style={{ marginTop: 24 }}>
        <div className="card-title">자산 잔고 추이</div>
        {history.length > 0 ? (
          <ResponsiveContainer width="100%" height={250}>
            <AreaChart data={history}>
              <defs>
                <linearGradient id="balanceGradient" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor="#a78bfa" stopOpacity={0.3} />
                  <stop offset="100%" stopColor="#a78bfa" stopOpacity={0} />
                </linearGradient>
              </defs>
              <XAxis dataKey="date" tick={{ fill: "#8b8fa3", fontSize: 11 }} />
              <YAxis tick={{ fill: "#8b8fa3", fontSize: 11 }} tickFormatter={(v) => `${(v / 10000).toFixed(0)}만`} />
              <Tooltip {...CHART_TOOLTIP_STYLE} formatter={(value) => [formatKRW(Number(value)), "총 자산"]} />
              <Area type="monotone" dataKey="total_asset_value_krw" stroke="#a78bfa" fill="url(#balanceGradient)" />
            </AreaChart>
          </ResponsiveContainer>
        ) : (
          <div className="empty-state">데이터 없음</div>
        )}
      </div>
    </div>
  );
}
