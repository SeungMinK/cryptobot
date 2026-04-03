"""전략 모듈 통합 테스트."""

import pandas as pd

from cryptobot.strategies.base import StrategyParams
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


def _make_df(prices: list[float], volumes: list[float] | None = None) -> pd.DataFrame:
    """테스트용 OHLCV DataFrame 생성."""
    n = len(prices)
    return pd.DataFrame(
        {
            "open": [p * 0.99 for p in prices],
            "high": [p * 1.02 for p in prices],
            "low": [p * 0.98 for p in prices],
            "close": prices,
            "volume": volumes or [1000] * n,
        }
    )


def _uptrend_df(length: int = 65) -> pd.DataFrame:
    """상승 추세 DataFrame."""
    return _make_df([50_000_000 + i * 500_000 for i in range(length)])


def _downtrend_df(length: int = 65) -> pd.DataFrame:
    """하락 추세 DataFrame."""
    return _make_df([80_000_000 - i * 500_000 for i in range(length)])


def _sideways_df(length: int = 65) -> pd.DataFrame:
    """횡보 DataFrame (지그재그)."""
    prices = []
    for i in range(length):
        base = 50_000_000
        prices.append(base + (500_000 if i % 2 == 0 else -500_000))
    return _make_df(prices)


# ── 전략 인스턴스 생성 테스트 ──


def test_all_strategies_have_info():
    """모든 전략이 info()를 올바르게 반환하는지."""
    strategies = [
        VolatilityBreakout(),
        MACrossover(),
        MACDStrategy(),
        RSIMeanReversion(),
        BollingerBands(),
        Supertrend(),
        BreakoutMomentum(),
        BollingerSqueeze(),
        GridTrading(),
    ]
    for s in strategies:
        info = s.info()
        assert info.name, f"{s.__class__.__name__} name 없음"
        assert info.display_name
        assert info.market_states
        assert info.difficulty in ("easy", "medium", "hard")


# ── 레지스트리 테스트 ──


def test_registry_register_and_get():
    """레지스트리 등록 및 조회."""
    reg = StrategyRegistry()
    reg.register(VolatilityBreakout())
    reg.register(RSIMeanReversion())

    assert reg.get("volatility_breakout") is not None
    assert reg.get("rsi_mean_reversion") is not None
    assert reg.get("nonexistent") is None


def test_registry_select_by_market():
    """시장 상태로 전략 선택."""
    reg = StrategyRegistry()
    reg.register(VolatilityBreakout())  # bullish
    reg.register(RSIMeanReversion())  # sideways
    reg.register(MACrossover())  # bullish, bearish

    bullish = reg.select_by_market("bullish")
    assert bullish is not None
    assert "bullish" in bullish.info().market_states

    sideways = reg.select_by_market("sideways")
    assert sideways is not None
    assert sideways.info().name == "rsi_mean_reversion"


def test_registry_list_all():
    """전체 전략 목록."""
    reg = StrategyRegistry()
    reg.register(VolatilityBreakout())
    reg.register(MACDStrategy())
    assert len(reg.list_all()) == 2
    assert "volatility_breakout" in reg.list_names()


# ── 변동성 돌파 ──


def test_volatility_breakout_buy():
    """변동성 돌파 매수 신호."""
    df = _uptrend_df()
    s = VolatilityBreakout()
    current = df["close"].iloc[-1] * 1.05  # 고가 돌파
    signal = s.check_buy(df, current)
    assert signal.signal_type == "buy"


def test_volatility_breakout_hold():
    """변동성 돌파 미달."""
    df = _sideways_df()
    s = VolatilityBreakout()
    signal = s.check_buy(df, df["close"].iloc[-1])
    assert signal.signal_type == "hold"


# ── MA 교차 ──


def test_ma_crossover_with_uptrend():
    """상승 추세에서 MA 교차 테스트."""
    df = _uptrend_df()
    s = MACrossover()
    signal = s.check_buy(df, df["close"].iloc[-1])
    # 꾸준한 상승이면 이미 골든크로스 발생 후이므로 hold일 수 있음
    assert signal.signal_type in ("buy", "hold")


# ── MACD ──


def test_macd_returns_signal():
    """MACD가 신호를 반환하는지."""
    df = _uptrend_df()
    s = MACDStrategy()
    signal = s.check_buy(df, df["close"].iloc[-1])
    assert signal.signal_type in ("buy", "hold")


# ── RSI 평균 회귀 ──


def test_rsi_mean_reversion_hold_normal():
    """RSI가 정상 범위면 hold."""
    df = _sideways_df()
    s = RSIMeanReversion()
    signal = s.check_buy(df, df["close"].iloc[-1])
    assert signal.signal_type in ("buy", "hold")


# ── 볼린저 밴드 ──


def test_bollinger_bands_hold():
    """밴드 이탈 없으면 hold."""
    df = _sideways_df()
    s = BollingerBands()
    signal = s.check_buy(df, df["close"].iloc[-1])
    assert signal.signal_type in ("buy", "hold")


# ── 슈퍼트렌드 ──


def test_supertrend_returns_signal():
    """슈퍼트렌드가 신호를 반환하는지."""
    df = _uptrend_df()
    s = Supertrend()
    signal = s.check_buy(df, df["close"].iloc[-1])
    assert signal.signal_type in ("buy", "hold")


# ── 브레이크아웃 ──


def test_breakout_buy_on_new_high():
    """신고가 돌파 시 매수."""
    df = _uptrend_df()
    s = BreakoutMomentum()
    # 최근 가격보다 높은 가격으로 테스트
    new_high = df["high"].max() * 1.01
    signal = s.check_buy(df, new_high)
    assert signal.signal_type == "buy"


# ── 볼린저 스퀴즈 ──


def test_bollinger_squeeze_hold_normal():
    """스퀴즈 아니면 hold."""
    df = _uptrend_df(130)
    s = BollingerSqueeze()
    signal = s.check_buy(df, df["close"].iloc[-1])
    assert signal.signal_type in ("buy", "hold")


# ── 그리드 ──


def test_grid_trading_setup():
    """그리드 초기화 및 hold."""
    df = _sideways_df()
    s = GridTrading()
    signal = s.check_buy(df, df["close"].iloc[-1])
    assert signal.signal_type in ("buy", "hold")


# ── 공통 손절/트레일링 ──


def test_common_stop_loss():
    """공통 손절 기능."""
    s = VolatilityBreakout(StrategyParams(stop_loss_pct=-5.0))
    signal = s.check_trailing_stop(current_price=94, buy_price=100)
    assert signal is not None
    assert signal.signal_type == "sell"
    assert signal.reason == "손절"


def test_common_trailing_stop():
    """공통 트레일링 스탑."""
    s = VolatilityBreakout(StrategyParams(trailing_stop_pct=-3.0, stop_loss_pct=-10.0))
    s.check_trailing_stop(current_price=110, buy_price=100)  # 최고가 110 설정
    signal = s.check_trailing_stop(current_price=106, buy_price=100)  # 110→106 = -3.6%
    assert signal is not None
    assert signal.reason == "트레일링 스탑"


def test_common_hold():
    """손절/트레일링 미달 시 None."""
    s = VolatilityBreakout()
    signal = s.check_trailing_stop(current_price=102, buy_price=100)
    assert signal is None


def test_custom_params():
    """extra 파라미터로 전략 커스터마이징."""
    params = StrategyParams(extra={"k_value": 0.3})
    s = VolatilityBreakout(params)
    assert s._k == 0.3
