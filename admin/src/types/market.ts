export interface MarketSnapshot {
  id: number;
  timestamp: string;
  btc_price: number;
  btc_open_24h: number;
  btc_high_24h: number;
  btc_low_24h: number;
  btc_change_pct_24h: number;
  btc_volume_24h: number;
  btc_trade_count_24h: number;
  btc_rsi_14: number;
  btc_ma_5: number;
  btc_ma_20: number;
  btc_ma_60: number;
  btc_bb_upper: number;
  btc_bb_lower: number;
  btc_atr_14: number;
  total_market_volume_krw: number;
  top10_avg_change_pct: number;
  market_state: "bullish" | "bearish" | "sideways";
  volatility_level: "low" | "medium" | "high";
}
