"""이동평균 교차 전략 (MA Crossover).

단기 MA가 장기 MA를 상향 돌파(골든크로스)하면 매수,
하향 돌파(데드크로스)하면 매도.
"""

import pandas as pd

from cryptobot.strategies.base import BaseStrategy, Signal, StrategyInfo, StrategyParams


class MACrossover(BaseStrategy):
    """이동평균 교차 전략."""

    def __init__(self, params: StrategyParams | None = None) -> None:
        super().__init__(params)
        self._short_period = self.params.extra.get("short_period", 5)
        self._long_period = self.params.extra.get("long_period", 20)

    def info(self) -> StrategyInfo:
        return StrategyInfo(
            name="ma_crossover",
            display_name="이동평균 교차",
            description=f"MA({self._short_period})이 MA({self._long_period})를 돌파하면 매수/매도.",
            market_states=["bullish", "bearish"],
            timeframe="1d",
            difficulty="easy",
        )

    def check_buy(self, df: pd.DataFrame, current_price: float) -> Signal:
        if len(df) < self._long_period + 1:
            return Signal("hold", 0.0, "데이터 부족")

        short_ma = df["close"].rolling(self._short_period).mean()
        long_ma = df["close"].rolling(self._long_period).mean()

        # 현재: 단기 > 장기, 이전: 단기 <= 장기 → 골든크로스
        current_cross = short_ma.iloc[-1] > long_ma.iloc[-1]
        previous_cross = short_ma.iloc[-2] > long_ma.iloc[-2]

        if current_cross and not previous_cross:
            gap_pct = (short_ma.iloc[-1] - long_ma.iloc[-1]) / long_ma.iloc[-1] * 100
            confidence = min(abs(gap_pct) / 2, 1.0)
            return Signal(
                "buy",
                round(confidence, 3),
                f"골든크로스 MA({self._short_period}/{self._long_period})",
                stop_loss=round(current_price * (1 + self.params.stop_loss_pct / 100), 2),
            )

        return Signal("hold", 0.0, "교차 없음")

    def check_sell(self, df: pd.DataFrame, current_price: float, buy_price: float) -> Signal:
        # 공통 손절/트레일링 체크
        stop_signal = self.check_trailing_stop(current_price, buy_price)
        if stop_signal:
            return stop_signal

        if len(df) < self._long_period + 1:
            return Signal("hold", 0.0, "데이터 부족")

        short_ma = df["close"].rolling(self._short_period).mean()
        long_ma = df["close"].rolling(self._long_period).mean()

        # 데드크로스
        current_cross = short_ma.iloc[-1] < long_ma.iloc[-1]
        previous_cross = short_ma.iloc[-2] < long_ma.iloc[-2]

        if current_cross and not previous_cross:
            return Signal("sell", 0.7, f"데드크로스 MA({self._short_period}/{self._long_period})")

        return Signal("hold", 0.0, "보유 유지")
