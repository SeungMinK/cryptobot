import { useEffect, useState, useCallback } from "react";
import client from "../api/client";
import StatCard from "../components/StatCard";
import Pagination from "../components/Pagination";
import { formatDateTime, formatNumber } from "../utils/format";

interface NewsItem {
  id: number;
  source: string;
  title: string;
  summary: string;
  url: string;
  published_at: string;
  collected_at: string;
  category: string;
  coins_mentioned: string;
  sentiment_keyword: string;
}

interface NewsStats {
  total: number;
  positive: number;
  negative: number;
  neutral: number;
  coin_tagged: number;
  fear_greed: { value: number; classification: string; timestamp: string } | null;
}

const SENTIMENT_COLORS: Record<string, string> = {
  positive: "badge-green",
  negative: "badge-red",
  neutral: "badge-yellow",
};

const SENTIMENT_KR: Record<string, string> = {
  positive: "긍정",
  negative: "부정",
  neutral: "중립",
};

const CATEGORY_KR: Record<string, string> = {
  market: "시장",
  regulation: "규제",
  security: "보안",
  technology: "기술",
  listing: "상장",
  maintenance: "점검",
  delisting: "폐지",
};

const SOURCE_LABELS: Record<string, string> = {
  coindesk: "CoinDesk",
  cointelegraph: "CoinTelegraph",
  upbit: "업비트",
};

const FILTERS = [
  { label: "전체", value: "" },
  { label: "긍정", value: "positive" },
  { label: "부정", value: "negative" },
  { label: "중립", value: "neutral" },
] as const;

