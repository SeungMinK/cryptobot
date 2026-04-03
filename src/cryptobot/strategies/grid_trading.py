"""그리드 트레이딩 전략.

가격 범위를 격자로 나누고, 각 격자마다 매수/매도를 반복.
추세 예측 없이 횡보장에서 꾸준한 수익.
"""

import logging

import pandas as pd

from cryptobot.strategies.base import BaseStrategy, Signal, StrategyInfo, StrategyParams

logger = logging.getLogger(__name__)


class GridTrading(BaseStrategy):
    """그리드 트레이딩 전략."""

    def __init__(self, params: StrategyParams | None = None) -> None:
        super().__init__(params)
        self._grid_count = self.params.extra.get("grid_count", 10)  # 격자 수
        self._range_pct = self.params.extra.get("range_pct", 10.0)  # 범위 (중심가 대비 ±%)
        self._center_price: float | None = None
        self._grids: list[float] = []
        self._last_grid_index: int | None = None

    def info(self) -> StrategyInfo:
        return StrategyInfo(
            name="grid_trading",
            display_name="그리드 트레이딩",
            description=f"가격 범위 ±{self._range_pct}%를 {self._grid_count}개 격자로 분할 매수/매도.",
            market_states=["sideways"],
            timeframe="1h",
            difficulty="medium",
        )

    def _setup_grids(self, center_price: float) -> None:
        """격자 설정."""
        self._center_price = center_price
        lower = center_price * (1 - self._range_pct / 100)
        upper = center_price * (1 + self._range_pct / 100)
        step = (upper - lower) / self._grid_count

        self._grids = [round(lower + step * i, 2) for i in range(self._grid_count + 1)]
        logger.info("그리드 설정: %s ~ %s (%d개)", f"{lower:,.0f}", f"{upper:,.0f}", self._grid_count)

    def _find_grid_index(self, price: float) -> int:
        """가격이 속한 격자 인덱스 반환."""
        for i in range(len(self._grids) - 1):
            if self._grids[i] <= price < self._grids[i + 1]:
                return i
        if price >= self._grids[-1]:
            return len(self._grids) - 2
        return 0

    def check_buy(self, df: pd.DataFrame, current_price: float) -> Signal:
        if len(df) < 20:
            return Signal("hold", 0.0, "데이터 부족")

        # 격자 미설정 시 초기화
        if not self._grids:
            center = df["close"].iloc[-20:].mean()
            self._setup_grids(center)

        current_index = self._find_grid_index(current_price)

        # 격자 범위 이탈 체크
        if current_price < self._grids[0]:
            return Signal("hold", 0.0, "그리드 하한 이탈 — 매수 보류")

        # 이전보다 낮은 격자로 이동 → 매수 신호
        if self._last_grid_index is not None and current_index < self._last_grid_index:
            self._last_grid_index = current_index
            grid_price = self._grids[current_index]
            return Signal(
                "buy",
                0.6,
                f"그리드 #{current_index} 하향 ({grid_price:,.0f}원)",
                trigger_value=grid_price,
                take_profit=self._grids[current_index + 1] if current_index + 1 < len(self._grids) else None,
            )

        self._last_grid_index = current_index
        return Signal("hold", 0.0, f"그리드 #{current_index} 대기")

    def check_sell(self, df: pd.DataFrame, current_price: float, buy_price: float) -> Signal:
        stop_signal = self.check_trailing_stop(current_price, buy_price)
        if stop_signal:
            return stop_signal

        if not self._grids:
            return Signal("hold", 0.0, "그리드 미설정")

        # 그리드 범위 상한 이탈 → 익절
        if current_price > self._grids[-1]:
            return Signal("sell", 0.8, "그리드 상한 돌파 — 익절")

        # 매수 격자보다 한 칸 이상 위로 이동 → 익절
        buy_index = self._find_grid_index(buy_price)
        current_index = self._find_grid_index(current_price)

        if current_index > buy_index:
            profit_pct = (current_price - buy_price) / buy_price * 100
            return Signal(
                "sell",
                0.6,
                f"그리드 익절 #{buy_index}→#{current_index} (+{profit_pct:.1f}%)",
            )

        return Signal("hold", 0.0, "보유 유지")

    def reset(self) -> None:
        """포지션 + 그리드 상태 초기화."""
        super().reset()
        self._last_grid_index = None
