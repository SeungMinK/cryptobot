"""변동성 돌파 전략 (래리 윌리엄스).

시가 + 전일 레인지 × K를 돌파하면 매수.
한국 코인 트레이딩에서 가장 인기 있는 전략.
"""

import pandas as pd

from cryptobot.strategies.base import BaseStrategy, Signal, StrategyInfo, StrategyParams


class VolatilityBreakout(BaseStrategy):
    """변동성 돌파 전략."""

    def __init__(self, params: StrategyParams | None = None) -> None:
        super().__init__(params)
        self._k = self.params.extra.get("k_value", 0.5)

    def info(self) -> StrategyInfo:
        return StrategyInfo(
            name="volatility_breakout",
            display_name="변동성 돌파",
            description="시가 + 전일 변동폭 × K 돌파 시 매수. 일중 단기 전략.",
            market_states=["bullish"],
            timeframe="1d",
            difficulty="easy",
        )

    def check_buy(self, df: pd.DataFrame, current_price: float) -> Signal:
        if len(df) < 2:
            return Signal("hold", 0.0, "데이터 부족")

        today = df.iloc[-1]
        yesterday = df.iloc[-2]

        price_range = yesterday["high"] - yesterday["low"]
        breakout_price = today["open"] + price_range * self._k

        if current_price > breakout_price:
            confidence = min((current_price - breakout_price) / price_range, 1.0) if price_range > 0 else 0.5
            return Signal(
                "buy",
                round(confidence, 3),
                f"변동성 돌파 (K={self._k})",
                trigger_value=round(breakout_price, 2),
                stop_loss=round(current_price * (1 + self.params.stop_loss_pct / 100), 2),
            )

        return Signal("hold", 0.0, "돌파 미달", trigger_value=round(breakout_price, 2))

    def check_sell(self, df: pd.DataFrame, current_price: float, buy_price: float) -> Signal:
        # 공통 트레일링 스탑/손절 체크
        stop_signal = self.check_trailing_stop(current_price, buy_price)
        if stop_signal:
            return stop_signal

        return Signal("hold", 0.0, "보유 유지")
