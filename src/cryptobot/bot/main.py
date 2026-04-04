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
import time as _time
from datetime import date, datetime, timezone

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
from cryptobot.strategies.bb_rsi_combined import BBRSICombined

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
    "bb_rsi_combined": BBRSICombined,
}


class CryptoBot:
    """메인 봇 클래스. NestJS의 AppModule 역할."""

    def __init__(self) -> None:
        # 모듈 초기화 — NestJS의 imports와 동일
        self._db = Database(config.bot.db_path)
        self._db.initialize()

        self._trader = Trader()
        self._recorder = DataRecorder(self._db)
        self._notifier = SlackNotifier()
        self._risk = RiskManager(self._db)

        # 멀티코인: 코인별 collector 관리
        # BTC, ETH, XRP는 항상 모니터링
        self._core_coins = ["KRW-BTC", "KRW-ETH", "KRW-XRP"]
        self._collectors: dict[str, DataCollector] = {}
        self._active_coins: list[str] = list(self._core_coins)
        self._last_coin_refresh: str = ""  # 타임스탬프 (epoch)
        self._init_collectors()

        # 캐시 초기화 (전략 로딩보다 먼저)
        self._config_cache: dict[str, str] = {}
        self._strategy_params_cache: dict[str, str | None] = {}
        self._refresh_config_cache()
        self._refresh_strategy_params_cache()

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

    def _init_collectors(self) -> None:
        """활성 코인별 DataCollector 초기화 + 불필요한 collector 정리."""
        # 새 코인 추가
        for coin in self._active_coins:
            if coin not in self._collectors:
                self._collectors[coin] = DataCollector(self._db, coin)
        # 목록에서 빠진 코인 정리 (메모리 누수 방지)
        removed = [c for c in self._collectors if c not in self._active_coins]
        for coin in removed:
            del self._collectors[coin]
            logger.debug("collector 정리: %s", coin)

    def _refresh_coins(self) -> None:
        """멀티코인 목록 갱신 (30분 주기)."""
        interval = int(self._get_config("coin_refresh_interval_minutes", "30"))

        # 타임스탬프 기반 정확한 간격 체크
        now_ts = _time.time()
        if self._last_coin_refresh:
            elapsed = now_ts - float(self._last_coin_refresh)
            if elapsed < interval * 60:
                return

        if not self._get_config_bool("multi_coin_enabled", True):
            self._active_coins = list(self._core_coins)
            self._init_collectors()
            return

        try:
            from cryptobot.bot.scanner import CoinScanner
            max_coins = int(self._get_config("max_coins", "5"))
            min_volume = float(self._get_config("min_volume_krw", "10000000000"))
            min_price = float(self._get_config("min_price_krw", "1000"))

            scanner = CoinScanner(
                min_volume_krw=min_volume,
                min_price_krw=min_price,
                max_coins=max_coins,
            )
            top_coins = scanner.scan_top_coins()

            if top_coins:
                new_coins = [c["ticker"] for c in top_coins]
                # 코어 코인(BTC, ETH, XRP)은 항상 포함
                for core in reversed(self._core_coins):
                    if core not in new_coins:
                        new_coins.insert(0, core)

                # 보유 중인 코인도 항상 포함 (매도 가능하도록)
                held_coins = self._get_held_coins()
                for held in held_coins:
                    if held not in new_coins:
                        new_coins.append(held)

                if set(new_coins) != set(self._active_coins):
                    logger.info("코인 목록 갱신: %s → %s", self._active_coins, new_coins)
                    self._active_coins = new_coins
                    self._init_collectors()

            self._last_coin_refresh = str(now_ts)

        except Exception as e:
            logger.error("코인 목록 갱신 실패: %s", e)

    def start(self) -> None:
        """봇 시작."""
        logger.info("=== CryptoBot 시작 ===")
        logger.info("종목: %s (%d개)", ", ".join(self._active_coins), len(self._active_coins))
        logger.info("활성 전략: %s", self._strategy_name or "없음")
        logger.info("등록 전략: %s", ", ".join(self._registry.list_names()))
        logger.info("API Key 설정: %s", "O" if self._trader.is_ready else "X")
        logger.info("Slack 설정: %s", "O" if self._notifier.is_configured else "X")
        logger.info("DB: %s", config.bot.db_path)

        self._notifier.notify_bot_status("시작됨")

        # 봇 시작 시 안전 장치
        self._safety_check()

        # 스케줄 등록
        self._tick_interval = int(self._get_config("tick_interval_seconds", "30"))
        self._scheduler.add_job(self._tick, "interval", seconds=self._tick_interval, id="main_tick")
        self._scheduler.add_job(self._daily_report, "cron", hour=0, minute=0, id="daily_report")
        self._scheduler.add_job(self._llm_analyze, "interval", hours=4, id="llm_analyze")

        # Graceful shutdown
        signal.signal(signal.SIGINT, self._shutdown)
        signal.signal(signal.SIGTERM, self._shutdown)

        logger.info("스케줄러 시작 (%d초 간격)", self._tick_interval)
        try:
            self._scheduler.start()
        except (KeyboardInterrupt, SystemExit):
            self._shutdown()

    def _refresh_config_cache(self) -> None:
        """bot_config 전체를 메모리에 캐시. 틱 시작 시 1회 호출."""
        rows = self._db.execute("SELECT key, value FROM bot_config").fetchall()
        self._config_cache = {r["key"]: r["value"] for r in rows}

    def _get_config(self, key: str, default: str = "") -> str:
        """캐시에서 봇 설정 값 조회."""
        return self._config_cache.get(key, default)

    def _get_strategy_params_json(self) -> str | None:
        """현재 활성 전략의 파라미터를 JSON 문자열로 반환 (캐시)."""
        if self._strategy is None:
            return None
        return self._strategy_params_cache.get(self._strategy_name)

    def _refresh_strategy_params_cache(self) -> None:
        """전략 파라미터 캐시 갱신."""
        rows = self._db.execute("SELECT name, default_params_json FROM strategies").fetchall()
        self._strategy_params_cache = {r["name"]: r["default_params_json"] for r in rows}

    def _get_config_bool(self, key: str, default: bool = False) -> bool:
        """봇 설정 bool 값 조회."""
        return self._get_config(key, str(default)).lower() == "true"

    def _send_tick_report(self, snapshot: dict, signal_type: str, confidence: float, reason: str) -> None:
        """틱별 판단 리포트를 Slack으로 발송."""
        if not self._get_config_bool("slack_tick_report"):
            return

        indicators = {
            "rsi_14": snapshot.get("rsi_14"),
            "ma_5": snapshot.get("ma_5"),
            "ma_20": snapshot.get("ma_20"),
            "bb_upper": snapshot.get("bb_upper"),
            "bb_lower": snapshot.get("bb_lower"),
            "atr_14": snapshot.get("atr_14"),
        }

        self._notifier.notify_tick_report(
            strategy_name=self._strategy_name,
            signal_type=signal_type,
            confidence=confidence,
            reason=reason,
            current_price=snapshot.get("price", 0),
            market_state=snapshot.get("market_state", "unknown"),
            indicators=indicators,
        )

    def _tick(self) -> None:
        """매 틱마다 실행되는 메인 로직. 멀티코인 순회."""
        try:
            # 0. 캐시 갱신 + 전략/설정 변경 확인 + 코인 목록 갱신
            self._refresh_config_cache()
            self._refresh_strategy_params_cache()
            self._refresh_strategy()
            self._refresh_coins()

            if self._strategy is None:
                return

            if not self._get_config_bool("allow_trading", True):
                return

            # 코인별 순회 (API rate limit 방지: 코인 간 0.5초 대기)
            for i, coin in enumerate(self._active_coins):
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
            # 틱 단위 배치 commit (signal 등)
            try:
                self._db.commit()
            except Exception as e:
                logger.warning("틱 commit 실패: %s", e)
                pass

    def _get_held_coins(self) -> list[str]:
        """현재 보유 중인 코인 목록 (미매도 매수 건)."""
        rows = self._db.execute(
            """
            SELECT DISTINCT t.coin FROM trades t
            WHERE t.side = 'buy'
            AND NOT EXISTS (SELECT 1 FROM trades s WHERE s.buy_trade_id = t.id AND s.side = 'sell')
            """
        ).fetchall()
        return [r["coin"] for r in rows]

    def _get_coin_category(self, coin: str) -> str:
        """코인의 카테고리 반환 (core / alt)."""
        return "core" if coin in self._core_coins else "alt"

    def _get_coin_strategy(self, coin: str) -> tuple["BaseStrategy | None", str, dict]:
        """코인의 시장 상태에 맞는 전략 자동 선택 + 카테고리 리스크 파라미터.

        흐름:
        1. 코인의 최신 스냅샷에서 market_state 확인
        2. 해당 시장에 적합한 전략을 StrategyRegistry에서 선택
        3. 카테고리(core/alt)의 리스크 파라미터 적용

        Returns:
            (전략 인스턴스, 전략 이름, 카테고리 설정 dict)
        """
        category = self._get_coin_category(coin)
        row = self._db.execute(
            "SELECT * FROM coin_strategy_config WHERE category = ?", (category,)
        ).fetchone()

        # 코인의 시장 상태 확인
        collector = self._collectors.get(coin)
        snapshot = collector.get_latest_snapshot() if collector else None
        market_state = snapshot.get("market_state", "sideways") if snapshot else "sideways"

        # 시장 상태에 맞는 전략 자동 선택 — bb_rsi_combined 우선
        if market_state in ("sideways", "bearish"):
            strategy = self._registry.get("bb_rsi_combined")
        else:
            strategy = self._registry.select_by_market(market_state)
        if strategy is None:
            strategy = self._registry.get("bb_rsi_combined")  # 기본 폴백
        if strategy is None:
            return self._strategy, self._strategy_name, {}

        strategy_name = strategy.info().name

        # 카테고리별 리스크 파라미터 적용
        if row:
            strategy.params.stop_loss_pct = row["stop_loss_pct"]
            strategy.params.trailing_stop_pct = row["trailing_stop_pct"]
            strategy.params.position_size_pct = row["position_size_pct"]

        cat_config = dict(row) if row else {}
        cat_config["market_state"] = market_state
        cat_config["auto_strategy"] = strategy_name
        return strategy, strategy_name, cat_config

    def _tick_coin(self, coin: str) -> None:
        """개별 코인에 대한 매매 판단."""
        collector = self._collectors.get(coin)
        if collector is None:
            return

        # 1. 시장 데이터 수집
        snapshot_id = collector.collect_and_save()
        if snapshot_id is None:
            return

        snapshot = collector.get_latest_snapshot()
        if snapshot is None:
            return

        current_price = snapshot["price"]

        # 2. 코인 카테고리에 맞는 전략 선택
        coin_strategy, coin_strategy_name, _ = self._get_coin_strategy(coin)
        if coin_strategy is None:
            return

        # 임시로 현재 전략을 코인별 전략으로 교체
        orig_strategy = self._strategy
        orig_name = self._strategy_name
        self._strategy = coin_strategy
        self._strategy_name = coin_strategy_name

        try:
            # 3. 보유 중인 포지션 확인
            active_trade = self._recorder.get_active_buy_trade(coin)

            if active_trade:
                self._check_and_sell(active_trade, current_price, snapshot_id, snapshot, coin)
            else:
                self._check_and_buy(snapshot, current_price, snapshot_id, coin)
        finally:
            # 원래 전략 복원
            self._strategy = orig_strategy
            self._strategy_name = orig_name

    def _get_coin_buy_amount(self, coin: str, confidence: float) -> float:
        """코인별 매수 금액 계산 (신뢰도 + 최대 포지션 비율 적용).

        Args:
            coin: 종목 코드
            confidence: 매수 신호 강도

        Returns:
            매수 가능 금액 (원)
        """
        balance = self._trader.get_balance_krw()
        max_per_coin_pct = float(self._get_config("max_position_per_coin_pct", "50"))
        position_size_pct = self._strategy.params.position_size_pct

        # 1종목당 최대 금액 = 잔고 × max_per_coin_pct%
        max_for_coin = balance * max_per_coin_pct / 100

        # 가용 금액 = min(잔고 기반 포지션, 종목당 최대) - 최소 유지 잔고
        available = min(max_for_coin, balance - self._risk.limits.min_balance_krw)
        if available <= 0:
            return 0

        ratio = max(0.0, min(confidence, 1.0)) * max(0.0, min(position_size_pct, 100.0)) / 100.0
        sized_amount = available * ratio

        return min(sized_amount, self._risk.limits.max_position_size_krw)

    def _check_and_buy(self, snapshot: dict, current_price: float, snapshot_id: int, coin: str | None = None) -> None:
        """매수 신호 확인 및 실행."""
        coin = coin or config.bot.coin
        collector = self._collectors.get(coin)
        df = collector.latest_df if collector else None
        if df is None:
            return

        signal_result = self._strategy.check_buy(df, current_price)

        # 틱 리포트 발송
        self._send_tick_report(snapshot, signal_result.signal_type, signal_result.confidence, signal_result.reason)

        if signal_result.signal_type != "buy":
            self._recorder.record_signal(
                coin=coin,
                signal_type=signal_result.signal_type,
                strategy=self._strategy_name,
                confidence=signal_result.confidence,
                trigger_reason=signal_result.reason,
                current_price=current_price,
                trigger_value=signal_result.trigger_value,
                skip_reason=signal_result.reason,
                snapshot_id=snapshot_id,
                strategy_params_json=self._get_strategy_params_json(),
            )
            return

        if not self._trader.is_ready:
            self._recorder.record_signal(
                coin=coin,
                signal_type="buy",
                strategy=self._strategy_name,
                confidence=signal_result.confidence,
                trigger_reason=signal_result.reason,
                current_price=current_price,
                trigger_value=signal_result.trigger_value,
                skip_reason="api_key_not_configured",
                snapshot_id=snapshot_id,
                strategy_params_json=self._get_strategy_params_json(),
            )
            logger.info("매수 신호 발생했으나 API Key 미설정 — 스킵")
            return

        # 매수 실행 — 코인별 배분 + 리스크 점검
        buy_amount = self._get_coin_buy_amount(coin, signal_result.confidence)
        balance = self._trader.get_balance_krw()

        can_buy, reason = self._risk.check_can_buy(coin, buy_amount, balance)
        if not can_buy:
            self._recorder.record_signal(
                coin=coin,
                signal_type="buy",
                strategy=self._strategy_name,
                confidence=signal_result.confidence,
                trigger_reason=signal_result.reason,
                current_price=current_price,
                trigger_value=signal_result.trigger_value,
                skip_reason=reason,
                snapshot_id=snapshot_id,
                strategy_params_json=self._get_strategy_params_json(),
            )
            logger.info("매수 신호 발생했으나 리스크 차단: %s", reason)
            return

        order = self._trader.buy_market(coin, buy_amount)
        if order.success:
            trade_id = self._recorder.record_trade(
                coin=coin,
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
                rsi_at_trade=snapshot.get("rsi_14"),
            )
            self._recorder.record_signal(
                coin=coin,
                signal_type="buy",
                strategy=self._strategy_name,
                confidence=signal_result.confidence,
                trigger_reason=signal_result.reason,
                current_price=current_price,
                trigger_value=signal_result.trigger_value,
                executed=True,
                trade_id=trade_id,
                snapshot_id=snapshot_id,
                strategy_params_json=self._get_strategy_params_json(),
            )
            if self._get_config_bool("slack_trade_notification", True):
                self._notifier.notify_trade("buy", coin, order.price, order.amount, order.total_krw)

    def _check_and_sell(self, active_trade: dict, current_price: float, snapshot_id: int, snapshot: dict | None = None, coin: str | None = None) -> None:
        """매도 신호 확인 및 실행."""
        coin = coin or config.bot.coin
        collector = self._collectors.get(coin)
        df = collector.latest_df if collector else None
        if df is None:
            return

        buy_price = active_trade["price"]
        signal_result = self._strategy.check_sell(df, current_price, buy_price)

        # 틱 리포트 발송 (보유 중)
        if snapshot:
            self._send_tick_report(snapshot, signal_result.signal_type, signal_result.confidence, signal_result.reason)

        if signal_result.signal_type != "sell":
            # 보유 중 hold 신호도 기록
            self._recorder.record_signal(
                coin=coin,
                signal_type=signal_result.signal_type,
                strategy=self._strategy_name,
                confidence=signal_result.confidence,
                trigger_reason=signal_result.reason,
                current_price=current_price,
                trigger_value=signal_result.trigger_value,
                skip_reason=signal_result.reason,
                snapshot_id=snapshot_id,
                strategy_params_json=self._get_strategy_params_json(),
            )
            return

        if not self._trader.is_ready:
            logger.info("매도 신호 발생했으나 API Key 미설정 — 스킵")
            return

        # 수수료 가드: 손절이 아닌 경우, 수수료 이상 수익이 나야 매도
        pnl_pct = (current_price - buy_price) / buy_price * 100
        is_stop_loss = "손절" in signal_result.reason
        min_profit_pct = BaseStrategy.ROUND_TRIP_FEE_PCT  # 0.1% (수수료)
        if not is_stop_loss and pnl_pct <= min_profit_pct:
            self._recorder.record_signal(
                coin=coin,
                signal_type="sell",
                strategy=self._strategy_name,
                confidence=signal_result.confidence,
                trigger_reason=signal_result.reason,
                current_price=current_price,
                trigger_value=signal_result.trigger_value,
                skip_reason=f"수수료 가드: 수익 {pnl_pct:+.2f}% < 수수료 0.1%",
                snapshot_id=snapshot_id,
                strategy_params_json=self._get_strategy_params_json(),
            )
            logger.info("매도 신호 발생했으나 수수료 가드: %s %+.2f%%", coin, pnl_pct)
            return

        # 매도 실행
        order = self._trader.sell_market(coin)
        if order.success:
            # 수수료 포함 실제 수익 계산
            buy_fee = active_trade.get("fee_krw") or 0
            buy_total = active_trade["total_krw"] + buy_fee
            sell_total = order.total_krw - order.fee_krw
            profit_krw = round(sell_total - buy_total, 2)
            profit_pct = round(profit_krw / buy_total * 100, 2) if buy_total > 0 else 0
            buy_time = datetime.fromisoformat(active_trade["timestamp"])
            if buy_time.tzinfo is None:
                buy_time = buy_time.replace(tzinfo=timezone.utc)
            hold_minutes = int((datetime.now(timezone.utc) - buy_time).total_seconds() / 60)

            trade_id = self._recorder.record_trade(
                coin=coin,
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
                coin=coin,
                signal_type="sell",
                strategy=self._strategy_name,
                confidence=signal_result.confidence,
                trigger_reason=signal_result.reason,
                current_price=current_price,
                trigger_value=signal_result.trigger_value,
                executed=True,
                trade_id=trade_id,
                snapshot_id=snapshot_id,
                strategy_params_json=self._get_strategy_params_json(),
            )
            self._strategy.reset()
            if self._get_config_bool("slack_trade_notification", True):
                self._notifier.notify_trade("sell", coin, order.price, order.amount, order.total_krw)
                self._notifier.notify_profit(coin, profit_pct, profit_krw, hold_minutes)

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
                stop_loss_pct=float(self._get_config("stop_loss_pct", "-5.0")),
                trailing_stop_pct=float(self._get_config("trailing_stop_pct", "-3.0")),
                position_size_pct=float(self._get_config("position_size_pct", "100.0")),
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
        from cryptobot.data.strategy_repository import StrategyRepository

        repo = StrategyRepository(self._db)

        # shutting_down 상태의 전략을 종료 완료 처리
        completed = repo.complete_shutdown()
        for name in completed:
            logger.info("전략 종료 완료: %s", name)

        # 활성 전략(status=active) 확인
        row = self._db.execute(
            "SELECT name FROM strategies WHERE is_active = TRUE AND status = 'active' LIMIT 1"
        ).fetchone()
        new_name = row["name"] if row else "volatility_breakout"

        # bot_config에서 리스크/전략 파라미터 실시간 반영
        if self._strategy is not None:
            self._strategy.params.stop_loss_pct = float(self._get_config("stop_loss_pct", "-5.0"))
            self._strategy.params.trailing_stop_pct = float(self._get_config("trailing_stop_pct", "-3.0"))
            self._strategy.params.position_size_pct = float(self._get_config("position_size_pct", "100.0"))

        # 리스크 매니저 한도 실시간 반영
        self._risk.limits.max_daily_trades = int(self._get_config("max_daily_trades", "10"))

        # 틱 간격 변경 감지
        new_interval = int(self._get_config("tick_interval_seconds", "30"))
        if new_interval != self._tick_interval:
            self._scheduler.reschedule_job("main_tick", trigger="interval", seconds=new_interval)
            logger.info("틱 간격 변경: %d초 → %d초", self._tick_interval, new_interval)
            self._tick_interval = new_interval
        self._risk.limits.max_daily_loss_pct = float(self._get_config("max_daily_loss_pct", "-10.0"))
        self._risk.limits.max_consecutive_losses = int(self._get_config("max_consecutive_losses", "3"))

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

        self._notifier.notify_bot_status(f"전략 전환: {old_name} → {new_name}")

    def _llm_analyze(self) -> None:
        """4시간마다 LLM 시장 분석 실행."""
        try:
            from cryptobot.llm.analyzer import LLMAnalyzer
            analyzer = LLMAnalyzer(self._db)
            if not analyzer.is_configured:
                return

            result = analyzer.analyze()
            if result:
                summary = result.get("market_summary_kr", "")[:100]
                self._notifier.send(f"📊 *LLM 시장 분석*\n{summary}")
                # 캐시 갱신 (LLM이 config를 변경했으므로)
                self._refresh_config_cache()
                self._refresh_strategy_params_cache()
        except Exception as e:
            logger.error("LLM 분석 에러: %s", e, exc_info=True)

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
            if not self._get_config_bool("slack_daily_report", True):
                return
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
    from cryptobot.logging_config import setup_logging

    setup_logging("bot", config.bot.log_level)

    bot = CryptoBot()
    bot.start()


if __name__ == "__main__":
    main()
