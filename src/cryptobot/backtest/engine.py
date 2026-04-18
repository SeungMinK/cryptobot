"""백테스트 시뮬레이션 엔진.

전략 인스턴스의 check_buy/check_sell을 직접 호출하여
라이브 봇과 동일한 로직으로 시뮬레이션한다.
"""

import logging
import sqlite3

import pandas as pd

from cryptobot.backtest.result import BacktestResult, Trade
from cryptobot.strategies.base import BaseStrategy

logger = logging.getLogger(__name__)

# 업비트 매수/매도 수수료 (편도)
DEFAULT_FEE_RATE = 0.0005

# 지표 계산용 최소 데이터 행 수
MIN_WARMUP_ROWS = 20


class BacktestEngine:
    """OHLCV 일봉 데이터로 전략을 시뮬레이션한다.

    Args:
        strategy: 매매 전략 인스턴스
        df: OHLCV DataFrame (date, open, high, low, close, volume)
        coin: 종목 코드 (예: "KRW-BTC")
        fee_rate: 편도 수수료율 (기본 0.05%)
    """

    def __init__(
        self,
        strategy: BaseStrategy,
        df: pd.DataFrame,
        coin: str,
        fee_rate: float = DEFAULT_FEE_RATE,
    ) -> None:
        self.strategy = strategy
        self.df = df.reset_index(drop=True)
        self.coin = coin
        self.fee_rate = fee_rate
        self.round_trip_fee_pct = fee_rate * 2 * 100  # 왕복 수수료 %

    @classmethod
    def from_db(
        cls,
        db_path: str,
        coin: str,
        strategy: BaseStrategy,
        fee_rate: float = DEFAULT_FEE_RATE,
    ) -> "BacktestEngine":
        """SQLite DB에서 OHLCV 데이터를 로드하여 엔진 생성.

        Args:
            db_path: SQLite 파일 경로
            coin: 종목 코드
            strategy: 전략 인스턴스
            fee_rate: 편도 수수료율

        Returns:
            BacktestEngine 인스턴스
        """
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        df = pd.read_sql_query(
            "SELECT date, open, high, low, close, volume FROM ohlcv_daily WHERE coin = ? ORDER BY date ASC",
            conn,
            params=(coin,),
        )
        conn.close()

        if df.empty:
            raise ValueError(f"DB에 {coin}의 ohlcv_daily 데이터가 없습니다: {db_path}")

        logger.info("DB에서 %s 일봉 %d건 로드 (%s ~ %s)", coin, len(df), df["date"].iloc[0], df["date"].iloc[-1])
        return cls(strategy=strategy, df=df, coin=coin, fee_rate=fee_rate)

    def run(self) -> BacktestResult:
        """시뮬레이션 실행.

        Returns:
            BacktestResult 통계 및 거래 목록
        """
        trades: list[Trade] = []
        df = self.df
        n = len(df)

        # 포지션 상태
        in_position = False
        entry_price = 0.0
        entry_date = ""
        entry_reason = ""

        for i in range(MIN_WARMUP_ROWS, n):
            current_price = df.iloc[i]["close"]
            current_date = str(df.iloc[i]["date"])
            window = df.iloc[: i + 1]

            if not in_position:
                signal = self.strategy.check_buy(window, current_price)
                if signal.signal_type == "buy":
                    in_position = True
                    entry_price = current_price
                    entry_date = current_date
                    entry_reason = signal.reason
                    self.strategy._highest_price = current_price
            else:
                # 보유 일수 → 분 변환 후 전략에 설정
                days_held = i - self._entry_index
                self.strategy._hold_minutes = days_held * 1440

                signal = self.strategy.check_sell(window, current_price, entry_price)
                if signal.signal_type == "sell":
                    trade = self._make_trade(
                        entry_date,
                        current_date,
                        entry_price,
                        current_price,
                        days_held,
                        entry_reason,
                        signal.reason,
                    )
                    trades.append(trade)
                    self.strategy.reset()
                    in_position = False

            # entry_index 기록 (포지션 진입 시점)
            if in_position and entry_date == current_date:
                self._entry_index = i

        # 미청산 포지션 강제 청산
        if in_position:
            last_price = df.iloc[-1]["close"]
            last_date = str(df.iloc[-1]["date"])
            days_held = (n - 1) - self._entry_index
            trade = self._make_trade(
                entry_date,
                last_date,
                entry_price,
                last_price,
                days_held,
                entry_reason,
                "백테스트 종료 (강제 청산)",
            )
            trades.append(trade)
            self.strategy.reset()

        period = f"{df['date'].iloc[0]} ~ {df['date'].iloc[-1]}"
        params_dict = {
            "stop_loss_pct": self.strategy.params.stop_loss_pct,
            "trailing_stop_pct": self.strategy.params.trailing_stop_pct,
            **self.strategy.params.extra,
        }

        return BacktestResult(
            strategy_name=self.strategy.info().name,
            coin=self.coin,
            params=params_dict,
            period=period,
            trades=trades,
        )

    def _make_trade(
        self,
        entry_date: str,
        exit_date: str,
        entry_price: float,
        exit_price: float,
        hold_days: int,
        entry_reason: str,
        exit_reason: str,
    ) -> Trade:
        """Trade 데이터클래스 생성."""
        pnl_pct = (exit_price - entry_price) / entry_price * 100
        net_pnl_pct = pnl_pct - self.round_trip_fee_pct

        return Trade(
            coin=self.coin,
            entry_date=entry_date,
            exit_date=exit_date,
            entry_price=round(entry_price, 2),
            exit_price=round(exit_price, 2),
            pnl_pct=round(pnl_pct, 2),
            net_pnl_pct=round(net_pnl_pct, 2),
            hold_days=hold_days,
            entry_reason=entry_reason,
            exit_reason=exit_reason,
        )
