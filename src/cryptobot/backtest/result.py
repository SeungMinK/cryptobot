"""백테스트 결과 데이터 구조."""

import math
from dataclasses import dataclass, field


@dataclass
class Trade:
    """개별 거래 기록."""

    coin: str
    entry_date: str
    exit_date: str
    entry_price: float
    exit_price: float
    pnl_pct: float  # 총 가격변동 %
    net_pnl_pct: float  # 수수료 차감 후
    hold_days: int
    entry_reason: str
    exit_reason: str


@dataclass
class BacktestResult:
    """백테스트 결과 요약.

    Args:
        strategy_name: 전략 식별자
        coin: 종목 코드
        params: 전략 파라미터 dict
        period: 테스트 기간 문자열
        trades: 거래 목록
    """

    strategy_name: str
    coin: str
    params: dict
    period: str
    trades: list[Trade]

    # __post_init__에서 계산되는 통계
    total_return_pct: float = field(init=False)
    win_rate: float = field(init=False)
    num_trades: int = field(init=False)
    avg_profit_pct: float = field(init=False)
    avg_loss_pct: float = field(init=False)
    max_drawdown_pct: float = field(init=False)
    sharpe_ratio: float = field(init=False)
    best_trade_pct: float = field(init=False)
    worst_trade_pct: float = field(init=False)

    def __post_init__(self) -> None:
        self.num_trades = len(self.trades)

        if self.num_trades == 0:
            self.total_return_pct = 0.0
            self.win_rate = 0.0
            self.avg_profit_pct = 0.0
            self.avg_loss_pct = 0.0
            self.max_drawdown_pct = 0.0
            self.sharpe_ratio = 0.0
            self.best_trade_pct = 0.0
            self.worst_trade_pct = 0.0
            return

        pnls = [t.net_pnl_pct for t in self.trades]

        # 복리 수익률
        cumulative = 1.0
        for p in pnls:
            cumulative *= 1 + p / 100
        self.total_return_pct = round((cumulative - 1) * 100, 2)

        # 승률
        wins = [p for p in pnls if p > 0]
        losses = [p for p in pnls if p <= 0]
        self.win_rate = round(len(wins) / self.num_trades * 100, 1)

        # 평균 수익/손실
        self.avg_profit_pct = round(sum(wins) / len(wins), 2) if wins else 0.0
        self.avg_loss_pct = round(sum(losses) / len(losses), 2) if losses else 0.0

        # 최대 낙폭 (누적 수익 곡선 기준)
        self.max_drawdown_pct = self._calc_max_drawdown(pnls)

        # 샤프 비율 (일별 수익률 기준)
        self.sharpe_ratio = self._calc_sharpe(pnls)

        # 최고/최저 거래
        self.best_trade_pct = round(max(pnls), 2)
        self.worst_trade_pct = round(min(pnls), 2)

    @staticmethod
    def _calc_max_drawdown(pnls: list[float]) -> float:
        """누적 수익 곡선의 고점 대비 최대 하락률 계산."""
        cumulative = 1.0
        peak = 1.0
        max_dd = 0.0

        for p in pnls:
            cumulative *= 1 + p / 100
            if cumulative > peak:
                peak = cumulative
            dd = (cumulative - peak) / peak * 100
            if dd < max_dd:
                max_dd = dd

        return round(max_dd, 2)

    @staticmethod
    def _calc_sharpe(pnls: list[float]) -> float:
        """샤프 비율 계산 (연율화).

        거래별 수익률을 일별 수익률로 간주하여 계산.
        """
        if len(pnls) < 2:
            return 0.0

        mean_r = sum(pnls) / len(pnls)
        variance = sum((p - mean_r) ** 2 for p in pnls) / (len(pnls) - 1)
        std_r = math.sqrt(variance)

        if std_r == 0:
            return 0.0

        return round(mean_r / std_r * math.sqrt(365), 2)
