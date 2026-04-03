import { useEffect, useState, useCallback } from "react";
import { getAllConfig, updateConfig } from "../api/config";
import type { ConfigItem } from "../api/config";

const CATEGORY_LABELS: Record<string, string> = {
  notification: "알림 설정",
  bot: "봇 설정",
  risk: "리스크 관리",
  strategy: "전략 파라미터",
};

const CATEGORY_ORDER = ["bot", "notification", "risk", "strategy"];

export default function ConfigPage() {
  const [configs, setConfigs] = useState<ConfigItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState<string | null>(null);
  const [editValues, setEditValues] = useState<Record<string, string>>({});

  const loadConfigs = useCallback(async () => {
    try {
      const data = await getAllConfig();
      setConfigs(data);
      const values: Record<string, string> = {};
      data.forEach((c) => (values[c.key] = c.value));
      setEditValues(values);
    } catch {
      // ignore
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadConfigs();
  }, [loadConfigs]);

  const handleToggle = async (key: string, currentValue: string) => {
    const newValue = currentValue === "true" ? "false" : "true";
    setSaving(key);
    try {
      const updated = await updateConfig(key, newValue);
      setConfigs((prev) => prev.map((c) => (c.key === key ? updated : c)));
      setEditValues((prev) => ({ ...prev, [key]: newValue }));
    } catch {
      // ignore
    } finally {
      setSaving(null);
    }
  };

  const handleSave = async (key: string) => {
    const newValue = editValues[key];
    if (newValue === undefined) return;
    setSaving(key);
    try {
      const updated = await updateConfig(key, newValue);
      setConfigs((prev) => prev.map((c) => (c.key === key ? updated : c)));
    } catch {
      // ignore
    } finally {
      setSaving(null);
    }
  };

  if (loading) return <div className="loading">로딩 중...</div>;

  // 카테고리별 그룹핑
  const grouped: Record<string, ConfigItem[]> = {};
  configs.forEach((c) => {
    if (!grouped[c.category]) grouped[c.category] = [];
    grouped[c.category].push(c);
  });

  return (
    <div>
      <div className="page-header">
        <h1>Config</h1>
        <p>봇 설정 관리 - 변경 시 즉시 반영됩니다</p>
      </div>

      {CATEGORY_ORDER.filter((cat) => grouped[cat]).map((category) => (
        <div key={category} className="card" style={{ marginBottom: 20 }}>
          <div className="card-title">{CATEGORY_LABELS[category] || category}</div>
          <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
            {grouped[category].map((cfg) => (
              <div
                key={cfg.key}
                style={{
                  display: "flex",
                  justifyContent: "space-between",
                  alignItems: "center",
                  padding: "12px 0",
                  borderBottom: "1px solid var(--border)",
                }}
              >
                <div style={{ flex: 1 }}>
                  <div style={{ fontWeight: 600, marginBottom: 4 }}>{cfg.display_name}</div>
                  <div style={{ fontSize: 12, color: "var(--text-muted)" }}>{cfg.description}</div>
                  <div style={{ fontSize: 11, color: "var(--text-muted)", marginTop: 2 }}>
                    key: <code>{cfg.key}</code>
                  </div>
                </div>
                <div style={{ marginLeft: 24, minWidth: 140, display: "flex", justifyContent: "flex-end", alignItems: "center", gap: 8 }}>
                  {cfg.value_type === "bool" ? (
                    <button
                      onClick={() => handleToggle(cfg.key, cfg.value)}
                      disabled={saving === cfg.key}
                      style={{
                        padding: "6px 16px",
                        borderRadius: 20,
                        border: "none",
                        cursor: "pointer",
                        fontSize: 13,
                        fontWeight: 600,
                        minWidth: 60,
                        background: cfg.value === "true" ? "#22c55e" : "#4b5563",
                        color: "#fff",
                        transition: "all 0.2s",
                        opacity: saving === cfg.key ? 0.6 : 1,
                      }}
                    >
                      {cfg.value === "true" ? "ON" : "OFF"}
                    </button>
                  ) : (
                    <>
                      <input
                        type={cfg.value_type === "int" || cfg.value_type === "float" ? "number" : "text"}
                        step={cfg.value_type === "float" ? "0.1" : "1"}
                        value={editValues[cfg.key] ?? ""}
                        onChange={(e) => setEditValues((prev) => ({ ...prev, [cfg.key]: e.target.value }))}
                        style={{
                          width: 80,
                          padding: "6px 8px",
                          borderRadius: 6,
                          border: "1px solid var(--border)",
                          background: "var(--bg-secondary)",
                          color: "var(--text-primary)",
                          fontSize: 13,
                          textAlign: "right",
                        }}
                      />
                      <button
                        onClick={() => handleSave(cfg.key)}
                        disabled={saving === cfg.key || editValues[cfg.key] === cfg.value}
                        style={{
                          padding: "6px 12px",
                          borderRadius: 6,
                          border: "none",
                          cursor: editValues[cfg.key] !== cfg.value ? "pointer" : "default",
                          fontSize: 12,
                          background: editValues[cfg.key] !== cfg.value ? "#4a9eff" : "#2a2d3e",
                          color: editValues[cfg.key] !== cfg.value ? "#fff" : "#666",
                          opacity: saving === cfg.key ? 0.6 : 1,
                        }}
                      >
                        저장
                      </button>
                    </>
                  )}
                </div>
              </div>
            ))}
          </div>
        </div>
      ))}
    </div>
  );
}
