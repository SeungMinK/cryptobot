import { useEffect, useState, useCallback } from "react";
import { getSignals, getSignalStats } from "../api/signals";
import type { SignalItem, SignalStats } from "../api/signals";
import StatCard from "../components/StatCard";
import Pagination from "../components/Pagination";
import { formatKRW, formatDateTime, formatNumber } from "../utils/format";

const SIGNAL_FILTERS = [
  { label: "전체", value: "" },
  { label: "매수", value: "buy" },
  { label: "매도", value: "sell" },
  { label: "HOLD", value: "hold" },
] as const;

const STAT_PERIODS = [
  { label: "1시간", hours: 1 },
  { label: "6시간", hours: 6 },
  { label: "24시간", hours: 24 },
  { label: "7일", hours: 168 },
] as const;

export default function SignalsPage() {
  const [signals, setSignals] = useState<SignalItem[]>([]);
  const [stats, setStats] = useState<SignalStats | null>(null);
  const [loading, setLoading] = useState(true);
  const [page, setPage] = useState(1);
  const [totalPages, setTotalPages] = useState(1);
  const [total, setTotal] = useState(0);
  const [filter, setFilter] = useState("");
  const [statPeriod, setStatPeriod] = useState(1);
  const [selected, setSelected] = useState<SignalItem | null>(null);

  const fetchData = useCallback(async () => {
    try {
      const [signalRes, statsRes] = await Promise.all([
        getSignals({ page, limit: 30, signal_type: filter || undefined }),
        getSignalStats(statPeriod),
      ]);
      setSignals(signalRes.items);
      setTotalPages(signalRes.pages);
      setTotal(signalRes.total);
      setStats(statsRes);
    } catch {
      // ignore
    } finally {
      setLoading(false);
    }
  }, [page, filter, statPeriod]);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  // 자동 새로고침 (30초)
  useEffect(() => {
    const interval = setInterval(fetchData, 30000);
    return () => clearInterval(interval);
  }, [fetchData]);

  if (loading) return <div className="loading">로딩 중...</div>;

  return (
    <div>
      <div className="page-header">
        <h1>Signals</h1>
        <p>매매 판단 이력 — 실시간 자동 갱신 (30초)</p>
      </div>

      {/* Stats */}
      <div style={{ display: "flex", gap: 4, marginBottom: 12 }}>
        {STAT_PERIODS.map((p) => (
          <button
            key={p.hours}
            onClick={() => setStatPeriod(p.hours)}
            style={{
              padding: "4px 10px",
              fontSize: 12,
              borderRadius: 6,
              border: "none",
              cursor: "pointer",
              background: statPeriod === p.hours ? "#4a9eff" : "#2a2d3e",
              color: statPeriod === p.hours ? "#fff" : "#8b8fa3",
            }}
          >
            {p.label}
          </button>
        ))}
      </div>

      {stats && (
        <div className="kpi-grid">
          <StatCard label="전체 신호" value={formatNumber(stats.total)} />
          <StatCard
            label="매수 신호"
            value={formatNumber(stats.buy_signals)}
            valueClass="positive"
          />
          <StatCard
            label="매도 신호"
            value={formatNumber(stats.sell_signals)}
            valueClass="negative"
          />
          <StatCard
            label="실행됨"
            value={formatNumber(stats.executed)}
            valueClass={stats.executed > 0 ? "positive" : undefined}
          />
        </div>
      )}

      {/* Filter */}
      <div className="card" style={{ marginBottom: 16 }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
          <div style={{ display: "flex", gap: 6 }}>
            {SIGNAL_FILTERS.map((f) => (
              <button
                key={f.value}
                onClick={() => { setFilter(f.value); setPage(1); }}
                style={{
                  padding: "6px 14px",
                  borderRadius: 6,
                  border: "none",
                  cursor: "pointer",
                  fontSize: 13,
                  background: filter === f.value ? "#4a9eff" : "#2a2d3e",
                  color: filter === f.value ? "#fff" : "#8b8fa3",
                }}
              >
                {f.label}
              </button>
            ))}
          </div>
          <div style={{ fontSize: 12, color: "var(--text-muted)" }}>
            총 {formatNumber(total)}건
          </div>
        </div>
      </div>

      {/* Signal List */}
      <div className="card">
        {signals.length > 0 ? (
          <div className="table-container">
            <table>
              <thead>
                <tr>
                  <th>시간</th>
                  <th>신호</th>
                  <th>전략</th>
                  <th>판단 근거</th>
                  <th>신뢰도</th>
                  <th>BTC 가격</th>
                  <th>시장</th>
                  <th>실행</th>
                </tr>
              </thead>
              <tbody>
                {signals.map((s) => (
                  <tr
                    key={s.id}
                    onClick={() => setSelected(s)}
                    style={{ cursor: "pointer" }}
                  >
                    <td style={{ fontSize: 11, whiteSpace: "nowrap" }}>{formatDateTime(s.timestamp)}</td>
                    <td>
                      <span className={`badge ${s.signal_type === "buy" ? "badge-green" : s.signal_type === "sell" ? "badge-red" : "badge-yellow"}`}>
                        {s.signal_type === "buy" ? "매수" : s.signal_type === "sell" ? "매도" : "HOLD"}
                      </span>
                    </td>
                    <td style={{ fontSize: 12 }}>{s.strategy}</td>
                    <td style={{ fontSize: 12, maxWidth: 200, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                      {s.trigger_reason}
                    </td>
                    <td>
                      <ConfidenceBar value={s.confidence} />
                    </td>
                    <td style={{ fontSize: 12, whiteSpace: "nowrap" }}>{formatKRW(s.current_price)}</td>
                    <td>
                      {s.market_state && (
                        <span className={`badge ${s.market_state === "bullish" ? "badge-green" : s.market_state === "bearish" ? "badge-red" : "badge-yellow"}`}>
                          {s.market_state}
                        </span>
                      )}
                    </td>
                    <td>
                      {s.executed ? (
                        <span className="badge badge-green">O</span>
                      ) : s.skip_reason ? (
                        <span style={{ fontSize: 11, color: "var(--text-muted)" }} title={s.skip_reason}>-</span>
                      ) : null}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <div className="empty-state">신호 데이터 없음</div>
        )}

        {totalPages > 1 && (
          <Pagination page={page} totalPages={totalPages} onPageChange={setPage} />
        )}
      </div>

      {/* Detail Modal */}
      {selected && (
        <div
          className="modal-overlay"
          onClick={() => setSelected(null)}
        >
          <div className="modal-content" onClick={(e) => e.stopPropagation()}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 16 }}>
              <h3 style={{ margin: 0 }}>신호 상세 #{selected.id}</h3>
              <button onClick={() => setSelected(null)} style={{ background: "none", border: "none", color: "var(--text-secondary)", fontSize: 18, cursor: "pointer" }}>x</button>
            </div>

            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16 }}>
              <DetailItem label="시간" value={formatDateTime(selected.timestamp)} />
              <DetailItem label="신호" value={selected.signal_type === "buy" ? "매수" : selected.signal_type === "sell" ? "매도" : "HOLD"} />
              <DetailItem label="전략" value={selected.strategy} />
              <DetailItem label="신뢰도" value={`${(selected.confidence * 100).toFixed(1)}%`} />
              <DetailItem label="BTC 가격" value={formatKRW(selected.current_price)} />
              <DetailItem label="시장 상태" value={selected.market_state || "-"} />
              <DetailItem label="판단 근거" value={selected.trigger_reason || "-"} full />
              {selected.skip_reason && (
                <DetailItem label="스킵 사유" value={selected.skip_reason} full />
              )}
            </div>

            {(selected.btc_rsi_14 != null || selected.btc_ma_5 != null) && (
              <>
                <div style={{ borderTop: "1px solid var(--border)", margin: "16px 0", paddingTop: 16 }}>
                  <div style={{ fontSize: 13, fontWeight: 600, marginBottom: 12 }}>지표 데이터</div>
                  <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
                    {selected.btc_rsi_14 != null && <DetailItem label="RSI (14)" value={selected.btc_rsi_14.toFixed(1)} />}
                    {selected.btc_ma_5 != null && <DetailItem label="MA (5)" value={formatKRW(selected.btc_ma_5)} />}
                    {selected.btc_ma_20 != null && <DetailItem label="MA (20)" value={formatKRW(selected.btc_ma_20)} />}
                    {selected.btc_bb_upper != null && <DetailItem label="볼린저 상단" value={formatKRW(selected.btc_bb_upper)} />}
                    {selected.btc_bb_lower != null && <DetailItem label="볼린저 하단" value={formatKRW(selected.btc_bb_lower)} />}
                    {selected.btc_atr_14 != null && <DetailItem label="ATR (14)" value={formatKRW(selected.btc_atr_14)} />}
                  </div>
                </div>
              </>
            )}

            {selected.trigger_value != null && (
              <DetailItem label="트리거 값" value={formatKRW(selected.trigger_value)} />
            )}
          </div>
        </div>
      )}
    </div>
  );
}

function ConfidenceBar({ value }: { value: number }) {
  const pct = Math.round(value * 100);
  const filled = Math.round(value * 10);
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
      <div style={{ display: "flex", gap: 1 }}>
        {Array.from({ length: 10 }).map((_, i) => (
          <div
            key={i}
            style={{
              width: 4,
              height: 14,
              borderRadius: 1,
              background: i < filled
                ? pct >= 70 ? "#22c55e" : pct >= 40 ? "#eab308" : "#4a9eff"
                : "#2a2d3e",
            }}
          />
        ))}
      </div>
      <span style={{ fontSize: 11, color: "var(--text-muted)", minWidth: 32 }}>{pct}%</span>
    </div>
  );
}

function DetailItem({ label, value, full }: { label: string; value: string; full?: boolean }) {
  return (
    <div style={full ? { gridColumn: "1 / -1" } : undefined}>
      <div style={{ fontSize: 11, color: "var(--text-muted)", marginBottom: 2 }}>{label}</div>
      <div style={{ fontSize: 13 }}>{value}</div>
    </div>
  );
}
