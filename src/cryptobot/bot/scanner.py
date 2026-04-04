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

    # 스테이블코인 + 매매 부적합 종목 제외
    EXCLUDED_COINS = {
        "KRW-USDT", "KRW-USDC", "KRW-DAI", "KRW-BUSD",
        "KRW-TUSD", "KRW-PAXG",
    }

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
                if ticker in self.EXCLUDED_COINS:
                    continue

                price = all_prices.get(ticker, 0)
                if price < self._min_price_krw:
                    continue

                # OHLCV로 거래대금 + 변동성 확인
                df = pyupbit.get_ohlcv(ticker, interval="day", count=14)
                if df is None or df.empty:
                    continue

                volume_krw = df.iloc[-1]["close"] * df.iloc[-1]["volume"]
                if volume_krw < self._min_volume_krw:
                    continue

                change_rate = (price - df.iloc[-1]["open"]) / df.iloc[-1]["open"] * 100

                # ATR (14일 평균 변동폭) 계산
                atr = 0.0
                if len(df) >= 2:
                    tr_values = []
                    for i in range(1, len(df)):
                        high = df.iloc[i]["high"]
                        low = df.iloc[i]["low"]
                        prev_close = df.iloc[i - 1]["close"]
                        tr = max(high - low, abs(high - prev_close), abs(low - prev_close))
                        tr_values.append(tr)
                    atr = sum(tr_values) / len(tr_values) if tr_values else 0

                # ATR 변동성 비율 (%)
                volatility_pct = (atr / price * 100) if price > 0 else 0

                # RSI 계산 (14일)
                rsi = None
                if len(df) >= 14:
                    deltas = df["close"].diff().dropna()
                    gains = deltas.where(deltas > 0, 0)
                    losses = (-deltas.where(deltas < 0, 0))
                    avg_gain = gains.rolling(14).mean().iloc[-1]
                    avg_loss = losses.rolling(14).mean().iloc[-1]
                    if avg_loss > 0:
                        rs = avg_gain / avg_loss
                        rsi = round(100 - (100 / (1 + rs)), 1)

                results.append(
                    {
                        "ticker": ticker,
                        "price": price,
                        "volume_krw": volume_krw,
                        "change_rate": round(change_rate, 2),
                        "atr": round(atr, 2),
                        "volatility_pct": round(volatility_pct, 2),
                        "rsi": rsi,
                    }
                )

            # 변동성 × 거래대금 종합 점수로 정렬 (변동성 높고 거래량 많은 코인 우선)
            for r in results:
                r["score"] = r["volatility_pct"] * (r["volume_krw"] / 1_000_000_000)
            results.sort(key=lambda x: x["score"], reverse=True)
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
