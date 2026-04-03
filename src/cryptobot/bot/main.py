"""CryptoBot 메인 루프.

NestJS의 main.ts (bootstrap) + AppModule과 동일한 역할.
스케줄러를 초기화하고, 10초마다 데이터 수집 + 매매 판단을 실행한다.

사용법:
    python -m cryptobot.bot.main
"""

import json
import logging
import signal
import sys
from datetime import date, datetime

from apscheduler.schedulers.blocking import BlockingScheduler

from cryptobot.bot.config import config
from cryptobot.bot.risk import RiskManager
from cryptobot.bot.trader import Trader
from cryptobot.data.collector import DataCollector
from cryptobot.data.database import Database
from cryptobot.data.recorder import DataRecorder
from cryptobot.notifier.slack import SlackNotifier
from cryptobot.strategies.base import BaseStrategy, StrategyParams
from cryptobot.strategies.bollinger_bands import BollingerBands
from cryptobot.strategies.bollinger_squeeze import BollingerSqueeze
from cryptobot.strategies.breakout_momentum import BreakoutMomentum
from cryptobot.strategies.grid_trading import GridTrading
from cryptobot.strategies.ma_crossover import MACrossover
from cryptobot.strategies.macd_strategy import MACDStrategy
from cryptobot.strategies.registry import StrategyRegistry
from cryptobot.strategies.rsi_mean_reversion import RSIMeanReversion
from cryptobot.strategies.supertrend import Supertrend
from cryptobot.strategies.volatility_breakout import VolatilityBreakout

logger = logging.getLogger(__name__)

