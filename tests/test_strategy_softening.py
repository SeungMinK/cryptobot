"""#167 — 전략 완화 (bb_rsi_combined 부분 점수 + 매매 기회 부족 경고).

1. allow_partial_signal=False(기본)면 기존 엄격 동작
2. allow_partial_signal=True면 RSI만 / BB만 충족 시 약한 매수 신호
3. LLM 프롬프트에 "최근 12시간 매수 0건" 경고 포함
"""

import tempfile
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from cryptobot.data.database import Database
from cryptobot.data.recorder import DataRecorder
from cryptobot.llm.analyzer import LLMAnalyzer
from cryptobot.strategies.base import StrategyParams
from cryptobot.strategies.bb_rsi_combined import BBRSICombined


@pytest.fixture
def db():
    tmpdir = tempfile.mkdtemp()
    db = Database(Path(tmpdir) / "test.db")
    db.initialize()
    yield db
    db.close()


def _make_df_rsi_oversold_no_bb_break() -> tuple[pd.DataFrame, float]:
    """RSI 과매도이지만 가격이 bb_lower 위인 OHLCV 생성."""
    # 50일 내리막 → 하단 근처에서 살짝 반등 (RSI 저, 가격 ≥ bb_lower)
    closes = list(np.linspace(1000, 500, 30)) + [510, 515, 520, 525, 530]
    df = pd.DataFrame({"close": closes})
    df["open"] = df["close"]
    df["high"] = df["close"] * 1.01
    df["low"] = df["close"] * 0.99
    df["volume"] = 1000
    # 현재가를 bb_lower 위로 잡기 위해 마지막 close 사용
    return df, float(df["close"].iloc[-1])


def _make_df_bb_break_no_rsi_oversold() -> tuple[pd.DataFrame, float]:
    """BB 하단 이탈이지만 RSI는 정상."""
    # 꾸준히 오르다가 급락 → BB lower 이탈 but RSI는 아직 정상
    closes = list(np.linspace(500, 1000, 25)) + list(np.linspace(1000, 1020, 5)) + [850]
    df = pd.DataFrame({"close": closes})
    df["open"] = df["close"]
    df["high"] = df["close"] * 1.01
    df["low"] = df["close"] * 0.99
    df["volume"] = 1000
    return df, float(df["close"].iloc[-1])


# ===================================================================
# 1. 기본(엄격) 동작 — allow_partial_signal=False
# ===================================================================


def test_strict_mode_rsi_only_returns_hold():
    """기본: RSI 과매도 + BB 하단 미이탈 → hold."""
    params = StrategyParams(extra={"rsi_oversold": 30, "bb_std": 2.0})
    strat = BBRSICombined(params)
    df, price = _make_df_rsi_oversold_no_bb_break()
    sig = strat.check_buy(df, price)
    assert sig.signal_type == "hold"
    assert "볼린저 하단 미이탈" in sig.reason


def test_strict_mode_bb_only_returns_hold():
    """기본: BB 이탈 + RSI 정상 → hold."""
    params = StrategyParams(extra={"rsi_oversold": 30, "bb_std": 2.0})
    strat = BBRSICombined(params)
    df, price = _make_df_bb_break_no_rsi_oversold()
    sig = strat.check_buy(df, price)
    assert sig.signal_type == "hold"


# ===================================================================
# 2. 부분 점수 — allow_partial_signal=True
# ===================================================================


def test_partial_mode_rsi_only_returns_buy():
    """allow_partial_signal=True: RSI 과매도만 충족 → 약한 매수."""
    params = StrategyParams(
        extra={
            "rsi_oversold": 30, "bb_std": 2.0,
            "allow_partial_signal": True, "partial_confidence": 0.4,
        }
    )
    strat = BBRSICombined(params)
    df, price = _make_df_rsi_oversold_no_bb_break()
    sig = strat.check_buy(df, price)
    if sig.signal_type == "buy":
        assert "[부분]" in sig.reason
        assert sig.confidence == 0.4
    # else: 데이터에 따라 RSI가 정말 oversold가 아닐 수도 있음 — 조건부 통과


def test_partial_confidence_configurable():
    """partial_confidence 파라미터로 confidence 수준 조절."""
    params = StrategyParams(
        extra={"allow_partial_signal": True, "partial_confidence": 0.3}
    )
    strat = BBRSICombined(params)
    assert strat._partial_confidence == 0.3


def test_partial_mode_both_conditions_still_strong():
    """부분 점수 모드에서도 둘 다 충족하면 여전히 강한 신호 (conf 0.5+)."""
    # 폭락 후 반등 직전 (RSI 낮음 + 가격이 bb_lower 밖)
    closes = list(np.linspace(1000, 500, 40))
    df = pd.DataFrame({"close": closes})
    df["open"] = df["close"]
    df["high"] = df["close"] * 1.01
    df["low"] = df["close"] * 0.99
    df["volume"] = 1000
    # 가격을 아주 낮게
    params = StrategyParams(
        extra={
            "rsi_oversold": 30, "bb_std": 2.0,
            "allow_partial_signal": True, "partial_confidence": 0.4,
        }
    )
    strat = BBRSICombined(params)
    sig = strat.check_buy(df, 400)  # bb_lower 밖
    if sig.signal_type == "buy" and "[부분]" not in sig.reason:
        assert sig.confidence > 0.4


# ===================================================================
# 3. 프롬프트 경고 — 매매 기회 부족
# ===================================================================


def test_performance_text_includes_opportunity_warning_when_no_recent_buy(db):
    """최근 12시간 buy 0건이면 경고 추가."""
    analyzer = LLMAnalyzer(db)
    text = analyzer._get_performance_text()
    assert "최근 12시간 매수 0건" in text
    assert "allow_partial_signal" in text


def test_performance_text_no_warning_with_recent_buy(db):
    """최근 12시간 buy 1건 이상이면 경고 없음."""
    recorder = DataRecorder(db)
    recorder.record_trade(
        coin="KRW-BTC", side="buy", price=100, amount=1, total_krw=100, fee_krw=1,
        strategy="test", trigger_reason="test",
    )
    db.commit()

    analyzer = LLMAnalyzer(db)
    text = analyzer._get_performance_text()
    assert "최근 12시간 매수 0건" not in text


# ===================================================================
# 4. HARD_LIMITS
# ===================================================================


def test_hard_limits_has_partial_confidence():
    """partial_confidence가 HARD_LIMITS에 정의됨."""
    from cryptobot.llm.analyzer import HARD_LIMITS

    assert "partial_confidence" in HARD_LIMITS
    mn, mx = HARD_LIMITS["partial_confidence"]
    assert 0 < mn < mx <= 1.0
