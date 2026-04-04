import client from "./client";

export interface ConfigItem {
  key: string;
  value: string;
  value_type: string;
  category: string;
  display_name: string;
  description: string | null;
  updated_at: string;
}

export async function getAllConfig(): Promise<ConfigItem[]> {
  const { data } = await client.get<ConfigItem[]>("/config");
  return data;
}

export async function updateConfig(key: string, value: string): Promise<ConfigItem> {
  const { data } = await client.put<ConfigItem>(`/config/${key}`, { value });
  return data;
}

export interface ScannedCoin {
  ticker: string;
  price: number;
  volume_krw: number;
  change_rate: number;
}

export async function scanCoinsPreview(params: {
  max_coins: number;
  min_volume_krw: number;
  min_price_krw: number;
}): Promise<ScannedCoin[]> {
  const { data } = await client.post<ScannedCoin[]>("/market/scan-preview", params);
  return data;
}

export async function scanCoinsCurrent(): Promise<ScannedCoin[]> {
  const { data } = await client.get<ScannedCoin[]>("/market/scan-current");
  return data;
}
