"""멀티코인 관리 — 코인 목록 갱신 + collector 관리."""

import json
import logging
import time as _time

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
                max_coins=int(self._config.get("max_coins", "30")),
                max_spread_pct=float(self._config.get("max_spread_pct", "0.3")),
            )
            top_coins = scanner.scan_top_coins()

            if top_coins:
                new_coins = [c["ticker"] for c in top_coins]

                # LLM 추천 코인 반영
                llm_add = self._get_llm_coins("llm_add_coins")
                llm_remove = set(self._get_llm_coins("llm_remove_coins"))

                for coin in llm_add:
                    if coin not in new_coins:
                        new_coins.append(coin)

                # LLM 제거 추천 (보유 중 코인만 제외 불가)
                held_coins = self._get_held_coins()
                new_coins = [c for c in new_coins if c not in llm_remove or c in held_coins]

                # 보유 중 코인 보장
                for held in held_coins:
                    if held not in new_coins:
                        new_coins.append(held)

                # max_coins 제한 (보유 코인은 항상 포함)
                max_coins = int(self._config.get("max_coins", "5"))
                if len(new_coins) > max_coins:
                    protected = set(held_coins)
                    trimmed = [c for c in new_coins if c in protected]
                    for c in new_coins:
                        if c not in protected and len(trimmed) < max_coins:
                            trimmed.append(c)
                    new_coins = trimmed

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

    def _get_llm_coins(self, key: str) -> list[str]:
        """bot_config에서 LLM 추천 코인 목록 조회."""
        row = self._db.execute("SELECT value FROM bot_config WHERE key = ?", (key,)).fetchone()
        if row:
            try:
                return json.loads(dict(row)["value"])
            except (json.JSONDecodeError, TypeError):
                pass
        return []

    def get_category(self, coin: str) -> str:
        """코인 카테고리 (core / alt)."""
        return "core" if coin in self.CORE_COINS else "alt"
