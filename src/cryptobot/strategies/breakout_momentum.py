"""브레이크아웃 모멘텀 전략 (Donchian Channel).

N일 최고가를 돌파하면 매수, M일 최저가를 하향 돌파하면 매도.
터틀 트레이딩의 핵심 전략. 추세 시작을 포착.
"""

import pandas as pd

from cryptobot.strategies.base import BaseStrategy, Signal, StrategyInfo, StrategyParams


class BreakoutMomentum(BaseStrategy):
    """브레이크아웃 모멘텀 전략."""

    def __init__(self, params: StrategyParams | None = None) -> None:
        super().__init__(params)
        self._entry_period = self.params.extra.get("entry_period", 20)  # 매수 돌파 기간
        self._exit_period = self.params.extra.get("exit_period", 10)  # 매도 이탈 기간
        self._volume_filter = self.params.extra.get("volume_filter", True)

    def info(self) -> StrategyInfo:
        return StrategyInfo(
            name="breakout_momentum",
            display_name="브레이크아웃 모멘텀",
            description=f"{self._entry_period}일 최고가 돌파 매수, {self._exit_period}일 최저가 이탈 매도.",
            market_states=["bullish", "sideways"],
            timeframe="1d",
            difficulty="easy",
        )

    def check_buy(self, df: pd.DataFrame, current_price: float) -> Signal:
        if len(df) < self._entry_period + 1:
            return Signal("hold", 0.0, "데이터 부족")

        # N일 최고가 (당일 제외)
        lookback = df.iloc[-(self._entry_period + 1) : -1]
        channel_high = lookback["high"].max()

        if current_price > channel_high:
            # 거래량 필터: 당일 거래량이 평균 이상인지
            confidence = 0.6
            if self._volume_filter and "volume" in df.columns:
                avg_volume = lookback["volume"].mean()
                today_volume = df["volume"].iloc[-1]
                if today_volume > avg_volume * 1.5:
                    confidence = 0.85  # 거래량 동반 돌파 → 높은 신뢰도
                elif today_volume > avg_volume:
                    confidence = 0.7

            return Signal(
                "buy",
                confidence,
                f"{self._entry_period}일 최고가 돌파",
                trigger_value=round(channel_high, 2),
                stop_loss=round(lookback["low"].min(), 2),
            )

        return Signal("hold", 0.0, "돌파 미달", trigger_value=round(channel_high, 2))

    def check_sell(self, df: pd.DataFrame, current_price: float, buy_price: float) -> Signal:
        stop_signal = self.check_trailing_stop(current_price, buy_price)
        if stop_signal:
            return stop_signal

        if len(df) < self._exit_period + 1:
            return Signal("hold", 0.0, "데이터 부족")

        # M일 최저가 (당일 제외)
        lookback = df.iloc[-(self._exit_period + 1) : -1]
        channel_low = lookback["low"].min()

        if current_price < channel_low:
            return Signal(
                "sell",
                0.75,
                f"{self._exit_period}일 최저가 이탈",
                trigger_value=round(channel_low, 2),
            )

        return Signal("hold", 0.0, "보유 유지")
