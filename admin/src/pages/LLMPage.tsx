import { useEffect, useState, useCallback } from "react";
import client from "../api/client";
import StatCard from "../components/StatCard";
import { formatDateTime, formatKRW } from "../utils/format";
import { getMarketStateKR } from "../utils/indicatorDescriptions";

interface LLMDecision {
  id: number;
  timestamp: string;
  model: string;
  output_market_state: string;
  output_aggression: number;
  output_allow_trading: boolean;
  output_k_value: number;
  output_stop_loss: number;
  output_trailing_stop: number;
  output_reasoning: string;
  input_tokens: number;
  output_tokens: number;
  cost_usd: number;
  input_market_snapshot_id: number; // prompt_version_id
  input_news_summary: string; // before/after JSON
  evaluation_period_pnl_pct: number | null;
  evaluation_was_good: boolean | null;
}

interface PromptVersion {
  id: number;
  version: string;
  description: string;
  is_active: boolean;
  created_at: string;
  activated_at: string;
}

export default function LLMPage() {
  const [decisions, setDecisions] = useState<LLMDecision[]>([]);
  const [prompts, setPrompts] = useState<PromptVersion[]>([]);
  const [selectedPrompt, setSelectedPrompt] = useState<PromptVersion | null>(null);
  const [promptText, setPromptText] = useState("");
  const [loading, setLoading] = useState(true);

  const fetchData = useCallback(async () => {
    try {
      const [dec, prm] = await Promise.all([
        client.get("/llm/decisions?limit=20").then((r) => r.data),
        client.get("/llm/prompts").then((r) => r.data),
      ]);
      setDecisions(dec);
      setPrompts(prm);
    } catch { /* ignore */ } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { fetchData(); }, [fetchData]);

  if (loading) return <div className="loading">로딩 중...</div>;

  // 통계
  const totalCost = decisions.reduce((s, d) => s + (d.cost_usd || 0), 0);
  const totalTokens = decisions.reduce((s, d) => s + (d.input_tokens || 0) + (d.output_tokens || 0), 0);
  const activeModel = decisions[0]?.model || "-";
  const activePrompt = prompts.find((p) => p.is_active);

  return (
    <div>
      <div className="page-header">
        <h1>LLM 관리</h1>
        <p>AI 시장분석 현황 — 모델, 비용, 프롬프트</p>
      </div>

      {/* KPI */}
      <div className="kpi-grid">
        <StatCard
          label="활성 모델"
          value={activeModel.replace("claude-", "").replace("-20251001", "")}
          sub={activeModel}
        />
        <StatCard
          label="분석 주기"
          value="4시간"
          sub={`총 ${decisions.length}회 분석`}
        />
        <StatCard
          label="총 비용"
          value={`$${totalCost.toFixed(4)}`}
          sub={`${formatKRW(totalCost * 1350)} (${totalTokens.toLocaleString()} 토큰)`}
        />
        <StatCard
          label="활성 프롬프트"
          value={activePrompt?.version || "-"}
          sub={activePrompt ? formatDateTime(activePrompt.activated_at) : ""}
        />
      </div>

      {/* 분석 이력 */}
      <div className="card" style={{ marginBottom: 20 }}>
        <div className="card-title">분석 이력</div>
        {decisions.length > 0 ? (
          <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
            {decisions.map((d) => {
              const parts = (d.output_reasoning || "").split("\n\n");
              const summary = parts[0] || "";
              const reasoning = parts[1] || "";
              let beforeAfter: any = null;
              try { beforeAfter = d.input_news_summary ? JSON.parse(d.input_news_summary) : null; } catch { /* */ }

              return (
                <div key={d.id} style={{ padding: 14, borderRadius: 8, background: "var(--bg-secondary)" }}>
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 8 }}>
                    <div style={{ display: "flex", gap: 6, alignItems: "center" }}>
                      <span style={{ fontSize: 12, color: "var(--text-muted)" }}>#{d.id}</span>
                      <span className={`badge ${d.output_market_state === "bullish" ? "badge-green" : d.output_market_state === "bearish" ? "badge-red" : "badge-yellow"}`}>
                        {getMarketStateKR(d.output_market_state || "")}
                      </span>
                      <span className="badge badge-blue" style={{ fontSize: 10 }}>
                        공격성 {((d.output_aggression || 0) * 100).toFixed(0)}%
                      </span>
                      {d.evaluation_was_good !== null && (
                        <span className={`badge ${d.evaluation_was_good ? "badge-green" : "badge-red"}`} style={{ fontSize: 10 }}>
                          {d.evaluation_was_good ? "good" : "bad"}
                        </span>
                      )}
                    </div>
                    <span style={{ fontSize: 11, color: "var(--text-muted)" }}>
                      ${d.cost_usd?.toFixed(4) || "0"} · {formatDateTime(d.timestamp)}
                    </span>
                  </div>

                  <div style={{ fontSize: 13, lineHeight: 1.6, marginBottom: 6 }}>{summary}</div>
                  {reasoning && <div style={{ fontSize: 12, color: "var(--text-muted)", lineHeight: 1.5, marginBottom: 6 }}>{reasoning}</div>}

                  {beforeAfter && (
                    <div style={{ fontSize: 11, color: "var(--text-muted)", borderTop: "1px solid var(--border)", paddingTop: 6 }}>
                      <span style={{ fontWeight: 600 }}>변경: </span>
                      {Object.entries(beforeAfter.after || {}).map(([k, v]) => (
                        <span key={k} style={{ marginRight: 8 }}>
                          {k}: <span style={{ textDecoration: "line-through" }}>{(beforeAfter.before || {})[k]}</span> → <span style={{ color: "#4a9eff" }}>{String(v)}</span>
                        </span>
                      ))}
                      {beforeAfter.strategy && <span>전략: {beforeAfter.strategy}</span>}
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        ) : (
          <div className="empty-state">분석 이력 없음 (4시간마다 자동 실행)</div>
        )}
      </div>

      {/* 프롬프트 히스토리 */}
      <div className="card">
        <div className="card-title">프롬프트 히스토리</div>
        {prompts.length > 0 ? (
          <div className="table-container">
            <table>
              <thead>
                <tr>
                  <th>버전</th>
                  <th>상태</th>
                  <th>생성</th>
                  <th>설명</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                {prompts.map((p) => (
                  <tr key={p.id} style={{ background: p.is_active ? "rgba(74, 158, 255, 0.05)" : "transparent" }}>
                    <td style={{ fontWeight: 600 }}>{p.version}</td>
                    <td>
                      <span className={`badge ${p.is_active ? "badge-green" : "badge-red"}`}>
                        {p.is_active ? "활성" : "비활성"}
                      </span>
                    </td>
                    <td style={{ fontSize: 12 }}>{formatDateTime(p.created_at)}</td>
                    <td style={{ fontSize: 12, color: "var(--text-muted)" }}>{p.description}</td>
                    <td>
                      <button
                        onClick={async () => {
                          const res = await client.get(`/llm/prompts/${p.id}`);
                          setSelectedPrompt(p);
                          setPromptText(res.data.prompt_text);
                        }}
                        style={{ padding: "4px 10px", fontSize: 11, borderRadius: 4, border: "none", background: "#2a2d3e", color: "#8b8fa3", cursor: "pointer" }}
                      >
                        보기
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <div className="empty-state">프롬프트 히스토리 없음</div>
        )}
      </div>

      {/* 프롬프트 상세 모달 */}
      {selectedPrompt && (
        <div className="modal-overlay" onClick={() => setSelectedPrompt(null)}>
          <div className="modal-content" onClick={(e) => e.stopPropagation()} style={{ maxWidth: 700, width: "90%" }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 16 }}>
              <h3 style={{ margin: 0 }}>프롬프트 {selectedPrompt.version}</h3>
              <button onClick={() => setSelectedPrompt(null)} style={{ background: "none", border: "none", color: "var(--text-secondary)", fontSize: 18, cursor: "pointer" }}>x</button>
            </div>
            <pre style={{ fontSize: 11, lineHeight: 1.5, background: "var(--bg-secondary)", padding: 16, borderRadius: 8, maxHeight: 500, overflow: "auto", whiteSpace: "pre-wrap" }}>
              {promptText}
            </pre>
          </div>
        </div>
      )}
    </div>
  );
}