# 전략 이름 → 클래스 매핑
_STRATEGY_CLASSES: dict[str, type[BaseStrategy]] = {
    "volatility_breakout": VolatilityBreakout,
    "ma_crossover": MACrossover,
    "macd": MACDStrategy,
    "rsi_mean_reversion": RSIMeanReversion,
    "bollinger_bands": BollingerBands,
    "bollinger_squeeze": BollingerSqueeze,
    "supertrend": Supertrend,
    "grid_trading": GridTrading,
    "breakout_momentum": BreakoutMomentum,
}


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
        self._risk = RiskManager(self._db)

        # 전략 레지스트리 초기화
        self._registry = StrategyRegistry()
        self._load_strategies()

        # 활성 전략 설정
        self._strategy: BaseStrategy | None = None
        self._strategy_name: str = ""
        self._select_active_strategy()

        # 전략 파라미터 로딩 (리스크 관리용)
        self._strategy_params = self._load_strategy_params()

        self._scheduler = BlockingScheduler()

    def start(self) -> None:
        """봇 시작."""
        logger.info("=== CryptoBot 시작 ===")
        logger.info("종목: %s", config.bot.coin)
        logger.info("활성 전략: %s", self._strategy_name or "없음")
        logger.info("등록 전략: %s", ", ".join(self._registry.list_names()))
        logger.info("API Key 설정: %s", "O" if self._trader.is_ready else "X")
        logger.info("Slack 설정: %s", "O" if self._notifier.is_configured else "X")
        logger.info("DB: %s", config.bot.db_path)

        self._notifier.notify_bot_status("시작됨")

        # 봇 시작 시 안전 장치
        self._safety_check()

        # 스케줄 등록
        self._scheduler.add_job(self._tick, "interval", seconds=10, id="main_tick")
        self._scheduler.add_job(self._daily_report, "cron", hour=0, minute=0, id="daily_report")
        # 5분마다 전략 변경 확인 (Admin에서 활성화/비활성화 시 반영)
        self._scheduler.add_job(self._refresh_strategy, "interval", minutes=5, id="strategy_refresh")

        # Graceful shutdown
        signal.signal(signal.SIGINT, self._shutdown)
        signal.signal(signal.SIGTERM, self._shutdown)

        logger.info("스케줄러 시작 (10초 간격)")
        try:
            self._scheduler.start()
        except (KeyboardInterrupt, SystemExit):
            self._shutdown()

    def _tick(self) -> None:
        """10초마다 실행되는 메인 로직."""
        try:
            if self._strategy is None:
                return

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
        df = self._collector.latest_df
        if df is None:
            return

        signal_result = self._strategy.check_buy(df, current_price)

        if signal_result.signal_type != "buy":
            self._recorder.record_signal(
                coin=config.bot.coin,
                signal_type=signal_result.signal_type,
                strategy=self._strategy_name,
                confidence=signal_result.confidence,
                trigger_reason=signal_result.reason,
                current_price=current_price,
                trigger_value=signal_result.trigger_value,
                skip_reason=signal_result.reason,
                snapshot_id=snapshot_id,
            )
            return

        if not self._trader.is_ready:
            self._recorder.record_signal(
                coin=config.bot.coin,
                signal_type="buy",
                strategy=self._strategy_name,
                confidence=signal_result.confidence,
                trigger_reason=signal_result.reason,
                current_price=current_price,
                trigger_value=signal_result.trigger_value,
                skip_reason="api_key_not_configured",
                snapshot_id=snapshot_id,
            )
            logger.info("매수 신호 발생했으나 API Key 미설정 — 스킵")
            return

        # 매수 실행 — 리스크 점검 후 진행
        balance = self._trader.get_balance_krw()
        buy_amount = self._risk.get_safe_position_size(
            balance,
            confidence=signal_result.confidence,
            position_size_pct=self._strategy.params.position_size_pct,
        )

        can_buy, reason = self._risk.check_can_buy(config.bot.coin, buy_amount, balance)
        if not can_buy:
            self._recorder.record_signal(
                coin=config.bot.coin,
                signal_type="buy",
                strategy=self._strategy_name,
                confidence=signal_result.confidence,
                trigger_reason=signal_result.reason,
                current_price=current_price,
                trigger_value=signal_result.trigger_value,
                skip_reason=reason,
                snapshot_id=snapshot_id,
            )
            logger.info("매수 신호 발생했으나 리스크 차단: %s", reason)
            return

        order = self._trader.buy_market(config.bot.coin, buy_amount)
        if order.success:
            trade_id = self._recorder.record_trade(
                coin=config.bot.coin,
                side="buy",
                price=order.price,
                amount=order.amount,
                total_krw=order.total_krw,
                fee_krw=order.fee_krw,
                strategy=self._strategy_name,
                trigger_reason=signal_result.reason,
                trigger_value=signal_result.trigger_value,
                param_k_value=self._strategy.params.extra.get("k_value"),
                param_stop_loss=self._strategy.params.stop_loss_pct,
                param_trailing_stop=self._strategy.params.trailing_stop_pct,
                market_state_at_trade=snapshot.get("market_state"),
                btc_price_at_trade=current_price,
                rsi_at_trade=snapshot.get("btc_rsi_14"),
            )
            self._recorder.record_signal(
                coin=config.bot.coin,
                signal_type="buy",
                strategy=self._strategy_name,
                confidence=signal_result.confidence,
                trigger_reason=signal_result.reason,
                current_price=current_price,
                trigger_value=signal_result.trigger_value,
                executed=True,
                trade_id=trade_id,
                snapshot_id=snapshot_id,
            )
            self._notifier.notify_trade("buy", config.bot.coin, order.price, order.amount, order.total_krw)

    def _check_and_sell(self, active_trade: dict, current_price: float, snapshot_id: int) -> None:
        """매도 신호 확인 및 실행."""
        df = self._collector.latest_df
        if df is None:
            return

        buy_price = active_trade["price"]
        signal_result = self._strategy.check_sell(df, current_price, buy_price)

        if signal_result.signal_type != "sell":
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
                strategy=self._strategy_name,
                trigger_reason=signal_result.reason,
                trigger_value=signal_result.trigger_value,
                param_k_value=self._strategy.params.extra.get("k_value"),
                param_stop_loss=self._strategy.params.stop_loss_pct,
                param_trailing_stop=self._strategy.params.trailing_stop_pct,
                buy_trade_id=active_trade["id"],
                profit_pct=round(profit_pct, 2),
                profit_krw=round(profit_krw, 2),
                hold_duration_minutes=hold_minutes,
            )
            self._recorder.record_signal(
                coin=config.bot.coin,
                signal_type="sell",
                strategy=self._strategy_name,
                confidence=signal_result.confidence,
                trigger_reason=signal_result.reason,
                current_price=current_price,
                trigger_value=signal_result.trigger_value,
                executed=True,
                trade_id=trade_id,
                snapshot_id=snapshot_id,
            )
            self._strategy.reset()
            self._notifier.notify_trade("sell", config.bot.coin, order.price, order.amount, order.total_krw)
            self._notifier.notify_profit(config.bot.coin, profit_pct, profit_krw, hold_minutes)

    def _load_strategies(self) -> None:
        """DB에서 전략 목록을 읽고 레지스트리에 등록."""
        rows = self._db.execute("SELECT * FROM strategies WHERE is_available = TRUE").fetchall()
        strategy_params = self._load_strategy_params()

        for row in rows:
            name = row["name"]
            cls = _STRATEGY_CLASSES.get(name)
            if cls is None:
                logger.warning("전략 클래스 미등록: %s (스킵)", name)
                continue

            # DB의 default_params_json을 StrategyParams.extra에 매핑
            extra = json.loads(row["default_params_json"]) if row["default_params_json"] else {}
            params = StrategyParams(
                stop_loss_pct=strategy_params.get("stop_loss_pct", -5.0),
                trailing_stop_pct=strategy_params.get("trailing_stop_pct", -3.0),
                position_size_pct=strategy_params.get("position_size_pct", 100.0),
                extra=extra,
            )

            try:
                strategy = cls(params)
                self._registry.register(strategy)
            except Exception as e:
                logger.error("전략 초기화 실패: %s — %s", name, e)

    def _select_active_strategy(self) -> None:
        """DB에서 is_active=True인 전략을 현재 전략으로 설정."""
        row = self._db.execute("SELECT name FROM strategies WHERE is_active = TRUE LIMIT 1").fetchone()

        if row is None:
            logger.warning("활성 전략 없음 — 기본 volatility_breakout 사용")
            strategy = self._registry.get("volatility_breakout")
        else:
            strategy = self._registry.get(row["name"])
            if strategy is None:
                logger.warning("활성 전략 '%s' 레지스트리에 없음 — 기본 전략 사용", row["name"])
                strategy = self._registry.get("volatility_breakout")

        if strategy is not None:
            self._strategy = strategy
            self._strategy_name = strategy.info().name
            logger.info("활성 전략 설정: %s (%s)", self._strategy_name, strategy.info().display_name)
        else:
            logger.error("사용 가능한 전략이 없습니다")

    def _refresh_strategy(self) -> None:
        """Admin에서 전략이 변경되었는지 확인하고 반영."""
        row = self._db.execute("SELECT name FROM strategies WHERE is_active = TRUE LIMIT 1").fetchone()
        new_name = row["name"] if row else "volatility_breakout"

        if new_name == self._strategy_name:
            return

        old_name = self._strategy_name
        new_strategy = self._registry.get(new_name)
        if new_strategy is None:
            logger.warning("전략 전환 실패: '%s' 레지스트리에 없음", new_name)
            return

        self._strategy = new_strategy
        self._strategy_name = new_name
        logger.info("전략 전환: %s → %s", old_name, new_name)

        # strategy_activations에 기록
        self._db.execute(
            """
            INSERT INTO strategy_activations (strategy_name, action, source, reason, previous_strategy)
            VALUES (?, 'activate', 'bot_refresh', '전략 자동 전환', ?)
            """,
            (new_name, old_name),
        )
        self._db.commit()

        self._notifier.notify_bot_status(f"전략 전환: {old_name} → {new_name}")

    def _daily_report(self) -> None:
        """자정에 실행되는 일일 정산."""
        logger.info("일일 정산 실행")
        try:
            today = date.today()
            trades = self._recorder.get_today_trades(config.bot.coin)

            sell_trades = [t for t in trades if t["side"] == "sell"]
            wins = [t for t in sell_trades if (t.get("profit_pct") or 0) > 0]
            losses = [t for t in sell_trades if (t.get("profit_pct") or 0) <= 0]
            total_fees = sum(t.get("fee_krw", 0) for t in trades)

            win_rate = (len(wins) / len(sell_trades) * 100) if sell_trades else 0
            avg_profit = sum(t["profit_pct"] for t in wins) / len(wins) if wins else 0
            avg_loss = sum(t["profit_pct"] for t in losses) / len(losses) if losses else 0

            # 잔고 조회 (API Key 없으면 0)
            balance = self._trader.get_balance_krw() if self._trader.is_ready else 0

            trades_summary = {
                "total": len(trades),
                "buys": len([t for t in trades if t["side"] == "buy"]),
                "sells": len(sell_trades),
                "wins": len(wins),
                "losses": len(losses),
                "win_rate": round(win_rate, 1),
                "avg_profit_pct": round(avg_profit, 2),
                "avg_loss_pct": round(avg_loss, 2),
                "total_fees": round(total_fees, 2),
            }

            # DB에 저장
            self._recorder.save_daily_report(
                report_date=today,
                starting_balance=balance,
                ending_balance=balance,
                total_asset_value=balance,
                realized_pnl=sum(t.get("profit_krw", 0) or 0 for t in sell_trades),
                unrealized_pnl=0,
                trades_summary=trades_summary,
            )

            # Slack 알림
            daily_pnl = sum(t.get("profit_pct", 0) or 0 for t in sell_trades)
            self._notifier.notify_daily_report(
                date_str=today.isoformat(),
                daily_return_pct=daily_pnl,
                total_trades=len(trades),
                win_rate=win_rate,
                balance_krw=balance,
            )

        except Exception as e:
            logger.error("일일 정산 에러: %s", e, exc_info=True)
            self._notifier.notify_error(f"일일 정산 실패: {e}")

    def _safety_check(self) -> None:
        """봇 시작 시 안전 장치."""
        if self._trader.is_ready:
            cancelled = self._trader.cancel_all_orders(config.bot.coin)
            if cancelled > 0:
                logger.info("미체결 주문 %d건 취소", cancelled)

    def _load_strategy_params(self) -> dict:
        """DB에서 최신 전략 파라미터 로딩."""
        row = self._db.execute("SELECT * FROM strategy_params ORDER BY id DESC LIMIT 1").fetchone()

        if row is None:
            return {
                "stop_loss_pct": -5.0,
                "trailing_stop_pct": -3.0,
                "position_size_pct": 100.0,
            }

        return {
            "k_value": row["k_value"],
            "stop_loss_pct": row["stop_loss_pct"],
            "trailing_stop_pct": row["trailing_stop_pct"],
            "position_size_pct": row["position_size_pct"] or 100.0,
        }

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
