import { useEffect, useState, useCallback } from "react";
import { Link } from "react-router-dom";
import { getBalance, getPositions, getBalanceHistory } from "../api/balance";
import client from "../api/client";
import { getCurrentMarket } from "../api/market";
import { getTrades } from "../api/trades";
import { getActiveStrategies } from "../api/strategies";
import type { BalanceResponse, PositionsResponse, BalanceHistory } from "../types/balance";
import type { MarketSnapshot } from "../types/market";
import type { Trade } from "../types/trades";
import type { Strategy } from "../types/strategies";
import StatCard from "../components/StatCard";
import { formatKRW, formatPercent, formatNumber, formatDateTime } from "../utils/format";
import { getMarketStateKR } from "../utils/indicatorDescriptions";

export default function DashboardPage() {
  const [balance, setBalance] = useState<BalanceResponse | null>(null);
  const [positions, setPositions] = useState<PositionsResponse | null>(null);
  const [history, setHistory] = useState<BalanceHistory[]>([]);
  const [market, setMarket] = useState<MarketSnapshot | null>(null);
  const [recentTrades, setRecentTrades] = useState<Trade[]>([]);
  const [activeStrategies, setActiveStrategies] = useState<Strategy[]>([]);
  const [monitoredCoins, setMonitoredCoins] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);

  const fetchAll = useCallback(() => {
    Promise.all([
      getBalance().catch(() => null),
      getPositions().catch(() => null),
      getBalanceHistory(30).catch(() => []),
      getCurrentMarket().catch(() => null),
      getTrades({ limit: 5 }).catch(() => ({ items: [] })),
      getActiveStrategies().catch(() => []),
      client.get("/market/coins").then((r) => r.data).catch(() => []),
    ]).then(([bal, pos, hist, mkt, trades, strats, coins]) => {
      setBalance(bal);
      setPositions(pos as PositionsResponse | null);
      setHistory(hist as BalanceHistory[]);
      setMarket(mkt as MarketSnapshot | null);
      setRecentTrades((trades as { items: Trade[] }).items);
      setActiveStrategies(strats as Strategy[]);
      setMonitoredCoins(coins as any[]);
      setLoading(false);
    });
  }, []);

  useEffect(() => {
    fetchAll();
    const interval = setInterval(fetchAll, 60000); // 60초 자동 갱신
    return () => clearInterval(interval);
  }, [fetchAll]);


  if (loading) return <div className="loading">로딩 중...</div>;

  const marketState = market && "market_state" in market ? market.market_state : null;

  return (
    <div>
      <div className="page-header" style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <div>
          <h1>대시보드</h1>
          <p>전체 현황 요약 (60초 자동 갱신)</p>
        </div>
        <button
          onClick={fetchAll}
          style={{
            padding: "8px 16px", borderRadius: 8, border: "none",
            background: "#4a9eff", color: "#fff", cursor: "pointer", fontSize: 13,
          }}
        >
          새로고침
        </button>
      </div>

      {/* KPI Cards */}
      {(() => {
        const pos = ((positions as any)?.positions || []) as any[];
        const totalCost = pos.reduce((s: number, p: any) => s + (p.total_krw || 0), 0);
        const totalValue = pos.reduce((s: number, p: any) => s + (p.amount || 0) * (p.current_price || 0), 0);
        const totalAsset = (balance?.krw_balance || 0) + totalValue;
        const totalPnl = totalAsset - 100000;
        return (
          <div className="kpi-grid">
            <StatCard
              label="총 보유 자산"
              value={balance ? formatKRW(totalAsset) : "-"}
              sub={`KRW ${formatKRW(balance?.krw_balance || 0)} + 코인 ${formatKRW(totalValue)}`}
            />
            <StatCard
              label="총 손익"
              value={formatKRW(totalPnl)}
              valueClass={totalPnl >= 0 ? "positive" : "negative"}
              sub="시작 ₩100,000 기준"
            />
            <StatCard
              label="매수 금액"
              value={formatKRW(totalCost)}
              sub={`${pos.length}종목 보유`}
            />
            <StatCard
              label="평가 금액"
              value={formatKRW(totalValue)}
              valueClass={totalValue >= totalCost ? "positive" : "negative"}
              sub={totalCost > 0 ? `${formatPercent((totalValue - totalCost) / totalCost * 100)} 수익률` : ""}
            />
          </div>
        );
      })()}

      <div className="grid-2">
        {/* Position Card */}
        <div className="card">
          <div className="card-title">현재 포지션</div>
          {positions?.has_position && (positions as any).positions?.length > 0 ? (
            <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
              {((positions as any).positions || []).map((p: any) => (
                <div key={p.id} style={{ padding: "8px 0", borderBottom: "1px solid var(--border)" }}>
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 6 }}>
                    <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
                      <span style={{ fontWeight: 600 }}>{p.coin?.replace("KRW-", "")}</span>
                      {p.strategy && <span className="badge badge-purple" style={{ fontSize: 10 }}>{p.strategy}</span>}
                    </div>
                    <span className={p.unrealized_pnl_pct >= 0 ? "positive" : "negative"} style={{ fontWeight: 600 }}>
                      {formatPercent(p.unrealized_pnl_pct)} ({formatKRW(p.unrealized_pnl_krw)})
                    </span>
                  </div>
                  <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 4, fontSize: 12 }}>
                    <div><span style={{ color: "var(--text-muted)" }}>투자 </span>{formatKRW(p.total_krw)}</div>
                    <div><span style={{ color: "var(--text-muted)" }}>현재 </span>{formatKRW(p.amount * p.current_price)}</div>
                  </div>
                </div>
              ))}
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
                    {getMarketStateKR(marketState)}
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

      {/* 모니터링 코인 종합 현황 */}
      <div className="card" style={{ marginBottom: 24 }}>
        <div className="card-title">모니터링 코인 현황</div>
        {monitoredCoins.length > 0 ? (
          <div className="table-container">
            <table>
              <thead>
                <tr>
                  <th>코인</th>
                  <th>현재가</th>
                  <th>전략</th>
                  <th>최근 신호</th>
                  <th>시장</th>
                  <th>보유</th>
                  <th>미실현 손익</th>
                </tr>
              </thead>
              <tbody>
                {monitoredCoins.map((c: any) => (
                  <tr key={c.coin}>
                    <td style={{ fontWeight: 600 }}>{c.coin?.replace("KRW-", "")}</td>
                    <td>{formatKRW(c.current_price || 0)}</td>
                    <td><span className="badge badge-purple">{c.strategy}</span></td>
                    <td>
                      <span className={`badge ${c.signal_type === "buy" ? "badge-green" : c.signal_type === "sell" ? "badge-red" : "badge-yellow"}`}>
                        {c.signal_type === "buy" ? "매수" : c.signal_type === "sell" ? "매도" : "HOLD"}
                      </span>
                    </td>
                    <td>
                      <span className={`badge ${c.market_state === "bullish" ? "badge-green" : c.market_state === "bearish" ? "badge-red" : "badge-yellow"}`}>
                        {getMarketStateKR(c.market_state || "")}
                      </span>
                    </td>
                    <td>
                      {c.holding ? (
                        <span className="badge badge-green">보유중</span>
                      ) : "-"}
                    </td>
                    <td className={c.unrealized_pnl_pct > 0 ? "positive" : c.unrealized_pnl_pct < 0 ? "negative" : ""}>
                      {c.holding ? formatPercent(c.unrealized_pnl_pct || 0) : "-"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <div className="empty-state">모니터링 중인 코인 없음 (봇 실행 후 표시)</div>
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

        </div>
      </div>
    </div>
  );
}
