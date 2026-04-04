import { useEffect, useState, useCallback } from "react";
import { getStrategies, getActivationHistory, activateStrategy, deactivateStrategy, updateStrategyParams, getStrategySimulation } from "../api/strategies";
import { getAllCoinStrategies, updateCoinStrategy } from "../api/coinStrategy";
import type { CoinStrategyConfig } from "../api/coinStrategy";
import type { Strategy, StrategyActivation, StrategySimulation } from "../types/strategies";
import ConfirmDialog from "../components/ConfirmDialog";
import { formatPercent, formatDateTime, formatKRW } from "../utils/format";
import { getParamDesc } from "../utils/paramDescriptions";

const MARKET_SECTIONS = [
  { state: "sideways", label: "횡보장 전략", emoji: "➡️", desc: "변동이 적은 박스권에서 유리" },
  { state: "bullish", label: "상승장 전략", emoji: "📈", desc: "상승 추세에서 유리" },
  { state: "bearish", label: "하락장 전략", emoji: "📉", desc: "하락 추세에서 유리" },
] as const;

const CATEGORY_INFO: Record<string, { label: string; emoji: string; desc: string }> = {
  core: { label: "대형코인", emoji: "🏦", desc: "BTC, ETH, XRP — 변동 적음, 보수적 운용" },
  alt: { label: "알트코인", emoji: "🚀", desc: "자동 선별 알트코인 — 변동 큼, 공격적 운용" },
};

export default function StrategiesPage() {
  const [tab, setTab] = useState<"strategies" | "coin-config">("strategies");
  const [strategies, setStrategies] = useState<Strategy[]>([]);
  const [activations, setActivations] = useState<StrategyActivation[]>([]);
  const [coinConfigs, setCoinConfigs] = useState<CoinStrategyConfig[]>([]);
  const [loading, setLoading] = useState(true);
  const [confirm, setConfirm] = useState<{ name: string; action: "activate" | "deactivate" } | null>(null);
  const [editingStrategy, setEditingStrategy] = useState<Strategy | null>(null);

  const fetchData = async () => {
    try {
      const [strats, hist, coinCfg] = await Promise.all([
        getStrategies(),
        getActivationHistory(20),
        getAllCoinStrategies().catch(() => []),
      ]);
      setStrategies(strats);
      setActivations(hist);
      setCoinConfigs(coinCfg);
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
  const hasSwitching = strategies.some((s) => s.status === "shutting_down");

  return (
    <div>
      <div className="page-header">
        <h1>전략 관리</h1>
        <p>매매 전략 및 코인별 전략 설정</p>
      </div>

      {/* 탭 바 */}
      <div style={{ display: "flex", gap: 4, marginBottom: 20 }}>
        {([["strategies", "전략 목록"], ["coin-config", "코인별 전략 설정"]] as const).map(([key, label]) => (
          <button
            key={key}
            onClick={() => setTab(key)}
            style={{
              padding: "8px 20px", fontSize: 14, fontWeight: 600, borderRadius: 8,
              border: "none", cursor: "pointer",
              background: tab === key ? "#4a9eff" : "#2a2d3e",
              color: tab === key ? "#fff" : "#8b8fa3",
            }}
          >
            {label}
          </button>
        ))}
      </div>

      {tab === "coin-config" ? (
        <CoinStrategyTab configs={coinConfigs} strategies={strategies} onSaved={fetchData} />
      ) : (
      <>

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

      {/* Strategy sections by market state */}
      {MARKET_SECTIONS.map((section) => {
        const sectionStrategies = strategies.filter((s) =>
          s.market_states.includes(section.state)
        );
        if (sectionStrategies.length === 0) return null;

        return (
          <div key={section.state} style={{ marginBottom: 28 }}>
            <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 14 }}>
              <span style={{ fontSize: 20 }}>{section.emoji}</span>
              <h2 style={{ margin: 0, fontSize: 18 }}>{section.label}</h2>
              <span style={{ fontSize: 13, color: "var(--text-muted)" }}>{section.desc}</span>
            </div>
            <div className="strategy-grid">
              {sectionStrategies.map((s) => (
                <StrategyCard
                  key={`${section.state}-${s.name}`}
                  strategy={s}
                  hasSwitching={hasSwitching}
                  onEdit={() => setEditingStrategy(s)}
                  onActivate={() => setConfirm({ name: s.name, action: "activate" })}
                  onDeactivate={() => setConfirm({ name: s.name, action: "deactivate" })}
                />
              ))}
            </div>
          </div>
        );
      })}

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
                      <span className={`badge ${a.action === "activate" ? "badge-green" : a.action === "shutting_down" ? "badge-yellow" : "badge-red"}`}>
                        {a.action === "activate" ? "활성화" : a.action === "shutting_down" ? "종료중" : "비활성화"}
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
          title={`전략 ${confirm.action === "activate" ? "전환" : "비활성화"}`}
          message={
            confirm.action === "activate"
              ? `'${confirm.name}' 전략으로 전환하시겠습니까? 기존 전략은 자동으로 종료됩니다.`
              : `'${confirm.name}' 전략을 비활성화하시겠습니까?`
          }
          onConfirm={handleToggle}
          onCancel={() => setConfirm(null)}
        />
      )}

      </>
      )}

      {editingStrategy && (
        <ParamsEditor
          strategy={editingStrategy}
          onClose={() => setEditingStrategy(null)}
          onSaved={fetchData}
        />
      )}
    </div>
  );
}


