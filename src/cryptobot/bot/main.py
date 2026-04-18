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
from cryptobot.bot.health_checker import HealthChecker
from cryptobot.bot.monthly_audit import MonthlyAudit
from cryptobot.bot.risk import RiskManager
from cryptobot.bot.strategy_selector import StrategySelector
from cryptobot.bot.trader import Trader
from cryptobot.bot.weekly_reporter import WeeklyReporter
from cryptobot.data.database import Database
from cryptobot.data.recorder import DataRecorder
from cryptobot.exceptions import APIError, InsufficientBalanceError
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
        self._coin_highest_prices: dict[str, float | None] = {}  # 코인별 최고가 추적

    def start(self) -> None:
        """봇 시작."""
        logger.info("=== CryptoBot 시작 ===")
        logger.info("종목: %s (%d개)", ", ".join(self._coin_mgr.active_coins), len(self._coin_mgr.active_coins))
        logger.info("활성 전략: %s", self._strategy_sel.current_strategy_name)
        logger.info("등록 전략: %s", ", ".join(self._strategy_sel.registry.list_names()))
        logger.info(
            "API Key: %s | Slack: %s",
            "O" if self._trader.is_ready else "X",
            "O" if self._notifier.is_configured else "X",
        )

        self._notifier.notify_bot_status("시작됨")
        self._safety_check()

        self._scheduler.add_job(self._tick, "interval", seconds=self._tick_interval, id="main_tick")
        self._scheduler.add_job(self._daily_report, "cron", hour=0, minute=0, id="daily_report")
        self._scheduler.add_job(self._daily_health_check, "cron", hour=6, minute=0, id="daily_health")
        self._scheduler.add_job(self._hourly_reconciliation, "interval", hours=1, id="hourly_reconciliation")
        self._scheduler.add_job(self._weekly_report, "cron", day_of_week="sun", hour=3, minute=0, id="weekly_report")
        self._scheduler.add_job(
            self._weekly_backtest,
            "cron",
            day_of_week="sun",
            hour=2,
            minute=0,
            id="weekly_backtest",
        )
        self._scheduler.add_job(self._monthly_audit, "cron", day=1, hour=4, minute=0, id="monthly_audit")
        self._scheduler.add_job(self._llm_analyze, "interval", minutes=10, id="llm_analyze")

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
            # 코인별 최고가 복원 (전략 인스턴스 공유 문제 방지)
            strategy._highest_price = self._coin_highest_prices.get(coin)

            active_trade = self._recorder.get_active_buy_trade(coin)
            if active_trade:
                self._check_and_sell(active_trade, snapshot["price"], snapshot_id, snapshot, coin)
            else:
                self._check_and_buy(snapshot, snapshot["price"], snapshot_id, coin)

            # 코인별 최고가 저장
            self._coin_highest_prices[coin] = strategy._highest_price
        finally:
            # 카테고리별 파라미터 복원 (공유 인스턴스 보호)
            if hasattr(strategy, "_orig_stop_loss"):
                strategy.params.stop_loss_pct = strategy._orig_stop_loss
                strategy.params.trailing_stop_pct = strategy._orig_trailing
                strategy.params.position_size_pct = strategy._orig_position
            # #152: 코인별 assignment_params로 오버라이드한 extra 복원
            if hasattr(strategy, "_orig_extra"):
                strategy.params.extra = strategy._orig_extra
                del strategy._orig_extra
            self._strategy_sel.current_strategy = orig
            self._strategy_sel.current_strategy_name = orig_name

    def _check_and_buy(self, snapshot, price, snapshot_id, coin=None):
        """매수 신호 확인 및 실행."""
        coin = coin or config.bot.coin
        s = self._strategy_sel.current_strategy
        sn = self._strategy_sel.current_strategy_name
        collector = self._coin_mgr.collectors.get(coin)
        df = collector.latest_df if collector else None
        if df is None or s is None:
            return

        sig = s.check_buy(df, price)
        pj = self._config_mgr.get_strategy_params_json(sn)

        if sig.signal_type != "buy":
            self._recorder.record_signal(
                coin=coin,
                signal_type=sig.signal_type,
                strategy=sn,
                confidence=sig.confidence,
                trigger_reason=sig.reason,
                current_price=price,
                trigger_value=sig.trigger_value,
                skip_reason=sig.reason,
                snapshot_id=snapshot_id,
                strategy_params_json=pj,
            )
            return
        if not self._trader.is_ready:
            self._recorder.record_signal(
                coin=coin,
                signal_type="buy",
                strategy=sn,
                confidence=sig.confidence,
                trigger_reason=sig.reason,
                current_price=price,
                trigger_value=sig.trigger_value,
                skip_reason="api_key_not_configured",
                snapshot_id=snapshot_id,
                strategy_params_json=pj,
            )
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
            self._recorder.record_signal(
                coin=coin,
                signal_type="buy",
                strategy=sn,
                confidence=sig.confidence,
                trigger_reason=sig.reason,
                current_price=price,
                trigger_value=sig.trigger_value,
                skip_reason=reason,
                snapshot_id=snapshot_id,
                strategy_params_json=pj,
            )
            return

        # 중복 매수 방지 — 매수 직전 재확인
        if self._recorder.get_active_buy_trade(coin):
            logger.warning("중복 매수 방지: %s 이미 보유 중", coin)
            return

        bal_before = bal  # 잔고 스냅샷
        # 주문 실행 — APIError가 중간에 나면 주문이 접수됐을 수도 있으니 긴급 알림 필수
        try:
            order = self._trader.buy_market(coin, amount)
        except (APIError, InsufficientBalanceError) as e:
            logger.error("매수 API 실패: %s %s원 — %s", coin, f"{amount:,.0f}", e)
            self._notifier.notify_error(
                f"⚠️ 매수 주문 API 실패: {coin} {amount:,.0f}원 — 접수 후 체결 조회 실패 가능성. "
                f"Upbit에서 수동 확인 필요.\n{e}"
            )
            skip = f"API 예외: {type(e).__name__}"
            self._recorder.record_signal(
                coin=coin,
                signal_type="buy",
                strategy=sn,
                confidence=sig.confidence,
                trigger_reason=sig.reason,
                current_price=price,
                trigger_value=sig.trigger_value,
                skip_reason=skip,
                snapshot_id=snapshot_id,
                strategy_params_json=pj,
            )
            return
        if order.success:
            tid = self._recorder.record_trade(
                coin=coin,
                side="buy",
                price=order.price,
                amount=order.amount,
                total_krw=order.total_krw,
                fee_krw=order.fee_krw,
                strategy=sn,
                trigger_reason=sig.reason,
                trigger_value=sig.trigger_value,
                param_k_value=s.params.extra.get("k_value"),
                param_stop_loss=s.params.stop_loss_pct,
                param_trailing_stop=s.params.trailing_stop_pct,
                market_state_at_trade=snapshot.get("market_state"),
                btc_price_at_trade=price,
                rsi_at_trade=snapshot.get("rsi_14"),
                order_uuid=order.order_uuid,
            )
            # 즉시 commit — 다음 틱이 이 buy를 찾지 못해 중복 매수하는 것을 방지
            try:
                self._db.commit()
            except Exception as ce:
                logger.critical("매수 trade commit 실패: coin=%s tid=%s — %s", coin, tid, ce)
                self._notifier.notify_error(f"🚨 DB commit 실패 (매수): {coin} — 수동 확인 필수")
                raise
            # DB 쓰기 검증
            verify = self._db.execute("SELECT id FROM trades WHERE id = ?", (tid,)).fetchone()
            if not verify:
                logger.error("DB 쓰기 검증 실패: trade_id=%s", tid)
                self._notifier.notify_error(f"DB 쓰기 검증 실패: {coin} 매수 기록 누락")
            # 잔고 일관성 체크
            bal_after = self._trader.get_balance_krw() if self._trader.is_ready else bal_before
            expected_diff = order.total_krw
            actual_diff = bal_before - bal_after
            if abs(actual_diff - expected_diff) > expected_diff * 0.05:
                logger.warning("잔고 불일치: 예상 -%s, 실제 -%s", f"{expected_diff:,.0f}", f"{actual_diff:,.0f}")
            self._recorder.record_signal(
                coin=coin,
                signal_type="buy",
                strategy=sn,
                confidence=sig.confidence,
                trigger_reason=sig.reason,
                current_price=price,
                trigger_value=sig.trigger_value,
                executed=True,
                trade_id=tid,
                snapshot_id=snapshot_id,
                strategy_params_json=pj,
            )
        else:
            # 사전 검증 실패 (최소 주문 금액 미달 등) — 기록만
            self._recorder.record_signal(
                coin=coin,
                signal_type="buy",
                strategy=sn,
                confidence=sig.confidence,
                trigger_reason=sig.reason,
                current_price=price,
                trigger_value=sig.trigger_value,
                skip_reason=order.error or "주문 실패",
                snapshot_id=snapshot_id,
                strategy_params_json=pj,
            )

    def _check_and_sell(self, active_trade, price, snapshot_id, snapshot=None, coin=None):
        """매도 신호 확인 및 실행."""
        coin = coin or config.bot.coin
        s = self._strategy_sel.current_strategy
        sn = self._strategy_sel.current_strategy_name
        collector = self._coin_mgr.collectors.get(coin)
        df = collector.latest_df if collector else None
        if df is None or s is None:
            return

        buy_price = active_trade["price"]
        buy_time = datetime.fromisoformat(active_trade["timestamp"])
        if buy_time.tzinfo is None:
            buy_time = buy_time.replace(tzinfo=timezone.utc)
        s._hold_minutes = int((datetime.now(timezone.utc) - buy_time).total_seconds() / 60)

        sig = s.check_sell(df, price, buy_price)
        pj = self._config_mgr.get_strategy_params_json(sn)

        if sig.signal_type != "sell":
            self._recorder.record_signal(
                coin=coin,
                signal_type=sig.signal_type,
                strategy=sn,
                confidence=sig.confidence,
                trigger_reason=sig.reason,
                current_price=price,
                trigger_value=sig.trigger_value,
                skip_reason=sig.reason,
                snapshot_id=snapshot_id,
                strategy_params_json=pj,
            )
            return
        if not self._trader.is_ready:
            return

        pnl_pct = (price - buy_price) / buy_price * 100
        net_pnl = pnl_pct - BaseStrategy.ROUND_TRIP_FEE_PCT
        # 수수료 가드: Signal에 명시된 is_profit_taking 플래그 기반 (이전엔 reason 문자열 매칭 취약).
        # 익절 신호(ROI/트레일링/중간선 등)만 수수료로 인한 실질 음수 시 차단.
        # 손절/전략 판단(RSI 정상복귀, 데드크로스 등)은 통과.
        if sig.is_profit_taking and net_pnl <= 0:
            self._recorder.record_signal(
                coin=coin,
                signal_type="sell",
                strategy=sn,
                confidence=sig.confidence,
                trigger_reason=sig.reason,
                current_price=price,
                trigger_value=sig.trigger_value,
                skip_reason=f"수수료 가드: 가격 {pnl_pct:+.2f}% 실질 {net_pnl:+.2f}%",
                snapshot_id=snapshot_id,
                strategy_params_json=pj,
            )
            return

        try:
            order = self._trader.sell_market(coin)
        except (APIError, InsufficientBalanceError) as e:
            logger.error("매도 API 실패: %s — %s", coin, e)
            self._notifier.notify_error(
                f"⚠️ 매도 주문 API 실패: {coin} — 접수 후 체결 조회 실패 가능성. Upbit에서 수동 확인 필요.\n{e}"
            )
            skip = f"API 예외: {type(e).__name__}"
            self._recorder.record_signal(
                coin=coin,
                signal_type="sell",
                strategy=sn,
                confidence=sig.confidence,
                trigger_reason=sig.reason,
                current_price=price,
                trigger_value=sig.trigger_value,
                skip_reason=skip,
                snapshot_id=snapshot_id,
                strategy_params_json=pj,
            )
            return
        if order.success:
            bf = active_trade.get("fee_krw") or 0
            profit_krw = round((order.total_krw - order.fee_krw) - (active_trade["total_krw"] + bf), 2)
            profit_pct = (
                round(profit_krw / (active_trade["total_krw"] + bf) * 100, 2)
                if (active_trade["total_krw"] + bf) > 0
                else 0
            )
            tid = self._recorder.record_trade(
                coin=coin,
                side="sell",
                price=order.price,
                amount=order.amount,
                total_krw=order.total_krw,
                fee_krw=order.fee_krw,
                strategy=sn,
                trigger_reason=sig.reason,
                trigger_value=sig.trigger_value,
                param_k_value=s.params.extra.get("k_value"),
                param_stop_loss=s.params.stop_loss_pct,
                param_trailing_stop=s.params.trailing_stop_pct,
                buy_trade_id=active_trade["id"],
                profit_pct=profit_pct,
                profit_krw=profit_krw,
                hold_duration_minutes=s._hold_minutes,
                order_uuid=order.order_uuid,
            )
            # 즉시 commit — 미커밋으로 다음 틱이 이 매도를 놓치면 이중 매도 위험
            try:
                self._db.commit()
            except Exception as ce:
                logger.critical("매도 trade commit 실패: coin=%s tid=%s — %s", coin, tid, ce)
                self._notifier.notify_error(f"🚨 DB commit 실패 (매도): {coin} — 수동 확인 필수")
                raise
            # DB 쓰기 검증
            verify = self._db.execute("SELECT id FROM trades WHERE id = ?", (tid,)).fetchone()
            if not verify:
                logger.error("DB 쓰기 검증 실패: trade_id=%s", tid)
                self._notifier.notify_error(f"DB 쓰기 검증 실패: {coin} 매도 기록 누락")
            self._recorder.record_signal(
                coin=coin,
                signal_type="sell",
                strategy=sn,
                confidence=sig.confidence,
                trigger_reason=sig.reason,
                current_price=price,
                trigger_value=sig.trigger_value,
                executed=True,
                trade_id=tid,
                snapshot_id=snapshot_id,
                strategy_params_json=pj,
            )
            s.reset()
        else:
            self._recorder.record_signal(
                coin=coin,
                signal_type="sell",
                strategy=sn,
                confidence=sig.confidence,
                trigger_reason=sig.reason,
                current_price=price,
                trigger_value=sig.trigger_value,
                skip_reason=order.error or "주문 실패",
                snapshot_id=snapshot_id,
                strategy_params_json=pj,
            )

    def _llm_analyze(self):
        try:
            from cryptobot.llm.analyzer import LLMAnalyzer

            a = LLMAnalyzer(self._db)
            if not a.is_configured:
                return
            # 시장 급변 감지 → 즉시 분석
            force = a.check_emergency()
            r = a.analyze(force=force)
            if r:
                self._config_mgr.refresh()
                self._strategy_sel.refresh(self._notifier)
                # 전략 적용 검증
                recommended = r.get("recommended_strategy")
                if recommended and recommended != self._strategy_sel.current_strategy_name:
                    logger.warning(
                        "전략 불일치: LLM 추천=%s, 실제=%s",
                        recommended,
                        self._strategy_sel.current_strategy_name,
                    )
                    self._notifier.notify_error(
                        f"전략 불일치: 추천={recommended}, 실제={self._strategy_sel.current_strategy_name}"
                    )
        except Exception as e:
            logger.error("LLM 에러: %s", e, exc_info=True)

    def _daily_report(self):
        try:
            import pyupbit

            today = date.today()
            trades = self._recorder.get_today_trades()  # 전체 코인
            sells = [t for t in trades if t["side"] == "sell"]
            buys = [t for t in trades if t["side"] == "buy"]
            wins = [t for t in sells if (t.get("profit_pct") or 0) > 0]
            losses = [t for t in sells if (t.get("profit_pct") or 0) <= 0]
            wr = (len(wins) / len(sells) * 100) if sells else 0

            # 실제 자산 가치 계산 (KRW + 보유 코인)
            krw = self._trader.get_balance_krw() if self._trader.is_ready else 0
            coin_value = 0
            unrealized = 0
            for coin in self._coin_mgr.active_coins:
                active = self._recorder.get_active_buy_trade(coin)
                if active:
                    cp = pyupbit.get_current_price(coin)
                    if cp:
                        val = active["amount"] * cp
                        coin_value += val
                        unrealized += val - active["total_krw"]

            total_asset = krw + coin_value
            realized = sum(t.get("profit_krw", 0) or 0 for t in sells)
            total_fees = sum(t.get("fee_krw", 0) or 0 for t in trades)

            avg_profit = sum(t.get("profit_pct", 0) or 0 for t in wins) / len(wins) if wins else 0
            avg_loss = sum(t.get("profit_pct", 0) or 0 for t in losses) / len(losses) if losses else 0

            self._recorder.save_daily_report(
                report_date=today,
                starting_balance=total_asset,
                ending_balance=total_asset,
                total_asset_value=total_asset,
                realized_pnl=realized,
                unrealized_pnl=round(unrealized, 2),
                trades_summary={
                    "total": len(trades),
                    "buys": len(buys),
                    "sells": len(sells),
                    "wins": len(wins),
                    "losses": len(losses),
                    "win_rate": round(wr, 1),
                    "avg_profit_pct": round(avg_profit, 2),
                    "avg_loss_pct": round(avg_loss, 2),
                    "total_fees": round(total_fees, 2),
                },
            )

            if self._config_mgr.get_bool("slack_daily_report", True):
                self._notifier.notify_daily_report(
                    date_str=today.isoformat(),
                    daily_return_pct=sum(t.get("profit_pct", 0) or 0 for t in sells),
                    total_trades=len(trades),
                    win_rate=wr,
                    balance_krw=total_asset,
                )
        except Exception as e:
            logger.error("일일 정산 에러: %s", e, exc_info=True)

    def _daily_health_check(self):
        """일일 헬스체크 (06:00)."""
        try:
            checker = HealthChecker(self._db, self._trader, self._notifier)
            checker.run_all()
        except Exception as e:
            logger.error("헬스체크 에러: %s", e, exc_info=True)

    def _hourly_reconciliation(self):
        """매시간 체결 정합성 검증."""
        try:
            checker = HealthChecker(self._db, self._trader, self._notifier)
            checker.reconcile_trades()
        except Exception as e:
            logger.error("체결 정합성 검증 에러: %s", e, exc_info=True)

    def _weekly_report(self):
        """주간 리포트 (일요일 03:00)."""
        try:
            reporter = WeeklyReporter(self._db, self._notifier)
            reporter.run_all()
        except Exception as e:
            logger.error("주간 리포트 에러: %s", e, exc_info=True)

    def _weekly_backtest(self):
        """주간 백테스트 (일요일 02:00)."""
        try:
            from cryptobot.backtest.reporter import BacktestReporter

            reporter = BacktestReporter(self._db, config.bot.db_path, self._notifier)
            reporter.run_all()
        except Exception as e:
            logger.error("주간 백테스트 에러: %s", e, exc_info=True)

    def _monthly_audit(self):
        """월간 감사 (매월 1일 04:00)."""
        try:
            audit = MonthlyAudit(self._db, config.bot.db_path, self._notifier)
            audit.run_all()
        except Exception as e:
            logger.error("월간 감사 에러: %s", e, exc_info=True)

    def _safety_check(self):
        if self._trader.is_ready:
            for coin in self._coin_mgr.active_coins:
                c = self._trader.cancel_all_orders(coin)
                if c > 0:
                    logger.info("미체결 주문 %d건 취소 (%s)", c, coin)

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
