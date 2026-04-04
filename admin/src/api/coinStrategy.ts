import client from "./client";

export interface CoinStrategyConfig {
  id: number;
  category: string;
  strategy_name: string;
  stop_loss_pct: number;
  trailing_stop_pct: number;
  position_size_pct: number;
  strategy_params_json: string | null;
  description: string | null;
  updated_at: string;
}

export interface CoinStrategyUpdate {
  strategy_name: string;
  stop_loss_pct: number;
  trailing_stop_pct: number;
  position_size_pct: number;
  strategy_params_json?: string;
}

export async function getAllCoinStrategies(): Promise<CoinStrategyConfig[]> {
  const { data } = await client.get<CoinStrategyConfig[]>("/coin-strategy");
  return data;
}

export async function updateCoinStrategy(category: string, body: CoinStrategyUpdate): Promise<CoinStrategyConfig> {
  const { data } = await client.put<CoinStrategyConfig>(`/coin-strategy/${category}`, body);
  return data;
}
