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
