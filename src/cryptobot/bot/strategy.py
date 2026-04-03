"""변동성 돌파 전략 엔진.

NestJS의 핵심 비즈니스 로직 Service와 동일한 역할.
시장 데이터를 받아서 매수/매도 신호를 판단한다.
"""

import logging
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class Signal:
    """매매 신호."""

    signal_type: str  # "buy_signal" / "sell_signal" / "hold"
    confidence: float  # 0.0 ~ 1.0
    trigger_reason: str  # 신호 발생 사유
    trigger_value: float | None = None  # 돌파 기준가 등
    target_price: float | None = None


@dataclass
class StrategyParams:
    """전략 파라미터. DB strategy_params 테이블에서 로딩."""

    k_value: float = 0.5
    stop_loss_pct: float = -5.0
    trailing_stop_pct: float = -3.0
    max_positions: int = 1
    position_size_pct: float = 100.0
    allow_trading: bool = True
    market_state: str = "sideways"
    aggression: float = 0.5


class VolatilityBreakoutStrategy:
    """변동성 돌파 전략.

    매수: 현재가 > 당일시가 + (전일고가 - 전일저가) × K
    매도: 트레일링 스탑 또는 손절
    """

    def __init__(self, params: StrategyParams) -> None:
        self.params = params
        self._highest_price: float | None = None  # 매수 이후 최고가 (트레일링 스탑용)

    def update_params(self, params: StrategyParams) -> None:
        """LLM 등으로 파라미터가 변경될 때 호출."""
        self.params = params
        logger.info(
            "전략 파라미터 업데이트: K=%.2f, 손절=%.1f%%, 트레일링=%.1f%%",
            params.k_value,
            params.stop_loss_pct,
            params.trailing_stop_pct,
        )

    def check_buy_signal(
        self,
        current_price: float,
        today_open: float,
        yesterday_high: float,
        yesterday_low: float,
    ) -> Signal:
        """변동성 돌파 매수 신호 판단.

        Args:
            current_price: 현재가
            today_open: 당일 시가
            yesterday_high: 전일 고가
            yesterday_low: 전일 저가

        Returns:
            매수 신호 또는 hold
        """
        if not self.params.allow_trading:
            return Signal("hold", 0.0, "매매 중단 상태")

        if self.params.market_state == "bearish":
            return Signal("hold", 0.0, "하락장 — 매매 중단")

        price_range = yesterday_high - yesterday_low
        breakout_price = today_open + price_range * self.params.k_value

        if current_price > breakout_price:
            confidence = min((current_price - breakout_price) / price_range, 1.0)
            if self.params.market_state == "sideways":
                confidence *= 0.7  # 횡보장에서는 신뢰도 낮춤
            return Signal(
                signal_type="buy_signal",
                confidence=round(confidence, 3),
                trigger_reason="변동성 돌파",
                trigger_value=round(breakout_price, 2),
                target_price=round(breakout_price, 2),
            )

        return Signal("hold", 0.0, "돌파 미달", trigger_value=round(breakout_price, 2))

    def check_sell_signal(self, current_price: float, buy_price: float) -> Signal:
        """매도 신호 판단 (트레일링 스탑 + 손절).

        Args:
            current_price: 현재가
            buy_price: 매수가

        Returns:
            매도 신호 또는 hold
        """
        # 최고가 갱신
        if self._highest_price is None or current_price > self._highest_price:
            self._highest_price = current_price

        # 손절 체크: 매수가 대비 stop_loss_pct 이상 하락
        loss_pct = (current_price - buy_price) / buy_price * 100
        if loss_pct <= self.params.stop_loss_pct:
            return Signal(
                signal_type="sell_signal",
                confidence=1.0,
                trigger_reason="손절",
                trigger_value=round(loss_pct, 2),
            )

        # 트레일링 스탑 체크: 최고가 대비 trailing_stop_pct 이상 하락
        drop_from_high = (current_price - self._highest_price) / self._highest_price * 100
        if drop_from_high <= self.params.trailing_stop_pct:
            return Signal(
                signal_type="sell_signal",
                confidence=0.8,
                trigger_reason="트레일링 스탑",
                trigger_value=round(drop_from_high, 2),
            )

        return Signal("hold", 0.0, "보유 유지")

    def reset_position(self) -> None:
        """포지션 종료 시 내부 상태 초기화."""
        self._highest_price = None


def determine_market_state(ma_5: float | None, ma_20: float | None) -> str:
    """MA(5)와 MA(20) 비교로 시장 상태 판단.

    Args:
        ma_5: 5일 이동평균
        ma_20: 20일 이동평균

    Returns:
        "bullish" / "bearish" / "sideways"
    """
    if ma_5 is None or ma_20 is None:
        return "sideways"

    diff_pct = (ma_5 - ma_20) / ma_20 * 100

    if diff_pct > 1.0:
        return "bullish"
    elif diff_pct < -1.0:
        return "bearish"
    return "sideways"
