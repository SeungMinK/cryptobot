"""CryptoBot 메인 루프.

스케줄러를 초기화하고, 매 틱마다 멀티코인 매매 판단을 실행한다.

사용법:
    python -m cryptobot.bot.main
"""

import logging
import signal
import sys
import time as _time
from datetime import date, datetime, timezone

from apscheduler.schedulers.blocking import BlockingScheduler

from cryptobot.bot.coin_manager import CoinManager
from cryptobot.bot.config import config
from cryptobot.bot.config_manager import ConfigManager
from cryptobot.bot.risk import RiskManager
from cryptobot.bot.strategy_selector import StrategySelector
from cryptobot.bot.trader import Trader
from cryptobot.data.database import Database
from cryptobot.data.recorder import DataRecorder
from cryptobot.notifier.slack import SlackNotifier
from cryptobot.strategies.base import BaseStrategy

logger = logging.getLogger(__name__)


class CryptoBot:
    """메인 봇 클래스."""

    def __init__(self) -> None:
        self._db = Database(config.bot.db_path)
        self._db.initialize()

        self._trader = Trader()
        self._recorder = DataRecorder(self._db)
        self._notifier = SlackNotifier()
        self._risk = RiskManager(self._db)

        self._config_mgr = ConfigManager(self._db)
        self._coin_mgr = CoinManager(self._db, self._config_mgr)
        self._strategy_sel = StrategySelector(self._db, self._config_mgr)

        self._scheduler = BlockingScheduler()
        self._tick_interval = int(self._config_mgr.get("tick_interval_seconds", "60"))

    def start(self) -> None:
        """봇 시작."""
        logger.info("=== CryptoBot 시작 ===")
        logger.info("종목: %s (%d개)", ", ".join(self._coin_mgr.active_coins), len(self._coin_mgr.active_coins))
        logger.info("활성 전략: %s", self._strategy_sel.current_strategy_name)
        logger.info("등록 전략: %s", ", ".join(self._strategy_sel.registry.list_names()))
        logger.info("API Key: %s | Slack: %s", "O" if self._trader.is_ready else "X", "O" if self._notifier.is_configured else "X")

        self._notifier.notify_bot_status("시작됨")
        self._safety_check()

        self._scheduler.add_job(self._tick, "interval", seconds=self._tick_interval, id="main_tick")
        self._scheduler.add_job(self._daily_report, "cron", hour=0, minute=0, id="daily_report")
        self._scheduler.add_job(self._llm_analyze, "interval", hours=4, id="llm_analyze")

        signal.signal(signal.SIGINT, self._shutdown)
        signal.signal(signal.SIGTERM, self._shutdown)

        logger.info("스케줄러 시작 (%d초 간격)", self._tick_interval)
        try:
            self._scheduler.start()
        except (KeyboardInterrupt, SystemExit):
            self._shutdown()

    def _tick(self) -> None:
        """매 틱 실행."""
        try:
            self._config_mgr.refresh()
            self._strategy_sel.refresh(self._notifier)
            self._coin_mgr.refresh()

            self._risk.limits.max_daily_trades = int(self._config_mgr.get("max_daily_trades", "10"))
            self._risk.limits.max_daily_loss_pct = float(self._config_mgr.get("max_daily_loss_pct", "-10.0"))
            self._risk.limits.max_consecutive_losses = int(self._config_mgr.get("max_consecutive_losses", "3"))

            new_interval = int(self._config_mgr.get("tick_interval_seconds", "60"))
            if new_interval != self._tick_interval:
                self._scheduler.reschedule_job("main_tick", trigger="interval", seconds=new_interval)
                self._tick_interval = new_interval

            if not self._strategy_sel.current_strategy or not self._config_mgr.get_bool("allow_trading", True):
                return

            for i, coin in enumerate(self._coin_mgr.active_coins):
                try:
                    if i > 0:
                        _time.sleep(0.5)
                    self._tick_coin(coin)
                except Exception as e:
                    logger.error("틱 에러 (%s): %s", coin, e, exc_info=True)
        except Exception as e:
            logger.error("틱 실행 에러: %s", e, exc_info=True)
            self._notifier.notify_error(str(e))
        finally:
            try:
                self._db.commit()
            except Exception as e:
                logger.warning("commit 실패: %s", e)

    def _tick_coin(self, coin: str) -> None:
        """개별 코인 매매 판단."""
        collector = self._coin_mgr.collectors.get(coin)
        if not collector:
            return
        snapshot_id = collector.collect_and_save()
        if not snapshot_id:
            return
        snapshot = collector.get_latest_snapshot()
        if not snapshot:
            return

        category = self._coin_mgr.get_category(coin)
        strategy, name = self._strategy_sel.get_coin_strategy(coin, category, self._coin_mgr.collectors)
        if not strategy:
            return

        orig, orig_name = self._strategy_sel.current_strategy, self._strategy_sel.current_strategy_name
        self._strategy_sel.current_strategy = strategy
        self._strategy_sel.current_strategy_name = name
        try:
            active_trade = self._recorder.get_active_buy_trade(coin)
            if active_trade:
                self._check_and_sell(active_trade, snapshot["price"], snapshot_id, snapshot, coin)
            else:
                self._check_and_buy(snapshot, snapshot["price"], snapshot_id, coin)
        finally:
            self._strategy_sel.current_strategy = orig
            self._strategy_sel.current_strategy_name = orig_name

    def _check_and_buy(self, snapshot, price, snapshot_id, coin=None):
        """매수 신호 확인 및 실행."""
        coin = coin or config.bot.coin
        s = self._strategy_sel.current_strategy
        sn = self._strategy_sel.current_strategy_name
        collector = self._coin_mgr.collectors.get(coin)
        df = collector.latest_df if collector else None
        if not df or not s:
            return

        sig = s.check_buy(df, price)
        pj = self._config_mgr.get_strategy_params_json(sn)

        if sig.signal_type != "buy":
            self._recorder.record_signal(coin=coin, signal_type=sig.signal_type, strategy=sn, confidence=sig.confidence, trigger_reason=sig.reason, current_price=price, trigger_value=sig.trigger_value, skip_reason=sig.reason, snapshot_id=snapshot_id, strategy_params_json=pj)
            return
        if not self._trader.is_ready:
            self._recorder.record_signal(coin=coin, signal_type="buy", strategy=sn, confidence=sig.confidence, trigger_reason=sig.reason, current_price=price, trigger_value=sig.trigger_value, skip_reason="api_key_not_configured", snapshot_id=snapshot_id, strategy_params_json=pj)
            return

        bal = self._trader.get_balance_krw()
        max_pct = float(self._config_mgr.get("max_position_per_coin_pct", "50"))
        avail = min(bal * max_pct / 100, bal - self._risk.limits.min_balance_krw)
        if avail <= 0:
            return
        ratio = max(0, min(sig.confidence, 1)) * max(0, min(s.params.position_size_pct, 100)) / 100
        amount = min(avail * ratio, self._risk.limits.max_position_size_krw)

        ok, reason = self._risk.check_can_buy(coin, amount, bal)
        if not ok:
            self._recorder.record_signal(coin=coin, signal_type="buy", strategy=sn, confidence=sig.confidence, trigger_reason=sig.reason, current_price=price, trigger_value=sig.trigger_value, skip_reason=reason, snapshot_id=snapshot_id, strategy_params_json=pj)
            return

        order = self._trader.buy_market(coin, amount)
        if order.success:
            tid = self._recorder.record_trade(coin=coin, side="buy", price=order.price, amount=order.amount, total_krw=order.total_krw, fee_krw=order.fee_krw, strategy=sn, trigger_reason=sig.reason, trigger_value=sig.trigger_value, param_k_value=s.params.extra.get("k_value"), param_stop_loss=s.params.stop_loss_pct, param_trailing_stop=s.params.trailing_stop_pct, market_state_at_trade=snapshot.get("market_state"), btc_price_at_trade=price, rsi_at_trade=snapshot.get("rsi_14"))
            self._recorder.record_signal(coin=coin, signal_type="buy", strategy=sn, confidence=sig.confidence, trigger_reason=sig.reason, current_price=price, trigger_value=sig.trigger_value, executed=True, trade_id=tid, snapshot_id=snapshot_id, strategy_params_json=pj)
            if self._config_mgr.get_bool("slack_trade_notification", True):
                self._notifier.notify_trade("buy", coin, order.price, order.amount, order.total_krw)

    def _check_and_sell(self, active_trade, price, snapshot_id, snapshot=None, coin=None):
        """매도 신호 확인 및 실행."""
        coin = coin or config.bot.coin
        s = self._strategy_sel.current_strategy
        sn = self._strategy_sel.current_strategy_name
        collector = self._coin_mgr.collectors.get(coin)
        df = collector.latest_df if collector else None
        if not df or not s:
            return

        buy_price = active_trade["price"]
        buy_time = datetime.fromisoformat(active_trade["timestamp"])
        if buy_time.tzinfo is None:
            buy_time = buy_time.replace(tzinfo=timezone.utc)
        s._hold_minutes = int((datetime.now(timezone.utc) - buy_time).total_seconds() / 60)

        sig = s.check_sell(df, price, buy_price)
        pj = self._config_mgr.get_strategy_params_json(sn)

        if sig.signal_type != "sell":
            self._recorder.record_signal(coin=coin, signal_type=sig.signal_type, strategy=sn, confidence=sig.confidence, trigger_reason=sig.reason, current_price=price, trigger_value=sig.trigger_value, skip_reason=sig.reason, snapshot_id=snapshot_id, strategy_params_json=pj)
            return
        if not self._trader.is_ready:
            return

        pnl_pct = (price - buy_price) / buy_price * 100
        if "손절" not in sig.reason and pnl_pct <= BaseStrategy.ROUND_TRIP_FEE_PCT:
            self._recorder.record_signal(coin=coin, signal_type="sell", strategy=sn, confidence=sig.confidence, trigger_reason=sig.reason, current_price=price, trigger_value=sig.trigger_value, skip_reason=f"수수료 가드: {pnl_pct:+.2f}%", snapshot_id=snapshot_id, strategy_params_json=pj)
            return

        order = self._trader.sell_market(coin)
        if order.success:
            bf = active_trade.get("fee_krw") or 0
            profit_krw = round((order.total_krw - order.fee_krw) - (active_trade["total_krw"] + bf), 2)
            profit_pct = round(profit_krw / (active_trade["total_krw"] + bf) * 100, 2) if (active_trade["total_krw"] + bf) > 0 else 0
            tid = self._recorder.record_trade(coin=coin, side="sell", price=order.price, amount=order.amount, total_krw=order.total_krw, fee_krw=order.fee_krw, strategy=sn, trigger_reason=sig.reason, trigger_value=sig.trigger_value, param_k_value=s.params.extra.get("k_value"), param_stop_loss=s.params.stop_loss_pct, param_trailing_stop=s.params.trailing_stop_pct, buy_trade_id=active_trade["id"], profit_pct=profit_pct, profit_krw=profit_krw, hold_duration_minutes=s._hold_minutes)
            self._recorder.record_signal(coin=coin, signal_type="sell", strategy=sn, confidence=sig.confidence, trigger_reason=sig.reason, current_price=price, trigger_value=sig.trigger_value, executed=True, trade_id=tid, snapshot_id=snapshot_id, strategy_params_json=pj)
            s.reset()
            if self._config_mgr.get_bool("slack_trade_notification", True):
                self._notifier.notify_trade("sell", coin, order.price, order.amount, order.total_krw)
                self._notifier.notify_profit(coin, profit_pct, profit_krw, s._hold_minutes)

    def _llm_analyze(self):
        try:
            from cryptobot.llm.analyzer import LLMAnalyzer
            a = LLMAnalyzer(self._db)
            if not a.is_configured:
                return
            r = a.analyze()
            if r:
                self._notifier.send(f"📊 *LLM 시장 분석*\n{r.get('market_summary_kr','')[:100]}")
                self._config_mgr.refresh()
        except Exception as e:
            logger.error("LLM 에러: %s", e, exc_info=True)

    def _daily_report(self):
        try:
            today = date.today()
            trades = self._recorder.get_today_trades(config.bot.coin)
            sells = [t for t in trades if t["side"] == "sell"]
            wins = [t for t in sells if (t.get("profit_pct") or 0) > 0]
            bal = self._trader.get_balance_krw() if self._trader.is_ready else 0
            wr = (len(wins) / len(sells) * 100) if sells else 0
            self._recorder.save_daily_report(report_date=today, starting_balance=bal, ending_balance=bal, total_asset_value=bal, realized_pnl=sum(t.get("profit_krw", 0) or 0 for t in sells), unrealized_pnl=0, trades_summary={"total": len(trades), "sells": len(sells), "wins": len(wins), "win_rate": round(wr, 1)})
            if self._config_mgr.get_bool("slack_daily_report", True):
                self._notifier.notify_daily_report(date_str=today.isoformat(), daily_return_pct=sum(t.get("profit_pct", 0) or 0 for t in sells), total_trades=len(trades), win_rate=wr, balance_krw=bal)
        except Exception as e:
            logger.error("일일 정산 에러: %s", e, exc_info=True)

    def _safety_check(self):
        if self._trader.is_ready:
            c = self._trader.cancel_all_orders(config.bot.coin)
            if c > 0:
                logger.info("미체결 주문 %d건 취소", c)

    def _shutdown(self, *args):
        logger.info("=== CryptoBot 종료 ===")
        self._notifier.notify_bot_status("종료됨")
        if self._scheduler.running:
            self._scheduler.shutdown(wait=False)
        self._db.close()
        sys.exit(0)


def main():
    from cryptobot.logging_config import setup_logging
    setup_logging("bot", config.bot.log_level)
    CryptoBot().start()


if __name__ == "__main__":
    main()
