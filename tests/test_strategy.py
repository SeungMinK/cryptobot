"""매매 전략 테스트."""

from cryptobot.bot.strategy import (
    StrategyParams,
    VolatilityBreakoutStrategy,
    determine_market_state,
)


def test_buy_signal_triggered():
    """변동성 돌파 매수 신호 발생."""
    params = StrategyParams(k_value=0.5, allow_trading=True, market_state="bullish")
    strategy = VolatilityBreakoutStrategy(params)

    # 전일 범위: 100 - 90 = 10, 돌파가: 95 + 10 * 0.5 = 100
    signal = strategy.check_buy_signal(
        current_price=105,
        today_open=95,
        yesterday_high=100,
        yesterday_low=90,
    )
    assert signal.signal_type == "buy_signal"
    assert signal.trigger_value == 100.0


def test_buy_signal_not_triggered():
    """돌파 미달 시 hold."""
    params = StrategyParams(k_value=0.5, allow_trading=True, market_state="bullish")
    strategy = VolatilityBreakoutStrategy(params)

    signal = strategy.check_buy_signal(
        current_price=98,
        today_open=95,
        yesterday_high=100,
        yesterday_low=90,
    )
    assert signal.signal_type == "hold"


def test_buy_signal_bearish_market():
    """하락장에서는 매수 안 함."""
    params = StrategyParams(market_state="bearish")
    strategy = VolatilityBreakoutStrategy(params)

    signal = strategy.check_buy_signal(
        current_price=105,
        today_open=95,
        yesterday_high=100,
        yesterday_low=90,
    )
    assert signal.signal_type == "hold"
    assert "하락장" in signal.trigger_reason


def test_sell_signal_stop_loss():
    """손절 매도."""
    params = StrategyParams(stop_loss_pct=-5.0, trailing_stop_pct=-3.0)
    strategy = VolatilityBreakoutStrategy(params)

    signal = strategy.check_sell_signal(current_price=94, buy_price=100)
    assert signal.signal_type == "sell_signal"
    assert signal.trigger_reason == "손절"


def test_sell_signal_trailing_stop():
    """트레일링 스탑 매도."""
    params = StrategyParams(stop_loss_pct=-10.0, trailing_stop_pct=-3.0)
    strategy = VolatilityBreakoutStrategy(params)

    # 최고가 110으로 갱신
    strategy.check_sell_signal(current_price=110, buy_price=100)
    # 110 → 106 = -3.6% 하락 → 트레일링 스탑 발동
    signal = strategy.check_sell_signal(current_price=106, buy_price=100)
    assert signal.signal_type == "sell_signal"
    assert signal.trigger_reason == "트레일링 스탑"


def test_sell_signal_hold():
    """매도 조건 미달 시 hold."""
    params = StrategyParams(stop_loss_pct=-5.0, trailing_stop_pct=-3.0)
    strategy = VolatilityBreakoutStrategy(params)

    signal = strategy.check_sell_signal(current_price=102, buy_price=100)
    assert signal.signal_type == "hold"


def test_determine_market_state():
    """시장 상태 판단."""
    assert determine_market_state(105, 100) == "bullish"
    assert determine_market_state(95, 100) == "bearish"
    assert determine_market_state(100.5, 100) == "sideways"
    assert determine_market_state(None, 100) == "sideways"
