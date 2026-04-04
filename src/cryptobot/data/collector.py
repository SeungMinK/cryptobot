"""시장 데이터 수집기.

10초 간격으로 업비트에서 시세/거래량 데이터를 수집하고
기술적 지표를 계산하여 market_snapshots에 저장한다.
OHLCV 일봉 데이터는 ohlcv_daily 테이블에 별도 저장 (백테스팅/LLM용).
"""

import logging
from datetime import datetime, timezone

import pyupbit

from cryptobot.bot.indicators import calculate_all
from cryptobot.bot.strategy import determine_market_state
from cryptobot.data.database import Database
from cryptobot.exceptions import APIError

logger = logging.getLogger(__name__)


def _utcnow() -> str:
    """UTC ISO 포맷 타임스탬프."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


class DataCollector:
    """시장 데이터 수집 및 저장."""

    def __init__(self, db: Database, coin: str = "KRW-BTC") -> None:
        self._db = db
        self._coin = coin
        self._latest_df: "pd.DataFrame | None" = None
        self._last_ohlcv_save_date: str = ""  # 일봉 저장 중복 방지

    @property
    def latest_df(self) -> "pd.DataFrame | None":
        """가장 최근 수집한 OHLCV DataFrame."""
        return self._latest_df

    def collect_and_save(self) -> int | None:
        """현재 시장 데이터를 수집하고 DB에 저장.

        Returns:
            저장된 snapshot의 id, 실패 시 None
        """
        try:
            snapshot = self._collect_market_data()
            if snapshot is None:
                return None

            snapshot_id = self._save_snapshot(snapshot)

            # OHLCV 일봉 데이터 저장 (하루 1회)
            self._save_ohlcv_daily()

            logger.debug("스냅샷 저장: id=%d, price=%s", snapshot_id, f"{snapshot['btc_price']:,.0f}")
            return snapshot_id
        except Exception as e:
            logger.error("데이터 수집 실패: %s", e)
            return None

    def _collect_market_data(self) -> dict | None:
        """업비트 API로 시장 데이터 수집."""
        try:
            # OHLCV 데이터 조회 (일봉 120개 — 지표 계산 + 전략에서 사용)
            df = pyupbit.get_ohlcv(self._coin, interval="day", count=120)
            if df is None or df.empty:
                raise APIError(f"OHLCV 데이터 없음: {self._coin}")

            # 전략에서 사용할 수 있도록 캐시
            self._latest_df = df

            # 현재가
            current_price = pyupbit.get_current_price(self._coin)
            if current_price is None:
                raise APIError(f"현재가 조회 실패: {self._coin}")

            # 기술적 지표 계산
            indicators = calculate_all(df)

            # 시장 상태 판단
            market_state = determine_market_state(indicators["ma_5"], indicators["ma_20"])

            # 24시간 변동 데이터
            today = df.iloc[-1]

            return {
                "timestamp": _utcnow(),
                "coin": self._coin,
                "btc_price": current_price,
                "btc_open_24h": today["open"],
                "btc_high_24h": today["high"],
                "btc_low_24h": today["low"],
                "btc_change_pct_24h": round((current_price - today["open"]) / today["open"] * 100, 2),
                "btc_volume_24h": today["volume"],
                "btc_rsi_14": indicators["rsi_14"],
                "btc_ma_5": indicators["ma_5"],
                "btc_ma_20": indicators["ma_20"],
                "btc_ma_60": indicators["ma_60"],
                "btc_bb_upper": indicators["bb_upper"],
                "btc_bb_lower": indicators["bb_lower"],
                "btc_atr_14": indicators["atr_14"],
                "market_state": market_state,
            }
        except Exception as e:
            logger.error("시장 데이터 수집 실패: %s", e)
            return None

    def _save_snapshot(self, data: dict) -> int:
        """스냅샷을 DB에 저장하고 id 반환."""
        cursor = self._db.execute(
            """
            INSERT INTO market_snapshots (
                timestamp, coin, btc_price, btc_open_24h, btc_high_24h, btc_low_24h,
                btc_change_pct_24h, btc_volume_24h, btc_rsi_14,
                btc_ma_5, btc_ma_20, btc_ma_60,
                btc_bb_upper, btc_bb_lower, btc_atr_14, market_state
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                data["timestamp"],
                data["coin"],
                data["btc_price"],
                data["btc_open_24h"],
                data["btc_high_24h"],
                data["btc_low_24h"],
                data["btc_change_pct_24h"],
                data["btc_volume_24h"],
                data["btc_rsi_14"],
                data["btc_ma_5"],
                data["btc_ma_20"],
                data["btc_ma_60"],
                data["btc_bb_upper"],
                data["btc_bb_lower"],
                data["btc_atr_14"],
                data["market_state"],
            ),
        )
        self._db.commit()
        return cursor.lastrowid

    def _save_ohlcv_daily(self) -> None:
        """OHLCV 일봉 데이터를 ohlcv_daily 테이블에 저장.

        매 틱마다 호출되지만 날짜 기준으로 중복 방지.
        120일 캔들 전체를 upsert (과거 데이터도 보정).
        """
        if self._latest_df is None:
            return

        today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        if today_str == self._last_ohlcv_save_date:
            return  # 오늘 이미 저장함

        now = _utcnow()
        rows = []
        for idx, row in self._latest_df.iterrows():
            date_str = idx.strftime("%Y-%m-%d") if hasattr(idx, "strftime") else str(idx)[:10]
            rows.append((
                self._coin, date_str,
                row["open"], row["high"], row["low"], row["close"], row["volume"],
                now,
            ))

        self._db.executemany(
            """
            INSERT OR REPLACE INTO ohlcv_daily (coin, date, open, high, low, close, volume, collected_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            rows,
        )
        self._db.commit()
        self._last_ohlcv_save_date = today_str
        logger.info("OHLCV 일봉 저장: %s %d일치", self._coin, len(rows))

    def get_latest_snapshot(self) -> dict | None:
        """이 코인의 가장 최근 스냅샷 조회."""
        row = self._db.execute(
            "SELECT * FROM market_snapshots WHERE coin = ? ORDER BY id DESC LIMIT 1",
            (self._coin,),
        ).fetchone()
        return dict(row) if row else None
