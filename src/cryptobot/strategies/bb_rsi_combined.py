"""볼린저밴드 + RSI 복합 전략.

단일 지표보다 거짓 신호를 줄여 승률을 높이는 전략.
매수: RSI 과매도 + 볼린저 하단 이탈 (두 조건 동시 충족)
매도: RSI 정상 복귀 또는 볼린저 중간선 도달 (하나만 충족)

벤치마크: 60%+ 승률, 시장의 ~34% 시간만 포지션 보유.
"""

import pandas as pd

from cryptobot.strategies.base import BaseStrategy, Signal, StrategyInfo, StrategyParams


class BBRSICombined(BaseStrategy):
    """볼린저밴드 + RSI 복합 전략."""

    def __init__(self, params: StrategyParams | None = None) -> None:
        super().__init__(params)
        self._bb_period = int(self.params.extra.get("bb_period", 20))
        self._bb_std = self.params.extra.get("bb_std", 2.0)
        self._rsi_period = int(self.params.extra.get("rsi_period", 14))
        self._rsi_oversold = self.params.extra.get("rsi_oversold", 30)
        self._rsi_overbought = self.params.extra.get("rsi_overbought", 50)

    def info(self) -> StrategyInfo:
        return StrategyInfo(
            name="bb_rsi_combined",
            display_name="볼린저+RSI 복합",
            description="RSI 과매도 + 볼린저 하단 이탈 동시 충족 시 매수. 거짓 신호 감소로 높은 승률.",
            market_states=["sideways", "bearish"],
            timeframe="1d",
            difficulty="medium",
        )

    def _calc_rsi(self, df: pd.DataFrame) -> float | None:
        """RSI 계산."""
        if len(df) < self._rsi_period + 1:
            return None
        deltas = df["close"].diff().dropna()
        gains = deltas.where(deltas > 0, 0)
        losses = (-deltas.where(deltas < 0, 0))
        avg_gain = gains.rolling(self._rsi_period).mean().iloc[-1]
        avg_loss = losses.rolling(self._rsi_period).mean().iloc[-1]
        if avg_loss == 0:
            return 100.0
        rs = avg_gain / avg_loss
        return round(100 - (100 / (1 + rs)), 2)

    def _calc_bb(self, df: pd.DataFrame) -> tuple[float, float, float] | None:
        """볼린저밴드 계산. (중간, 상단, 하단)"""
        if len(df) < self._bb_period:
            return None
        ma = df["close"].rolling(self._bb_period).mean().iloc[-1]
        std = df["close"].rolling(self._bb_period).std().iloc[-1]
        upper = ma + std * self._bb_std
        lower = ma - std * self._bb_std
        return (ma, upper, lower)

    def check_buy(self, df: pd.DataFrame, current_price: float) -> Signal:
        """매수: RSI < oversold AND 가격 < 볼린저 하단."""
        rsi = self._calc_rsi(df)
        bb = self._calc_bb(df)

        if rsi is None or bb is None:
            return Signal("hold", 0.0, "데이터 부족")

        ma, upper, lower = bb

        rsi_oversold = current_price > 0 and rsi <= self._rsi_oversold
        below_lower = current_price < lower

        if rsi_oversold and below_lower:
            # 두 조건 모두 충족 → 강한 매수 신호
            # confidence: RSI가 낮을수록 + 밴드 이탈이 클수록 높음
            rsi_strength = max(0, (self._rsi_oversold - rsi) / self._rsi_oversold)
            band_depth = min((lower - current_price) / (upper - lower), 1.0) if upper != lower else 0
            confidence = min(0.5 + rsi_strength * 0.3 + band_depth * 0.2, 1.0)

            return Signal(
                "buy",
                round(confidence, 3),
                f"RSI({rsi:.0f}) 과매도 + 볼린저 하단 이탈",
                trigger_value=round(lower, 2),
                stop_loss=round(current_price * (1 + self.params.stop_loss_pct / 100), 2),
            )

        if rsi_oversold and not below_lower:
            return Signal("hold", 0.0, f"RSI({rsi:.0f}) 과매도이나 볼린저 하단 미이탈")

        if below_lower and not rsi_oversold:
            return Signal("hold", 0.0, f"볼린저 하단 이탈이나 RSI({rsi:.0f}) 정상")

        return Signal("hold", 0.0, f"조건 미충족 (RSI={rsi:.0f})")

    def check_sell(self, df: pd.DataFrame, current_price: float, buy_price: float) -> Signal:
        """매도: RSI > overbought OR 가격 > 볼린저 중간선."""
        rsi = self._calc_rsi(df)

        # 공통 손절/트레일링 체크 (RSI 전달 → 과매도 시 ROI 매도 보류)
        stop_signal = self.check_trailing_stop(current_price, buy_price, current_rsi=rsi)
        if stop_signal:
            return stop_signal

        bb = self._calc_bb(df)

        if rsi is None or bb is None:
            return Signal("hold", 0.0, "데이터 부족")

        ma, upper, lower = bb
        profit_pct = (current_price - buy_price) / buy_price * 100
        net_pnl = self._net_pnl_pct(profit_pct)

        # RSI 정상 복귀 → 전략적 매도 (수수료 무관, 알고리즘 판단 존중)
        if rsi >= self._rsi_overbought:
            return Signal(
                "sell", 0.7,
                f"RSI({rsi:.0f}) 정상 복귀 (실질 {net_pnl:+.1f}%)",
                trigger_value=round(rsi, 1),
            )

        # 볼린저 중간선 도달 → 익절 (실질 수익 있을 때만)
        if current_price >= ma and net_pnl > 0:
            return Signal(
                "sell", 0.6,
                f"볼린저 중간선 도달 (실질 +{net_pnl:.1f}%)",
                trigger_value=round(ma, 2),
                is_profit_taking=True,
            )

        return Signal("hold", 0.0, f"보유 유지 (RSI={rsi:.0f}, 실질 {net_pnl:+.1f}%)")
