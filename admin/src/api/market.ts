import client from "./client";
import type { MarketSnapshot } from "../types/market";

export async function getCurrentMarket(): Promise<MarketSnapshot> {
  const { data } = await client.get<MarketSnapshot>("/market/current");
  return data;
}

export async function getMarketSnapshots(limit: number = 60): Promise<MarketSnapshot[]> {
  const { data } = await client.get<MarketSnapshot[]>("/market/snapshots", { params: { limit } });
  return data;
}