// ── 코인별 전략 설정 탭 ──

function CoinStrategyTab({ configs, strategies, onSaved }: {
  configs: CoinStrategyConfig[];
  strategies: Strategy[];
  onSaved: () => void;
}) {
  const [saving, setSaving] = useState<string | null>(null);
  const [editState, setEditState] = useState<Record<string, {
    strategy_name: string;
    stop_loss_pct: string;
    trailing_stop_pct: string;
    position_size_pct: string;
    strategy_params_json: string;
  }>>({});

  useEffect(() => {
    const state: typeof editState = {};
    configs.forEach((c) => {
      state[c.category] = {
        strategy_name: c.strategy_name,
        stop_loss_pct: String(c.stop_loss_pct),
        trailing_stop_pct: String(c.trailing_stop_pct),
        position_size_pct: String(c.position_size_pct),
        strategy_params_json: c.strategy_params_json || "{}",
      };
    });
    setEditState(state);
  }, [configs]);

  const handleSave = async (category: string) => {
    const edit = editState[category];
    if (!edit) return;
    setSaving(category);
    try {
      await updateCoinStrategy(category, {
        strategy_name: edit.strategy_name,
        stop_loss_pct: parseFloat(edit.stop_loss_pct),
        trailing_stop_pct: parseFloat(edit.trailing_stop_pct),
        position_size_pct: parseFloat(edit.position_size_pct),
        strategy_params_json: edit.strategy_params_json,
      });
      onSaved();
    } finally {
      setSaving(null);
    }
  };

  const strategyNames = strategies.map((s) => s.name);

  return (
    <div>
      {configs.map((cfg) => {
        const info = CATEGORY_INFO[cfg.category] || { label: cfg.category, emoji: "📦", desc: "" };
        const edit = editState[cfg.category];
        if (!edit) return null;

        return (
          <div key={cfg.category} className="card" style={{ marginBottom: 20 }}>
            <div className="card-title">
              <span style={{ marginRight: 8 }}>{info.emoji}</span>
              {info.label}
              <span style={{ fontSize: 12, color: "var(--text-muted)", marginLeft: 8 }}>{info.desc}</span>
            </div>

            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16 }}>
              {/* 전략 선택 */}
              <div>
                <div style={{ fontSize: 12, color: "var(--text-muted)", marginBottom: 4 }}>매매 전략</div>
                <select
                  value={edit.strategy_name}
                  onChange={(e) => setEditState((prev) => ({ ...prev, [cfg.category]: { ...edit, strategy_name: e.target.value } }))}
                  style={{
                    width: "100%", padding: "8px", borderRadius: 6,
                    border: "1px solid var(--border)", background: "var(--bg-secondary)",
                    color: "var(--text-primary)", fontSize: 13,
                  }}
                >
                  {strategyNames.map((name) => (
                    <option key={name} value={name}>{name}</option>
                  ))}
                </select>
              </div>

              {/* 포지션 크기 */}
              <EditField label="포지션 크기 (%)" caption="잔고 대비 투자 비율" value={edit.position_size_pct}
                onChange={(v) => setEditState((prev) => ({ ...prev, [cfg.category]: { ...edit, position_size_pct: v } }))} />

              {/* 손절 */}
              <EditField label="손절률 (%)" caption="매수가 대비 이 비율 하락 시 자동 매도" value={edit.stop_loss_pct}
                onChange={(v) => setEditState((prev) => ({ ...prev, [cfg.category]: { ...edit, stop_loss_pct: v } }))} />

              {/* 트레일링 */}
              <EditField label="트레일링 스탑 (%)" caption="최고가 대비 이 비율 하락 시 자동 매도" value={edit.trailing_stop_pct}
                onChange={(v) => setEditState((prev) => ({ ...prev, [cfg.category]: { ...edit, trailing_stop_pct: v } }))} />

              {/* 전략 파라미터 */}
              <div style={{ gridColumn: "1 / -1" }}>
                <div style={{ fontSize: 12, color: "var(--text-muted)", marginBottom: 4 }}>전략 파라미터 (JSON)</div>
                <input
                  value={edit.strategy_params_json}
                  onChange={(e) => setEditState((prev) => ({ ...prev, [cfg.category]: { ...edit, strategy_params_json: e.target.value } }))}
                  style={{
                    width: "100%", padding: "8px", borderRadius: 6, fontFamily: "monospace",
                    border: "1px solid var(--border)", background: "var(--bg-secondary)",
                    color: "var(--text-primary)", fontSize: 12,
                  }}
                />
                <div style={{ fontSize: 11, color: "var(--text-muted)", marginTop: 2 }}>
                  {cfg.description}
                </div>
              </div>
            </div>

            <div style={{ marginTop: 16, display: "flex", justifyContent: "flex-end" }}>
              <button
                onClick={() => handleSave(cfg.category)}
                disabled={saving === cfg.category}
                className="btn btn-primary btn-sm"
                style={{ opacity: saving === cfg.category ? 0.6 : 1 }}
              >
                {saving === cfg.category ? "저장 중..." : "설정 저장"}
              </button>
            </div>
          </div>
        );
      })}
    </div>
  );
}

