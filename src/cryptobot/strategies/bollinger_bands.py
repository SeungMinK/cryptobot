"""볼린저 밴드 반전 전략.

가격이 하단 밴드 이탈 후 복귀하면 매수,
상단 밴드 이탈 후 복귀하면 매도.
횡보장에서 높은 승률.
"""

import pandas as pd

from cryptobot.strategies.base import BaseStrategy, Signal, StrategyInfo, StrategyParams


class BollingerBands(BaseStrategy):
    """볼린저 밴드 반전 전략."""

    def __init__(self, params: StrategyParams | None = None) -> None:
        super().__init__(params)
        self._period = self.params.extra.get("bb_period", 20)
        self._num_std = self.params.extra.get("bb_std", 2.0)

    def _calc_bands(self, close: pd.Series) -> tuple[pd.Series, pd.Series, pd.Series]:
        """(middle, upper, lower) 밴드 계산."""
        middle = close.rolling(self._period).mean()
        std = close.rolling(self._period).std()
        upper = middle + self._num_std * std
        lower = middle - self._num_std * std
        return middle, upper, lower

    def info(self) -> StrategyInfo:
        return StrategyInfo(
            name="bollinger_bands",
            display_name="볼린저 밴드",
            description=f"BB({self._period}, {self._num_std}) 밴드 이탈 후 복귀 시 반전 진입.",
            market_states=["sideways"],
            timeframe="1h",
            difficulty="easy",
        )

    def check_buy(self, df: pd.DataFrame, current_price: float) -> Signal:
        if len(df) < self._period + 1:
            return Signal("hold", 0.0, "데이터 부족")

        middle, upper, lower = self._calc_bands(df["close"])
        prev_close = df["close"].iloc[-2]
        prev_lower = lower.iloc[-2]
        curr_lower = lower.iloc[-1]

        # 이전에 하단 밴드 아래였다가 다시 밴드 안으로 복귀
        if prev_close <= prev_lower and current_price > curr_lower:
            # 밴드 폭 대비 이탈 정도로 신뢰도 계산
            band_width = upper.iloc[-1] - curr_lower
            if band_width > 0:
                confidence = min((curr_lower - prev_close) / band_width + 0.5, 1.0)
            else:
                confidence = 0.5
            return Signal(
                "buy",
                round(max(confidence, 0.3), 3),
                "볼린저 하단 반등",
                trigger_value=round(curr_lower, 2),
                stop_loss=round(curr_lower * 0.99, 2),
                take_profit=round(middle.iloc[-1], 2),
            )

        return Signal("hold", 0.0, "밴드 이탈 없음")

    def check_sell(self, df: pd.DataFrame, current_price: float, buy_price: float) -> Signal:
        stop_signal = self.check_trailing_stop(current_price, buy_price)
        if stop_signal:
            return stop_signal

        if len(df) < self._period + 1:
            return Signal("hold", 0.0, "데이터 부족")

        middle, upper, lower = self._calc_bands(df["close"])
        prev_close = df["close"].iloc[-2]
        prev_upper = upper.iloc[-2]
        curr_upper = upper.iloc[-1]

        # 상단 밴드 위였다가 다시 밴드 안으로 복귀
        if prev_close >= prev_upper and current_price < curr_upper:
            return Signal("sell", 0.7, "볼린저 상단 반전", trigger_value=round(curr_upper, 2))

        # 중심선 도달 시 익절 (수수료 차감 후 실질 수익 기준)
        if current_price >= middle.iloc[-1] and buy_price < middle.iloc[-1]:
            profit_pct = (current_price - buy_price) / buy_price * 100
            net_pnl = self._net_pnl_pct(profit_pct)
            if net_pnl > 1.0:
                return Signal("sell", 0.5, f"중심선 익절 (실질 +{net_pnl:.1f}%)", is_profit_taking=True)

        return Signal("hold", 0.0, "보유 유지")
