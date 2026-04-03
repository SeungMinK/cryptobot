"""볼린저 밴드 스퀴즈 전략.

밴드 폭이 극도로 좁아진(스퀴즈) 후 폭발적 움직임 포착.
횡보 → 추세 전환 구간에서 효과적.
"""

import pandas as pd

from cryptobot.strategies.base import BaseStrategy, Signal, StrategyInfo, StrategyParams


class BollingerSqueeze(BaseStrategy):
    """볼린저 밴드 스퀴즈 전략."""

    def __init__(self, params: StrategyParams | None = None) -> None:
        super().__init__(params)
        self._bb_period = self.params.extra.get("bb_period", 20)
        self._bb_std = self.params.extra.get("bb_std", 2.0)
        self._squeeze_lookback = self.params.extra.get("squeeze_lookback", 120)  # 스퀴즈 판단 기간

    def info(self) -> StrategyInfo:
        return StrategyInfo(
            name="bollinger_squeeze",
            display_name="볼린저 스퀴즈",
            description="밴드 폭 최소 수축 후 상방 돌파 시 매수. 변동성 폭발 포착.",
            market_states=["sideways", "bullish"],
            timeframe="1d",
            difficulty="medium",
        )

    def _calc_bandwidth(self, close: pd.Series) -> pd.Series:
        """밴드 폭 (Bandwidth) 계산."""
        middle = close.rolling(self._bb_period).mean()
        std = close.rolling(self._bb_period).std()
        upper = middle + self._bb_std * std
        lower = middle - self._bb_std * std
        return (upper - lower) / middle * 100  # % 기준

    def check_buy(self, df: pd.DataFrame, current_price: float) -> Signal:
        min_data = max(self._bb_period, self._squeeze_lookback) + 2
        if len(df) < min_data:
            return Signal("hold", 0.0, "데이터 부족")

        close = df["close"]
        bandwidth = self._calc_bandwidth(close)

        # 스퀴즈 감지: 현재 밴드 폭이 최근 N일 중 최소 수준인지
        recent_bw = bandwidth.iloc[-self._squeeze_lookback :]
        current_bw = bandwidth.iloc[-1]
        min_bw = recent_bw.min()
        prev_bw = bandwidth.iloc[-2]

        is_squeeze = current_bw <= min_bw * 1.1  # 최소 대비 10% 이내

        if not is_squeeze:
            return Signal("hold", 0.0, "스퀴즈 아님")

        # 스퀴즈 상태에서 상방 돌파 확인
        middle = close.rolling(self._bb_period).mean()
        std = close.rolling(self._bb_period).std()
        upper = middle + self._bb_std * std

        if current_price > upper.iloc[-1] and prev_bw <= current_bw:
            # 밴드가 확장되기 시작하면서 상방 돌파
            return Signal(
                "buy",
                0.75,
                f"스퀴즈 후 상방 돌파 (밴드폭 {current_bw:.2f}%)",
                trigger_value=round(upper.iloc[-1], 2),
                stop_loss=round(middle.iloc[-1], 2),
            )

        return Signal("hold", 0.0, f"스퀴즈 감지 — 돌파 대기 (밴드폭 {current_bw:.2f}%)")

    def check_sell(self, df: pd.DataFrame, current_price: float, buy_price: float) -> Signal:
        stop_signal = self.check_trailing_stop(current_price, buy_price)
        if stop_signal:
            return stop_signal

        if len(df) < self._bb_period + 2:
            return Signal("hold", 0.0, "데이터 부족")

        close = df["close"]
        bandwidth = self._calc_bandwidth(close)

        # 모멘텀 약화: 밴드가 다시 수축하기 시작
        if bandwidth.iloc[-1] < bandwidth.iloc[-2] < bandwidth.iloc[-3]:
            profit_pct = (current_price - buy_price) / buy_price * 100
            if profit_pct > 0:
                return Signal("sell", 0.6, f"모멘텀 약화 — 밴드 재수축 (+{profit_pct:.1f}%)")

        return Signal("hold", 0.0, "보유 유지")
