"""슈퍼트렌드 전략.

ATR 기반 동적 지지/저항선으로 추세 방향 판단.
가격이 슈퍼트렌드 라인 위면 상승, 아래면 하락.
변동성 적응형이라 코인에 적합.
"""

import numpy as np
import pandas as pd

from cryptobot.strategies.base import BaseStrategy, Signal, StrategyInfo, StrategyParams


def _calculate_supertrend(df: pd.DataFrame, period: int = 10, multiplier: float = 3.0) -> pd.DataFrame:
    """슈퍼트렌드 계산."""
    high = df["high"]
    low = df["low"]
    close = df["close"]

    # ATR 계산
    prev_close = close.shift(1)
    tr = pd.concat([high - low, (high - prev_close).abs(), (low - prev_close).abs()], axis=1).max(axis=1)
    atr = tr.rolling(window=period).mean()

    # 기본 밴드
    hl2 = (high + low) / 2
    upper_band = hl2 + multiplier * atr
    lower_band = hl2 - multiplier * atr

    supertrend = pd.Series(np.nan, index=df.index)
    direction = pd.Series(1, index=df.index)  # 1=상승, -1=하락

    for i in range(period, len(df)):
        if close.iloc[i] > upper_band.iloc[i - 1]:
            direction.iloc[i] = 1
        elif close.iloc[i] < lower_band.iloc[i - 1]:
            direction.iloc[i] = -1
        else:
            direction.iloc[i] = direction.iloc[i - 1]

        if direction.iloc[i] == 1:
            supertrend.iloc[i] = lower_band.iloc[i]
        else:
            supertrend.iloc[i] = upper_band.iloc[i]

    return pd.DataFrame({"supertrend": supertrend, "direction": direction})


class Supertrend(BaseStrategy):
    """슈퍼트렌드 전략."""

    def __init__(self, params: StrategyParams | None = None) -> None:
        super().__init__(params)
        self._period = self.params.extra.get("st_period", 10)
        self._multiplier = self.params.extra.get("st_multiplier", 3.0)

    def info(self) -> StrategyInfo:
        return StrategyInfo(
            name="supertrend",
            display_name="슈퍼트렌드",
            description=f"ATR({self._period}) × {self._multiplier} 기반 동적 추세 추종.",
            market_states=["bullish", "bearish"],
            timeframe="1d",
            difficulty="medium",
        )

    def check_buy(self, df: pd.DataFrame, current_price: float) -> Signal:
        if len(df) < self._period + 2:
            return Signal("hold", 0.0, "데이터 부족")

        st = _calculate_supertrend(df, self._period, self._multiplier)

        # 방향 전환: 하락 → 상승
        curr_dir = st["direction"].iloc[-1]
        prev_dir = st["direction"].iloc[-2]

        if curr_dir == 1 and prev_dir == -1:
            return Signal(
                "buy",
                0.75,
                "슈퍼트렌드 상승 전환",
                trigger_value=round(st["supertrend"].iloc[-1], 2),
                stop_loss=round(st["supertrend"].iloc[-1], 2),
            )

        return Signal("hold", 0.0, f"추세 방향: {'상승' if curr_dir == 1 else '하락'}")

    def check_sell(self, df: pd.DataFrame, current_price: float, buy_price: float) -> Signal:
        stop_signal = self.check_trailing_stop(current_price, buy_price)
        if stop_signal:
            return stop_signal

        if len(df) < self._period + 2:
            return Signal("hold", 0.0, "데이터 부족")

        st = _calculate_supertrend(df, self._period, self._multiplier)

        # 방향 전환: 상승 → 하락
        curr_dir = st["direction"].iloc[-1]
        prev_dir = st["direction"].iloc[-2]

        if curr_dir == -1 and prev_dir == 1:
            return Signal("sell", 0.8, "슈퍼트렌드 하락 전환")

        return Signal("hold", 0.0, "보유 유지")
