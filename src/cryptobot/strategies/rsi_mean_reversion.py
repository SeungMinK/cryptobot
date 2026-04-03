"""RSI 평균 회귀 전략.

RSI가 과매도(30 이하)에서 반등하면 매수,
과매수(70 이상)에서 하락하면 매도.
횡보장에 적합.
"""

import pandas as pd

from cryptobot.strategies.base import BaseStrategy, Signal, StrategyInfo, StrategyParams


def _calculate_rsi(close: pd.Series, period: int = 14) -> pd.Series:
    """RSI 시리즈 계산."""
    delta = close.diff()
    gain = delta.where(delta > 0, 0.0)
    loss = (-delta).where(delta < 0, 0.0)
    avg_gain = gain.rolling(window=period).mean()
    avg_loss = loss.rolling(window=period).mean()
    rs = avg_gain / avg_loss
    return 100.0 - (100.0 / (1.0 + rs))


class RSIMeanReversion(BaseStrategy):
    """RSI 평균 회귀 전략."""

    def __init__(self, params: StrategyParams | None = None) -> None:
        super().__init__(params)
        self._period = self.params.extra.get("rsi_period", 14)
        self._oversold = self.params.extra.get("oversold", 30)
        self._overbought = self.params.extra.get("overbought", 70)

    def info(self) -> StrategyInfo:
        return StrategyInfo(
            name="rsi_mean_reversion",
            display_name="RSI 평균 회귀",
            description=f"RSI({self._period}) 과매도/과매수 반전 매매.",
            market_states=["sideways"],
            timeframe="1h",
            difficulty="easy",
        )

    def check_buy(self, df: pd.DataFrame, current_price: float) -> Signal:
        if len(df) < self._period + 2:
            return Signal("hold", 0.0, "데이터 부족")

        rsi = _calculate_rsi(df["close"], self._period)
        current_rsi = rsi.iloc[-1]
        previous_rsi = rsi.iloc[-2]

        # RSI가 과매도 영역에서 반등 (30 아래 → 30 위로 복귀)
        if previous_rsi <= self._oversold and current_rsi > self._oversold:
            confidence = min((self._oversold - previous_rsi) / 10 + 0.5, 1.0)
            return Signal(
                "buy",
                round(confidence, 3),
                f"RSI 과매도 반등 ({previous_rsi:.1f} → {current_rsi:.1f})",
                stop_loss=round(current_price * (1 + self.params.stop_loss_pct / 100), 2),
            )

        return Signal("hold", 0.0, f"RSI {current_rsi:.1f} — 대기")

    def check_sell(self, df: pd.DataFrame, current_price: float, buy_price: float) -> Signal:
        stop_signal = self.check_trailing_stop(current_price, buy_price)
        if stop_signal:
            return stop_signal

        if len(df) < self._period + 2:
            return Signal("hold", 0.0, "데이터 부족")

        rsi = _calculate_rsi(df["close"], self._period)
        current_rsi = rsi.iloc[-1]
        previous_rsi = rsi.iloc[-2]

        # RSI가 과매수 영역에서 하락 (70 위 → 70 아래로 복귀)
        if previous_rsi >= self._overbought and current_rsi < self._overbought:
            return Signal(
                "sell",
                0.7,
                f"RSI 과매수 하락 ({previous_rsi:.1f} → {current_rsi:.1f})",
            )

        return Signal("hold", 0.0, "보유 유지")
