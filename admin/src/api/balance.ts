import client from "./client";
import type { BalanceResponse, PositionsResponse, BalanceHistory } from "../types/balance";

export async function getBalance(): Promise<BalanceResponse> {
  const { data } = await client.get<BalanceResponse>("/balance");
  return data;
}

export async function getPositions(): Promise<PositionsResponse> {
  const { data } = await client.get<PositionsResponse>("/balance/positions");
  return data;
}

export async function getBalanceHistory(days: number = 30): Promise<BalanceHistory[]> {
  const { data } = await client.get<BalanceHistory[]>("/balance/history", { params: { days } });
  return data;
}
