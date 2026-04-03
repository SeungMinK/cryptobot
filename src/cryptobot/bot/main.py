"""CryptoBot 메인 루프.

NestJS의 main.ts (bootstrap) + AppModule과 동일한 역할.
스케줄러를 초기화하고, 1분마다 데이터 수집 + 매매 판단을 실행한다.

사용법:
    python -m cryptobot.bot.main
"""

import logging
import signal
import sys
from datetime import datetime

from apscheduler.schedulers.blocking import BlockingScheduler

from cryptobot.bot.config import config
from cryptobot.bot.strategy import StrategyParams, VolatilityBreakoutStrategy
from cryptobot.bot.trader import Trader
from cryptobot.data.collector import DataCollector
from cryptobot.data.database import Database
from cryptobot.data.recorder import DataRecorder
from cryptobot.notifier.slack import SlackNotifier

logger = logging.getLogger(__name__)


class CryptoBot:
    """메인 봇 클래스. NestJS의 AppModule 역할."""

    def __init__(self) -> None:
        # 모듈 초기화 — NestJS의 imports와 동일
        self._db = Database(config.bot.db_path)
        self._db.initialize()

        self._trader = Trader()
        self._collector = DataCollector(self._db, config.bot.coin)
        self._recorder = DataRecorder(self._db)
        self._notifier = SlackNotifier()

        # 전략 파라미터 로딩
        params = self._load_strategy_params()
        self._strategy = VolatilityBreakoutStrategy(params)

        self._scheduler = BlockingScheduler()

    def start(self) -> None:
        """봇 시작."""
        logger.info("=== CryptoBot 시작 ===")
        logger.info("종목: %s", config.bot.coin)
        logger.info("API Key 설정: %s", "O" if self._trader.is_ready else "X")
        logger.info("Slack 설정: %s", "O" if self._notifier.is_configured else "X")
        logger.info("DB: %s", config.bot.db_path)

        self._notifier.notify_bot_status("시작됨")

        # 봇 시작 시 안전 장치
        self._safety_check()

        # 스케줄 등록 — NestJS의 @Cron() 데코레이터와 동일
        self._scheduler.add_job(self._tick, "interval", minutes=1, id="main_tick")
        self._scheduler.add_job(self._daily_report, "cron", hour=0, minute=0, id="daily_report")

        # Graceful shutdown
        signal.signal(signal.SIGINT, self._shutdown)
        signal.signal(signal.SIGTERM, self._shutdown)

        logger.info("스케줄러 시작 (1분 간격)")
        try:
            self._scheduler.start()
        except (KeyboardInterrupt, SystemExit):
            self._shutdown()

    def _tick(self) -> None:
        """1분마다 실행되는 메인 로직."""
        try:
            # 1. 시장 데이터 수집
            snapshot_id = self._collector.collect_and_save()
            if snapshot_id is None:
                return

            snapshot = self._collector.get_latest_snapshot()
            if snapshot is None:
                return

            current_price = snapshot["btc_price"]

            # 2. 보유 중인 포지션 확인
            active_trade = self._recorder.get_active_buy_trade(config.bot.coin)

            if active_trade:
                # 보유 중 → 매도 신호 확인
                self._check_and_sell(active_trade, current_price, snapshot_id)
            else:
                # 미보유 → 매수 신호 확인
                self._check_and_buy(snapshot, current_price, snapshot_id)

        except Exception as e:
            logger.error("틱 실행 에러: %s", e, exc_info=True)
            self._notifier.notify_error(str(e))

    def _check_and_buy(self, snapshot: dict, current_price: float, snapshot_id: int) -> None:
        """매수 신호 확인 및 실행."""
        signal_result = self._strategy.check_buy_signal(
            current_price=current_price,
            today_open=snapshot.get("btc_open_24h", current_price),
            yesterday_high=snapshot.get("btc_high_24h", current_price),
            yesterday_low=snapshot.get("btc_low_24h", current_price),
        )

        if signal_result.signal_type != "buy_signal":
            # 매수 조건 미달 — 신호만 기록
            self._recorder.record_signal(
                coin=config.bot.coin,
                signal_type=signal_result.signal_type,
                strategy="volatility_breakout",
                confidence=signal_result.confidence,
                trigger_reason=signal_result.trigger_reason,
                current_price=current_price,
                trigger_value=signal_result.trigger_value,
                skip_reason=signal_result.trigger_reason,
                snapshot_id=snapshot_id,
            )
            return

        if not self._trader.is_ready:
            self._recorder.record_signal(
                coin=config.bot.coin,
                signal_type="buy_signal",
                strategy="volatility_breakout",
                confidence=signal_result.confidence,
                trigger_reason=signal_result.trigger_reason,
                current_price=current_price,
                trigger_value=signal_result.trigger_value,
                skip_reason="api_key_not_configured",
                snapshot_id=snapshot_id,
            )
            logger.info("매수 신호 발생했으나 API Key 미설정 — 스킵")
            return

        # 매수 실행
        balance = self._trader.get_balance_krw()
        buy_amount = balance * (self._strategy.params.position_size_pct / 100)

        order = self._trader.buy_market(config.bot.coin, buy_amount)
        if order.success:
            trade_id = self._recorder.record_trade(
                coin=config.bot.coin,
                side="buy",
                price=order.price,
                amount=order.amount,
                total_krw=order.total_krw,
                fee_krw=order.fee_krw,
                strategy="volatility_breakout",
                trigger_reason=signal_result.trigger_reason,
                trigger_value=signal_result.trigger_value,
                param_k_value=self._strategy.params.k_value,
                param_stop_loss=self._strategy.params.stop_loss_pct,
                param_trailing_stop=self._strategy.params.trailing_stop_pct,
                market_state_at_trade=snapshot.get("market_state"),
                btc_price_at_trade=current_price,
                rsi_at_trade=snapshot.get("btc_rsi_14"),
            )
            self._recorder.record_signal(
                coin=config.bot.coin,
                signal_type="buy_signal",
                strategy="volatility_breakout",
                confidence=signal_result.confidence,
                trigger_reason=signal_result.trigger_reason,
                current_price=current_price,
                trigger_value=signal_result.trigger_value,
                executed=True,
                trade_id=trade_id,
                snapshot_id=snapshot_id,
            )
            self._notifier.notify_trade("buy", config.bot.coin, order.price, order.amount, order.total_krw)

    def _check_and_sell(self, active_trade: dict, current_price: float, snapshot_id: int) -> None:
        """매도 신호 확인 및 실행."""
        buy_price = active_trade["price"]
        signal_result = self._strategy.check_sell_signal(current_price, buy_price)

        if signal_result.signal_type != "sell_signal":
            return

        if not self._trader.is_ready:
            logger.info("매도 신호 발생했으나 API Key 미설정 — 스킵")
            return

        # 매도 실행
        order = self._trader.sell_market(config.bot.coin)
        if order.success:
            profit_pct = (order.price - buy_price) / buy_price * 100
            profit_krw = order.total_krw - active_trade["total_krw"]
            buy_time = datetime.fromisoformat(active_trade["timestamp"])
            hold_minutes = int((datetime.now() - buy_time).total_seconds() / 60)

            trade_id = self._recorder.record_trade(
                coin=config.bot.coin,
                side="sell",
                price=order.price,
                amount=order.amount,
                total_krw=order.total_krw,
                fee_krw=order.fee_krw,
                strategy="volatility_breakout",
                trigger_reason=signal_result.trigger_reason,
                trigger_value=signal_result.trigger_value,
                param_k_value=self._strategy.params.k_value,
                param_stop_loss=self._strategy.params.stop_loss_pct,
                param_trailing_stop=self._strategy.params.trailing_stop_pct,
                buy_trade_id=active_trade["id"],
                profit_pct=round(profit_pct, 2),
                profit_krw=round(profit_krw, 2),
                hold_duration_minutes=hold_minutes,
            )
            self._recorder.record_signal(
                coin=config.bot.coin,
                signal_type="sell_signal",
                strategy="volatility_breakout",
                confidence=signal_result.confidence,
                trigger_reason=signal_result.trigger_reason,
                current_price=current_price,
                trigger_value=signal_result.trigger_value,
                executed=True,
                trade_id=trade_id,
                snapshot_id=snapshot_id,
            )
            self._strategy.reset_position()
            self._notifier.notify_trade("sell", config.bot.coin, order.price, order.amount, order.total_krw)
            self._notifier.notify_profit(config.bot.coin, profit_pct, profit_krw, hold_minutes)

    def _daily_report(self) -> None:
        """자정에 실행되는 일일 정산."""
        logger.info("일일 정산 실행")
        # Phase 1에서는 기본 알림만, 상세 리포트는 Phase 2에서 구현

    def _safety_check(self) -> None:
        """봇 시작 시 안전 장치."""
        if self._trader.is_ready:
            cancelled = self._trader.cancel_all_orders(config.bot.coin)
            if cancelled > 0:
                logger.info("미체결 주문 %d건 취소", cancelled)

    def _load_strategy_params(self) -> StrategyParams:
        """DB에서 최신 전략 파라미터 로딩."""
        row = self._db.execute("SELECT * FROM strategy_params ORDER BY id DESC LIMIT 1").fetchone()

        if row is None:
            logger.warning("전략 파라미터 없음 — 기본값 사용")
            return StrategyParams()

        return StrategyParams(
            k_value=row["k_value"],
            stop_loss_pct=row["stop_loss_pct"],
            trailing_stop_pct=row["trailing_stop_pct"],
            max_positions=row["max_positions"],
            position_size_pct=row["position_size_pct"] or 100.0,
            allow_trading=bool(row["allow_trading"]),
            market_state=row["market_state"] or "sideways",
            aggression=row["aggression"] or 0.5,
        )

    def _shutdown(self, *args) -> None:
        """Graceful shutdown."""
        logger.info("=== CryptoBot 종료 ===")
        self._notifier.notify_bot_status("종료됨")
        if self._scheduler.running:
            self._scheduler.shutdown(wait=False)
        self._db.close()
        sys.exit(0)


def main() -> None:
    """진입점."""
    logging.basicConfig(
        level=getattr(logging, config.bot.log_level),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    bot = CryptoBot()
    bot.start()


if __name__ == "__main__":
    main()
