export function formatKRW(value: number): string {
  return new Intl.NumberFormat("ko-KR", { style: "currency", currency: "KRW" }).format(value);
}

export function formatPercent(value: number): string {
  const sign = value >= 0 ? "+" : "";
  return `${sign}${value.toFixed(2)}%`;
}

export function formatDate(isoString: string): string {
  return new Date(isoString).toLocaleDateString("ko-KR", {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  });
}

export function formatDateTime(isoString: string): string {
  // SQLite CURRENT_TIMESTAMP는 UTC — 명시적으로 Z 붙여서 KST 변환
  const date = isoString.endsWith("Z") || isoString.includes("+")
    ? new Date(isoString)
    : new Date(isoString + "Z");
  return date.toLocaleString("ko-KR", {
    timeZone: "Asia/Seoul",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });
}

export function formatNumber(value: number, decimals: number = 0): string {
  return new Intl.NumberFormat("ko-KR", {
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
  }).format(value);
}
