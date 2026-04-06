import { useEffect, useState, useCallback } from "react";
import { Link } from "react-router-dom";
import { useAuth } from "../context/AuthContext";
import StatCard from "../components/StatCard";
import { formatPercent, formatDateTime } from "../utils/format";
import { getMarketStateKR } from "../utils/indicatorDescriptions";

interface PublicSummary {
  total_trades: number;
  win_rate: number;
  avg_profit_pct: number;
  today_trades: number;
  today_win_rate: number;
  today_avg_pct: number;
}

interface PublicTrade {
  coin: string;
  side: string;
  strategy: string;
  trigger_reason: string;
  profit_pct: number | null;
  timestamp: string;
  hold_minutes: number | null;
}

interface PublicAnalysis {
  market_state: string;
  aggression: number;
  summary: string;
  timestamp: string;
}

const API = import.meta.env.VITE_API_BASE_URL || "http://localhost:8000/api";

export default function PublicDashboardPage() {
  const { isAuthenticated } = useAuth();
  const [summary, setSummary] = useState<PublicSummary | null>(null);
  const [trades, setTrades] = useState<PublicTrade[]>([]);
  const [analysis, setAnalysis] = useState<PublicAnalysis[]>([]);
  const [news, setNews] = useState<any[]>([]);
  const [fg, setFg] = useState<any>(null);
  const [portfolio, setPortfolio] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);

  const fetchAll = useCallback(() => {
    const base = API.replace(/\/api$/, "");
    Promise.all([
      fetch(`${base}/api/public/summary`).then(r => r.json()).catch(() => null),
      fetch(`${base}/api/public/trades?limit=10`).then(r => r.json()).catch(() => []),
      fetch(`${base}/api/public/analysis?limit=3`).then(r => r.json()).catch(() => []),
      fetch(`${base}/api/public/news?limit=6`).then(r => r.json()).catch(() => ({ news: [], fear_greed: null })),
      fetch(`${base}/api/public/portfolio`).then(r => r.json()).catch(() => ({ positions: [] })),
    ]).then(([s, t, a, n, p]) => {
      setSummary(s);
      setTrades(t);
      setAnalysis(a);
      setNews(n?.news || []);
      setFg(n?.fear_greed || null);
      setPortfolio(p?.positions || []);
      setLoading(false);
    }).catch(() => setLoading(false));
  }, []);

  useEffect(() => {
    fetchAll();
    const interval = setInterval(fetchAll, 60000);
    return () => clearInterval(interval);
  }, [fetchAll]);

  if (loading) return <div className="loading">로딩 중...</div>;

  return (
    <div>
      <div className="page-header" style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <div>
          <h1>CryptoBot Dashboard</h1>
          <p>AI 기반 코인 자동매매 실시간 현황</p>
        </div>
        {!isAuthenticated && (
          <Link to="/login" className="btn btn-primary btn-sm">관리자 로그인</Link>
        )}
      </div>

      {/* KPI */}
      {summary && (
        <div className="kpi-grid">
          <StatCard label="총 거래" value={`${summary.total_trades}건`} sub={`오늘 ${summary.today_trades}건`} />
          <StatCard
            label="전체 승률"
            value={`${summary.win_rate}%`}
            valueClass={summary.win_rate >= 50 ? "positive" : "negative"}
            sub={`오늘 ${summary.today_win_rate}%`}
          />
          <StatCard
            label="평균 수익률"
            value={formatPercent(summary.avg_profit_pct)}
            valueClass={summary.avg_profit_pct >= 0 ? "positive" : "negative"}
            sub={`오늘 ${formatPercent(summary.today_avg_pct)}`}
          />
          <StatCard
            label="공포/탐욕"
            value={fg ? `${fg.value}` : "-"}
            sub={fg ? (fg.classification === "Extreme Fear" ? "극도 공포" : fg.classification === "Fear" ? "공포" : fg.classification === "Neutral" ? "중립" : fg.classification === "Greed" ? "탐욕" : "극도 탐욕") : ""}
            valueClass={fg && fg.value <= 25 ? "negative" : fg && fg.value >= 75 ? "positive" : ""}
          />
        </div>
      )}

      <div className="grid-2">
        {/* AI 분석 */}
        <div className="card">
          <div className="card-title">AI 시장 분석</div>
          {analysis.length > 0 ? (
            <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
              {analysis.map((a, i) => (
                <div key={i} style={{ padding: "10px 0", borderBottom: i < analysis.length - 1 ? "1px solid var(--border)" : "none" }}>
                  <div style={{ display: "flex", gap: 6, marginBottom: 4 }}>
                    <span className={`badge ${a.market_state === "bullish" ? "badge-green" : a.market_state === "bearish" ? "badge-red" : "badge-yellow"}`}>
                      {getMarketStateKR(a.market_state)}
                    </span>
                    <span style={{ fontSize: 10, color: "var(--text-muted)" }}>{formatDateTime(a.timestamp)}</span>
                  </div>
                  <div style={{ fontSize: 13, lineHeight: 1.6 }}>{a.summary}</div>
                </div>
              ))}
            </div>
          ) : (
            <div className="empty-state">분석 데이터 없음</div>
          )}
        </div>

        {/* 보유 포트폴리오 */}
        <div className="card">
          <div className="card-title">포트폴리오 비중</div>
          {portfolio.length > 0 ? (
            <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
              {portfolio.map((p: any) => (
                <div key={p.coin} style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                  <span style={{ fontWeight: 600 }}>{p.coin?.replace("KRW-", "")}</span>
                  <div style={{ display: "flex", alignItems: "center", gap: 8, flex: 1, marginLeft: 16 }}>
                    <div style={{ flex: 1, background: "var(--bg-secondary)", borderRadius: 4, height: 20 }}>
                      <div style={{ width: `${p.weight_pct}%`, background: "#4a9eff", borderRadius: 4, height: "100%", minWidth: 2 }} />
                    </div>
                    <span style={{ fontSize: 13, fontWeight: 600, minWidth: 45, textAlign: "right" }}>{p.weight_pct}%</span>
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <div className="empty-state">보유 포지션 없음</div>
          )}
        </div>
      </div>

      {/* 최근 매매 */}
      <div className="card" style={{ marginTop: 24 }}>
        <div className="card-title">최근 매매</div>
        {trades.length > 0 ? (
          <div className="table-container">
            <table>
              <thead>
                <tr>
                  <th>시간</th>
                  <th>종목</th>
                  <th>방향</th>
                  <th>전략</th>
                  <th>수익률</th>
                  <th>사유</th>
                </tr>
              </thead>
              <tbody>
                {trades.map((t, i) => (
                  <tr key={i}>
                    <td style={{ fontSize: 11 }}>{formatDateTime(t.timestamp).replace(/\d{4}\. /, "")}</td>
                    <td style={{ fontWeight: 600 }}>{t.coin?.replace("KRW-", "")}</td>
                    <td>
                      <span className={`badge ${t.side === "buy" ? "badge-green" : "badge-red"}`} style={{ fontSize: 10 }}>
                        {t.side === "buy" ? "매수" : "매도"}
                      </span>
                    </td>
                    <td style={{ fontSize: 11 }}>{t.strategy}</td>
                    <td className={t.profit_pct != null ? (t.profit_pct >= 0 ? "positive" : "negative") : ""} style={{ fontWeight: 600 }}>
                      {t.profit_pct != null ? formatPercent(t.profit_pct) : "-"}
                    </td>
                    <td style={{ fontSize: 10, color: "var(--text-muted)", maxWidth: 150, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                      {t.trigger_reason || "-"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <div className="empty-state">매매 내역 없음</div>
        )}
      </div>

      {/* 뉴스 */}
      {news.length > 0 && (
        <div className="card" style={{ marginTop: 24 }}>
          <div className="card-title">최근 뉴스</div>
          <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
            {news.map((n: any, i: number) => (
              <div key={i} style={{ display: "flex", justifyContent: "space-between", padding: "6px 0", borderBottom: i < news.length - 1 ? "1px solid var(--border)" : "none" }}>
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{ display: "flex", gap: 6, marginBottom: 2 }}>
                    <span className={`badge ${n.sentiment_keyword === "positive" ? "badge-green" : n.sentiment_keyword === "negative" ? "badge-red" : "badge-yellow"}`} style={{ fontSize: 9 }}>
                      {n.sentiment_keyword === "positive" ? "긍정" : n.sentiment_keyword === "negative" ? "부정" : "중립"}
                    </span>
                    <span style={{ fontSize: 10, color: "var(--text-muted)" }}>{n.source}</span>
                  </div>
                  <a href={n.url} target="_blank" rel="noopener noreferrer" style={{ fontSize: 12, color: "var(--text-primary)", textDecoration: "none", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", display: "block" }}>
                    {n.title}
                  </a>
                </div>
                <span style={{ fontSize: 10, color: "var(--text-muted)", whiteSpace: "nowrap", marginLeft: 8 }}>
                  {formatDateTime(n.published_at).replace(/\d{4}\. /, "")}
                </span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
