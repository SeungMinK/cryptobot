import client from "./client";
import type { Strategy, StrategyActivation, ActivateResponse } from "../types/strategies";

export async function getStrategies(): Promise<Strategy[]> {
  const { data } = await client.get<Strategy[]>("/strategies");
  return data;
}

export async function getActiveStrategies(): Promise<Strategy[]> {
  const { data } = await client.get<Strategy[]>("/strategies/active");
  return data;
}

export async function getStrategy(name: string): Promise<Strategy> {
  const { data } = await client.get<Strategy>(`/strategies/${name}`);
  return data;
}

export async function getActivationHistory(limit: number = 50): Promise<StrategyActivation[]> {
  const { data } = await client.get<StrategyActivation[]>("/strategies/activations", { params: { limit } });
  return data;
}

export async function activateStrategy(name: string, reason?: string): Promise<ActivateResponse> {
  const { data } = await client.put<ActivateResponse>(`/strategies/${name}/activate`, { reason });
  return data;
}

export async function deactivateStrategy(name: string, reason?: string): Promise<ActivateResponse> {
  const { data } = await client.put<ActivateResponse>(`/strategies/${name}/deactivate`, { reason });
  return data;
}
