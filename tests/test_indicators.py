"""기술적 지표 테스트."""

import pandas as pd

from cryptobot.bot.indicators import (
    calculate_all,
    calculate_atr,
    calculate_bollinger_bands,
    calculate_ma,
    calculate_rsi,
)


def _make_prices(values: list[float]) -> pd.Series:
    return pd.Series(values)


def test_rsi_basic():
    """RSI 기본 계산."""
    # 15개 이상의 가격 데이터 (상승 추세)
    prices = _make_prices([100 + i * 2 for i in range(20)])
    rsi = calculate_rsi(prices)
    assert rsi is not None
    assert rsi > 50  # 상승 추세이므로 50 이상


def test_rsi_insufficient_data():
    """데이터 부족 시 None."""
    prices = _make_prices([100, 101, 102])
    assert calculate_rsi(prices) is None


def test_ma_basic():
    """이동평균 기본 계산."""
    prices = _make_prices([10, 20, 30, 40, 50])
    ma = calculate_ma(prices, 5)
    assert ma == 30.0


def test_ma_insufficient_data():
    prices = _make_prices([10, 20])
    assert calculate_ma(prices, 5) is None


def test_bollinger_bands():
    """볼린저밴드 기본 계산."""
    prices = _make_prices([100 + i for i in range(25)])
    result = calculate_bollinger_bands(prices, period=20)
    assert result is not None
    upper, lower = result
    assert upper > lower


def test_atr_basic():
    """ATR 기본 계산."""
    high = _make_prices([110 + i for i in range(20)])
    low = _make_prices([90 + i for i in range(20)])
    close = _make_prices([100 + i for i in range(20)])
    atr = calculate_atr(high, low, close)
    assert atr is not None
    assert atr > 0


def test_calculate_all():
    """모든 지표 일괄 계산."""
    df = pd.DataFrame(
        {
            "open": [100 + i for i in range(65)],
            "high": [110 + i for i in range(65)],
            "low": [90 + i for i in range(65)],
            "close": [100 + i for i in range(65)],
            "volume": [1000] * 65,
        }
    )
    result = calculate_all(df)
    assert "rsi_14" in result
    assert "ma_5" in result
    assert "ma_20" in result
    assert "ma_60" in result
    assert "bb_upper" in result
    assert "atr_14" in result
