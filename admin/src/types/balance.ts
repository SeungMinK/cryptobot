import type { Trade } from "./trades";

export interface BalanceResponse {
  krw_balance: number;
  coin_balance: number;
  coin_value_krw: number;
  total_asset_krw: number;
  api_connected: boolean;
}

export interface Position extends Trade {
  current_price: number;
  unrealized_pnl_pct: number;
  unrealized_pnl_krw: number;
}

export interface PositionsResponse {
  has_position: boolean;
  position: Position | null;
}

export interface BalanceHistory {
  date: string;
  ending_balance_krw: number;
  total_asset_value_krw: number;
  daily_return_pct: number;
  cumulative_return_pct: number;
}
