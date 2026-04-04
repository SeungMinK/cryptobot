import { useEffect, useState, useCallback } from "react";
import { updateStrategyParams, getStrategySimulation } from "../../api/strategies";
import type { Strategy, StrategySimulation } from "../../types/strategies";
import { getParamDesc } from "../../utils/paramDescriptions";
import SimulationResult from "./SimulationResult";

export default function ParamsEditor({ strategy, onClose, onSaved }: {
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
  }, [strategy.name, strategy.default_params_json]);

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
