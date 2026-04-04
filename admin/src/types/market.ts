export interface MarketSnapshot {
  id: number;
  timestamp: string;
  price: number;
  open_24h: number;
  high_24h: number;
  low_24h: number;
  change_pct_24h: number;
  volume_24h: number;
  btc_trade_count_24h: number;
  rsi_14: number;
  ma_5: number;
  ma_20: number;
  ma_60: number;
  bb_upper: number;
  bb_lower: number;
  atr_14: number;
  total_market_volume_krw: number;
  top10_avg_change_pct: number;
  market_state: "bullish" | "bearish" | "sideways";
  volatility_level: "low" | "medium" | "high";
}
