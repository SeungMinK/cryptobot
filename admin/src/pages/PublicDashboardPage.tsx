import { useEffect, useState, useCallback } from "react";
import { Link } from "react-router-dom";
import {
  AreaChart, Area, XAxis, YAxis, Tooltip, ResponsiveContainer,
  PieChart, Pie, Cell,
} from "recharts";
import { useAuth } from "../context/AuthContext";
import { formatPercent, formatDateTime } from "../utils/format";
import { getMarketStateKR } from "../utils/indicatorDescriptions";

const API = import.meta.env.VITE_API_BASE_URL || "http://localhost:8000/api";
const TOOLTIP_STYLE = {
  contentStyle: { background: "#1e2130", border: "1px solid #2a2d3e", borderRadius: 8, color: "#e4e6f0" },
};

export default function PublicDashboardPage() {
  const { isAuthenticated } = useAuth();
  const [summary, setSummary] = useState<any>(null);
  const [trades, setTrades] = useState<any[]>([]);
  const [analysis, setAnalysis] = useState<any[]>([]);
  const [news, setNews] = useState<any[]>([]);
  const [fg, setFg] = useState<any>(null);
  const [portfolio, setPortfolio] = useState<any[]>([]);
  const [dailyReturns, setDailyReturns] = useState<any[]>([]);
  const [strategyStats, setStrategyStats] = useState<any[]>([]);
  const [monitoringCoins, setMonitoringCoins] = useState<any[]>([]);
  const [strategies, setStrategies] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);

  const fetchAll = useCallback(() => {
    const base = API.replace(/\/api$/, "");
    Promise.all([
      fetch(`${base}/api/public/summary`).then(r => r.json()).catch(() => null),
      fetch(`${base}/api/public/trades?limit=20`).then(r => r.json()).catch(() => []),
      fetch(`${base}/api/public/analysis?limit=3`).then(r => r.json()).catch(() => []),
      fetch(`${base}/api/public/news?limit=20`).then(r => r.json()).catch(() => ({ news: [], fear_greed: null })),
      fetch(`${base}/api/public/portfolio`).then(r => r.json()).catch(() => ({ positions: [] })),
      fetch(`${base}/api/public/daily-returns?days=14`).then(r => r.json()).catch(() => []),
      fetch(`${base}/api/public/strategy-stats`).then(r => r.json()).catch(() => []),
      fetch(`${base}/api/public/monitoring-coins`).then(r => r.json()).catch(() => []),
      fetch(`${base}/api/public/strategies`).then(r => r.json()).catch(() => []),
    ]).then(([s, t, a, n, p, dr, ss, mc, st]) => {
      setSummary(s); setTrades(t); setAnalysis(a);
      setNews(n?.news || []); setFg(n?.fear_greed || null);
      setPortfolio(p?.positions || []);
      setDailyReturns(dr); setStrategyStats(ss);
      setMonitoringCoins(mc); setStrategies(st);
      setLoading(false);
    }).catch(() => setLoading(false));
  }, []);

  useEffect(() => {
    fetchAll();
    const interval = setInterval(fetchAll, 60000);
    return () => clearInterval(interval);
  }, [fetchAll]);

  if (loading) return <div className="loading">로딩 중...</div>;

  const fgLabel = fg ? (fg.classification === "Extreme Fear" ? "극도 공포" : fg.classification === "Fear" ? "공포" : fg.classification === "Neutral" ? "중립" : fg.classification === "Greed" ? "탐욕" : "극도 탐욕") : "";
  const fgColor = fg && fg.value <= 25 ? "#f87171" : fg && fg.value >= 75 ? "#34d399" : "#fbbf24";

  // 누적 수익률 계산
  const cumData = dailyReturns.map((d: any, i: number) => ({
    ...d,
    cumulative: dailyReturns.slice(0, i + 1).reduce((s: number, x: any) => s + (x.daily_pnl_pct || 0), 0),
  }));

  return (
    <div>
      {/* 히어로 */}
      <div style={{
        background: "linear-gradient(135deg, #0d1a33 0%, #162040 50%, #1a1545 100%)",
        borderRadius: 16, padding: "32px 28px", marginBottom: 28,
        border: "1px solid rgba(45, 140, 240, 0.2)",
        boxShadow: "0 8px 32px rgba(45, 140, 240, 0.08)",
      }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start" }}>
          <div>
            <h1 style={{ margin: 0, fontSize: 26, fontWeight: 700 }}>CryptoBot</h1>
            <p style={{ margin: "6px 0 0", color: "var(--text-muted)", fontSize: 14 }}>
              AI 기반 코인 자동매매 — 실시간 성과 공개
            </p>
          </div>
          {!isAuthenticated && (
            <Link to="/login" style={{
              padding: "8px 16px", borderRadius: 8, fontSize: 12,
              background: "rgba(74, 158, 255, 0.15)", color: "#4a9eff",
              textDecoration: "none", border: "1px solid rgba(74, 158, 255, 0.3)",
            }}>관리자</Link>
          )}
        </div>

        {summary && (
          <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 16, marginTop: 24 }}>
            <div style={{ textAlign: "center" }}>
              <div style={{ fontSize: 11, color: "var(--text-muted)", marginBottom: 4 }}>전체 승률</div>
              <div style={{ fontSize: 28, fontWeight: 700 }} className={summary.win_rate >= 50 ? "positive" : "negative"}>
                {summary.win_rate.toFixed(1)}%
              </div>
              <div style={{ fontSize: 11, color: "var(--text-muted)" }}>오늘 {summary.today_win_rate.toFixed(0)}%</div>
            </div>
            <div style={{ textAlign: "center" }}>
              <div style={{ fontSize: 11, color: "var(--text-muted)", marginBottom: 4 }}>손익비</div>
              <div style={{ fontSize: 28, fontWeight: 700 }}>
                {summary.risk_reward_ratio ? `1:${summary.risk_reward_ratio}` : "-"}
              </div>
              <div style={{ fontSize: 11, color: "var(--text-muted)" }}>
                승 {formatPercent(summary.avg_win_pct || 0)} / 패 {formatPercent(summary.avg_loss_pct || 0)}
              </div>
            </div>
            <div style={{ textAlign: "center" }}>
              <div style={{ fontSize: 11, color: "var(--text-muted)", marginBottom: 4 }}>총 거래</div>
              <div style={{ fontSize: 28, fontWeight: 700 }}>{summary.total_trades}</div>
              <div style={{ fontSize: 11, color: "var(--text-muted)" }}>오늘 {summary.today_trades}건</div>
            </div>
            <div style={{ textAlign: "center" }}>
              <div style={{ fontSize: 11, color: "var(--text-muted)", marginBottom: 4 }}>공포/탐욕</div>
              <div style={{ fontSize: 28, fontWeight: 700, color: fgColor }}>{fg ? fg.value : "-"}</div>
              <div style={{ fontSize: 11, color: fgColor }}>{fgLabel}</div>
            </div>
          </div>
        )}
      </div>

      {/* 누적 수익률 차트 */}
      {cumData.length > 1 && (
        <div className="card" style={{ marginBottom: 24 }}>
          <div className="card-title">누적 수익률 추이</div>
          <ResponsiveContainer width="100%" height={200}>
            <AreaChart data={cumData}>
              <defs>
                <linearGradient id="pubCumGrad" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor="#4a9eff" stopOpacity={0.3} />
                  <stop offset="100%" stopColor="#4a9eff" stopOpacity={0} />
                </linearGradient>
              </defs>
              <XAxis dataKey="date" tick={{ fill: "#8b8fa3", fontSize: 10 }} tickFormatter={(v: string) => v.slice(5)} />
              <YAxis tick={{ fill: "#8b8fa3", fontSize: 11 }} tickFormatter={(v: number) => `${v.toFixed(1)}%`} />
              <Tooltip {...TOOLTIP_STYLE} formatter={(value) => [formatPercent(Number(value)), "누적 수익률"]} />
              <Area type="monotone" dataKey="cumulative" stroke="#4a9eff" fill="url(#pubCumGrad)" strokeWidth={2} />
            </AreaChart>
          </ResponsiveContainer>
        </div>
      )}

      {/* 일별 성과 테이블 */}
      {dailyReturns.length > 0 && (
        <div className="card" style={{ marginBottom: 24 }}>
          <div className="card-title">일별 성과</div>
          <div className="table-container">
            <table>
              <thead><tr><th>날짜</th><th>거래</th><th>승률</th><th>수익률</th></tr></thead>
              <tbody>
                {[...dailyReturns].reverse().map((d: any) => (
                  <tr key={d.date}>
                    <td>{d.date}</td>
                    <td>{d.total_trades || "-"}</td>
                    <td className={(d.win_rate || 0) >= 50 ? "positive" : d.win_rate ? "negative" : ""}>{d.win_rate != null ? `${d.win_rate.toFixed(0)}%` : "-"}</td>
                    <td className={d.daily_pnl_pct >= 0 ? "positive" : "negative"} style={{ fontWeight: 600 }}>{formatPercent(d.daily_pnl_pct)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      <div className="grid-2" style={{ marginBottom: 24 }}>
        {/* AI 분석 */}
        <div className="card">
          <div className="card-title">AI 시장 분석</div>
          {analysis.length > 0 ? (
            <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
              {analysis.map((a: any, i: number) => (
                <div key={i} style={{
                  padding: 12, borderRadius: 8,
                  background: i === 0 ? "rgba(74, 158, 255, 0.06)" : "transparent",
                  border: i === 0 ? "1px solid rgba(74, 158, 255, 0.12)" : "none",
                }}>
                  <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 6 }}>
                    <span className={`badge ${a.market_state === "bullish" ? "badge-green" : a.market_state === "bearish" ? "badge-red" : "badge-yellow"}`}>
                      {getMarketStateKR(a.market_state)}
                    </span>
                    <span style={{ fontSize: 10, color: "var(--text-muted)" }}>{formatDateTime(a.timestamp)}</span>
                  </div>
                  <div style={{ fontSize: 13, lineHeight: 1.7, color: i === 0 ? "var(--text-primary)" : "var(--text-muted)" }}>{a.summary}</div>
                </div>
              ))}
            </div>
          ) : <div className="empty-state">분석 데이터 없음</div>}
        </div>

        {/* 포트폴리오 파이차트 */}
        <div className="card">
          <div className="card-title">포트폴리오 비중</div>
          {portfolio.length > 0 ? (
            <div style={{ display: "flex", alignItems: "center", gap: 16 }}>
              <ResponsiveContainer width="55%" height={180}>
                <PieChart>
                  <Pie data={portfolio.map((p: any) => ({ name: p.coin?.replace("KRW-", ""), value: p.weight_pct }))}
                    cx="50%" cy="50%" innerRadius={45} outerRadius={75} dataKey="value"
                    label={({ name, value }: any) => `${name} ${value}%`} labelLine={false}
                    style={{ fontSize: 10 }}
                  >
                    {portfolio.map((_: any, i: number) => (
                      <Cell key={i} fill={["#4a9eff", "#6366f1", "#34d399", "#f59e0b", "#f87171", "#a78bfa", "#ec4899", "#06b6d4"][i % 8]} />
                    ))}
                  </Pie>
                </PieChart>
              </ResponsiveContainer>
              <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
                {portfolio.map((p: any, i: number) => (
                  <div key={p.coin} style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 12 }}>
                    <div style={{ width: 10, height: 10, borderRadius: 2, background: ["#4a9eff", "#6366f1", "#34d399", "#f59e0b", "#f87171", "#a78bfa", "#ec4899", "#06b6d4"][i % 8] }} />
                    <span style={{ fontWeight: 600 }}>{p.coin?.replace("KRW-", "")}</span>
                    <span style={{ color: "var(--text-muted)" }}>{p.weight_pct}%</span>
                  </div>
                ))}
              </div>
            </div>
          ) : <div className="empty-state">보유 포지션 없음</div>}
        </div>
      </div>

      <div className="grid-2" style={{ marginBottom: 24 }}>
        {/* 전략별 성과 */}
        {strategyStats.length > 0 && (
          <div className="card">
            <div className="card-title">전략별 성과</div>
            <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
              {strategyStats.map((s: any) => (
                <div key={s.strategy} style={{ display: "flex", justifyContent: "space-between", alignItems: "center", padding: "8px 0", borderBottom: "1px solid var(--border)" }}>
                  <div>
                    <div style={{ fontWeight: 600, fontSize: 13 }}>{s.strategy.replace(/_/g, " ")}</div>
                    <div style={{ fontSize: 11, color: "var(--text-muted)" }}>{s.trades}건 거래</div>
                  </div>
                  <div style={{ textAlign: "right" }}>
                    <div className={s.win_rate >= 50 ? "positive" : "negative"} style={{ fontWeight: 600 }}>{s.win_rate}%</div>
                    <div style={{ fontSize: 11 }} className={s.avg_pct >= 0 ? "positive" : "negative"}>{formatPercent(s.avg_pct)}</div>
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* 모니터링 코인 */}
        {monitoringCoins.length > 0 && (
          <div className="card">
            <div className="card-title">모니터링 중 ({monitoringCoins.length}개 코인)</div>
            <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
              {monitoringCoins.map((c: any) => (
                <div key={c.coin} style={{
                  padding: "6px 10px", borderRadius: 8, fontSize: 12,
                  background: "var(--bg-secondary)",
                  border: `1px solid ${c.market_state === "bullish" ? "rgba(34,197,94,0.3)" : c.market_state === "bearish" ? "rgba(248,113,113,0.3)" : "var(--border)"}`,
                }}>
                  <span style={{ fontWeight: 600 }}>{c.coin.replace("KRW-", "")}</span>
                  {c.rsi && <span style={{ marginLeft: 4, color: "var(--text-muted)", fontSize: 10 }}>RSI {c.rsi}</span>}
                </div>
              ))}
            </div>
          </div>
        )}
      </div>

      {/* 매매 전략 소개 */}
      {strategies.length > 0 && (
        <div className="card" style={{ marginBottom: 24 }}>
          <div className="card-title">매매 전략 ({strategies.length}개)</div>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(220px, 1fr))", gap: 12 }}>
            {strategies.map((s: any) => (
              <div key={s.name} style={{
                padding: 12, borderRadius: 8, background: "var(--bg-secondary)",
                border: s.is_active ? "1px solid rgba(74, 158, 255, 0.4)" : "1px solid var(--border)",
              }}>
                <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 4 }}>
                  <span style={{ fontWeight: 600, fontSize: 13 }}>{s.display_name}</span>
                  {s.is_active && <span className="badge badge-blue" style={{ fontSize: 9 }}>활성</span>}
                </div>
                <div style={{ fontSize: 11, color: "var(--text-muted)", lineHeight: 1.5 }}>{s.description}</div>
                <div style={{ display: "flex", gap: 4, marginTop: 6 }}>
                  <span className="badge badge-purple" style={{ fontSize: 9 }}>{s.category}</span>
                  <span className="badge badge-yellow" style={{ fontSize: 9 }}>{s.difficulty}</span>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* 최근 매매 */}
      <div className="card" style={{ marginBottom: 24 }}>
        <div className="card-title">최근 매매</div>
        {trades.length > 0 ? (
          <div className="table-container">
            <table>
              <thead><tr><th>시간</th><th>종목</th><th>방향</th><th>전략</th><th>수익률</th><th>보유</th></tr></thead>
              <tbody>
                {trades.map((t: any, i: number) => (
                  <tr key={i}>
                    <td style={{ fontSize: 11, color: "var(--text-muted)" }}>{formatDateTime(t.timestamp).replace(/\d{4}\. /, "")}</td>
                    <td style={{ fontWeight: 600 }}>{t.coin?.replace("KRW-", "")}</td>
                    <td><span className={`badge ${t.side === "buy" ? "badge-green" : "badge-red"}`} style={{ fontSize: 10 }}>{t.side === "buy" ? "매수" : "매도"}</span></td>
                    <td style={{ fontSize: 11, color: "var(--text-muted)" }}>{t.strategy?.replace(/_/g, " ")}</td>
                    <td className={t.profit_pct != null ? (t.profit_pct >= 0 ? "positive" : "negative") : ""} style={{ fontWeight: 600 }}>{t.profit_pct != null ? formatPercent(t.profit_pct) : "-"}</td>
                    <td style={{ fontSize: 11, color: "var(--text-muted)" }}>{t.hold_minutes != null ? `${t.hold_minutes}분` : "-"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : <div className="empty-state">매매 내역 없음</div>}
      </div>

      {/* 뉴스 */}
      {news.length > 0 && (
        <div className="card" style={{ marginBottom: 24 }}>
          <div className="card-title">최근 뉴스</div>
          <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
            {news.map((n: any, i: number) => (
              <div key={i} style={{ display: "flex", justifyContent: "space-between", padding: "8px 0", borderBottom: i < news.length - 1 ? "1px solid var(--border)" : "none" }}>
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{ display: "flex", gap: 6, marginBottom: 3 }}>
                    <span className={`badge ${n.sentiment_keyword === "positive" ? "badge-green" : n.sentiment_keyword === "negative" ? "badge-red" : "badge-yellow"}`} style={{ fontSize: 9 }}>
                      {n.sentiment_keyword === "positive" ? "긍정" : n.sentiment_keyword === "negative" ? "부정" : "중립"}
                    </span>
                    <span style={{ fontSize: 10, color: "var(--text-muted)" }}>{n.source}</span>
                  </div>
                  <a href={n.url} target="_blank" rel="noopener noreferrer" style={{ fontSize: 13, color: "var(--text-primary)", textDecoration: "none", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", display: "block" }}>{n.title}</a>
                </div>
                <span style={{ fontSize: 10, color: "var(--text-muted)", whiteSpace: "nowrap", marginLeft: 12 }}>{formatDateTime(n.published_at).replace(/\d{4}\. /, "")}</span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* 푸터 */}
      <div style={{ textAlign: "center", padding: "24px 0 8px", color: "var(--text-muted)", fontSize: 11 }}>
        Powered by Claude AI + {strategies.length} Trading Strategies — <a href="https://github.com/SeungMinK/cryptobot" target="_blank" rel="noopener noreferrer" style={{ color: "#4a9eff", textDecoration: "none" }}>GitHub</a>
      </div>
    </div>
  );
}
