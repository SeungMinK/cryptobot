"""멀티코인 관리 — 코인 목록 갱신 + collector 관리."""

import logging
import time as _time

from cryptobot.bot.config import config
from cryptobot.data.collector import DataCollector

logger = logging.getLogger(__name__)


class CoinManager:
    """멀티코인 선별 + DataCollector 관리."""

    CORE_COINS = ["KRW-BTC", "KRW-ETH", "KRW-XRP"]

    def __init__(self, db, config_manager) -> None:
        self._db = db
        self._config = config_manager
        self.active_coins: list[str] = list(self.CORE_COINS)
        self.collectors: dict[str, DataCollector] = {}
        self._last_refresh: str = ""
        self._init_collectors()

    def _init_collectors(self) -> None:
        """활성 코인별 DataCollector 초기화 + 불필요한 collector 정리."""
        for coin in self.active_coins:
            if coin not in self.collectors:
                self.collectors[coin] = DataCollector(self._db, coin)
        removed = [c for c in self.collectors if c not in self.active_coins]
        for coin in removed:
            del self.collectors[coin]
            logger.debug("collector 정리: %s", coin)

    def refresh(self) -> None:
        """코인 목록 갱신 (30분 주기)."""
        interval = int(self._config.get("coin_refresh_interval_minutes", "30"))
        now_ts = _time.time()
        if self._last_refresh:
            elapsed = now_ts - float(self._last_refresh)
            if elapsed < interval * 60:
                return

        if not self._config.get_bool("multi_coin_enabled", True):
            self.active_coins = list(self.CORE_COINS)
            self._init_collectors()
            return

        try:
            from cryptobot.bot.scanner import CoinScanner
            scanner = CoinScanner(
                min_volume_krw=float(self._config.get("min_volume_krw", "1000000000")),
                min_price_krw=float(self._config.get("min_price_krw", "1000")),
                max_coins=int(self._config.get("max_coins", "5")),
            )
            top_coins = scanner.scan_top_coins()

            if top_coins:
                new_coins = [c["ticker"] for c in top_coins]
                for core in reversed(self.CORE_COINS):
                    if core not in new_coins:
                        new_coins.insert(0, core)

                held_coins = self._get_held_coins()
                for held in held_coins:
                    if held not in new_coins:
                        new_coins.append(held)

                if set(new_coins) != set(self.active_coins):
                    logger.info("코인 목록 갱신: %s → %s", self.active_coins, new_coins)
                    self.active_coins = new_coins
                    self._init_collectors()

            self._last_refresh = str(now_ts)
        except Exception as e:
            logger.error("코인 목록 갱신 실패: %s", e)

    def _get_held_coins(self) -> list[str]:
        """현재 보유 중인 코인 목록."""
        rows = self._db.execute(
            """
            SELECT DISTINCT t.coin FROM trades t
            WHERE t.side = 'buy'
            AND NOT EXISTS (SELECT 1 FROM trades s WHERE s.buy_trade_id = t.id AND s.side = 'sell')
            """
        ).fetchall()
        return [r["coin"] for r in rows]

    def get_category(self, coin: str) -> str:
        """코인 카테고리 (core / alt)."""
        return "core" if coin in self.CORE_COINS else "alt"