function EditField({ label, caption, value, onChange }: {
  label: string; caption: string; value: string; onChange: (v: string) => void;
}) {
  return (
    <div>
      <div style={{ fontSize: 12, color: "var(--text-muted)", marginBottom: 4 }}>{label}</div>
      <input
        type="number" step="0.5" value={value}
        onChange={(e) => onChange(e.target.value)}
        style={{
          width: "100%", padding: "8px", borderRadius: 6,
          border: "1px solid var(--border)", background: "var(--bg-secondary)",
          color: "var(--text-primary)", fontSize: 13,
        }}
      />
      <div style={{ fontSize: 11, color: "var(--text-muted)", marginTop: 2 }}>{caption}</div>
    </div>
  );
}


// ── 전략 카드 ──

function StrategyCard({ strategy: s, hasSwitching, onEdit, onActivate, onDeactivate }: {
  strategy: Strategy;
  hasSwitching: boolean;
  onEdit: () => void;
  onActivate: () => void;
  onDeactivate: () => void;
}) {
  return (
    <div
      className={`strategy-card ${s.is_active ? "active-strategy" : ""}`}
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
        <span className={`badge ${s.status === "active" ? "badge-green" : s.status === "shutting_down" ? "badge-yellow" : "badge-red"}`}>
          {s.status === "active" ? "활성" : s.status === "shutting_down" ? "종료중" : "비활성"}
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
      </div>
      <div style={{ display: "flex", gap: 8 }}>
        <span className="badge badge-blue">{s.timeframe}</span>
      </div>
      <div style={{ marginTop: 12 }} onClick={(e) => e.stopPropagation()}>
        {s.status === "shutting_down" ? (
          <button className="btn btn-sm" disabled style={{ opacity: 0.5 }}>종료 중...</button>
        ) : s.status === "active" ? (
          <button className="btn btn-danger btn-sm" onClick={onDeactivate}>비활성화</button>
        ) : (
          <button className="btn btn-primary btn-sm" disabled={!s.is_available || hasSwitching} onClick={onActivate}>활성화</button>
        )}
      </div>
    </div>
  );
}


