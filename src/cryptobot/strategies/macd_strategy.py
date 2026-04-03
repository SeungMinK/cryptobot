"""MACD 전략.

MACD 라인이 시그널 라인을 상향 돌파하면 매수,
하향 돌파하면 매도. 히스토그램으로 추세 강도 확인.
"""

import pandas as pd

from cryptobot.strategies.base import BaseStrategy, Signal, StrategyInfo, StrategyParams


def _calculate_macd(
    close: pd.Series, fast: int = 12, slow: int = 26, signal_period: int = 9
) -> tuple[pd.Series, pd.Series, pd.Series]:
    """MACD 계산. (macd_line, signal_line, histogram) 반환."""
    ema_fast = close.ewm(span=fast, adjust=False).mean()
    ema_slow = close.ewm(span=slow, adjust=False).mean()
    macd_line = ema_fast - ema_slow
    signal_line = macd_line.ewm(span=signal_period, adjust=False).mean()
    histogram = macd_line - signal_line
    return macd_line, signal_line, histogram


class MACDStrategy(BaseStrategy):
    """MACD 전략."""

    def __init__(self, params: StrategyParams | None = None) -> None:
        super().__init__(params)
        self._fast = self.params.extra.get("fast", 12)
        self._slow = self.params.extra.get("slow", 26)
        self._signal = self.params.extra.get("signal_period", 9)

    def info(self) -> StrategyInfo:
        return StrategyInfo(
            name="macd",
            display_name="MACD",
            description=f"MACD({self._fast},{self._slow},{self._signal}) 교차 전략.",
            market_states=["bullish", "bearish"],
            timeframe="1d",
            difficulty="easy",
        )

    def check_buy(self, df: pd.DataFrame, current_price: float) -> Signal:
        if len(df) < self._slow + self._signal:
            return Signal("hold", 0.0, "데이터 부족")

        macd_line, signal_line, histogram = _calculate_macd(df["close"], self._fast, self._slow, self._signal)

        # MACD가 시그널을 상향 돌파 + 히스토그램 양수 전환
        current_above = macd_line.iloc[-1] > signal_line.iloc[-1]
        previous_above = macd_line.iloc[-2] > signal_line.iloc[-2]

        if current_above and not previous_above:
            # 0선 위에서 교차하면 더 강한 신호
            above_zero = macd_line.iloc[-1] > 0
            confidence = 0.8 if above_zero else 0.6
            return Signal(
                "buy",
                confidence,
                "MACD 골든크로스" + (" (0선 상)", "" if above_zero else ""),
                stop_loss=round(current_price * (1 + self.params.stop_loss_pct / 100), 2),
            )

        return Signal("hold", 0.0, "MACD 교차 없음")

    def check_sell(self, df: pd.DataFrame, current_price: float, buy_price: float) -> Signal:
        stop_signal = self.check_trailing_stop(current_price, buy_price)
        if stop_signal:
            return stop_signal

        if len(df) < self._slow + self._signal:
            return Signal("hold", 0.0, "데이터 부족")

        macd_line, signal_line, histogram = _calculate_macd(df["close"], self._fast, self._slow, self._signal)

        # MACD가 시그널을 하향 돌파
        current_below = macd_line.iloc[-1] < signal_line.iloc[-1]
        previous_below = macd_line.iloc[-2] < signal_line.iloc[-2]

        if current_below and not previous_below:
            return Signal("sell", 0.7, "MACD 데드크로스")

        return Signal("hold", 0.0, "보유 유지")
