"""종목 스캐너 테스트.

API 호출이 필요하므로 mock 사용.
"""

from unittest.mock import patch

from cryptobot.bot.scanner import CoinScanner


def test_is_valid_coin_with_mock():
    """종목 유효성 검증 (mock)."""
    scanner = CoinScanner()
    with patch("cryptobot.bot.scanner.pyupbit.get_current_price", return_value=50_000_000):
        assert scanner.is_valid_coin("KRW-BTC") is True


def test_is_valid_coin_too_cheap():
    """최소 가격 미달 종목."""
    scanner = CoinScanner(min_price_krw=1_000)
    with patch("cryptobot.bot.scanner.pyupbit.get_current_price", return_value=500):
        assert scanner.is_valid_coin("KRW-CHEAP") is False


def test_is_valid_coin_api_fail():
    """API 실패 시 False."""
    scanner = CoinScanner()
    with patch("cryptobot.bot.scanner.pyupbit.get_current_price", return_value=None):
        assert scanner.is_valid_coin("KRW-FAIL") is False


def test_get_tradable_coins_with_mock():
    """KRW 마켓 종목 목록 조회 (mock)."""
    scanner = CoinScanner()
    mock_tickers = ["KRW-BTC", "KRW-ETH", "KRW-XRP"]
    with patch("cryptobot.bot.scanner.pyupbit.get_tickers", return_value=mock_tickers):
        result = scanner.get_tradable_coins()
        assert result == mock_tickers
        assert len(result) == 3