// ── 파라미터 편집 모달 ──

function ParamsEditor({ strategy, onClose, onSaved }: {
  strategy: Strategy;
  onClose: () => void;
  onSaved: () => void;
}) {
  const currentParams = JSON.parse(strategy.default_params_json || "{}");
  const [editParams, setEditParams] = useState<Record<string, string>>({});
  const [simulation, setSimulation] = useState<StrategySimulation | null>(null);
  const [saving, setSaving] = useState(false);
  const [simLoading, setSimLoading] = useState(false);

  useEffect(() => {
    const initial: Record<string, string> = {};
    Object.entries(currentParams).forEach(([k, v]) => {
      initial[k] = String(v);
    });
    setEditParams(initial);
  }, [strategy.name]);

  const hasChanges = Object.keys(editParams).some(
    (k) => editParams[k] !== String(currentParams[k])
  );

  const runSimulation = useCallback(async () => {
    setSimLoading(true);
    try {
      const newParams: Record<string, number> = {};
      Object.entries(editParams).forEach(([k, v]) => {
        newParams[k] = parseFloat(v) || 0;
      });
      const result = await getStrategySimulation(strategy.name, JSON.stringify(newParams));
      setSimulation(result);
    } catch {
      // ignore
    } finally {
      setSimLoading(false);
    }
  }, [editParams, strategy.name]);

  // 파라미터 변경 시 자동 시뮬레이션
  useEffect(() => {
    const timer = setTimeout(() => {
      runSimulation();
    }, 300);
    return () => clearTimeout(timer);
  }, [editParams, runSimulation]);

  const handleSave = async () => {
    setSaving(true);
    try {
      const newParams: Record<string, number> = {};
      Object.entries(editParams).forEach(([k, v]) => {
        newParams[k] = parseFloat(v) || 0;
      });
      await updateStrategyParams(strategy.name, JSON.stringify(newParams));
      onSaved();
      onClose();
    } finally {
      setSaving(false);
    }
  };

  const sim = simulation?.simulation || {};

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal-content" onClick={(e) => e.stopPropagation()} style={{ maxWidth: 700, width: "90%" }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 20 }}>
          <div>
            <h3 style={{ margin: 0 }}>{strategy.display_name} — 파라미터 설정</h3>
            <div style={{ fontSize: 12, color: "var(--text-muted)", marginTop: 4 }}>{strategy.description}</div>
          </div>
          <button onClick={onClose} style={{ background: "none", border: "none", color: "var(--text-secondary)", fontSize: 18, cursor: "pointer" }}>x</button>
        </div>

        {/* 파라미터 편집 — 설명 포함 */}
        <div style={{ marginBottom: 20 }}>
          <div style={{ display: "grid", gridTemplateColumns: "1fr auto auto", gap: 0, fontSize: 12, fontWeight: 600, color: "var(--text-muted)", padding: "0 0 8px", borderBottom: "1px solid var(--border)" }}>
            <span>파라미터</span>
            <span style={{ width: 80, textAlign: "center" }}>현재값</span>
            <span style={{ width: 90, textAlign: "center", color: "#4a9eff" }}>변경값</span>
          </div>
          {Object.entries(editParams).map(([key, value]) => {
            const desc = getParamDesc(strategy.name, key);
            const changed = value !== String(currentParams[key]);
            return (
              <div key={key} style={{ padding: "12px 0", borderBottom: "1px solid var(--border)" }}>
                <div style={{ display: "grid", gridTemplateColumns: "1fr auto auto", gap: 8, alignItems: "center" }}>
                  <div>
                    <div style={{ fontSize: 14, fontWeight: 600 }}>
                      {desc.label}
                      {desc.unit && <span style={{ fontSize: 11, color: "var(--text-muted)", marginLeft: 4 }}>({desc.unit})</span>}
                    </div>
                  </div>
                  <div style={{ width: 80, textAlign: "center", fontSize: 14, color: changed ? "var(--text-muted)" : "var(--text-primary)", textDecoration: changed ? "line-through" : "none" }}>
                    {String(currentParams[key])}
                  </div>
                  <input
                    type="number"
                    step={desc.step || 0.05}
                    min={desc.min}
                    max={desc.max}
                    value={value}
                    onChange={(e) => setEditParams((prev) => ({ ...prev, [key]: e.target.value }))}
                    style={{
                      width: 90,
                      padding: "6px 8px",
                      borderRadius: 6,
                      border: changed ? "2px solid #4a9eff" : "1px solid var(--border)",
                      background: "var(--bg-secondary)",
                      color: "var(--text-primary)",
                      fontSize: 14,
                      textAlign: "right",
                      fontWeight: 600,
                    }}
                  />
                </div>
                <div style={{ fontSize: 12, color: "var(--text-muted)", marginTop: 4 }}>{desc.description}</div>
                {desc.tip && (
                  <div style={{ fontSize: 11, color: "#4a9eff", marginTop: 2 }}>
                    {desc.tip}
                  </div>
                )}
              </div>
            );
          })}
        </div>

        {/* 시뮬레이션 결과 */}
        {simLoading ? (
          <div style={{ textAlign: "center", padding: 16, color: "var(--text-muted)" }}>시뮬레이션 중...</div>
        ) : Object.keys(sim).length > 0 ? (
          <div style={{ background: "var(--bg-secondary)", borderRadius: 8, padding: 16, marginBottom: 16 }}>
            <div style={{ fontSize: 13, fontWeight: 600, marginBottom: 12 }}>
              현재 시장 기반 시뮬레이션
            </div>
            <SimulationResult strategyName={strategy.name} sim={sim} hasChanges={hasChanges} />
          </div>
        ) : null}

        {/* 저장 버튼 */}
        <div style={{ display: "flex", justifyContent: "flex-end", gap: 8 }}>
          <button onClick={onClose} className="btn btn-sm" style={{ background: "#2a2d3e" }}>취소</button>
          <button
            onClick={handleSave}
            disabled={!hasChanges || saving}
            className="btn btn-primary btn-sm"
            style={{ opacity: hasChanges ? 1 : 0.4 }}
          >
            {saving ? "저장 중..." : "파라미터 적용"}
          </button>
        </div>
      </div>
    </div>
  );
}


