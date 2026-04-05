"""전략 베이스 클래스.

NestJS의 interface/abstract class와 동일한 역할.
모든 매매 전략은 이 클래스를 상속해서 구현한다.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field

import pandas as pd


@dataclass
class Signal:
    """매매 신호. 모든 전략이 공통으로 반환하는 결과."""

    signal_type: str  # "buy" / "sell" / "hold"
    confidence: float  # 0.0 ~ 1.0
    reason: str  # 신호 발생 사유
    trigger_value: float | None = None  # 돌파 기준가 등
    stop_loss: float | None = None  # 이 신호에 대한 권장 손절가
    take_profit: float | None = None  # 이 신호에 대한 권장 익절가


@dataclass
class StrategyInfo:
    """전략 메타 정보."""

    name: str  # 전략 식별자 (예: "volatility_breakout")
    display_name: str  # 화면 표시명 (예: "변동성 돌파")
    description: str  # 전략 설명
    market_states: list[str]  # 적합한 시장 상태 ["bullish", "sideways", "bearish"]
    timeframe: str  # 권장 타임프레임 ("1m", "5m", "1h", "1d")
    difficulty: str  # 구현 난이도 ("easy", "medium", "hard")


@dataclass
class StrategyParams:
    """전략 공통 파라미터."""

    stop_loss_pct: float = -5.0  # 손절률 (%)
    trailing_stop_pct: float = -3.0  # 트레일링 스탑 (%)
    position_size_pct: float = 100.0  # 포지션 크기 (잔고 대비 %)
    extra: dict = field(default_factory=dict)  # 전략별 추가 파라미터

    # 시간 기반 ROI 테이블: {보유 분: 최소 수익%}
    # 보유 시간이 길어질수록 목표 수익을 낮춤
    roi_table: dict = field(default_factory=lambda: {
        10: 3.0,    # 10분 내 +3% 이상이면 매도
        30: 2.0,    # 30분 내 +2%
        60: 1.0,    # 60분 내 +1%
        120: 0.15,  # 120분 내 +0.15% (수수료 이상이면 탈출)
    })


class BaseStrategy(ABC):
    """매매 전략 베이스 클래스.

    NestJS의 abstract class + interface와 동일.
    모든 전략은 이 클래스를 상속하고 아래 메서드를 구현해야 한다.
    """

    def __init__(self, params: StrategyParams | None = None) -> None:
        self.params = params or StrategyParams()
        self._highest_price: float | None = None  # 트레일링 스탑용
        self._hold_minutes: int = 0  # 보유 시간 (main.py에서 설정)

    @abstractmethod
    def info(self) -> StrategyInfo:
        """전략 메타 정보 반환."""

    @abstractmethod
    def check_buy(self, df: pd.DataFrame, current_price: float) -> Signal:
        """매수 신호 판단.

        Args:
            df: OHLCV DataFrame (최근 N일 봉 데이터)
            current_price: 현재가

        Returns:
            매수 신호 또는 hold
        """

    @abstractmethod
    def check_sell(self, df: pd.DataFrame, current_price: float, buy_price: float) -> Signal:
        """매도 신호 판단.

        Args:
            df: OHLCV DataFrame
            current_price: 현재가
            buy_price: 매수가

        Returns:
            매도 신호 또는 hold
        """

    # 업비트 수수료: 매수 0.05% + 매도 0.05% = 왕복 0.1% + 슬리피지 마진
    ROUND_TRIP_FEE_PCT = 0.15

    def check_trailing_stop(self, current_price: float, buy_price: float, hold_minutes: int | None = None) -> Signal | None:
        """공통 트레일링 스탑 + 손절 + ROI + 수수료 가드."""
        # 최고가 갱신
        if self._highest_price is None or current_price > self._highest_price:
            self._highest_price = current_price

        pnl_pct = (current_price - buy_price) / buy_price * 100

        # 손절 — 무조건 실행 (수수료 무시)
        if pnl_pct <= self.params.stop_loss_pct:
            return Signal("sell", 1.0, "손절", trigger_value=round(pnl_pct, 2))

        # 시간 기반 ROI — 보유 시간별 최소 수익 도달 시 매도
        hold_minutes = hold_minutes if hold_minutes is not None else self._hold_minutes
        if hold_minutes > 0 and self.params.roi_table:
            for minutes, min_roi in sorted(self.params.roi_table.items()):
                if hold_minutes >= minutes and pnl_pct >= min_roi and pnl_pct > self.ROUND_TRIP_FEE_PCT:
                    return Signal(
                        "sell", 0.9,
                        f"ROI 도달 ({hold_minutes}분 보유, +{pnl_pct:.2f}% >= {min_roi}%)",
                        trigger_value=round(pnl_pct, 2),
                    )

        # 트레일링 스탑
        drop_pct = (current_price - self._highest_price) / self._highest_price * 100
        if drop_pct <= self.params.trailing_stop_pct:
            if pnl_pct > self.ROUND_TRIP_FEE_PCT:
                return Signal("sell", 0.8, f"트레일링 스탑 (익절 {pnl_pct:+.2f}%)", trigger_value=round(drop_pct, 2))
            return None

        return None

    def reset(self) -> None:
        """포지션 종료 시 내부 상태 초기화."""
        self._highest_price = None
