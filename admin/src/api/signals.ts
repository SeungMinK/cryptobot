import client from "./client";

export interface SignalItem {
  id: number;
  timestamp: string;
  coin: string;
  signal_type: string;
  strategy: string;
  confidence: number;
  trigger_reason: string;
  trigger_value: number | null;
  current_price: number;
  target_price: number | null;
  executed: boolean;
  trade_id: number | null;
  skip_reason: string | null;
  snapshot_id: number | null;
  strategy_params_json: string | null;
  // joined from market_snapshots
  rsi_14: number | null;
  ma_5: number | null;
  ma_20: number | null;
  bb_upper: number | null;
  bb_lower: number | null;
  atr_14: number | null;
  market_state: string | null;
}

export interface SignalListResponse {
  items: SignalItem[];
  total: number;
  page: number;
  limit: number;
  pages: number;
}

export interface SignalStats {
  total: number;
  buy_signals: number;
  sell_signals: number;
  hold_signals: number;
  executed: number;
  avg_buy_confidence: number | null;
  avg_price: number | null;
}

export async function getSignals(params: {
  page?: number;
  limit?: number;
  signal_type?: string;
  strategy?: string;
  exclude_hold?: boolean;
  min_confidence?: number;
}): Promise<SignalListResponse> {
  const { data } = await client.get<SignalListResponse>("/signals", { params });
  return data;
}

export async function getSignalStats(hours: number = 1): Promise<SignalStats> {
  const { data } = await client.get<SignalStats>("/signals/stats", { params: { hours } });
  return data;
}
