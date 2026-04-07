"""주문 실행 모듈.

NestJS의 외부 API 호출 Service와 동일한 역할.
pyupbit을 통해 업비트에 실제 주문을 실행한다.
"""

import logging
from dataclasses import dataclass

import pyupbit

from cryptobot.bot.config import config
from cryptobot.exceptions import APIError, ConfigError, InsufficientBalanceError

logger = logging.getLogger(__name__)


@dataclass
class OrderResult:
    """주문 실행 결과."""

    success: bool
    side: str  # "buy" / "sell"
    coin: str
    price: float
    amount: float
    total_krw: float
    fee_krw: float
    raw_response: dict | None = None
    error: str | None = None


class Trader:
    """업비트 주문 실행기.

    NestJS에서 외부 API를 호출하는 Service와 동일.
    """

    FEE_RATE = 0.0005  # 업비트 수수료 0.05%

    def __init__(self) -> None:
        if not config.upbit.is_configured:
            logger.warning("업비트 API Key 미설정 — 주문 실행 불가 (조회만 가능)")
            self._upbit: pyupbit.Upbit | None = None
        else:
            self._upbit = pyupbit.Upbit(config.upbit.access_key, config.upbit.secret_key)

    @property
    def is_ready(self) -> bool:
        """주문 가능 상태인지 확인."""
        return self._upbit is not None

    def get_balance_krw(self) -> float:
        """원화 잔고 조회."""
        self._ensure_ready()
        try:
            balance = self._upbit.get_balance("KRW")
            return float(balance) if balance else 0.0
        except Exception as e:
            raise APIError(f"잔고 조회 실패: {e}") from e

    def get_balance_coin(self, coin: str) -> float:
        """코인 보유량 조회.

        Args:
            coin: 종목 코드 (예: "KRW-BTC" → "BTC")
        """
        self._ensure_ready()
        try:
            ticker = coin.replace("KRW-", "")
            balance = self._upbit.get_balance(ticker)
            return float(balance) if balance else 0.0
        except Exception as e:
            raise APIError(f"코인 잔고 조회 실패: {e}") from e

    def get_current_price(self, coin: str) -> float:
        """현재가 조회 (API Key 없이도 가능)."""
        try:
            price = pyupbit.get_current_price(coin)
            if price is None:
                raise APIError(f"현재가 조회 실패: {coin}")
            return float(price)
        except Exception as e:
            raise APIError(f"현재가 조회 실패: {e}") from e

    def buy_market(self, coin: str, krw_amount: float) -> OrderResult:
        """시장가 매수.

        Args:
            coin: 종목 코드 (예: "KRW-BTC")
            krw_amount: 매수 금액 (원)

        Returns:
            주문 실행 결과
        """
        self._ensure_ready()

        if krw_amount < 5000:
            return OrderResult(
                success=False,
                side="buy",
                coin=coin,
                price=0,
                amount=0,
                total_krw=0,
                fee_krw=0,
                error="최소 주문 금액 5,000원 미달",
            )

        try:
            balance = self.get_balance_krw()
            if balance < krw_amount:
                raise InsufficientBalanceError(f"잔고 부족: {balance:,.0f}원 < {krw_amount:,.0f}원")

            result = self._upbit.buy_market_order(coin, krw_amount)
            logger.info("매수 주문 실행: %s %s원", coin, f"{krw_amount:,.0f}")

            price = self.get_current_price(coin)
            fee = krw_amount * self.FEE_RATE
            amount = (krw_amount - fee) / price

            # 체결 검증 — 실제 잔고 확인
            import time as _time
            _time.sleep(0.5)  # 체결 대기
            actual_balance = self.get_balance_coin(coin)
            if actual_balance <= 0:
                logger.error("매수 체결 검증 실패: %s 잔고=0 (주문 응답: %s)", coin, result)
                return OrderResult(
                    success=False, side="buy", coin=coin,
                    price=0, amount=0, total_krw=0, fee_krw=0,
                    error="체결 검증 실패: 잔고 0",
                )

            return OrderResult(
                success=True,
                side="buy",
                coin=coin,
                price=price,
                amount=actual_balance,  # 실제 체결량 사용
                total_krw=krw_amount,
                fee_krw=fee,
                raw_response=result,
            )
        except (InsufficientBalanceError, APIError):
            raise
        except Exception as e:
            raise APIError(f"매수 주문 실패: {e}") from e

    def sell_market(self, coin: str, amount: float | None = None) -> OrderResult:
        """시장가 매도.

        Args:
            coin: 종목 코드 (예: "KRW-BTC")
            amount: 매도 수량 (None이면 전량 매도)

        Returns:
            주문 실행 결과
        """
        self._ensure_ready()

        try:
            if amount is None:
                amount = self.get_balance_coin(coin)

            if amount <= 0:
                return OrderResult(
                    success=False,
                    side="sell",
                    coin=coin,
                    price=0,
                    amount=0,
                    total_krw=0,
                    fee_krw=0,
                    error="매도 가능한 수량 없음",
                )

            price = self.get_current_price(coin)
            result = self._upbit.sell_market_order(coin, amount)
            logger.info("매도 주문 실행: %s %.8f개", coin, amount)

            # 체결 검증 — 매도 후 잔고 확인
            import time as _time
            _time.sleep(0.5)
            remaining = self.get_balance_coin(coin)
            if remaining > amount * 0.01:  # 1% 이상 남아있으면 미체결
                logger.warning("매도 부분 체결: %s 잔여 %.8f개", coin, remaining)

            total_krw = price * amount
            fee = total_krw * self.FEE_RATE

            return OrderResult(
                success=True,
                side="sell",
                coin=coin,
                price=price,
                amount=amount,
                total_krw=total_krw,
                fee_krw=fee,
                raw_response=result,
            )
        except APIError:
            raise
        except Exception as e:
            raise APIError(f"매도 주문 실패: {e}") from e

    def cancel_all_orders(self, coin: str) -> int:
        """미체결 주문 전부 취소.

        Args:
            coin: 종목 코드

        Returns:
            취소한 주문 수
        """
        self._ensure_ready()
        try:
            orders = self._upbit.get_order(coin, state="wait")
            if not orders:
                return 0
            for order in orders:
                self._upbit.cancel_order(order["uuid"])
            logger.info("미체결 주문 %d건 취소: %s", len(orders), coin)
            return len(orders)
        except Exception as e:
            raise APIError(f"주문 취소 실패: {e}") from e

    def _ensure_ready(self) -> None:
        """API Key 설정 확인."""
        if not self.is_ready:
            raise ConfigError("업비트 API Key가 설정되지 않았습니다. .env 파일을 확인하세요.")
