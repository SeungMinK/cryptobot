export interface StrategyStats {
  total_trades: number;
  win_rate: number;
  avg_profit_pct: number;
  max_loss_pct: number;
}

export interface Strategy {
  id: number;
  name: string;
  display_name: string;
  description: string;
  category: string;
  market_states: string;
  timeframe: string;
  difficulty: string;
  default_params_json: string;
  is_active: boolean;
  status: "active" | "shutting_down" | "inactive";
  is_available: boolean;
  created_at: string;
  updated_at: string;
  stats: StrategyStats;
}

export interface StrategyActivation {
  id: number;
  timestamp: string;
  strategy_name: string;
  action: "activate" | "deactivate" | "shutting_down";
  source: "manual" | "llm" | "backtest";
  market_state: string;
  reason: string | null;
  previous_strategy: string | null;
  performance_at_switch_json: string;
}

export interface ActivateRequest {
  reason?: string;
}

export interface ActivateResponse {
  status: "activated" | "deactivated";
  strategy: string;
}
