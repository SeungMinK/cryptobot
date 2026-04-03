"""종목 자동 선별 모듈.

업비트에서 거래 가능한 종목 중 매매 조건에 맞는 종목을 자동으로 선별한다.
Phase 1에서는 단일 종목(BTC)만 지원하지만, 멀티 종목 확장을 위해 구현.
"""

import logging

import pyupbit

from cryptobot.exceptions import APIError

logger = logging.getLogger(__name__)


class CoinScanner:
    """종목 스캐너.

    거래량/변동성 기준으로 유망 종목을 선별한다.
    """

    def __init__(
        self,
        min_volume_krw: float = 10_000_000_000,  # 최소 24시간 거래대금 100억
        min_price_krw: float = 1_000,  # 최소 현재가 1,000원
        max_coins: int = 5,  # 최대 선별 종목 수
    ) -> None:
        self._min_volume_krw = min_volume_krw
        self._min_price_krw = min_price_krw
        self._max_coins = max_coins

    def get_tradable_coins(self) -> list[str]:
        """업비트 KRW 마켓 종목 목록 조회.

        Returns:
            종목 코드 리스트 (예: ["KRW-BTC", "KRW-ETH", ...])
        """
        try:
            tickers = pyupbit.get_tickers(fiat="KRW")
            if tickers is None:
                raise APIError("종목 목록 조회 실패")
            return tickers
        except Exception as e:
            raise APIError(f"종목 목록 조회 실패: {e}") from e

    def scan_top_coins(self) -> list[dict]:
        """거래대금 상위 종목 선별.

        Returns:
            선별된 종목 정보 리스트 [{ticker, price, volume, change_rate}, ...]
        """
        try:
            tickers = self.get_tradable_coins()
            if not tickers:
                return []

            # 전체 종목 시세 조회
            all_prices = pyupbit.get_current_price(tickers)
            if all_prices is None:
                return []

            results = []
            for ticker in tickers:
                price = all_prices.get(ticker, 0)
                if price < self._min_price_krw:
                    continue

                # OHLCV로 거래대금 확인
                df = pyupbit.get_ohlcv(ticker, interval="day", count=1)
                if df is None or df.empty:
                    continue

                volume_krw = df.iloc[-1]["close"] * df.iloc[-1]["volume"]
                if volume_krw < self._min_volume_krw:
                    continue

                change_rate = (price - df.iloc[-1]["open"]) / df.iloc[-1]["open"] * 100

                results.append(
                    {
                        "ticker": ticker,
                        "price": price,
                        "volume_krw": volume_krw,
                        "change_rate": round(change_rate, 2),
                    }
                )

            # 거래대금 내림차순 정렬
            results.sort(key=lambda x: x["volume_krw"], reverse=True)
            top = results[: self._max_coins]

            for coin in top:
                logger.info(
                    "선별: %s | 가격 %s원 | 거래대금 %s원 | 변동 %+.1f%%",
                    coin["ticker"],
                    f"{coin['price']:,.0f}",
                    f"{coin['volume_krw']:,.0f}",
                    coin["change_rate"],
                )

            return top

        except APIError:
            raise
        except Exception as e:
            logger.error("종목 스캔 실패: %s", e)
            return []

    def is_valid_coin(self, ticker: str) -> bool:
        """종목이 매매 가능한 상태인지 확인.

        Args:
            ticker: 종목 코드 (예: "KRW-BTC")
        """
        try:
            price = pyupbit.get_current_price(ticker)
            return price is not None and price >= self._min_price_krw
        except Exception:
            return False
