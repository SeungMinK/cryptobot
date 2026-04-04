import { formatKRW } from "../../utils/format";

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

export default function SimulationResult({ strategyName, sim, hasChanges }: {
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