export default function NewsPage() {
  const [news, setNews] = useState<NewsItem[]>([]);
  const [stats, setStats] = useState<NewsStats | null>(null);
  const [loading, setLoading] = useState(true);
  const [page, setPage] = useState(1);
  const [totalPages, setTotalPages] = useState(1);
  const [total, setTotal] = useState(0);
  const [filter, setFilter] = useState("");
  const [coinFilter, setCoinFilter] = useState("");

  const fetchData = useCallback(async () => {
    try {
      const params: Record<string, string | number> = { page, limit: 15 };
      if (filter) params.sentiment = filter;
      if (coinFilter) params.coin = coinFilter;

      const [newsRes, statsRes] = await Promise.all([
        client.get("/news", { params }).then((r) => r.data),
        client.get("/news/stats", { params: { hours: 24 } }).then((r) => r.data),
      ]);
      setNews(newsRes.items);
      setTotalPages(newsRes.pages);
      setTotal(newsRes.total);
      setStats(statsRes);
    } catch {
      // ignore
    } finally {
      setLoading(false);
    }
  }, [page, filter, coinFilter]);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  // 5분 자동 갱신
  useEffect(() => {
    const interval = setInterval(fetchData, 300000);
    return () => clearInterval(interval);
  }, [fetchData]);

  if (loading) return <div className="loading">로딩 중...</div>;

  const fg = stats?.fear_greed;
  const fgColor = fg ? (fg.value <= 25 ? "negative" : fg.value >= 75 ? "positive" : "") : "";
  const fgLabel = fg ? `${fg.value} — ${fg.classification === "Extreme Fear" ? "극도 공포" : fg.classification === "Fear" ? "공포" : fg.classification === "Neutral" ? "중립" : fg.classification === "Greed" ? "탐욕" : "극도 탐욕"}` : "-";

  return (
    <div>
      <div className="page-header">
        <h1>뉴스</h1>
        <p>코인 시장 뉴스 + 공포/탐욕 지수 (30분 자동 수집)</p>
      </div>

      {/* Stats */}
      {stats && (
        <div className="kpi-grid">
          <StatCard label="공포/탐욕 지수" value={fgLabel} valueClass={fgColor} sub={fg ? formatDateTime(fg.timestamp) : ""} />
          <StatCard label="뉴스 (24h)" value={formatNumber(stats.total)} sub={`긍정 ${stats.positive} / 부정 ${stats.negative} / 중립 ${stats.neutral}`} />
          <StatCard
            label="시장 심리"
            value={stats.negative > stats.positive ? "부정적" : stats.positive > stats.negative ? "긍정적" : "중립"}
            valueClass={stats.negative > stats.positive ? "negative" : stats.positive > stats.negative ? "positive" : ""}
            sub={`긍정 ${((stats.positive / (stats.total || 1)) * 100).toFixed(0)}% / 부정 ${((stats.negative / (stats.total || 1)) * 100).toFixed(0)}%`}
          />
          <StatCard label="코인 언급" value={`${stats.coin_tagged}건`} sub={`전체 ${stats.total}건 중`} />
        </div>
      )}

      {/* Filters */}
      <div className="card" style={{ marginBottom: 16 }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: 8 }}>
          <div style={{ display: "flex", gap: 6 }}>
            {FILTERS.map((f) => (
              <button
                key={f.value}
                onClick={() => { setFilter(f.value); setPage(1); }}
                style={{
                  padding: "6px 14px", borderRadius: 6, border: "none", cursor: "pointer", fontSize: 13,
                  background: filter === f.value ? "#4a9eff" : "#2a2d3e",
                  color: filter === f.value ? "#fff" : "#8b8fa3",
                }}
              >
                {f.label}
              </button>
            ))}
          </div>
          <div style={{ display: "flex", gap: 6, alignItems: "center" }}>
            <input
              placeholder="코인 검색 (BTC, ETH...)"
              value={coinFilter}
              onChange={(e) => { setCoinFilter(e.target.value.toUpperCase()); setPage(1); }}
              style={{
                padding: "6px 12px", borderRadius: 6, border: "1px solid var(--border)",
                background: "var(--bg-secondary)", color: "var(--text-primary)", fontSize: 13, width: 160,
              }}
            />
            <span style={{ fontSize: 12, color: "var(--text-muted)" }}>{formatNumber(total)}건</span>
          </div>
        </div>
      </div>

      {/* News List */}
      <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
        {news.map((n) => (
          <div key={n.id} className="card" style={{ padding: 16 }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: 8 }}>
              <div style={{ flex: 1 }}>
                <a
                  href={n.url}
                  target="_blank"
                  rel="noopener noreferrer"
                  style={{ fontSize: 15, fontWeight: 600, color: "var(--text-primary)", textDecoration: "none" }}
                >
                  {n.title}
                </a>
              </div>
              <div style={{ display: "flex", gap: 4, marginLeft: 12, flexShrink: 0 }}>
                <span className={`badge ${SENTIMENT_COLORS[n.sentiment_keyword] || "badge-yellow"}`}>
                  {SENTIMENT_KR[n.sentiment_keyword] || n.sentiment_keyword}
                </span>
                <span className="badge badge-blue">{CATEGORY_KR[n.category] || n.category}</span>
              </div>
            </div>

            {n.summary && (
              <p style={{ fontSize: 13, color: "var(--text-secondary)", margin: "0 0 8px", lineHeight: 1.5 }}>
                {n.summary.length > 200 ? n.summary.slice(0, 200) + "..." : n.summary}
              </p>
            )}

            <div style={{ display: "flex", gap: 12, alignItems: "center", fontSize: 11, color: "var(--text-muted)" }}>
              <span>{SOURCE_LABELS[n.source] || n.source}</span>
              <span>{n.published_at ? formatDateTime(n.published_at) : "-"}</span>
              {n.coins_mentioned && (
                <div style={{ display: "flex", gap: 3 }}>
                  {n.coins_mentioned.split(",").map((c) => (
                    <span
                      key={c}
                      className="badge badge-purple"
                      style={{ fontSize: 10, cursor: "pointer" }}
                      onClick={() => { setCoinFilter(c); setPage(1); }}
                    >
                      {c}
                    </span>
                  ))}
                </div>
              )}
            </div>
          </div>
        ))}

        {news.length === 0 && <div className="empty-state">뉴스 없음</div>}
      </div>

      {totalPages > 1 && (
        <div style={{ marginTop: 16 }}>
          <Pagination page={page} totalPages={totalPages} onPageChange={setPage} />
        </div>
      )}
    </div>
  );
}
