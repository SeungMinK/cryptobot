/**
 * 전략 파라미터 설명 사전.
 * 코인/트레이딩을 모르는 사람도 이해할 수 있도록 쉬운 설명 제공.
 */

interface ParamDesc {
  label: string;
  description: string;
  tip?: string;
  min?: number;
  max?: number;
  step?: number;
  unit?: string;
}

const PARAM_DESCRIPTIONS: Record<string, Record<string, ParamDesc>> = {
  // ── 볼린저 밴드 / 볼린저 스퀴즈 공통 ──
  bollinger_bands: {
    bb_period: {
      label: "밴드 기준 기간",
      description: "최근 며칠간의 평균 가격을 기준으로 밴드를 계산합니다.",
      tip: "20이 표준. 줄이면 최근 가격에 민감, 늘리면 장기 추세 반영.",
      min: 5, max: 50, step: 1, unit: "일",
    },
    bb_std: {
      label: "밴드 폭 (표준편차 배수)",
      description: "밴드의 넓이를 결정합니다. 낮추면 밴드가 좁아져서 매매가 자주 발생합니다.",
      tip: "2.0이 표준. 0.95~1.1이면 아주 민감 (테스트용), 1.5면 적당히 민감, 2.0이면 보수적.",
      min: 0.5, max: 3.0, step: 0.05,
    },
  },
  bollinger_squeeze: {
    bb_period: {
      label: "밴드 기준 기간",
      description: "최근 며칠간의 평균 가격을 기준으로 밴드를 계산합니다.",
      min: 5, max: 50, step: 1, unit: "일",
    },
    bb_std: {
      label: "밴드 폭 (표준편차 배수)",
      description: "밴드의 넓이를 결정합니다. 낮추면 더 작은 스퀴즈도 감지합니다.",
      tip: "2.0이 표준. 낮추면 스퀴즈 감지가 민감해짐.",
      min: 0.5, max: 3.0, step: 0.05,
    },
    squeeze_lookback: {
      label: "스퀴즈 비교 기간",
      description: "현재 밴드 폭을 최근 며칠과 비교해서 수축 여부를 판단합니다.",
      tip: "120이면 최근 120개 봉 중 가장 좁은 구간을 찾음.",
      min: 20, max: 200, step: 10, unit: "봉",
    },
  },

  // ── 변동성 돌파 ──
  volatility_breakout: {
    k_value: {
      label: "K 값 (돌파 민감도)",
      description: "어제 가격 변동폭의 몇 배를 돌파해야 매수하는지 결정합니다.",
      tip: "0.5가 표준. 낮추면(0.3) 작은 상승에도 매수, 높이면(0.7) 큰 상승만 매수. 낮을수록 매매 빈번.",
      min: 0.1, max: 1.0, step: 0.05,
    },
  },

  // ── 이동평균 교차 ──
  ma_crossover: {
    short_period: {
      label: "단기 이동평균 기간",
      description: "최근 며칠의 평균 가격 (빠르게 움직이는 선).",
      tip: "5가 표준. 줄이면 더 빨리 반응하지만 오신호도 증가.",
      min: 2, max: 20, step: 1, unit: "일",
    },
    long_period: {
      label: "장기 이동평균 기간",
      description: "더 긴 기간의 평균 가격 (느리게 움직이는 선). 단기선이 이 선을 넘으면 매수.",
      tip: "20이 표준. 단기선이 장기선 위로 올라가면 상승 신호(골든크로스).",
      min: 10, max: 60, step: 1, unit: "일",
    },
  },

  // ── MACD ──
  macd: {
    fast: {
      label: "빠른 이동평균",
      description: "MACD 계산에 사용하는 짧은 기간. 가격 변화에 빠르게 반응합니다.",
      tip: "12가 표준.",
      min: 5, max: 30, step: 1, unit: "일",
    },
    slow: {
      label: "느린 이동평균",
      description: "MACD 계산에 사용하는 긴 기간. 장기 추세를 반영합니다.",
      tip: "26이 표준.",
      min: 15, max: 50, step: 1, unit: "일",
    },
    signal_period: {
      label: "시그널 기간",
      description: "MACD의 이동평균. MACD가 이 선을 넘으면 매수 신호.",
      tip: "9가 표준.",
      min: 3, max: 20, step: 1, unit: "일",
    },
  },

  // ── RSI 평균 회귀 ──
  rsi_mean_reversion: {
    rsi_period: {
      label: "RSI 계산 기간",
      description: "RSI(상대강도지수) 계산에 사용하는 기간.",
      tip: "14가 표준.",
      min: 5, max: 30, step: 1, unit: "일",
    },
    oversold: {
      label: "과매도 기준",
      description: "RSI가 이 값 아래로 내려가면 '너무 많이 팔렸다' = 반등 예상 → 매수.",
      tip: "30이 표준. 높이면(35) 더 일찍 매수, 낮추면(25) 더 확실할 때만 매수.",
      min: 10, max: 45, step: 1,
    },
    overbought: {
      label: "과매수 기준",
      description: "RSI가 이 값 위로 올라가면 '너무 많이 샀다' = 하락 예상 → 매도.",
      tip: "70이 표준. 낮추면(65) 더 일찍 매도, 높이면(75) 더 올라갈 때까지 보유.",
      min: 55, max: 90, step: 1,
    },
  },

  // ── 슈퍼트렌드 ──
  supertrend: {
    st_period: {
      label: "ATR 기간",
      description: "변동성(ATR) 계산 기간. 이 변동성으로 지지/저항선을 그립니다.",
      tip: "10이 표준.",
      min: 5, max: 30, step: 1, unit: "일",
    },
    st_multiplier: {
      label: "ATR 배수",
      description: "변동성의 몇 배로 지지/저항선을 설정할지. 높이면 느슨, 낮추면 민감.",
      tip: "3.0이 표준. 낮추면(2.0) 작은 변동에도 반응, 높이면(4.0) 큰 추세만 포착.",
      min: 1.0, max: 5.0, step: 0.5,
    },
  },

  // ── 그리드 트레이딩 ──
  grid_trading: {
    grid_count: {
      label: "격자 수",
      description: "가격 범위를 몇 개로 나눌지. 많을수록 소액으로 자주 매매.",
      tip: "10이 표준. 5면 큰 간격으로 듬성듬성, 20이면 촘촘하게 매매.",
      min: 3, max: 30, step: 1, unit: "개",
    },
    range_pct: {
      label: "가격 범위 (%)",
      description: "현재가 기준 위아래 몇 %를 격자 범위로 설정할지.",
      tip: "10이면 현재가 ±10% 범위에서 매매. 좁히면 더 자주 거래.",
      min: 2, max: 30, step: 1, unit: "%",
    },
  },

  // ── 브레이크아웃 모멘텀 ──
  breakout_momentum: {
    entry_period: {
      label: "진입 기간 (최고가)",
      description: "최근 며칠간 최고가를 돌파하면 매수. 터틀 트레이딩의 핵심.",
      tip: "20이 표준. 줄이면(10) 더 자주 매수, 늘리면(40) 큰 돌파만.",
      min: 5, max: 60, step: 1, unit: "일",
    },
    exit_period: {
      label: "청산 기간 (최저가)",
      description: "최근 며칠간 최저가를 깨면 매도.",
      tip: "10이 표준. 진입 기간보다 짧게 설정하는 게 일반적.",
      min: 3, max: 30, step: 1, unit: "일",
    },
  },

  // ── 볼린저+RSI 복합 ──
  bb_rsi_combined: {
    bb_period: {
      label: "밴드 기준 기간",
      description: "볼린저밴드 계산에 사용하는 이동평균 기간.",
      tip: "20이 표준.",
      min: 5, max: 50, step: 1, unit: "일",
    },
    bb_std: {
      label: "밴드 폭 (표준편차 배수)",
      description: "밴드의 넓이. 매수 조건에 사용 (가격 < 하단 밴드).",
      tip: "2.0이 표준. 낮추면 매수 기회 증가, 높이면 강한 이탈만 포착.",
      min: 0.5, max: 3.0, step: 0.1,
    },
    rsi_period: {
      label: "RSI 계산 기간",
      description: "RSI 지표 계산 기간.",
      tip: "14가 표준.",
      min: 5, max: 30, step: 1, unit: "일",
    },
    rsi_oversold: {
      label: "RSI 매수 기준 (과매도)",
      description: "RSI가 이 값 이하이고 볼린저 하단도 이탈해야 매수. 두 조건 동시 충족.",
      tip: "30이 표준. 낮추면(25) 더 확실한 매수만, 높이면(35) 매수 기회 증가.",
      min: 15, max: 40, step: 1,
    },
    rsi_overbought: {
      label: "RSI 매도 기준 (정상 복귀)",
      description: "RSI가 이 값 이상이면 매도. 볼린저 중간선 도달 시에도 매도.",
      tip: "50이 표준 (70보다 낮게 설정하여 빠른 익절). 높이면 더 오래 보유.",
      min: 40, max: 70, step: 1,
    },
  },
};

/**
 * 전략 이름과 파라미터 키로 설명을 가져옵니다.
 */
export function getParamDesc(strategyName: string, paramKey: string): ParamDesc {
  const strategyDescs = PARAM_DESCRIPTIONS[strategyName];
  if (strategyDescs && strategyDescs[paramKey]) {
    return strategyDescs[paramKey];
  }
  // 폴백: 키 이름 그대로
  return {
    label: paramKey,
    description: "",
  };
}

export type { ParamDesc };
