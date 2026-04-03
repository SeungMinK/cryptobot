/**
 * 기술적 지표 + 시장 용어 한글 설명.
 * 코인/트레이딩을 모르는 사람도 이해할 수 있도록.
 */

export interface IndicatorDesc {
  label: string;
  description: string;
}

export const INDICATOR_DESCRIPTIONS: Record<string, IndicatorDesc> = {
  btc_rsi_14: {
    label: "RSI (14일)",
    description: "가격이 최근 14일간 얼마나 올랐는지/내렸는지 나타내는 지수 (0~100). 30 이하면 과매도(반등 가능), 70 이상이면 과매수(하락 가능).",
  },
  btc_ma_5: {
    label: "5일 이동평균",
    description: "최근 5일간의 평균 가격. 현재가보다 낮으면 단기 상승 추세.",
  },
  btc_ma_20: {
    label: "20일 이동평균",
    description: "최근 20일간의 평균 가격. 5일선이 이 선 위로 올라가면 상승 신호(골든크로스).",
  },
  btc_ma_60: {
    label: "60일 이동평균",
    description: "최근 60일간의 평균 가격. 장기 추세를 나타냄.",
  },
  btc_bb_upper: {
    label: "볼린저 상단",
    description: "이 가격 근처에 도달하면 '비싸다'는 신호. 매도 타이밍 참고.",
  },
  btc_bb_lower: {
    label: "볼린저 하단",
    description: "이 가격 근처에 도달하면 '싸다'는 신호. 매수 타이밍 참고.",
  },
  btc_atr_14: {
    label: "ATR (14일 변동성)",
    description: "최근 14일간 하루 평균 가격 변동 폭. 높으면 변동성이 큰 시장.",
  },
};

/**
 * 시장 상태 한글 변환.
 */
export const MARKET_STATE_KR: Record<string, { label: string; description: string }> = {
  bullish: {
    label: "상승장",
    description: "가격이 전반적으로 오르는 추세",
  },
  bearish: {
    label: "하락장",
    description: "가격이 전반적으로 내리는 추세",
  },
  sideways: {
    label: "횡보장",
    description: "뚜렷한 방향 없이 일정 범위에서 오르내림",
  },
};

/**
 * 신호 타입 한글 변환.
 */
export const SIGNAL_TYPE_KR: Record<string, string> = {
  buy: "매수",
  sell: "매도",
  hold: "HOLD",
};

export function getIndicatorDesc(key: string): IndicatorDesc {
  return INDICATOR_DESCRIPTIONS[key] || { label: key, description: "" };
}

export function getMarketStateKR(state: string): string {
  return MARKET_STATE_KR[state]?.label || state;
}