function SimulationResult({ strategyName, sim, hasChanges }: {
  strategyName: string;
  sim: Record<string, number | string | null>;
  hasChanges: boolean;
}) {
  if (strategyName === "bollinger_bands" || strategyName === "bollinger_squeeze") {
    return (
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12, fontSize: 13 }}>
        <SimRow label="현재 BTC" value={formatKRW(Number(sim.current_price))} />
        <SimRow label="MA(20)" value={formatKRW(Number(sim.ma_20))} />
        <SimRow label="현재 상단" value={formatKRW(Number(sim.current_upper))} changed={hasChanges} />
        <SimRow label="변경 상단" value={formatKRW(Number(sim.new_upper))} highlight={hasChanges} />
        <SimRow label="현재 하단" value={formatKRW(Number(sim.current_lower))} changed={hasChanges} />
        <SimRow label="변경 하단" value={formatKRW(Number(sim.new_lower))} highlight={hasChanges} />
        <SimRow label="현재 밴드폭" value={formatKRW(Number(sim.current_band_width))} changed={hasChanges} />
        <SimRow label="변경 밴드폭" value={formatKRW(Number(sim.new_band_width))} highlight={hasChanges} />
        <SimRow
          label="현재 하단까지"
          value={`${formatKRW(Number(sim.current_distance_to_lower))} (${sim.current_distance_to_lower_pct}%)`}
          changed={hasChanges}
        />
        <SimRow
          label="변경 하단까지"
          value={`${formatKRW(Number(sim.new_distance_to_lower))} (${sim.new_distance_to_lower_pct}%)`}
          highlight={hasChanges}
        />
      </div>
    );
  }

  if (strategyName === "volatility_breakout") {
    return (
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12, fontSize: 13 }}>
        <SimRow label="현재 BTC" value={formatKRW(Number(sim.current_price))} />
        <SimRow label="금일 시가" value={formatKRW(Number(sim.today_open))} />
        <SimRow label="전일 변동폭" value={formatKRW(Number(sim.price_range))} />
        <div />
        <SimRow label="현재 돌파선" value={formatKRW(Number(sim.current_breakout))} changed={hasChanges} />
        <SimRow label="변경 돌파선" value={formatKRW(Number(sim.new_breakout))} highlight={hasChanges} />
        <SimRow label="현재 거리" value={formatKRW(Number(sim.current_distance))} changed={hasChanges} />
        <SimRow label="변경 거리" value={formatKRW(Number(sim.new_distance))} highlight={hasChanges} />
      </div>
    );
  }

  if (strategyName === "rsi_mean_reversion") {
    return (
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12, fontSize: 13 }}>
        <SimRow label="현재 RSI" value={String(sim.current_rsi)} />
        <div />
        <SimRow label="현재 과매도" value={String(sim.current_oversold)} changed={hasChanges} />
        <SimRow label="변경 과매도" value={String(sim.new_oversold)} highlight={hasChanges} />
        <SimRow label="현재 과매수" value={String(sim.current_overbought)} changed={hasChanges} />
        <SimRow label="변경 과매수" value={String(sim.new_overbought)} highlight={hasChanges} />
        <SimRow label="현재 매수까지" value={`RSI ${sim.current_buy_distance} 남음`} changed={hasChanges} />
        <SimRow label="변경 매수까지" value={`RSI ${sim.new_buy_distance} 남음`} highlight={hasChanges} />
      </div>
    );
  }

  // 기본: key-value 나열
  return (
    <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8, fontSize: 13 }}>
      {Object.entries(sim).map(([key, value]) => (
        <SimRow key={key} label={key} value={value != null ? String(typeof value === "number" ? value.toLocaleString() : value) : "-"} />
      ))}
    </div>
  );
}


function SimRow({ label, value, changed, highlight }: {
  label: string;
  value: string;
  changed?: boolean;
  highlight?: boolean;
}) {
  return (
    <div style={{
      display: "flex",
      justifyContent: "space-between",
      padding: "4px 8px",
      borderRadius: 4,
      background: highlight ? "rgba(74, 158, 255, 0.1)" : "transparent",
      opacity: changed ? 0.5 : 1,
      textDecoration: changed ? "line-through" : "none",
    }}>
      <span style={{ color: "var(--text-muted)" }}>{label}</span>
      <span style={{ fontWeight: 600, color: highlight ? "#4a9eff" : "var(--text-primary)" }}>{value}</span>
    </div>
  );
}
